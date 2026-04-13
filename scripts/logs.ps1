Param(
    [string]$Service
)

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

$logArgs = @("logs", "--follow")
if ($Service) {
    $logArgs += $Service
}

Write-Host "Showing live logs from Freeparty services (Ctrl+C to stop)..."
Write-Host ""
if ($composeCmd.Length -gt 1) {
    & $composeCmd[0] $composeCmd[1] @logArgs
}
else {
    & $composeCmd[0] @logArgs
}
