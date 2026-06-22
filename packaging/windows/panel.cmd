@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHONPATH=%ROOT%python"
python -m panel_core.cli %*
