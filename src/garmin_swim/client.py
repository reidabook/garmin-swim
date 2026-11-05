"""Thin wrapper over python-garminconnect for workout upload + scheduling."""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
from typing import Any

from garminconnect import Garmin

from .builder import DEFAULT_CATALOG

TOKEN_DIR = Path(os.getenv("GARMINTOKENS", "~/.garminconnect")).expanduser()


def login(interactive: bool = True) -> Garmin:
    """Log in with cached tokens; fall back to email/password (+ MFA prompt)."""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        g = Garmin()
        g.login(str(TOKEN_DIR))
        return g
    except Exception:
        if not interactive:
            raise
    email = os.getenv("GARMIN_EMAIL") or input("Garmin email: ")
    password = os.getenv("GARMIN_PASSWORD") or getpass.getpass("Garmin password: ")
    g = Garmin(email, password, prompt_mfa=lambda: input("MFA code: "))
    g.login(str(TOKEN_DIR))
    return g


def fetch_types(g: Garmin) -> Any:
    return g.connectapi("/workout-service/workout/types")


def fetch_catalog(g: Garmin) -> dict[str, dict[str, int]]:
    """Build an ID catalog from Garmin's type listing, falling back to defaults."""
    raw = fetch_types(g)
    fields = {
        "step": ("stepTypeKey", "stepTypeId"),
        "condition": ("conditionTypeKey", "conditionTypeId"),
        "stroke": ("strokeTypeKey", "strokeTypeId"),
        "equipment": ("equipmentTypeKey", "equipmentTypeId"),
        "drill": ("drillTypeKey", "drillTypeId"),
    }
    catalog = {k: dict(v) for k, v in DEFAULT_CATALOG.items()}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for kind, (key_f, id_f) in fields.items():
                if node.get(key_f) and node.get(id_f) is not None:
                    catalog[kind][node[key_f]] = node[id_f]
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(raw)
    return catalog


def find_workout(g: Garmin, name: str) -> dict[str, Any] | None:
    start = 0
    while True:
        page = g.get_workouts(start=start, limit=100) or []
        for w in page:
            if w.get("workoutName") == name:
                return w
        if len(page) < 100:
            return None
        start += 100


def scheduled_ids(g: Garmin, workout_id: int, date: str) -> list[int]:
    """Calendar entries for `workout_id` on `date` (YYYY-MM-DD)."""
    y, m, _ = date.split("-")
    cal = g.get_scheduled_workouts(int(y), int(m)) or {}
    return [
        item["id"]
        for item in cal.get("calendarItems") or []
        if item.get("itemType") == "workout"
        and item.get("workoutId") == workout_id
        and item.get("date") == date
    ]


def push(g: Garmin, payload: dict[str, Any], date: str | None) -> tuple[int, str]:
    """Create or update workout by name; schedule on date if not already there.

    Returns (workout_id, action) where action is 'created' or 'updated'.
    """
    existing = find_workout(g, payload["workoutName"])
    if existing:
        wid = int(existing["workoutId"])
        # PUT replaces the whole workout, so keep server fields (ownerId etc.)
        g.update_workout(wid, g.get_workout_by_id(wid) | payload)
        action = "updated"
    else:
        wid = int(g.upload_workout(payload)["workoutId"])
        action = "created"
    if date and not scheduled_ids(g, wid, date):
        g.schedule_workout(wid, date)
    return wid, action


def delete(g: Garmin, name: str) -> bool:
    w = find_workout(g, name)
    if not w:
        return False
    g.delete_workout(w["workoutId"])
    return True


def dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)
