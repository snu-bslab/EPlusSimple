# ============================================================================
# EPlusSimple command dispatcher
# ============================================================================
# Location:
#   /scripts/dev/run.ps1
#
# Thin launcher:
#   /run.cmd
#
# Usage:
#   run
#   run help
#   run setup [args...]
#   run build-go [args...]
#   run build-docs [args...]
#   run regression-test
#   run release [args...]
#   run py [python-args...]
#   run python [python-args...]
#   run path\to\script.ps1 [args...]
#   run path\to\script.py [args...]
#
# Design:
#   - Common commands are exposed directly: setup, build-go, build-docs,
#     regression-test, and release.
#   - Runtime Python is exposed as: run py / run python.
#   - Stable Python scripts are registered in $DirectPythonScriptCommands.
#   - No EPlusSimple-specific Python environment variables are set here.
# ============================================================================

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RunArgs
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$RuntimeDir = Join-Path $RepoRoot 'runtime'
$PythonExe = Join-Path $RuntimeDir 'PythonV3-12-7\python.exe'
$PowerShellExe = (Get-Command powershell.exe -ErrorAction Stop).Source

# Direct PowerShell commands.
# Add stable project-level PowerShell tasks here.
$DirectPowerShellCommands = [ordered]@{
    'setup' = @{
        Path = 'scripts\setup\setup.ps1'
        Description = 'Prepare the local runtime directory.'
    }
    'build-go' = @{
        Path = 'scripts\dev\build-go.ps1'
        Description = 'Build Go executables.'
    }
    'build-docs' = @{
        Path = 'scripts\dev\build-docs.ps1'
        Description = 'Build documentation PDFs.'
    }
    'release' = @{
        Path = 'scripts\release\release.ps1'
        Description = 'Build release outputs.'
    }
}

# Direct Python-script commands.
# Keep this list conservative. Add only scripts that are stable enough to expose
# as repository-level commands.
$DirectPythonScriptCommands = [ordered]@{
    'regression-test' = @{
        Path = 'scripts\dev\regressiontest.py'
        Description = 'Run regression tests and update the report tables.'
    }
}

function Write-Usage {
    Write-Host ''
    Write-Host 'EPlusSimple command dispatcher'
    Write-Host ''
    Write-Host 'Usage:'
    Write-Host '  run'
    Write-Host '  run help'
    Write-Host '  run setup [args...]'
    Write-Host '  run build-go [args...]'
    Write-Host '  run build-docs [args...]'
    Write-Host '  run regression-test'
    Write-Host '  run release [args...]'
    Write-Host '  run py [python-args...]'
    Write-Host '  run python [python-args...]'
    Write-Host '  run path\to\script.ps1 [args...]'
    Write-Host '  run path\to\script.py [args...]'
    Write-Host ''
    Write-Host 'Common commands:'

    foreach ($name in $DirectPowerShellCommands.Keys) {
        $description = $DirectPowerShellCommands[$name].Description
        Write-Host ('  {0,-16} {1}' -f $name, $description)
    }

    foreach ($name in $DirectPythonScriptCommands.Keys) {
        $description = $DirectPythonScriptCommands[$name].Description
        Write-Host ('  {0,-16} {1}' -f $name, $description)
    }

    Write-Host ('  {0,-16} {1}' -f 'py', 'Run runtime\PythonV3-12-7\python.exe.')
    Write-Host ('  {0,-16} {1}' -f 'python', 'Alias of py.')
    Write-Host ''
    Write-Host 'Python import helper:'
    Write-Host '  run py -i'
    Write-Host '  run py --importsrc'
    Write-Host ''
    Write-Host 'Both open an interactive Python console after running:'
    Write-Host '  import epsimple; import idragon'
    Write-Host ''
    Write-Host 'To pass raw Python arguments without wrapper handling, use --:'
    Write-Host '  run py -- -i script.py'
    Write-Host ''
}

function Resolve-RepoPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return $Path
    }

    return (Join-Path $RepoRoot $Path)
}

