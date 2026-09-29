"""A local LLM plans before the race; Jev chooses each immediate action."""
import os
from race.app import Provider
from race.brains.jev import JevBrain
from race.brains.planner import HttpPlanner
from race.contracts import Agent, PlanLayer


def register(registry, client, settings):
    planner = HttpPlanner(os.getenv("PLANNER_URL", "http://127.0.0.1:11434/v1/chat/completions"),
                          os.environ["PLANNER_MODEL"])
    def make_agent(token):
        return Agent(JevBrain(client, token, settings.jev_model, settings.input_price),
                     layers=(PlanLayer(),), planner=planner)
    registry["jev-plan"] = Provider("LLM + Jev", make_agent, planning=True)
