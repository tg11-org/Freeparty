$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "Stopping Freeparty services (preserves containers, volumes, and files)..."
& docker compose stop
if ($LASTEXITCODE -ne 0) {
    throw "docker compose stop failed with exit code $LASTEXITCODE"
}

Write-Host "Services stopped."
