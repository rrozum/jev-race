"""Stateless API: no database, sessions, credential cache or report endpoints."""
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib import import_module
from typing import Callable
from pathlib import Path
import asyncio
import base64
import hashlib
import logging
import re
import time

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from race.brains.jev import JevBrain, ProviderError
from race.contracts import Agent
from race.levels import context_for, generate
from race.settings import Settings
from race.static import CompressedFiles

UI = Path(__file__).parent / "ui"


@dataclass
class Provider:
    label: str
    factory: Callable[[str], Agent]
    requires_token: bool = True
    planning: bool = False


class TrackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    seed: int = Field(ge=0, le=1_000_000_000)
    count: int = Field(default=12, ge=4, le=100)


class PlanRequest(TrackRequest):
    provider: str = Field(default="jev", max_length=40)


class DecisionRequest(PlanRequest):
    event_id: int = Field(ge=0, le=99)
    energy: int = Field(ge=0, le=3)
    plan: str = Field(default="", max_length=2000)


def create_app(settings: Settings | None = None, providers: dict | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    registry = {} if providers is None else dict(providers)
    capacity = asyncio.Semaphore(32)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    @asynccontextmanager
    async def lifespan(_app):
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.timeout),
                                    limits=httpx.Limits(max_connections=32)) as client:
            if providers is None:
                registry["jev"] = Provider("Jev · TypeSafe API", lambda token: Agent(
                    JevBrain(client, token, settings.jev_model, settings.input_price)))
            if settings.plugin:
                module, function = settings.plugin.split(":", 1)
                getattr(import_module(module), function)(registry, client, settings)
            yield
            registry.clear()

    app = FastAPI(title="Jev Race", lifespan=lifespan, docs_url=None, redoc_url=None)
    # Godot's generated bootstrap is the only inline script allowed by CSP.
    hashes = []
    export = settings.web_dir / "index.html"
    if export.exists():
        for script in re.findall(r"<script>(.*?)</script>", export.read_text(), re.S):
            digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
            hashes.append(f"'sha256-{digest}'")
    csp = ("default-src 'self'; script-src 'self' 'wasm-unsafe-eval' " + " ".join(hashes)
           + "; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
           "worker-src 'self' blob:; connect-src 'self'; media-src 'self' blob:; "
           "frame-src 'self'; frame-ancestors 'self'; object-src 'none'; base-uri 'self'")

    @app.middleware("http")
    async def privacy_headers(request, call_next):
        if request.method == "POST":
            # The browser only sends a small typed context, never arbitrary prompts.
            chunks, length = [], 0
            async for chunk in request.stream():
                length += len(chunk)
                if length > 8192:
                    return JSONResponse({"detail": "Слишком большой запрос"}, status_code=413,
                                        headers={"Cache-Control": "no-store"})
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        if not request.url.path.startswith(("/game/", "/assets/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _exc):
        return JSONResponse({"detail": "Некорректные параметры запроса"}, status_code=422)

    @app.get("/healthz")
    async def health():
        if not export.is_file():
            raise HTTPException(503, "Сначала соберите игру")
        return {"status": "ok"}

    @app.get("/")
    @app.get("/race")
    async def index():
        return FileResponse(UI / "index.html")

    @app.get("/api/config")
    async def config():
        return {"providers": [{"id": key, "label": item.label,
                  "requires_token": item.requires_token, "planning": item.planning}
                 for key, item in registry.items()],
                "max_obstacles": settings.generator.max_obstacles,
                "input_price": settings.input_price}

    def build(payload):
        try:
            return generate(payload.seed, payload.count, settings.generator)
        except ValueError:
            raise HTTPException(400, "Недопустимые параметры трассы") from None

    def agent_for(payload, authorization):
        provider = registry.get(payload.provider)
        if not provider:
            raise HTTPException(400, "Неизвестная модель")
        token = ""
        if provider.requires_token:
            if not authorization or not authorization.startswith("Bearer "):
                raise HTTPException(401, "Введите токен Jev")
            token = authorization[7:].strip()
            if not 8 <= len(token) <= 512 or not token.isascii() or any(c.isspace() for c in token):
                raise HTTPException(401, "Некорректный токен")
        return provider.factory(token)

    @app.post("/api/track")
    async def track(payload: TrackRequest):
        return build(payload)

    @app.post("/api/plan")
    async def plan(payload: PlanRequest, authorization: str | None = Header(default=None)):
        track = build(payload)
        agent = agent_for(payload, authorization)
        if agent.planner is None:
            return {"plan": "", "latency_ms": 0}
        start = time.perf_counter()
        try:
            async with asyncio.timeout(65):
                value = await agent.planner.prepare(track)
            return {"plan": value[:2000], "latency_ms": round((time.perf_counter()-start)*1000, 1)}
        except Exception:
            raise HTTPException(502, "Планировщик недоступен") from None

    @app.post("/api/decide")
    async def decide(payload: DecisionRequest, authorization: str | None = Header(default=None)):
        track = build(payload)
        if payload.event_id >= len(track["events"]):
            raise HTTPException(400, "Неизвестное препятствие")
        agent = agent_for(payload, authorization)
        if capacity.locked():
            raise HTTPException(503, "Сервер занят, повторите заезд позже")
        start = time.perf_counter()
        result = {"event_id": payload.event_id, "action": "none", "status": "ok",
                  "model": payload.provider, "input_tokens": 0, "cost_usd": 0.0}
        async with capacity:
            try:
                async with asyncio.timeout(settings.timeout + 0.5):
                    decision = await agent.decide(context_for(track, payload.event_id,
                                                              payload.energy, payload.plan))
                result.update(action=decision.action, model=decision.model,
                              input_tokens=decision.input_tokens, cost_usd=decision.cost_usd)
            except ProviderError as exc:
                result["status"] = exc.status
            except TimeoutError:
                result["status"] = "timeout"
            except Exception:
                result["status"] = "invalid_response"
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
        return result

    settings.web_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/game", CompressedFiles(directory=settings.web_dir), name="game")
    app.mount("/assets", StaticFiles(directory=UI), name="assets")
    return app
