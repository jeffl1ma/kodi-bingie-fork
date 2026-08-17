@echo off
title Publicador Automatico do Repositorio Kodi
cd /d "%~dp0"
python generate_repo.py
echo.
pause
