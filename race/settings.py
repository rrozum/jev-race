"""Operator configuration. Jev credentials are deliberately not environment settings."""
from dataclasses import dataclass, field
import os
import tomllib
from pathlib import Path
from race.levels import GeneratorConfig

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    web_dir: Path = ROOT / "web/game"
    jev_model: str = "jev-1.13.0"
    input_price: float = 0.042
    timeout: float = 3.0
    plugin: str = ""
    generator: GeneratorConfig = field(default_factory=GeneratorConfig)

    @classmethod
    def from_env(cls):
        rules = {}
        if filename := os.getenv("RACE_RULES_FILE"):
            with open(filename, "rb") as stream:
                rules = tomllib.load(stream).get("generator", {})
            if "hazard_types" in rules:
                rules["hazard_types"] = tuple(rules["hazard_types"])
        return cls(web_dir=Path(os.getenv("RACE_WEB_DIR", ROOT / "web/game")),
                   jev_model=os.getenv("JEV_MODEL", "jev-1.13.0"),
                   input_price=float(os.getenv("JEV_INPUT_USD_PER_MILLION", "0.042")),
                   timeout=float(os.getenv("JEV_TIMEOUT_SECONDS", "3")),
                   plugin=os.getenv("RACE_PLUGIN", ""), generator=GeneratorConfig(**rules))
