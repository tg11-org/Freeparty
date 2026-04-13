Param(
    [switch]$NoBuild
)

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

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

$composeCmd = Get-ComposeCommand
$composeArgs = @("up", "--detach")
if (-not $NoBuild) {
    $composeArgs += "--build"
}

Write-Host "Starting Freeparty services (non-destructive)..."
$runner = Get-Command $composeCmd[0] -ErrorAction Stop
if ($composeCmd.Length -gt 1) {
    & $runner.Source @($composeCmd[1..($composeCmd.Length - 1)] + $composeArgs)
}
else {
    & $runner.Source @($composeArgs)
}
if ($LASTEXITCODE -ne 0) {
    throw "Compose up failed with exit code $LASTEXITCODE"
}

Write-Host "Services are starting."
Write-Host "App: http://localhost:8000"
