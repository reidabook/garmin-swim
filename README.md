# garmin-swim

Push structured swim workouts (stroke, equipment, drill, kick, pull, rest, send-off, per-step notes) to Garmin Connect and schedule them on your calendar. They then sync to your watch.

## Setup
```sh
brew install uv
uv sync
uv run garmin-swim login     # email/password (+MFA) once; tokens cached in ~/.garminconnect
```

## Usage
In Claude Code, run `/swim` and paste the workout text. Claude writes `workouts/*.yaml`, validates it, and pushes it after you confirm.

Manual:
```sh
uv run garmin-swim validate workouts/*.yaml   # check + summary
uv run garmin-swim preview workouts/x.yaml    # Garmin JSON, no network
uv run garmin-swim push workouts/*.yaml       # create/update by name + schedule on `date`
uv run garmin-swim push --no-schedule f.yaml
uv run garmin-swim list | delete "Name" | show <id> | types
```

The YAML format is documented in `src/garmin_swim/schema.py`. See `workouts/example.yaml` for a full example.

## Notes
- This uses Garmin's unofficial API through [python-garminconnect](https://github.com/cyberjunky/python-garminconnect), pinned to one version. If login breaks, bump the version.
- Turn off TrainingPeaks → Garmin workout sync so you don't get duplicate workouts.
