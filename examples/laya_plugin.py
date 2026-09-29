"""RACE_PLUGIN=examples.laya_plugin:register; weights are loaded once."""
import os
from race.app import Provider
from race.brains.laya import LayaBrain
from race.contracts import Agent


def register(registry, _client, _settings):
    brain = LayaBrain(os.environ["LAYA_MODEL_PATH"], os.getenv("LAYA_DEVICE", "cpu"))
    registry["laya"] = Provider("Laya · локальная модель", lambda _token: Agent(brain),
                                requires_token=False)
