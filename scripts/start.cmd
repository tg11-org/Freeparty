@echo off
setlocal

cd /d "%~dp0.."

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example
)

echo Starting Freeparty services (non-destructive)...
docker compose up -d --build
if errorlevel 1 (
  echo Failed to start services.
  exit /b 1
)

echo Services are starting.
echo App: http://localhost:8000
exit /b 0
