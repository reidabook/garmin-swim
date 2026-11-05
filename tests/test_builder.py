from pathlib import Path

import pytest
from pydantic import ValidationError

from garmin_swim import builder, schema

EXAMPLE = Path(__file__).parent.parent / "workouts" / "example.yaml"


def w(steps, **kw):
    return schema.Workout.model_validate({"name": "t", "steps": steps, **kw})


def flat(steps):
    for s in steps:
        yield s
        yield from flat(s.get("workoutSteps", []))


def test_example_builds():
    out = builder.build(schema.load(EXAMPLE))
    assert out["sportType"]["sportTypeKey"] == "swimming"
    assert out["estimatedDistanceInMeters"] == 2100
    orders = [s["stepOrder"] for s in flat(out["workoutSegments"][0]["workoutSteps"])]
    assert orders == list(range(1, len(orders) + 1))


def test_repeat_children_share_child_id():
    out = builder.build(w([{"repeat": 3, "steps": [{"type": "swim", "distance": 100}, {"rest": 20}]}]))
    rep = out["workoutSegments"][0]["workoutSteps"][0]
    assert rep["type"] == "RepeatGroupDTO" and rep["numberOfIterations"] == 3
    assert {c["childStepId"] for c in rep["workoutSteps"]} == {rep["childStepId"]}


def test_stroke_equipment_drill():
    out = builder.build(w([{"type": "kick", "distance": 50, "stroke": "fly", "equipment": "fins"}]))
    s = out["workoutSegments"][0]["workoutSteps"][0]
    assert s["strokeType"]["strokeTypeKey"] == "fly"
    assert s["equipmentType"]["equipmentTypeKey"] == "fins"
    assert s["drillType"]["drillTypeKey"] == "kick"
    assert s["stepType"]["stepTypeKey"] == "interval"


def test_rest_variants():
    out = builder.build(w([{"rest": "0:30"}, {"rest": "lap"}, {"sendoff": "1:45"}]))
    a, b, c = out["workoutSegments"][0]["workoutSteps"]
    assert (a["endCondition"]["conditionTypeKey"], a["endConditionValue"]) == ("fixed.rest", 30)
    assert b["endCondition"]["conditionTypeKey"] == "lap.button"
    assert (c["endCondition"]["conditionTypeKey"], c["endConditionValue"]) == ("fixed.repetition", 105)


def test_yards_sent_as_yards():
    out = builder.build(w([{"type": "swim", "distance": 100}], pool={"length": 25, "unit": "yd"}))
    s = out["workoutSegments"][0]["workoutSteps"][0]
    assert s["endConditionValue"] == 100
    assert s["preferredEndConditionUnit"]["unitKey"] == "yard"
    assert out["poolLengthUnit"]["unitKey"] == "yard"


@pytest.mark.parametrize("step", [
    {"type": "swim"},                                   # no end condition
    {"type": "swim", "distance": 100, "time": 60},      # two end conditions
    {"type": "swim", "distance": 100, "stroke": "doggy"},
    {"rest": 10, "sendoff": 60},
    {"repeat": 1, "steps": [{"rest": 10}]},
])
def test_invalid(step):
    with pytest.raises(ValidationError):
        w([step])


def test_unknown_catalog_key_errors():
    cat = {k: dict(v) for k, v in builder.DEFAULT_CATALOG.items()}
    del cat["equipment"]["snorkel"]
    with pytest.raises(builder.CatalogError):
        builder.build(w([{"type": "swim", "distance": 50, "equipment": "snorkel"}]), cat)
