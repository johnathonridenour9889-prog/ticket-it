from __future__ import annotations

import json
import sys
from pathlib import Path


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = app_base_dir()
DATA_DIR = BASE_DIR / "Data"
SETTINGS_PATH = DATA_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "discord_token": "",
    "discord_guild_id": "",
    "backend_channel_id": "",
    "display_name": "Ticket-it",
    "groq_api_key": "",
}


def load_settings() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not SETTINGS_PATH.exists():
        save_settings(DEFAULT_SETTINGS.copy())
        return DEFAULT_SETTINGS.copy()

    try:
        with SETTINGS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        merged = DEFAULT_SETTINGS.copy()
        merged.update(data if isinstance(data, dict) else {})
        return merged
    except Exception:
        return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    merged = DEFAULT_SETTINGS.copy()
    merged.update(settings or {})

    with SETTINGS_PATH.open("w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)