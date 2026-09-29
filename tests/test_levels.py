from collections import Counter
import pytest
from race.levels import GeneratorConfig, context_for, generate


@pytest.mark.parametrize("seed", [0, 1, 42, 999999])
@pytest.mark.parametrize("count", [4, 6, 12, 40])
def test_repeatable_balanced_and_traversable(seed, count):
    track = generate(seed, count)
    assert track == generate(seed, count)
    assert len(track["events"]) == count
    counts = Counter(event["type"] for event in track["events"])
    assert max(counts.values()) - min(counts.values()) <= 1
    for left, right in zip(track["events"], track["events"][1:]):
        assert left["type"] != right["type"]
        assert right["x"] - left["x"] >= 448
    for event in track["events"]:
        assert event["x"] % 64 == 0
        if event["type"] == "gap":
            removed = [tile for tile in range(event["x"]//64-3,event["x"]//64+3)
                       if abs(tile*64+32-event["x"]) < 64]
            assert len(removed) == 2


def test_model_sees_observation_not_gold_answer():
    track = generate(42)
    context = context_for(track, 0, 0)
    assert {c.id for c in context.candidates} == {"jump", "slide"}
    assert "best" not in context.state and "alternative" not in context.state


@pytest.mark.parametrize("kwargs", [{"spacing":128},{"spacing":450},{"speed":500},
                                    {"hazard_types":("gap",)},
                                    {"hazard_types":("drone", "gap")},{"max_obstacles":101}])
def test_unsafe_configuration_rejected(kwargs):
    with pytest.raises(ValueError):
        GeneratorConfig(**kwargs)


def test_config_controls_generated_track():
    rules = GeneratorConfig(spacing=576, max_obstacles=60, hazard_types=("beam", "gap"))
    track = generate(42, 50, rules)
    assert len(track["events"]) == 50
    assert track["events"][1]["x"]-track["events"][0]["x"] == 576
