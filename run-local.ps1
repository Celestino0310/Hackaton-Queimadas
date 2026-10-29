[CmdletBinding()]
param(
    [ValidateRange(1, 31)]
    [int]$Days = 1,

    [switch]$SkipIngest,

    [switch]$PrepareOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VirtualEnvironment = Join-Path $ProjectRoot ".venv"
$Python = Join-Path $VirtualEnvironment "Scripts\python.exe"

Set-Location $ProjectRoot

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Description,

        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    Write-Host "`n==> $Description" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path $Python)) {
    Invoke-Checked "Creating Python virtual environment" {
        python -m venv $VirtualEnvironment
    }
}

& $Python -c "import queimalerta, dash, pandas, plotly, sqlalchemy" 2>$null
if ($LASTEXITCODE -ne 0) {
    Invoke-Checked "Installing QueimAlerta and dependencies" {
        & $Python -m pip install --upgrade pip
        & $Python -m pip install -e ".[dev]"
    }
}

Invoke-Checked "Initializing local SQLite database" {
    & $Python -m queimalerta.cli init-db
}

if (-not $SkipIngest) {
    Invoke-Checked "Refreshing the latest $Days INPE daily file(s)" {
        & $Python -m queimalerta.cli ingest --days $Days
    }
}
else {
    Write-Host "`n==> Skipping INPE refresh; using locally stored data." -ForegroundColor Yellow
}

Invoke-Checked "Checking local data status" {
    & $Python -m queimalerta.cli status
}

if ($PrepareOnly) {
    Write-Host "`nLocal preparation completed successfully." -ForegroundColor Green
    Write-Host "Start the dashboard with: .\run-local.ps1 -SkipIngest"
    exit 0
}

$Port = if ($env:QUEIMALERTA_PORT) { $env:QUEIMALERTA_PORT } else { "8050" }
$DashboardUrl = "http://127.0.0.1:$Port"

Write-Host "`nQueimAlerta is starting at $DashboardUrl" -ForegroundColor Green
Write-Host "Keep this terminal open. Press Ctrl+C to stop the dashboard."

& $Python -m queimalerta.dashboard.app
