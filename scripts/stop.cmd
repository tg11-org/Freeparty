@echo off
setlocal

cd /d "%~dp0.."

echo Stopping Freeparty services (preserves containers, volumes, and files)...
docker compose stop
if errorlevel 1 (
  echo Failed to stop services.
  exit /b 1
)

echo Services stopped.
exit /b 0
