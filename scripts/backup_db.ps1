param(
    [string]$OutputDir = "backups",
    [string]$Database = "freeparty",
    [string]$DbUser = "freeparty"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -Path $OutputDir)) {
    New-Item -Path $OutputDir -ItemType Directory | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupFile = Join-Path $OutputDir "freeparty-$timestamp.sql"

Write-Host "Creating backup: $backupFile"
docker compose exec -T db pg_dump -U $DbUser -d $Database --no-owner --no-privileges > $backupFile

if (-not (Test-Path -Path $backupFile)) {
    throw "Backup file was not created."
}

if ((Get-Item $backupFile).Length -le 0) {
    throw "Backup file is empty: $backupFile"
}

Write-Host "Backup completed: $backupFile"
