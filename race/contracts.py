"""Small contracts between the game, planners and decision models."""
from dataclasses import dataclass, replace
from typing import Protocol


@dataclass(frozen=True)
class Candidate:
    id: str
    text: str


@dataclass(frozen=True)
class Context:
    state: str
    candidates: tuple[Candidate, ...]
    question: str = "Choose one immediate action. Avoid the obstacle and conserve energy."
    plan: str = ""


@dataclass(frozen=True)
class Decision:
    action: str
    model: str
    input_tokens: int = 0
    cost_usd: float = 0.0


class Brain(Protocol):
    async def choose(self, context: Context) -> Decision: ...


class Layer(Protocol):
    async def apply(self, context: Context) -> Context: ...


class Planner(Protocol):
    async def prepare(self, track: dict) -> str: ...


@dataclass
class Agent:
    brain: Brain
    layers: tuple[Layer, ...] = ()
    planner: Planner | None = None

    async def decide(self, context: Context) -> Decision:
        current = context
        for layer in self.layers:
            current = await layer.apply(current)
            if current.candidates != context.candidates:
                raise ValueError("Layers must preserve the executable candidates")
        decision = await self.brain.choose(current)
        if decision.action not in {c.id for c in context.candidates}:
            raise ValueError("Model selected an unknown action")
        return decision


class PlanLayer:
    """A plan is prepared before the race; applying it has no network cost."""
    async def apply(self, context: Context) -> Context:
        if not context.plan:
            return context
        return replace(context, state=f"{context.state}\nRace plan: {context.plan}")
