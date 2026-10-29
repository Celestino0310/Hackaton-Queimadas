@echo off
setlocal EnableExtensions

cd /d "%~dp0"
set "PYTHON=.venv\Scripts\python.exe"
set "DAYS=1"
set "SKIP_INGEST=0"
set "PREPARE_ONLY=0"

:parse_args
if "%~1"=="" goto setup
if /I "%~1"=="--skip-ingest" (
    set "SKIP_INGEST=1"
    shift
    goto parse_args
)
if /I "%~1"=="--prepare-only" (
    set "PREPARE_ONLY=1"
    shift
    goto parse_args
)
if /I "%~1"=="--days" (
    if "%~2"=="" (
        echo Missing number after --days.
        exit /b 2
    )
    set "DAYS=%~2"
    shift
    shift
    goto parse_args
)
echo Unknown option: %~1
exit /b 2

:setup
if not exist "%PYTHON%" (
    echo.
    echo ==^> Creating Python virtual environment
    python -m venv .venv
    if errorlevel 1 goto failed
)

"%PYTHON%" -c "import queimalerta, dash, pandas, plotly, sqlalchemy" >nul 2>&1
if errorlevel 1 (
    echo.
    echo ==^> Installing QueimAlerta and dependencies
    "%PYTHON%" -m pip install -e ".[dev]"
    if errorlevel 1 goto failed
)

echo.
echo ==^> Initializing local SQLite database
"%PYTHON%" -m queimalerta.cli init-db
if errorlevel 1 goto failed

if "%SKIP_INGEST%"=="1" (
    echo.
    echo ==^> Skipping INPE refresh; using locally stored data.
) else (
    echo.
    echo ==^> Refreshing the latest %DAYS% INPE daily file(s)
    "%PYTHON%" -m queimalerta.cli ingest --days %DAYS%
    if errorlevel 1 goto failed
)

echo.
echo ==^> Checking local data status
"%PYTHON%" -m queimalerta.cli status
if errorlevel 1 goto failed

if "%PREPARE_ONLY%"=="1" (
    echo.
    echo Local preparation completed successfully.
    echo Start the dashboard with: .\run-local.cmd --skip-ingest
    exit /b 0
)

echo.
echo QueimAlerta is starting at http://127.0.0.1:8050
echo Keep this terminal open. Press Ctrl+C to stop the dashboard.
"%PYTHON%" -m queimalerta.dashboard.app
exit /b %ERRORLEVEL%

:failed
echo.
echo QueimAlerta local setup failed. Review the error above.
exit /b 1
