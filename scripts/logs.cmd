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

echo Showing live logs from Freeparty services (Ctrl+C to stop)...
echo.
%COMPOSE% logs --follow %*
pause
