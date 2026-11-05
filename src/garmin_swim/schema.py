"""YAML workout schema.

A workout file looks like:

    name: "Wk3 D2 - Aerobic Endurance"
    date: 2026-10-01            # optional; schedules on the Garmin calendar
    pool: {length: 25, unit: m} # unit: m | yd
    description: "Focus on long strokes"
    steps:
      - {type: warmup, distance: 400, stroke: choice, notes: easy}
      - repeat: 4
        steps:
          - {type: drill, distance: 50, stroke: free, equipment: fins, notes: catch-up}
          - {rest: 15}
      - {type: cooldown, distance: 200}

Step kinds:
  swim step  -> has `type` (warmup|swim|drill|kick|pull|recovery|cooldown)
                plus one of `distance` (pool units), `time` (seconds or "m:ss"), `lap: true`
  rest step  -> `rest: <seconds|"m:ss"|lap>` or `sendoff: <seconds|"m:ss">`
  repeat     -> `repeat: N` + `steps: [...]`
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Annotated, Literal, Union

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

Stroke = Literal["free", "back", "breast", "fly", "im", "mixed", "choice", "drill"]
Equipment = Literal["fins", "kickboard", "paddles", "pull_buoy", "snorkel"]
SwimType = Literal["warmup", "swim", "drill", "kick", "pull", "recovery", "cooldown"]


def parse_seconds(v: object) -> object:
    """Accept 20, "20", "0:20", "1:45" -> seconds."""
    if isinstance(v, str) and v.strip().lower() != "lap":
        s = v.strip()
        if ":" in s:
            m, sec = s.split(":", 1)
            return int(m) * 60 + int(sec)
        return int(s)
    return v


Seconds = Annotated[int, BeforeValidator(parse_seconds), Field(gt=0)]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SwimStep(_Base):
    type: SwimType
    distance: int | None = Field(default=None, gt=0)
    time: Seconds | None = None
    lap: bool = False
    stroke: Stroke | None = None
    equipment: Equipment | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _one_end_condition(self) -> SwimStep:
        n = sum([self.distance is not None, self.time is not None, self.lap])
        if n != 1:
            raise ValueError("swim step needs exactly one of: distance, time, lap: true")
        return self


class RestStep(_Base):
    rest: Seconds | Literal["lap"] | None = None
    sendoff: Seconds | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _one_kind(self) -> RestStep:
        if (self.rest is None) == (self.sendoff is None):
            raise ValueError("rest step needs exactly one of: rest, sendoff")
        return self


class Repeat(_Base):
    repeat: int = Field(gt=1)
    steps: list[Step] = Field(min_length=1)


def _pick_step(v: object) -> object:
    if not isinstance(v, dict):
        return v
    if "repeat" in v:
        return Repeat.model_validate(v)
    if "rest" in v or "sendoff" in v:
        return RestStep.model_validate(v)
    return SwimStep.model_validate(v)


Step = Annotated[Union[Repeat, RestStep, SwimStep], BeforeValidator(_pick_step)]
Repeat.model_rebuild()


class Pool(_Base):
    length: float = Field(gt=0)
    unit: Literal["m", "yd"] = "m"


class Workout(_Base):
    name: str = Field(min_length=1, max_length=80)
    date: dt.date | None = None
    pool: Pool = Pool(length=25, unit="m")
    description: str | None = None
    steps: list[Step] = Field(min_length=1)

    def total_distance(self) -> float:
        """Total swim distance in pool units (time/lap steps excluded)."""

        def walk(steps: list, mult: int = 1) -> float:
            total = 0.0
            for s in steps:
                if isinstance(s, Repeat):
                    total += walk(s.steps, mult * s.repeat)
                elif isinstance(s, SwimStep) and s.distance:
                    total += s.distance * mult
            return total

        return walk(self.steps)


def load(path: str | Path) -> Workout:
    data = yaml.safe_load(Path(path).read_text())
    return Workout.model_validate(data)
