"""Load attack definitions and give each run a new fake secret."""

import secrets
from pathlib import Path

import yaml

ATTACKS_DIR = Path(__file__).resolve().parent.parent / "attacks"


def _fill(value, canary: str):
    if isinstance(value, str):
        return value.replace("{canary}", canary)
    if isinstance(value, list):
        return [_fill(item, canary) for item in value]
    if isinstance(value, dict):
        return {key: _fill(item, canary) for key, item in value.items()}
    return value


def load_attack(attack_id: str) -> dict:
    path = ATTACKS_DIR / f"{attack_id}.yaml"
    attack = yaml.safe_load(path.read_text(encoding="utf-8"))
    canary = f"CANARY-{secrets.token_hex(4).upper()}"
    return {**_fill(attack, canary), "canary": canary}
