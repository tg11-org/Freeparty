taskkill /f /im com.docker.backend.exe /t
taskkill /f /im "Docker Desktop.exe" /t
net stop com.docker.service
wsl --shutdown
pause