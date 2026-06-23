from __future__ import annotations

import json
from pathlib import Path

import typer
from pydantic import ValidationError

from app.models import config_summary, format_validation_error, load_configs


router = typer.Typer(add_completion=False, help="Configuration validation commands.")

@router.command("validate-config")
def validate_config(
    config_dir: Path = typer.Option(
        Path("config"),
        "--config-dir",
        help="Directory containing scenarios.yaml and sources.yaml.",
    )
) -> None:
    """Validate scenario and source configuration files."""
    try:
        bundle = load_configs(config_dir)
    except FileNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except ValidationError as exc:
        typer.secho("Config validation failed:", fg=typer.colors.RED, err=True)
        typer.echo(format_validation_error(exc), err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.secho(f"Config validation failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps({"status": "ok", **config_summary(bundle)}, indent=2))


@router.command("list-scenarios")
def list_scenarios(
    config_dir: Path = typer.Option(
        Path("config"),
        "--config-dir",
        help="Directory containing scenarios.yaml and sources.yaml.",
    )
) -> None:
    """List all configured scenario IDs and names."""
    try:
        bundle = load_configs(config_dir)
    except FileNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except ValidationError as exc:
        typer.secho("Config validation failed:", fg=typer.colors.RED, err=True)
        typer.echo(format_validation_error(exc), err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.secho(f"Config load failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    scenarios = [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "primary_term_count": len(s.primary_terms),
            "secondary_term_count": len(s.secondary_terms),
            "exclusion_term_count": len(s.exclusion_terms),
        }
        for s in bundle.scenarios.scenarios
    ]
    typer.echo(
        json.dumps(
            {"status": "ok", "scenario_count": len(scenarios), "scenarios": scenarios},
            indent=2,
        )
    )

