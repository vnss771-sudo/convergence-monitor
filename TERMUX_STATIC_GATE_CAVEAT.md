# Termux Static Gate Caveat

## Result

The 10-run live proof completed successfully at runtime level, but the Ruff/static gate did not pass in Termux.

## Evidence

`pip install -e ".[dev]"` successfully built the local `convergence-monitor` package, but failed while building Ruff.

Observed error:

```text
Failed to build ruff
failed-wheel-build-for-install
No module named ruff
