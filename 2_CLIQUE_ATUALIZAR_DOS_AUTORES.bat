@echo off
title Atualizador Automatico dos Autores Oficiais
cd /d "%~dp0"
python update_from_upstream.py
echo.
pause
