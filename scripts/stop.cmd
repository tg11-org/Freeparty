@echo off
setlocal

cd /d "%~dp0.."

set "COMPOSE=docker compose"
docker compose version >nul 2>nul
if errorlevel 1 (
  docker-compose --version >nul 2>nul
  if errorlevel 1 (
    echo Neither docker compose nor docker-compose is available.
    pause
    exit /b 1
  )
  set "COMPOSE=docker-compose"
)

echo Stopping Freeparty services (preserves containers, volumes, and files)...
%COMPOSE% stop
if errorlevel 1 (
  echo Failed to stop services.
  pause
  exit /b 1
)

echo Services stopped.
pause
exit /b 0
