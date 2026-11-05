"""Convert a schema.Workout into Garmin Connect workout JSON."""

from __future__ import annotations

import copy
from typing import Any

from .schema import Repeat, RestStep, SwimStep, Workout

# Default catalog of Garmin IDs, keyed by Garmin's own keys. `client.fetch_catalog`
# refreshes these from /workout-service/workout/types so wrong guesses self-correct.
DEFAULT_CATALOG: dict[str, dict[str, int]] = {
    "step": {"warmup": 1, "cooldown": 2, "interval": 3, "recovery": 4, "rest": 5, "repeat": 6},
    "condition": {
        "lap.button": 1,
        "time": 2,
        "distance": 3,
        "iterations": 7,
        "fixed.rest": 8,
        "fixed.repetition": 9,
    },
    "stroke": {
        "any_stroke": 1,
        "backstroke": 2,
        "breaststroke": 3,
        "drill": 4,
        "fly": 5,
        "free": 6,
        "individual_medley": 7,
        "mixed": 8,
    },
    "equipment": {"fins": 1, "kickboard": 2, "paddles": 3, "pull_buoy": 4, "snorkel": 5},
    "drill": {"kick": 1, "pull": 2, "drill": 3},
}

# schema value -> Garmin key
STROKE_KEYS = {
    "free": "free",
    "back": "backstroke",
    "breast": "breaststroke",
    "fly": "fly",
    "im": "individual_medley",
    "mixed": "mixed",
    "choice": "any_stroke",
    "drill": "drill",
}
STEP_KEYS = {
    "warmup": "warmup",
    "swim": "interval",
    "drill": "interval",
    "kick": "interval",
    "pull": "interval",
    "recovery": "recovery",
    "cooldown": "cooldown",
}
DRILL_KEYS = {"drill": "drill", "kick": "kick", "pull": "pull"}

UNITS = {
    "m": {"unitId": 1, "unitKey": "meter", "factor": 100.0},
    "yd": {"unitId": 230, "unitKey": "yard", "factor": 91.44},
}
METERS_PER_UNIT = {"m": 1.0, "yd": 0.9144}

SWIMMING = {"sportTypeId": 4, "sportTypeKey": "swimming", "displayOrder": 3}
SEC_PER_100M = 120  # rough pace, only used for Garmin's duration estimate


class CatalogError(ValueError):
    pass


