#!/usr/bin/env python3
"""Split the monolithic Typer CLI into command modules.

The script reads the current `app/cli.py`, extracts known command functions with
AST line numbers, writes `app/commands/*.py`, and replaces `app/cli.py` with a
thin router.

It is backup-first and dry-run by default.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModuleSpec:
    filename: str
    help_text: str
    functions: tuple[str, ...]
    root_router: bool = True
    typer_name: str | None = None


MODULES: tuple[ModuleSpec, ...] = (
    ModuleSpec(
        filename="config.py",
        help_text="Configuration validation commands.",
        functions=("validate_config",),
    ),
    ModuleSpec(
        filename="ingest.py",
        help_text="RSS ingestion commands.",
        functions=("_raw_path", "_ingest_one_source", "ingest"),
    ),
    ModuleSpec(
        filename="classify.py",
        help_text="Document classification commands.",
        functions=("classify",),
    ),
    ModuleSpec(
        filename="score.py",
        help_text="Scenario scoring commands.",
        functions=("score",),
    ),
    ModuleSpec(
        filename="baselines.py",
        help_text="Scenario baseline commands.",
        functions=("show_baseline", "update_baseline"),
        root_router=False,
        typer_name="baselines",
    ),
    ModuleSpec(
        filename="live.py",
        help_text="Live verification and review commands.",
        functions=("verify_live", "accept_live", "review_live", "live_history"),
    ),
    ModuleSpec(
        filename="status.py",
        help_text="Scenario status commands.",
        functions=("scenario_status",),
    ),
    ModuleSpec(
        filename="alerts.py",
        help_text="Alert generation commands.",
        functions=("alert",),
    ),
    ModuleSpec(
        filename="runs.py",
        help_text="Run snapshot inspection commands.",
        functions=("list_runs", "source_health"),
        root_router=False,
        typer_name="runs",
    ),
)


def run_git(repo_dir: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def ensure_clean_worktree(repo_dir: Path, allow_dirty: bool) -> None:
    if allow_dirty:
        return
    status = run_git(repo_dir, "status", "--porcelain")
    if status:
        raise SystemExit(
            "Working tree is dirty. Commit/stash changes first, or pass --allow-dirty."
        )


def read_source(cli_path: Path) -> str:
    if not cli_path.exists():
        raise SystemExit(f"Missing CLI file: {cli_path}")
    return cli_path.read_text(encoding="utf-8")


def parse_tree(source: str, cli_path: Path) -> ast.Module:
    try:
        return ast.parse(source, filename=str(cli_path))
    except SyntaxError as exc:
        raise SystemExit(f"Cannot parse {cli_path}: {exc}") from exc


def extract_import_block(source: str, tree: ast.Module) -> str:
    lines = source.splitlines()
    end_line = 0

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            end_line = max(end_line, getattr(node, "end_lineno", node.lineno))
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        break

    if end_line == 0:
        return "from __future__ import annotations\n\nimport json\nfrom pathlib import Path\nfrom typing import Any\n\nimport typer\n"

    block = "\n".join(lines[:end_line]).strip()
    if "import typer" not in block:
        block += "\nimport typer"
    return block + "\n"


def function_map(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def segment_for_function(source: str, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    lines = source.splitlines()
    start = node.lineno
    if node.decorator_list:
        start = min(decorator.lineno for decorator in node.decorator_list)
    end = getattr(node, "end_lineno", node.lineno)
    return "\n".join(lines[start - 1 : end]).rstrip() + "\n"


def rewrite_decorators(segment: str) -> str:
    replacements = {
        "@app.command": "@router.command",
        "@runs_app.command": "@router.command",
        "@baselines_app.command": "@router.command",
    }
    for old, new in replacements.items():
        segment = segment.replace(old, new)
    return segment


def build_command_module(import_block: str, spec: ModuleSpec, fmap: dict[str, ast.AST], source: str) -> str:
    missing = [name for name in spec.functions if name not in fmap]
    if missing:
        raise SystemExit(
            f"Cannot split CLI; missing expected functions for {spec.filename}: {', '.join(missing)}"
        )

    body_segments = [
        rewrite_decorators(segment_for_function(source, fmap[name])) for name in spec.functions
    ]

    return (
        f"{import_block}\n"
        "# Generated by tools/split_cli_commands.py.\n"
        "# ruff: noqa: F401\n\n"
        f'router = typer.Typer(add_completion=False, help="{spec.help_text}")\n\n'
        + "\n\n".join(body_segments)
        + "\n"
    )


def build_cli_router() -> str:
    root_imports: list[str] = []
    add_lines: list[str] = []

    for spec in MODULES:
        stem = Path(spec.filename).stem
        alias = f"{stem}_router"
        root_imports.append(f"from app.commands.{stem} import router as {alias}")
        if spec.typer_name:
            add_lines.append(f'app.add_typer({alias}, name="{spec.typer_name}")')
        else:
            add_lines.append(f"app.add_typer({alias})")

    return (
        "from __future__ import annotations\n\n"
        "import typer\n\n"
        + "\n".join(root_imports)
        + "\n\n\n"
        "app = typer.Typer(\n"
        "    add_completion=False,\n"
        '    help="Convergence Monitor command-line interface.",\n'
        ")\n\n"
        + "\n".join(add_lines)
        + "\n\n\n"
        'if __name__ == "__main__":\n'
        "    app()\n"
    )


def write_if_changed(path: Path, content: str, apply: bool) -> bool:
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old == content:
        return False

    if not apply:
        diff = difflib.unified_diff(
            old.splitlines(),
            content.splitlines(),
            fromfile=str(path),
            tofile=f"{path} (generated)",
            lineterm="",
        )
        print("\n".join(diff))
        return True

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def backup_file(path: Path) -> Path:
    backup = path.with_suffix(path.suffix + ".pre-split.bak")
    index = 1
    while backup.exists():
        backup = path.with_suffix(path.suffix + f".pre-split.{index}.bak")
        index += 1
    shutil.copy2(path, backup)
    return backup


def split_cli(repo_dir: Path, apply: bool, allow_dirty: bool) -> int:
    ensure_clean_worktree(repo_dir, allow_dirty)

    cli_path = repo_dir / "app" / "cli.py"
    source = read_source(cli_path)
    tree = parse_tree(source, cli_path)
    import_block = extract_import_block(source, tree)
    fmap = function_map(tree)

    generated: dict[Path, str] = {}
    commands_dir = repo_dir / "app" / "commands"
    generated[commands_dir / "__init__.py"] = '"""Typer command modules."""\n'

    for spec in MODULES:
        generated[commands_dir / spec.filename] = build_command_module(
            import_block=import_block,
            spec=spec,
            fmap=fmap,
            source=source,
        )

    generated[cli_path] = build_cli_router()

    changed = False
    if apply:
        backup = backup_file(cli_path)
        print(f"backup: {backup.relative_to(repo_dir)}")

    for path, content in generated.items():
        changed = write_if_changed(path, content, apply=apply) or changed

    if not changed:
        print("No changes required.")
        return 0

    if apply:
        print("CLI split written.")
        print("Run: python -m compileall -q app && pytest -q && ruff check .")
    else:
        print("Dry-run complete. Re-run with --apply to write files.")

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-dir", type=Path, default=Path.cwd())
    parser.add_argument("--apply", action="store_true", help="Write generated files.")
    parser.add_argument("--dry-run", action="store_true", help="Show diffs only.")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow running with uncommitted changes.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.apply and args.dry_run:
        raise SystemExit("Use either --apply or --dry-run, not both.")
    return split_cli(
        repo_dir=args.repo_dir.resolve(),
        apply=args.apply,
        allow_dirty=args.allow_dirty,
    )


if __name__ == "__main__":
    raise SystemExit(main())
