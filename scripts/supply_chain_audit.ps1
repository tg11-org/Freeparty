param(
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

Write-Host "[1/3] Installing pip-audit"
& $PythonExe -m pip install --disable-pip-version-check pip-audit==2.7.3

Write-Host "[2/3] Running Python dependency audit"
& $PythonExe -m pip_audit -r requirements.txt

Write-Host "[3/3] Validating Docker Compose configuration"
docker compose config -q

Write-Host "Supply chain audit completed."