function Assert-FileExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Message`n  $Path"
    }
}

function Enter-RepoPowerShell {
    Push-Location $RepoRoot
    try {
        & $PowerShellExe -NoProfile -ExecutionPolicy Bypass
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    if ($null -ne $exitCode) {
        exit $exitCode
    }

    exit 0
}

function Invoke-RepoPowerShellScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [string[]]$Arguments = @()
    )

    $fullPath = Resolve-RepoPath $Path

    Assert-FileExists `
        -Path $fullPath `
        -Message 'PowerShell script was not found.'

    Push-Location $RepoRoot

    try {
        $childArguments = @(
            '-NoProfile'
            '-ExecutionPolicy'
            'Bypass'
            '-File'
            $fullPath
        )

        $childArguments += @($Arguments)

        & $PowerShellExe @childArguments
        $exitCode = $LASTEXITCODE
    }
    catch {
        Write-Host '[ERROR] PowerShell script failed.'
        Write-Host "Script : $fullPath"
        Write-Host "Reason : $($_.Exception.Message)"
        exit 1
    }
    finally {
        Pop-Location
    }

    if ($null -eq $exitCode) {
        $exitCode = 0
    }

    exit $exitCode
}

function Invoke-RepoPythonScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [string[]]$Arguments = @()
    )

    Assert-FileExists -Path $PythonExe -Message 'Python runtime was not found. Run setup first: run setup'

    $fullPath = Resolve-RepoPath $Path
    Assert-FileExists -Path $fullPath -Message 'Python script was not found.'

    Push-Location $RepoRoot
    try {
        & $PythonExe $fullPath @Arguments
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    if ($null -ne $exitCode) {
        exit $exitCode
    }

    exit 0
}

function Invoke-PythonRuntime {
    param(
        [string[]]$Arguments = @()
    )

    Assert-FileExists -Path $PythonExe -Message 'Python runtime was not found. Run setup first: run setup'

    $importSrc = $false
    $rawMode = $false
    $passArgs = New-Object System.Collections.Generic.List[string]

    foreach ($arg in $Arguments) {
        if (-not $rawMode -and $arg -eq '--') {
            $rawMode = $true
            continue
        }

        if (-not $rawMode -and ($arg -eq '-i' -or $arg -eq '--importsrc')) {
            $importSrc = $true
            continue
        }

        [void]$passArgs.Add($arg)
    }

    Push-Location $RepoRoot
    try {
        if ($importSrc) {
            if ($passArgs.Count -gt 0) {
                throw 'run py -i and run py --importsrc open an import-ready interactive console. Use "run py -- <args>" for raw Python argument passthrough.'
            }

            & $PythonExe -i -c 'import epsimple; import idragon'
            $exitCode = $LASTEXITCODE
        } else {
            & $PythonExe @($passArgs.ToArray())
            $exitCode = $LASTEXITCODE
        }
    } finally {
        Pop-Location
    }

    if ($null -ne $exitCode) {
        exit $exitCode
    }

    exit 0
}

function Get-RestArgs {
    param([string[]]$Values)

    if ($null -eq $Values -or $Values.Count -le 1) {
        return @()
    }

    return @($Values[1..($Values.Count - 1)])
}

if ($null -eq $RunArgs -or $RunArgs.Count -eq 0) {
    Enter-RepoPowerShell
}

$command = $RunArgs[0]
$restArgs = @(Get-RestArgs -Values $RunArgs)

if ($command -in @('help', '-h', '--help', '/?')) {
    Write-Usage
    exit 0
}

if ($command -in @('py', 'python')) {
    Invoke-PythonRuntime -Arguments $restArgs
}

if ($DirectPowerShellCommands.Contains($command)) {
    Invoke-RepoPowerShellScript -Path $DirectPowerShellCommands[$command].Path -Arguments $restArgs
}

if ($DirectPythonScriptCommands.Contains($command)) {
    Invoke-RepoPythonScript -Path $DirectPythonScriptCommands[$command].Path -Arguments $restArgs
}

# Fallback: allow explicit script paths without adding direct commands first.
# Examples:
#   run scripts\setup\setup.ps1 -Force
#   run scripts\dev\some_tool.py --flag
$resolvedCommandPath = Resolve-RepoPath $command

if ($command -match '(?i)\.ps1$' -and (Test-Path -LiteralPath $resolvedCommandPath -PathType Leaf)) {
    Invoke-RepoPowerShellScript -Path $resolvedCommandPath -Arguments $restArgs
}

if ($command -match '(?i)\.py$' -and (Test-Path -LiteralPath $resolvedCommandPath -PathType Leaf)) {
    Invoke-RepoPythonScript -Path $resolvedCommandPath -Arguments $restArgs
}

Write-Host "[ERROR] Unknown command: $command"
Write-Usage
exit 1
