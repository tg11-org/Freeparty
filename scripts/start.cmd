@echo off
setlocal

cd /d "%~dp0.."

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example
)

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

echo Starting Freeparty services (non-destructive)...
%COMPOSE% up --detach --build
if errorlevel 1 (
  echo Failed to start services.
  pause
  exit /b 1
)

echo Services are starting.
echo App: http://localhost:8000
pause
exit /b 0
