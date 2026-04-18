param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [string]$Database = "freeparty",
    [string]$DbUser = "freeparty",
    [switch]$DropAndRecreate
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -Path $BackupFile)) {
    throw "Backup file not found: $BackupFile"
}

Write-Host "Restoring from: $BackupFile"

if ($DropAndRecreate) {
    Write-Host "Dropping and recreating database: $Database"
    docker compose exec -T db psql -U $DbUser -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$Database' AND pid <> pg_backend_pid();"
    docker compose exec -T db psql -U $DbUser -d postgres -c "DROP DATABASE IF EXISTS $Database;"
    docker compose exec -T db psql -U $DbUser -d postgres -c "CREATE DATABASE $Database;"
}

Get-Content -Path $BackupFile | docker compose exec -T db psql -U $DbUser -d $Database

Write-Host "Restore completed for database: $Database"
