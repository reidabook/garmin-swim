---
name: swim
description: Convert pasted swim workout text (single workout, a week, or a whole plan) into YAML files and push them to Garmin Connect as structured swim workouts scheduled on the calendar.
---

# /swim — pasted workout text → Garmin

The user pastes swim workout text (from TrainingPeaks, a website, or a PDF), usually with a date or day label.

## Steps

1. **Read the schema** in `src/garmin_swim/schema.py` (docstring at top) and look at `workouts/example.yaml`.
2. **Parse** each workout into one YAML file: `workouts/YYYY-MM-DD-<slug>.yaml` (no date → `workouts/<slug>.yaml`).
   - `name`: short and unique, and ideally includes the plan week and day, e.g. `"W3D2 Aerobic Endurance"`. Pushing matches on name, so keep it stable across edits.
   - Keep **every detail** from the source. Anything without a field (drill name, pace/effort, breathing pattern, focus cues) goes in that step's `notes`. Anything that applies to the whole workout goes in `description`.
   - `N x D` → `repeat: N` with inner steps. For a single rep, use a plain step.
   - Rest: `"15s rest"` / `":15"` → `{rest: 15}`. `"on 1:45"` / `"@1:45"` (send-off interval) → `{sendoff: "1:45"}` after the swim step. `"rest as needed"` → `{rest: lap}`.
   - Types: warmup / swim / drill / kick / pull / recovery / cooldown. Main-set efforts are `swim`. Easy swims between sets are `recovery`.
   - Stroke: `free | back | breast | fly | im | mixed | choice | drill`. "Choice" / unspecified warmup → `choice`. Leave it out if genuinely unknown.
   - Equipment: `fins | kickboard | paddles | pull_buoy | snorkel` (one per step; put extras in notes). Pull sets usually mean `pull_buoy`.
   - Nested sets (e.g. `3 x (4x50 + 100)`) are allowed: repeat inside repeat.
   - Distances are in pool units (`pool.unit`).
3. **Ask, don't guess**, when it matters: pool length or unit if not stated and there's no earlier file to copy from, whether "@1:45" means a send-off or a pace target, and dates when only "Day 3" is given (ask for the plan start date).
4. **Validate** with `uv run garmin-swim validate <files>`. Fix any errors. Show the user the summary and check that total distance matches the source's stated total, if it has one.
5. **After the user confirms**, run `uv run garmin-swim push <files>`. If login needs credentials or MFA, tell the user to run `! uv run garmin-swim login` themselves (it's interactive).
6. Report what was created, updated, or scheduled.

## Notes
- Re-pushing a file with the same `name` updates the workout in place and keeps its calendar entry.
- Changing a file's `date` adds a new calendar entry; the old one stays. Remove it in Garmin Connect.
- `uv run garmin-swim types` dumps Garmin's stroke, equipment and drill IDs if a push fails with a catalog error.
