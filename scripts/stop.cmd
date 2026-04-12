@echo off
setlocal

cd /d "%~dp0.."

echo Stopping Freeparty services (preserves containers, volumes, and files)...
docker compose stop
if errorlevel 1 (
  echo Failed to stop services.
  pause
  exit /b 1
)

echo Services stopped.
pause
exit /b 0
