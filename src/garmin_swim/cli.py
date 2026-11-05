"""garmin-swim CLI."""

from __future__ import annotations

from pathlib import Path

import typer
from pydantic import ValidationError

from . import builder, schema
from .schema import Repeat, RestStep, SwimStep

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _load(path: Path) -> schema.Workout:
    try:
        return schema.load(path)
    except ValidationError as e:
        typer.secho(f"{path}: invalid\n{e}", fg="red", err=True)
        raise typer.Exit(1)


def _fmt_secs(s: int) -> str:
    return f"{s // 60}:{s % 60:02d}"


def _describe(steps: list, indent: int = 0) -> list[str]:
    pad = "  " * indent
    lines = []
    for s in steps:
        if isinstance(s, Repeat):
            lines.append(f"{pad}{s.repeat}x")
            lines += _describe(s.steps, indent + 1)
        elif isinstance(s, RestStep):
            what = f"send-off {_fmt_secs(s.sendoff)}" if s.sendoff else (
                "rest until lap" if s.rest == "lap" else f"rest {s.rest}s"
            )
            lines.append(f"{pad}{what}" + (f"  ({s.notes})" if s.notes else ""))
        else:
            assert isinstance(s, SwimStep)
            amount = s.distance or (_fmt_secs(s.time) if s.time else "lap")
            bits = [s.type, str(amount), s.stroke or "", s.equipment or ""]
            line = " ".join(b for b in bits if b)
            lines.append(f"{pad}{line}" + (f"  ({s.notes})" if s.notes else ""))
    return lines


@app.command()
def validate(files: list[Path]) -> None:
    """Check workout files and print a summary."""
    for f in files:
        w = _load(f)
        unit = w.pool.unit
        typer.secho(f"✓ {w.name}", fg="green", bold=True)
        typer.echo(f"  {w.date or 'unscheduled'} · pool {w.pool.length:g}{unit} · {w.total_distance():g}{unit}")
        for line in _describe(w.steps, 2):
            typer.echo(line)


@app.command()
def preview(file: Path) -> None:
    """Print the Garmin JSON that would be uploaded (no network)."""
    from .client import dump

    typer.echo(dump(builder.build(_load(file))))


@app.command()
def push(
    files: list[Path],
    schedule: bool = typer.Option(True, help="Schedule on the file's date"),
) -> None:
    """Upload (create or update by name) and schedule workouts."""
    from . import client

    workouts = [(f, _load(f)) for f in files]
    g = client.login()
    catalog = client.fetch_catalog(g)
    for f, w in workouts:
        payload = builder.build(w, catalog)
        date = w.date.isoformat() if (schedule and w.date) else None
        wid, action = client.push(g, payload, date)
        when = f" → {date}" if date else ""
        typer.secho(f"{action} {w.name} (id {wid}){when}", fg="green")


@app.command("list")
def list_() -> None:
    """List swim workouts in your Garmin library."""
    from . import client

    g = client.login()
    for w in g.get_workouts(0, 200) or []:
        if (w.get("sportType") or {}).get("sportTypeKey") == "swimming":
            typer.echo(f"{w['workoutId']}\t{w['workoutName']}")


@app.command()
def delete(names: list[str]) -> None:
    """Delete workouts by exact name."""
    from . import client

    g = client.login()
    for n in names:
        ok = client.delete(g, n)
        typer.echo(f"{'deleted' if ok else 'not found'}: {n}")


@app.command()
def show(workout_id: int) -> None:
    """Dump a Garmin workout's raw JSON (useful for reverse-engineering fields)."""
    from . import client

    typer.echo(client.dump(client.login().get_workout_by_id(workout_id)))


@app.command()
def types() -> None:
    """Dump Garmin's workout type catalog (stroke/equipment/drill IDs)."""
    from . import client

    typer.echo(client.dump(client.fetch_types(client.login())))


@app.command()
def login() -> None:
    """Log in and cache tokens."""
    from . import client

    client.login()
    typer.secho(f"logged in; tokens in {client.TOKEN_DIR}", fg="green")


def main() -> None:
    app()
