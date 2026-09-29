import asyncio
from dataclasses import replace
import httpx
import pytest
from race.brains.jev import JevBrain, ProviderError
from race.contracts import Agent, Candidate, Context, Decision, PlanLayer

CONTEXT = Context("A gap ahead", (Candidate("jump","Jump"), Candidate("slide","Slide")))


def test_each_jev_call_uses_only_the_supplied_token():
    seen = []
    def handler(request):
        seen.append(request.headers["Authorization"])
        return httpx.Response(200,json={"answers":{"action":{"type":"choice","choice":"jump"}},
                                       "usage":{"input_tokens":100},"model":"jev-test"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            for token in ("fixture-token-one","fixture-token-two"):
                brain = JevBrain(client,token)
                result = await Agent(brain).decide(CONTEXT)
                assert result.action == "jump" and result.cost_usd == pytest.approx(.0000042)
                assert brain.token == ""
            assert "Authorization" not in client.headers
    asyncio.run(run())
    assert seen == ["Bearer fixture-token-one","Bearer fixture-token-two"]


@pytest.mark.parametrize("code,status", [(401,"invalid_token"),(403,"invalid_token"),
                                       (429,"rate_limited"),(500,"unavailable")])
def test_provider_errors_are_sanitized(code,status):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request:httpx.Response(code,text="upstream echoed a private credential"))) as client:
            with pytest.raises(ProviderError) as error:
                await JevBrain(client,"fixture-private-key").choose(CONTEXT)
            assert str(error.value) == status
    asyncio.run(run())


def test_layers_cannot_rewrite_actions_and_plan_is_explicit():
    class Brain:
        async def choose(self, context):
            assert "save energy" in context.state
            return Decision("jump","fixture")
    class InvalidLayer:
        async def apply(self, context):
            return replace(context,candidates=(Candidate("cheat","Skip race"),))
    async def run():
        result = await Agent(Brain(),(PlanLayer(),)).decide(replace(CONTEXT,plan="save energy"))
        assert result.action == "jump"
        with pytest.raises(ValueError):
            await Agent(Brain(),(InvalidLayer(),)).decide(CONTEXT)
    asyncio.run(run())


def test_laya_cancellation_keeps_inference_serial(monkeypatch):
    import sys
    from threading import Event
    from types import SimpleNamespace
    from race.brains.laya import LayaBrain

    started, release = Event(), Event()
    calls = []

    def predict(*_args):
        calls.append(1)
        if len(calls) == 1:
            started.set()
            assert release.wait(2)
        return {"answers": {"action": {"choice": "jump"}}}

    monkeypatch.setitem(sys.modules, "laya", SimpleNamespace(
        load=lambda *_args, **_kwargs: SimpleNamespace(predict=predict)))
    brain = LayaBrain("fixture")

    async def run():
        first = asyncio.create_task(brain.choose(CONTEXT))
        assert await asyncio.to_thread(started.wait, 1)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        second = asyncio.create_task(brain.choose(CONTEXT))
        await asyncio.sleep(.02)
        assert len(calls) == 1
        release.set()
        assert (await second).action == "jump"

    try:
        asyncio.run(run())
    finally:
        release.set()
        brain.worker.shutdown()
