#!/usr/bin/env pwsh
# Generate secure random secrets for a Freeparty .env file.
# Run: .\scripts\generate_secrets.ps1
# Optionally pipe straight into a new .env: .\scripts\generate_secrets.ps1 | Out-File -Encoding utf8 .env

function New-Secret {
    param([int]$Bytes = 48, [switch]$UrlSafe)
    $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $buffer = New-Object byte[] $Bytes
    $random.GetBytes($buffer)
    if ($UrlSafe) {
        # Hex — no special characters, safe in URLs and connection strings
        return ($buffer | ForEach-Object { $_.ToString("x2") }) -join ""
    }
    return [Convert]::ToBase64String($buffer)
}

$djangoSecret      = New-Secret -Bytes 48
$dbPassword        = New-Secret -Bytes 32 -UrlSafe   # hex — safe in DATABASE_URL
$federationSecret  = New-Secret -Bytes 48

Write-Host ""
Write-Host "# -----------------------------------------------------------------------"
Write-Host "# Freeparty generated secrets — $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
Write-Host "# Copy these into your .env file. Do not commit .env to version control."
Write-Host "# -----------------------------------------------------------------------"
Write-Host ""
Write-Host "SECRET_KEY=$djangoSecret"
Write-Host "POSTGRES_PASSWORD=$dbPassword"
Write-Host "FEDERATION_SHARED_SECRET=$federationSecret"
Write-Host ""
Write-Host "# Update DATABASE_URL to match POSTGRES_PASSWORD above:"
Write-Host "# DATABASE_URL=postgres://freeparty:$dbPassword@db:5432/freeparty"
Write-Host ""
