$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Get-ComposeCommand {
    & docker compose version *> $null
    if ($LASTEXITCODE -eq 0) {
        return @("docker", "compose")
    }
    & docker-compose --version *> $null
    if ($LASTEXITCODE -eq 0) {
        return @("docker-compose")
    }
    throw "Neither 'docker compose' nor 'docker-compose' is available on PATH."
}

$composeCmd = Get-ComposeCommand

Write-Host "Stopping Freeparty services (preserves containers, volumes, and files)..."
if ($composeCmd.Length -gt 1) {
    & $composeCmd[0] $composeCmd[1] stop
}
else {
    & $composeCmd[0] stop
}
if ($LASTEXITCODE -ne 0) {
    throw "Compose stop failed with exit code $LASTEXITCODE"
}

Write-Host "Services stopped."
