@echo off
uv run --directory "%~dp0backend" python -m app.cli.demo_carga %*
