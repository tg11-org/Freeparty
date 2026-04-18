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
$backupFile = Join-Path $OutputDir "drill-$timestamp.sql"
$drillDb = "${Database}_drill"

Write-Host "[1/4] Creating backup for drill: $backupFile"
docker compose exec -T db pg_dump -U $DbUser -d $Database --no-owner --no-privileges > $backupFile

if ((Get-Item $backupFile).Length -le 0) {
    throw "Backup drill failed: backup file is empty."
}

Write-Host "[2/4] Creating drill database: $drillDb"
docker compose exec -T db psql -U $DbUser -d postgres -c "DROP DATABASE IF EXISTS $drillDb;"
docker compose exec -T db psql -U $DbUser -d postgres -c "CREATE DATABASE $drillDb;"

Write-Host "[3/4] Restoring backup into drill database"
Get-Content -Path $backupFile | docker compose exec -T db psql -U $DbUser -d $drillDb

Write-Host "[4/4] Validating restored schema"
$tables = docker compose exec -T db psql -U $DbUser -d $drillDb -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"
$normalized = ($tables | Out-String).Trim()
if (-not $normalized -or [int]$normalized -le 0) {
    throw "Backup drill failed: restored database appears empty."
}

Write-Host "Backup drill passed. Restored public table count: $normalized"
Write-Host "Temporary drill database retained: $drillDb"
