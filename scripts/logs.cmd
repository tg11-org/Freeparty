@echo off
setlocal

cd /d "%~dp0.."

echo Showing live logs from Freeparty services (Ctrl+C to stop)...
echo.
docker compose logs -f %*
pause
