@echo off
setlocal EnableExtensions

REM ==========================================================================
REM EPlusSimple developer entrypoint wrapper
REM ==========================================================================
REM Location:
REM   /run.cmd
REM
REM Usage:
REM   run
REM   run help
REM   run setup [args...]
REM   run build-go [args...]
REM   run build-docs [args...]
REM   run regression-test
REM   run release [args...]
REM   run py [python args...]
REM   run scripts\path\script.ps1 [args...]
REM   run scripts\path\script.py [args...]
REM ==========================================================================

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

set "DISPATCHER=%ROOT_DIR%\scripts\dev\run.ps1"

if not exist "%DISPATCHER%" (
    echo [ERROR] Dispatcher was not found:
    echo   %DISPATCHER%
    exit /b 1
)

where powershell.exe >nul 2>nul
if errorlevel 1 (
    echo [ERROR] powershell.exe was not found in PATH.
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%DISPATCHER%" %*
exit /b %ERRORLEVEL%
