"""Seeded tracks. Geometry stays inside the runner's movement envelope."""
from dataclasses import dataclass
import random

from race.contracts import Candidate, Context

ACTION_TEXT = {
    "jump": "Jump over a floor obstacle or gap. No energy cost.",
    "slide": "Slide under a low overhead obstacle. No energy cost.",
    "shield": "Use a temporary shield against an obstacle or enemy. Costs one charge.",
    "shoot": "Shoot an enemy ahead. Costs one charge.",
}
HAZARDS = {
    "spikes": ("Шипы", "Sharp floor spikes block the lane.", "jump", "shield"),
    "beam": ("Низкая балка", "A low beam hangs across the lane. Stay low.", "slide", "shield"),
    "drone": ("Дрон", "A hostile drone fires across the lane. Destroy or block it.", "shoot", "shield"),
    "gap": ("Разрыв", "A gap opens in the floor. Cross it without falling.", "jump", None),
    "laser": ("Лазер", "A horizontal laser sweeps the upper part of the lane.", "slide", "shield"),
    "beetle": ("Жук", "An armored beetle rolls along the floor.", "jump", "shoot"),
}


@dataclass(frozen=True)
class GeneratorConfig:
    # Multiples of 64 keep gaps aligned to the terrain tiles.
    start_x: int = 704
    spacing: int = 448
    finish_margin: int = 384
    speed: int = 300
    penalty_seconds: float = 2.0
    max_obstacles: int = 40
    hazard_types: tuple[str, ...] = tuple(HAZARDS)

    def __post_init__(self):
        if self.start_x < 640 or self.start_x % 64:
            raise ValueError("start_x must be a multiple of 64 and at least 640")
        if self.spacing < 448 or self.spacing % 64 or self.finish_margin < 192:
            raise ValueError("Unsafe obstacle spacing or finish margin")
        if self.speed != 300 or self.penalty_seconds < 0:
            raise ValueError("Changing speed requires recalibrating the Godot controller")
        if not 4 <= self.max_obstacles <= 100:
            raise ValueError("max_obstacles must be in 4..100")
        if len(set(self.hazard_types)) != len(self.hazard_types) or len(self.hazard_types) < 2:
            raise ValueError("Choose at least two distinct hazard types")
        if any(kind not in HAZARDS for kind in self.hazard_types):
            raise ValueError("Unknown hazard type")
        if "drone" in self.hazard_types and len(self.hazard_types) < 3:
            raise ValueError("A drone needs energy: include at least three hazard types")


def generate(seed: int, count: int = 12, config: GeneratorConfig | None = None) -> dict:
    config = config or GeneratorConfig()
    if type(seed) is not int or not 0 <= seed <= 1_000_000_000:
        raise ValueError("Seed must be an integer in 0..1000000000")
    if type(count) is not int or not 4 <= count <= config.max_obstacles:
        raise ValueError(f"Obstacle count must be in 4..{config.max_obstacles}")
    rng = random.Random(seed)
    sequence = []
    while len(sequence) < count:
        bag = list(config.hazard_types)
        rng.shuffle(bag)
        if sequence and sequence[-1] == bag[0]:
            bag = bag[1:] + bag[:1]
        sequence.extend(bag[:count - len(sequence)])
    events = []
    for index, kind in enumerate(sequence):
        title, cue, best, alternative = HAZARDS[kind]
        events.append(dict(id=index, type=kind, x=config.start_x + index * config.spacing,
                           title=title, cue=cue, best=best, alternative=alternative))
    return dict(version=1, seed=seed, obstacle_count=count, events=events,
                finish_x=events[-1]["x"] + config.finish_margin, speed=config.speed,
                penalty_seconds=config.penalty_seconds, energy=3)


def context_for(track: dict, event_id: int, energy: int, plan: str = "") -> Context:
    event = track["events"][event_id]
    candidates = tuple(Candidate(key, text) for key, text in ACTION_TEXT.items()
                       if energy > 0 or key not in ("shield", "shoot"))
    state = (f"Robot runs right automatically at {track['speed']} px/s. "
             f"Obstacle {event_id + 1}/{len(track['events'])}: {event['cue']} "
             f"Energy: {energy}/3. One charge recharges after every third obstacle. "
             "The movement controller executes your choice near the obstacle.")
    return Context(state, candidates, plan=plan)
