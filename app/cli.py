from __future__ import annotations

import typer

from app.commands.config import router as config_router
from app.commands.ingest import router as ingest_router
from app.commands.classify import router as classify_router
from app.commands.score import router as score_router
from app.commands.baselines import router as baselines_router
from app.commands.live import router as live_router
from app.commands.status import router as status_router
from app.commands.alerts import router as alerts_router
from app.commands.runs import router as runs_router


app = typer.Typer(
    add_completion=False,
    help="Convergence Monitor command-line interface.",
)

app.add_typer(config_router)
app.add_typer(ingest_router)
app.add_typer(classify_router)
app.add_typer(score_router)
app.add_typer(baselines_router, name="baselines")
app.add_typer(live_router)
app.add_typer(status_router)
app.add_typer(alerts_router)
app.add_typer(runs_router, name="runs")


if __name__ == "__main__":
    app()
