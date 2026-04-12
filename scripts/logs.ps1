Param(
    [string]$Service
)

Set-Location (Join-Path $PSScriptRoot "..")

$logArgs = @("compose", "logs", "-f")
if ($Service) {
    $logArgs += $Service
}

Write-Host "Showing live logs from Freeparty services (Ctrl+C to stop)..."
Write-Host ""
& docker @logArgs