class _Builder:
    def __init__(self, workout: Workout, catalog: dict[str, dict[str, int]]):
        self.w = workout
        self.cat = catalog
        self.order = 0
        self.child_id = 0
        self.est_secs = 0.0
        self.unit = workout.pool.unit

    def _ref(self, kind: str, key: str) -> int:
        try:
            return self.cat[kind][key]
        except KeyError:
            known = ", ".join(sorted(self.cat.get(kind, {})))
            raise CatalogError(f"Garmin has no {kind} type '{key}' (known: {known})") from None

    def step_type(self, key: str) -> dict[str, Any]:
        i = self._ref("step", key)
        return {"stepTypeId": i, "stepTypeKey": key, "displayOrder": i}

    def condition(self, key: str) -> dict[str, Any]:
        i = self._ref("condition", key)
        return {"conditionTypeId": i, "conditionTypeKey": key, "displayOrder": i, "displayable": True}

    def _next_order(self) -> int:
        self.order += 1
        return self.order

    def steps(self, steps: list, child_id: int | None, mult: int = 1) -> list[dict[str, Any]]:
        out = []
        for s in steps:
            if isinstance(s, Repeat):
                out.append(self.repeat(s, mult))
            elif isinstance(s, RestStep):
                out.append(self.rest(s, child_id, mult))
            else:
                out.append(self.swim(s, child_id, mult))
        return out

    def repeat(self, r: Repeat, mult: int) -> dict[str, Any]:
        order = self._next_order()
        self.child_id += 1
        cid = self.child_id
        cond = self.condition("iterations") | {"displayable": False}
        return {
            "type": "RepeatGroupDTO",
            "stepOrder": order,
            "stepType": self.step_type("repeat"),
            "childStepId": cid,
            "numberOfIterations": r.repeat,
            "endCondition": cond,
            "endConditionValue": float(r.repeat),
            "smartRepeat": False,
            "workoutSteps": self.steps(r.steps, cid, mult * r.repeat),
        }

    def _base(self, step_key: str, child_id: int | None, notes: str | None) -> dict[str, Any]:
        return {
            "type": "ExecutableStepDTO",
            "stepOrder": self._next_order(),
            "stepType": self.step_type(step_key),
            "childStepId": child_id,
            "description": notes,
            "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1},
            "strokeType": {"strokeTypeId": 0, "strokeTypeKey": None, "displayOrder": 0},
            "equipmentType": {"equipmentTypeId": 0, "equipmentTypeKey": None, "displayOrder": 0},
        }

    def swim(self, s: SwimStep, child_id: int | None, mult: int) -> dict[str, Any]:
        d = self._base(STEP_KEYS[s.type], child_id, s.notes)
        if s.distance is not None:
            meters = s.distance * METERS_PER_UNIT[self.unit]
            d["endCondition"] = self.condition("distance")
            # Garmin reads the value in preferredEndConditionUnit (yards stay yards)
            d["endConditionValue"] = float(s.distance)
            d["preferredEndConditionUnit"] = UNITS[self.unit]
            self.est_secs += meters / 100 * SEC_PER_100M * mult
        elif s.time is not None:
            d["endCondition"] = self.condition("time")
            d["endConditionValue"] = float(s.time)
            self.est_secs += s.time * mult
        else:
            d["endCondition"] = self.condition("lap.button")
        if s.stroke:
            key = STROKE_KEYS[s.stroke]
            i = self._ref("stroke", key)
            d["strokeType"] = {"strokeTypeId": i, "strokeTypeKey": key, "displayOrder": i}
        if s.equipment:
            i = self._ref("equipment", s.equipment)
            d["equipmentType"] = {"equipmentTypeId": i, "equipmentTypeKey": s.equipment, "displayOrder": i}
        if s.type in DRILL_KEYS:
            key = DRILL_KEYS[s.type]
            i = self._ref("drill", key)
            d["drillType"] = {"drillTypeId": i, "drillTypeKey": key, "displayOrder": i}
        return d

    def rest(self, s: RestStep, child_id: int | None, mult: int) -> dict[str, Any]:
        d = self._base("rest", child_id, s.notes)
        if s.sendoff is not None:
            # "repeat on" / send-off: rest until the interval clock hits this time
            d["endCondition"] = self.condition("fixed.repetition")
            d["endConditionValue"] = float(s.sendoff)
        elif s.rest == "lap":
            d["endCondition"] = self.condition("lap.button")
        else:
            d["endCondition"] = self.condition("fixed.rest")
            d["endConditionValue"] = float(s.rest)
            self.est_secs += s.rest * mult
        return d

    def build(self) -> dict[str, Any]:
        steps = self.steps(self.w.steps, None)
        pool_len = self.w.pool.length
        return {
            "workoutName": self.w.name,
            "description": self.w.description,
            "sportType": SWIMMING,
            "subSportType": None,
            "poolLength": pool_len,
            "poolLengthUnit": UNITS[self.unit],
            "estimatedDurationInSecs": int(self.est_secs),
            "estimatedDistanceInMeters": round(self.w.total_distance() * METERS_PER_UNIT[self.unit], 2),
            "workoutSegments": [
                {
                    "segmentOrder": 1,
                    "sportType": SWIMMING,
                    "poolLength": pool_len,
                    "poolLengthUnit": UNITS[self.unit],
                    "workoutSteps": steps,
                }
            ],
        }


def build(workout: Workout, catalog: dict[str, dict[str, int]] | None = None) -> dict[str, Any]:
    return _Builder(workout, copy.deepcopy(catalog or DEFAULT_CATALOG)).build()
