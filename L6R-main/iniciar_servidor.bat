@echo off
chcp 65001 >nul
title GEOPORTAL CSN - Servidor & Proxy NASA FIRMS
echo =======================================================
echo   INICIANDO GEOPORTAL CSN (WEBGIS + PROXY NASA FIRMS)
echo =======================================================
echo.

cd /d "%~dp0"

echo Iniciando servidor backend na porta 8000...
echo Acesse no navegador: http://localhost:8000
echo.

:: Abre o navegador automaticamente apos 2 segundos
start "" cmd /c "timeout /t 2 >nul & start http://localhost:8000"

python server.py
pause
