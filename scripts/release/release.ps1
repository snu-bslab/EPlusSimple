# ============================================================================
# EPlusSimple release script
# Release script revision: separate-release-python-runtime-20260618
# ============================================================================
#
# Expected location:
#   scripts\release\release.ps1
#
# Intended caller:
#   runscript.bat release ...
#
# This script creates:
#   dist\EPlusSimple_V<Version>\
#   dist\EPlusSimple_V<Version>.zip
#
# Notes:
# - There is no target option.
# - The standard package is the only release package.
# - Release Python is created fresh under the release directory.
# - Release runtime packages are installed from scripts\release\requirements-release.txt.
# - EnergyPlus release pruning is driven by scripts\release\energyplus-release-prune.txt.
# - Regression doc updates run with the repository runtime prepared by setup.
# - src is not installed as a Python package. It is copied as source files.
# - Detailed release log is written to logs\release.log.
# ============================================================================

[CmdletBinding()]
param(
    # Release version without leading V.
    [string]$Version = '0.6.6',

    # Skip regression only when iterating on packaging logic.
    [switch]$SkipRegressionTest,

    # Skip documentation build when latexmk is not available or when testing
    # packaging-only changes.
    [switch]$SkipDocs,

    # Keep the existing dist directory.
    # Useful for debugging, but not recommended for normal releases.
    [switch]$NoClean
)

Set-StrictMode -Version 1.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# Force TLS 1.2 for older Windows PowerShell environments.
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch {
    # Ignore if unavailable.
}

# ----------------------------------------------------------------------------
# Repository root
# ----------------------------------------------------------------------------

function Resolve-RepoRoot {
    $scriptDir = Split-Path -Parent $MyInvocation.ScriptName

    if ([string]::IsNullOrWhiteSpace($scriptDir)) {
        $scriptDir = Split-Path -Parent $PSCommandPath
    }

    if ([string]::IsNullOrWhiteSpace($scriptDir)) {
        throw 'Cannot resolve script directory. Run this script from a saved .ps1 file.'
    }

    $candidates = @(
        $scriptDir,
        (Join-Path $scriptDir '..'),
        (Join-Path $scriptDir '..\..')
    )

    foreach ($candidate in $candidates) {
        $resolved = $null

        try {
            $resolved = (Resolve-Path -LiteralPath $candidate -ErrorAction Stop).Path
        } catch {
            continue
        }

        if (
            (Test-Path -LiteralPath (Join-Path $resolved 'src') -PathType Container) -and
            (Test-Path -LiteralPath (Join-Path $resolved 'runtime') -PathType Container) -and
            (Test-Path -LiteralPath (Join-Path $resolved 'scripts') -PathType Container)
        ) {
            return $resolved
        }
    }

    throw "Cannot resolve repository root from script directory: $scriptDir"
}

$RepoRoot = Resolve-RepoRoot
Set-Location $RepoRoot

# ----------------------------------------------------------------------------
# Path configuration
# ----------------------------------------------------------------------------

$ProjectName = 'EPlusSimple'
$VersionString = "V$Version"
$ReleaseName = "$ProjectName`_$VersionString"

$DistDir = Join-Path $RepoRoot 'dist'
$ReleaseDir = Join-Path $DistDir $ReleaseName
$OutputZip = Join-Path $DistDir "$ReleaseName.zip"

$LogsDir = Join-Path $RepoRoot 'logs'
$ReleaseLog = Join-Path $LogsDir 'release.log'
$TempLogDir = Join-Path $LogsDir '_tmp_release'

$RuntimeDir = Join-Path $RepoRoot 'runtime'
$DownloadDir = Join-Path $RuntimeDir 'downloads'

$PythonRuntimeName = 'PythonV3-12-7'
$EnergyPlusRuntimeName = 'EnergyPlusV24-2-0'
$WeatherRuntimeName = 'Weather'

$PythonVersionShort = '312'
$PythonVersionFull = '3.12.7'
$PythonPthFileName = "python$PythonVersionShort._pth"
$PythonZipFileName = "python-$PythonVersionFull-embed-amd64.zip"
$PythonZipPath = Join-Path $DownloadDir $PythonZipFileName
$PythonDownloadUrl = "https://www.python.org/ftp/python/$PythonVersionFull/$PythonZipFileName"

$GetPipUrl = 'https://bootstrap.pypa.io/get-pip.py'
$GetPipPath = Join-Path $DownloadDir 'get-pip.py'

$RepoPythonDir = Join-Path $RuntimeDir $PythonRuntimeName
$RepoPythonExe = Join-Path $RepoPythonDir 'python.exe'

$ReleaseRuntimeDir = Join-Path $ReleaseDir 'runtime'
$ReleasePythonDir = Join-Path $ReleaseRuntimeDir $PythonRuntimeName
$ReleasePythonExe = Join-Path $ReleasePythonDir 'python.exe'
$ReleasePythonPthFile = Join-Path $ReleasePythonDir $PythonPthFileName

$EnergyPlusDir = Join-Path $RuntimeDir $EnergyPlusRuntimeName
$EnergyPlusExe = Join-Path $EnergyPlusDir 'energyplus.exe'
$ReleaseEnergyPlusDir = Join-Path $ReleaseRuntimeDir $EnergyPlusRuntimeName
$ReleaseEnergyPlusExe = Join-Path $ReleaseEnergyPlusDir 'energyplus.exe'

$WeatherRootDir = Join-Path $RuntimeDir $WeatherRuntimeName
$WeatherTmyDir = Join-Path $WeatherRootDir 'TMY'
$ReleaseWeatherRootDir = Join-Path $ReleaseRuntimeDir $WeatherRuntimeName
$ReleaseWeatherTmyDir = Join-Path $ReleaseWeatherRootDir 'TMY'

$ReleaseConfigDir = Join-Path $RepoRoot 'scripts\release'
$ReleaseRequirementsPath = Join-Path $ReleaseConfigDir 'requirements-release.txt'
$EnergyPlusPruneSpecPath = Join-Path $ReleaseConfigDir 'energyplus-release-prune.txt'

$BuildGoScript = Join-Path $RepoRoot 'scripts\dev\build-go.ps1'
$EPlusSimpleCLIExe = Join-Path $RepoRoot 'EPlusSimpleCLI.exe'
$EPlusSimpleLauncherExe = Join-Path $RepoRoot 'EPlusSimpleLauncher.exe'

$ExamplesDir = Join-Path $RepoRoot 'examples'
$DocsDir = Join-Path $RepoRoot 'docs'
$SrcDir = Join-Path $RepoRoot 'src'
$ReleaseSrcDir = Join-Path $ReleaseDir 'src'

$RegressionTestScript = Join-Path $RepoRoot 'scripts\dev\regressiontest.py'
$RegressionLogLegacy = Join-Path $RepoRoot 'regtest.log'

$script:CurrentStep = 'initializing release script'
$script:LogStream = $null
$script:LogWriter = $null

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------

function New-DirectoryIfMissing {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
    }
}

function Open-ReleaseLog {
    New-DirectoryIfMissing $LogsDir

    if ($null -ne $script:LogWriter) {
        Close-ReleaseLog
    }

    $script:LogStream = [System.IO.FileStream]::new(
        $ReleaseLog,
        [System.IO.FileMode]::Create,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::ReadWrite
    )

    $encoding = [System.Text.UTF8Encoding]::new($false)
    $script:LogWriter = [System.IO.StreamWriter]::new($script:LogStream, $encoding)
    $script:LogWriter.AutoFlush = $true

    Write-LogRaw '============================================================================'
    Write-LogRaw ' EPlusSimple release log'
    Write-LogRaw '============================================================================'
    Write-LogRaw "Started      : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    Write-LogRaw "Repository   : $RepoRoot"
    Write-LogRaw "Version      : $VersionString"
    Write-LogRaw "Release dir  : $ReleaseDir"
    Write-LogRaw "Release zip  : $OutputZip"
    Write-LogRaw '============================================================================'
    Write-LogRaw ''
}

function Close-ReleaseLog {
    if ($null -ne $script:LogWriter) {
        try {
            $script:LogWriter.Flush()
            $script:LogWriter.Close()
        } catch {
            # Avoid masking the original release error.
        }

        $script:LogWriter = $null
    }

    if ($null -ne $script:LogStream) {
        try {
            $script:LogStream.Close()
        } catch {
            # Avoid masking the original release error.
        }

        $script:LogStream = $null
    }
}

function Write-LogRaw {
    param([string]$Message)

    if ($null -eq $script:LogWriter) {
        return
    }

    $script:LogWriter.WriteLine($Message)
}

function Write-Log {
    param([string]$Message)

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Write-LogRaw "[$timestamp] $Message"
}

function Write-LogBlock {
    param(
        [string]$Title,
        [string[]]$Lines = @()
    )

    Write-LogRaw ''
    Write-LogRaw "===== $Title ====="

    foreach ($line in @($Lines)) {
        if ($null -eq $line) {
            Write-LogRaw ''
        } else {
            Write-LogRaw ([string]$line)
        }
    }
}

function Write-Step {
    param([string]$Message)

    $script:CurrentStep = $Message
    Write-Host $Message
    Write-Log $Message
}

function Write-ProgressLine {
    param([string]$Message)

    Write-Host " ...$Message"
    Write-Log " ...$Message"
}

# ----------------------------------------------------------------------------
# Generic helpers
# ----------------------------------------------------------------------------

function Remove-DirectoryIfExists {
    param([string]$Path)

    if (Test-Path -LiteralPath $Path -PathType Container) {
        Write-Log "Removing directory: $Path"
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Remove-FileIfExists {
    param([string]$Path)

    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        Write-Log "Removing file: $Path"
        Remove-Item -LiteralPath $Path -Force
    }
}

function Test-FileExists {
    param(
        [string]$Path,
        [string]$Message
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Message`nMissing file: $Path"
    }

    Write-Log "Validated file: $Path"
}

function Test-DirectoryExists {
    param(
        [string]$Path,
        [string]$Message
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Message`nMissing directory: $Path"
    }

    Write-Log "Validated directory: $Path"
}

function Invoke-LoggedCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = $RepoRoot,
        [string]$Description = 'external command'
    )

    Write-ProgressLine $Description

    $commandLine = "$FilePath " + (($Arguments | ForEach-Object {
        if ($_ -match '[\s"]') {
            '"' + ($_.Replace('"', '\"')) + '"'
        } else {
            $_
        }
    }) -join ' ')

    Write-LogBlock -Title "COMMAND: $Description" -Lines @(
        "Working directory: $WorkingDirectory",
        "Command          : $commandLine"
    )

    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()

    Push-Location $WorkingDirectory

    try {
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'

        try {
            & $FilePath @Arguments > $stdoutPath 2> $stderrPath
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }

        $exitCode = $LASTEXITCODE

        if (Test-Path -LiteralPath $stdoutPath -PathType Leaf) {
            foreach ($line in @(Get-Content -LiteralPath $stdoutPath -ErrorAction SilentlyContinue)) {
                Write-Log ([string]$line)
            }
        }

        if (Test-Path -LiteralPath $stderrPath -PathType Leaf) {
            foreach ($line in @(Get-Content -LiteralPath $stderrPath -ErrorAction SilentlyContinue)) {
                Write-Log "[stderr] $line"
            }
        }

        if ($null -eq $exitCode) {
            $exitCode = 0
        }

        Write-Log "Exit code: $exitCode"

        if ($exitCode -ne 0) {
            throw "$Description failed. Exit code: $exitCode. See log: $ReleaseLog"
        }
    } finally {
        Pop-Location
        Remove-FileIfExists $stdoutPath
        Remove-FileIfExists $stderrPath
    }
}

function Copy-Directory {
    param(
        [string]$Source,
        [string]$Destination
    )

    Test-DirectoryExists -Path $Source -Message 'Cannot copy directory because the source directory was not found.'
    Remove-DirectoryIfExists $Destination

    $parent = Split-Path -Parent $Destination
    New-DirectoryIfMissing $parent

    Write-Log "Copy directory: $Source -> $Destination"
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
}

function Copy-File {
    param(
        [string]$Source,
        [string]$Destination
    )

    Test-FileExists -Path $Source -Message 'Cannot copy file because the source file was not found.'

    $parent = Split-Path -Parent $Destination
    New-DirectoryIfMissing $parent

    Write-Log "Copy file: $Source -> $Destination"
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

function Add-UniqueLine {
    param(
        [string]$Path,
        [string]$Line
    )

    Test-FileExists -Path $Path -Message 'Cannot update file because it was not found.'

    $lines = Get-Content -LiteralPath $Path -ErrorAction Stop

    if ($lines -contains $Line) {
        Write-Log "Already present in file: $Path :: $Line"
    } else {
        [System.IO.File]::AppendAllText(
            $Path,
            "`r`n$Line",
            [System.Text.UTF8Encoding]::new($false)
        )
        Write-Log "Added to file: $Path :: $Line"
    }
}

function Save-RemoteFileIfMissing {
    param(
        [string]$Url,
        [string]$Destination
    )

    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        Write-ProgressLine "Using cached file: $Destination"
        return
    }

    $parent = Split-Path -Parent $Destination
    New-DirectoryIfMissing $parent

    Write-ProgressLine "Downloading: $Url"
    Write-Log "Download target: $Destination"

    try {
        Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
    } catch {
        throw "Download failed. URL: $Url. Error: $($_.Exception.Message)"
    }

    Test-FileExists -Path $Destination -Message 'Downloaded file was not created.'
}

function Set-ReleasePythonInstallEnvironment {
    $env:PYTHONNOUSERSITE = '1'
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
}

# ----------------------------------------------------------------------------
# Release steps
# ----------------------------------------------------------------------------

function Test-ReleaseInputs {
    Write-Step '[0/7] Validating release inputs...'

    Test-DirectoryExists -Path $SrcDir -Message 'src directory was not found.'
    Test-DirectoryExists -Path $ExamplesDir -Message 'examples directory was not found.'
    Test-DirectoryExists -Path $DocsDir -Message 'docs directory was not found.'

    Test-DirectoryExists -Path (Join-Path $SrcDir 'epsimple') -Message 'src\epsimple was not found.'
    Test-DirectoryExists -Path (Join-Path $SrcDir 'idragon') -Message 'src\idragon was not found.'

    Test-FileExists -Path $ReleaseRequirementsPath -Message 'Release requirements file was not found.'
    Test-FileExists -Path $EnergyPlusPruneSpecPath -Message 'EnergyPlus release prune specification was not found.'
    Test-FileExists -Path $RepoPythonExe -Message 'Repository Python runtime was not found. Run "runscript setup" before release.'
    Test-FileExists -Path $EnergyPlusExe -Message 'EnergyPlus runtime was not found. Run "runscript setup" before release.'
    Test-DirectoryExists -Path $WeatherTmyDir -Message 'Korean TMY weather data was not found. Run "runscript setup" before release.'

    Test-FileExists -Path $BuildGoScript -Message 'Go build script was not found.'
    Test-DirectoryExists -Path (Join-Path $RepoRoot 'tools\go') -Message 'Go source directory was not found.'
    Test-FileExists -Path (Join-Path $RepoRoot 'tools\go\go.mod') -Message 'Go module file was not found.'

    if (-not $SkipRegressionTest) {
        Test-FileExists -Path $RegressionTestScript -Message 'Regression test script was not found.'
    }

    Write-LogBlock -Title 'RELEASE INPUTS' -Lines @(
        "Repository           : $RepoRoot",
        "Version              : $VersionString",
        "Release requirements : $ReleaseRequirementsPath",
        "EnergyPlus prune spec: $EnergyPlusPruneSpecPath",
        "Repository Python    : $RepoPythonExe",
        "Release Python       : $ReleasePythonExe",
        "EnergyPlus source    : $EnergyPlusExe",
        "Weather TMY source   : $WeatherTmyDir",
        "Go build             : $BuildGoScript",
        "Skip docs            : $SkipDocs",
        "Skip regtest         : $SkipRegressionTest",
        "No clean             : $NoClean"
    )
}

function Initialize-Dist {
    Write-Step '[1/7] Preparing dist directory...'

    if (-not $NoClean) {
        Remove-DirectoryIfExists $DistDir
    }

    New-DirectoryIfMissing $ReleaseDir
    New-DirectoryIfMissing $ReleaseRuntimeDir
    Write-Log "Release directory prepared: $ReleaseDir"
}

function Install-ReleasePythonRuntime {
    Write-Step '[2/7] Creating release Python runtime...'

    Set-ReleasePythonInstallEnvironment

    Remove-DirectoryIfExists $ReleasePythonDir
    New-DirectoryIfMissing $ReleasePythonDir

    Save-RemoteFileIfMissing -Url $PythonDownloadUrl -Destination $PythonZipPath

    Write-ProgressLine "Extracting Python embeddable runtime to: $ReleasePythonDir"
    Expand-Archive -LiteralPath $PythonZipPath -DestinationPath $ReleasePythonDir -Force

    Test-FileExists -Path $ReleasePythonExe -Message 'Release python.exe was not found after extraction.'
    Test-FileExists -Path $ReleasePythonPthFile -Message 'Release Python ._pth file was not found after extraction.'

    Add-UniqueLine -Path $ReleasePythonPthFile -Line 'Lib\site-packages'
    Add-UniqueLine -Path $ReleasePythonPthFile -Line '..\..\src'
    Add-UniqueLine -Path $ReleasePythonPthFile -Line 'import site'

    Save-RemoteFileIfMissing -Url $GetPipUrl -Destination $GetPipPath

    Invoke-LoggedCommand `
        -FilePath $ReleasePythonExe `
        -Arguments @($GetPipPath) `
        -WorkingDirectory $RepoRoot `
        -Description 'pip bootstrap for release Python'

    Invoke-LoggedCommand `
        -FilePath $ReleasePythonExe `
        -Arguments @(
            '-m',
            'pip',
            'install',
            '--upgrade',
            'setuptools',
            'wheel'
        ) `
        -WorkingDirectory $RepoRoot `
        -Description 'release Python packaging bootstrap'

    Invoke-LoggedCommand `
        -FilePath $ReleasePythonExe `
        -Arguments @(
            '-m',
            'pip',
            'install',
            '-r',
            $ReleaseRequirementsPath
        ) `
        -WorkingDirectory $RepoRoot `
        -Description 'release Python requirements installation'

    Invoke-LoggedCommand `
        -FilePath $ReleasePythonExe `
        -Arguments @('--version') `
        -WorkingDirectory $RepoRoot `
        -Description 'release Python version check'

    Write-Log 'Release Python runtime created.'
}

function Invoke-GoLauncherBuild {
    Write-Log 'Building Go executables.'

    Invoke-LoggedCommand `
        -FilePath 'powershell.exe' `
        -Arguments @(
            '-NoProfile',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            $BuildGoScript,
            '-RepoRoot',
            $RepoRoot
        ) `
        -WorkingDirectory $RepoRoot `
        -Description 'Go executable build'

    Test-FileExists -Path $EPlusSimpleCLIExe -Message 'EPlusSimpleCLI.exe was not generated by build-go.ps1.'
    Test-FileExists -Path $EPlusSimpleLauncherExe -Message 'EPlusSimpleLauncher.exe was not generated by build-go.ps1.'

    Write-Log 'Go executables built.'
}

function Convert-EnergyPlusSpecPath {
    param([string]$Path)

    $normalized = $Path.Trim()
    $normalized = $normalized -replace '/', '\'
    $normalized = $normalized.TrimStart('.', '\', '/')
    $normalized = $normalized.TrimEnd('\', '/')

    return $normalized
}

function Read-EnergyPlusPruneSpec {
    param([string]$Path)

    Test-FileExists -Path $Path -Message 'EnergyPlus release prune specification was not found.'

    $required = New-Object System.Collections.Generic.List[string]
    $prune = New-Object System.Collections.Generic.List[string]

    foreach ($rawLine in @(Get-Content -LiteralPath $Path -ErrorAction Stop)) {
        $line = ([string]$rawLine).Trim()

        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith('#')) {
            continue
        }

        $commentIndex = $line.IndexOf('#')

        if ($commentIndex -ge 0) {
            $line = $line.Substring(0, $commentIndex).Trim()
        }

        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $parts = $line -split '\s+', 2
        $command = $parts[0].ToLowerInvariant()
        $value = $null

        if ($parts.Count -eq 2) {
            $value = $parts[1].Trim()
        }

        switch ($command) {
            'require' {
                if ([string]::IsNullOrWhiteSpace($value)) {
                    throw "Invalid EnergyPlus prune spec line. Missing require path: $rawLine"
                }

                $required.Add((Convert-EnergyPlusSpecPath $value))
            }
            'prune' {
                if ([string]::IsNullOrWhiteSpace($value)) {
                    throw "Invalid EnergyPlus prune spec line. Missing prune path: $rawLine"
                }

                $prune.Add((Convert-EnergyPlusSpecPath $value))
            }
            default {
                $prune.Add((Convert-EnergyPlusSpecPath $line))
            }
        }
    }

    return [pscustomobject]@{
        Required = @($required)
        Prune    = @($prune)
    }
}

function Test-PathUnderDirectory {
    param(
        [string]$Parent,
        [string]$Child
    )

    $resolvedParent = (Resolve-Path -LiteralPath $Parent -ErrorAction Stop).Path.TrimEnd('\')
    $resolvedChild = (Resolve-Path -LiteralPath $Child -ErrorAction Stop).Path

    return $resolvedChild.StartsWith($resolvedParent + '\', [System.StringComparison]::OrdinalIgnoreCase)
}

function Remove-EnergyPlusPruneEntry {
    param(
        [string]$TargetEnergyPlusDir,
        [string]$Pattern
    )

    if ([string]::IsNullOrWhiteSpace($Pattern)) {
        return
    }

    $hasWildcard = ($Pattern.IndexOfAny([char[]]'*?[]') -ge 0)

    if ($hasWildcard) {
        $globPath = Join-Path $TargetEnergyPlusDir $Pattern
        $matches = @(Get-ChildItem -Path $globPath -Force -ErrorAction SilentlyContinue)

        if ($matches.Count -eq 0) {
            Write-Log "EnergyPlus prune pattern not found, skipped: $Pattern"
            return
        }

        foreach ($match in $matches) {
            if (-not (Test-PathUnderDirectory -Parent $TargetEnergyPlusDir -Child $match.FullName)) {
                throw "Refusing to prune outside EnergyPlus directory: $($match.FullName)"
            }

            if ($match.PSIsContainer) {
                Remove-DirectoryIfExists $match.FullName
            } else {
                Remove-FileIfExists $match.FullName
            }

            Write-Log "Pruned EnergyPlus path from pattern '$Pattern': $($match.FullName)"
        }

        return
    }

    $target = Join-Path $TargetEnergyPlusDir $Pattern

    if (-not (Test-Path -LiteralPath $target)) {
        Write-Log "EnergyPlus prune path not found, skipped: $Pattern"
        return
    }

    if (-not (Test-PathUnderDirectory -Parent $TargetEnergyPlusDir -Child $target)) {
        throw "Refusing to prune outside EnergyPlus directory: $target"
    }

    if (Test-Path -LiteralPath $target -PathType Container) {
        Remove-DirectoryIfExists $target
    } elseif (Test-Path -LiteralPath $target -PathType Leaf) {
        Remove-FileIfExists $target
    }

    Write-Log "Pruned EnergyPlus path: $Pattern"
}

function Test-EnergyPlusRequiredEntries {
    param(
        [string]$TargetEnergyPlusDir,
        [string[]]$RequiredEntries
    )

    foreach ($entry in @($RequiredEntries)) {
        $target = Join-Path $TargetEnergyPlusDir $entry

        if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
            throw "Required EnergyPlus release file is missing after pruning: $entry"
        }

        Write-Log "Validated required EnergyPlus release file: $entry"
    }
}

function Remove-EnergyPlusReleaseExtras {
    param([string]$TargetEnergyPlusDir)

    Test-DirectoryExists -Path $TargetEnergyPlusDir -Message 'Release EnergyPlus runtime was not found.'

    $spec = Read-EnergyPlusPruneSpec -Path $EnergyPlusPruneSpecPath

    Write-LogBlock -Title 'ENERGYPLUS RELEASE PRUNE SPEC' -Lines @(
        "Spec file       : $EnergyPlusPruneSpecPath",
        "Required entries: $($spec.Required.Count)",
        "Prune entries   : $($spec.Prune.Count)"
    )

    foreach ($pattern in @($spec.Prune)) {
        Remove-EnergyPlusPruneEntry -TargetEnergyPlusDir $TargetEnergyPlusDir -Pattern $pattern
    }

    Test-EnergyPlusRequiredEntries -TargetEnergyPlusDir $TargetEnergyPlusDir -RequiredEntries $spec.Required
}

function Copy-RuntimeAndRootFiles {
    Write-Step '[3/7] Copying non-Python runtime and root files...'

    New-DirectoryIfMissing $ReleaseRuntimeDir

    Copy-Directory -Source $EnergyPlusDir -Destination $ReleaseEnergyPlusDir
    Remove-EnergyPlusReleaseExtras -TargetEnergyPlusDir $ReleaseEnergyPlusDir

    New-DirectoryIfMissing $ReleaseWeatherRootDir
    Copy-Directory -Source $WeatherTmyDir -Destination $ReleaseWeatherTmyDir

    Copy-Directory -Source $ExamplesDir -Destination (Join-Path $ReleaseDir 'examples')

    Invoke-GoLauncherBuild

    Copy-File -Source $EPlusSimpleCLIExe -Destination (Join-Path $ReleaseDir 'EPlusSimpleCLI.exe')
    Copy-File -Source $EPlusSimpleLauncherExe -Destination (Join-Path $ReleaseDir 'EPlusSimpleLauncher.exe')

    Write-Log 'Non-Python runtime, weather data, examples, and root executables copied.'
}

function Copy-SourceFiles {
    Write-Step '[4/7] Copying source files...'

    New-DirectoryIfMissing $ReleaseSrcDir

    Copy-Directory -Source (Join-Path $SrcDir 'epsimple') -Destination (Join-Path $ReleaseSrcDir 'epsimple')
    Copy-Directory -Source (Join-Path $SrcDir 'idragon') -Destination (Join-Path $ReleaseSrcDir 'idragon')

    Write-Log 'Source files copied.'
}

function Set-ReleaseEnvironment {
    $env:EPSIMPLE_RUNTIME_DIR = $ReleaseRuntimeDir
    $env:IDRAGON_RUNTIME_DIR = $ReleaseRuntimeDir
    $env:IDRAGON_ENERGYPLUS_DIR = $ReleaseEnergyPlusDir
    $env:ENERGYPLUS_DIR = $ReleaseEnergyPlusDir
    $env:ENERGYPLUS_EXE = $ReleaseEnergyPlusExe
    $env:EPSIMPLE_WEATHER_DIR = $ReleaseWeatherRootDir
    $env:EPSIMPLE_TMY_DIR = $ReleaseWeatherTmyDir
    $env:PYTHONNOUSERSITE = '1'
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    $env:PATH = "$ReleaseEnergyPlusDir;$env:PATH"

    Write-LogBlock -Title 'RELEASE ENVIRONMENT' -Lines @(
        "EPSIMPLE_RUNTIME_DIR    = $env:EPSIMPLE_RUNTIME_DIR",
        "IDRAGON_RUNTIME_DIR     = $env:IDRAGON_RUNTIME_DIR",
        "IDRAGON_ENERGYPLUS_DIR  = $env:IDRAGON_ENERGYPLUS_DIR",
        "ENERGYPLUS_DIR          = $env:ENERGYPLUS_DIR",
        "ENERGYPLUS_EXE          = $env:ENERGYPLUS_EXE",
        "EPSIMPLE_WEATHER_DIR    = $env:EPSIMPLE_WEATHER_DIR",
        "EPSIMPLE_TMY_DIR        = $env:EPSIMPLE_TMY_DIR",
        "PYTHONNOUSERSITE        = $env:PYTHONNOUSERSITE",
        "PATH head               = $($env:PATH.Split(';')[0])"
    )
}

function Set-RepositoryRuntimeEnvironment {
    $env:EPSIMPLE_RUNTIME_DIR = $RuntimeDir
    $env:IDRAGON_RUNTIME_DIR = $RuntimeDir
    $env:IDRAGON_ENERGYPLUS_DIR = $EnergyPlusDir
    $env:ENERGYPLUS_DIR = $EnergyPlusDir
    $env:ENERGYPLUS_EXE = $EnergyPlusExe
    $env:EPSIMPLE_WEATHER_DIR = $WeatherRootDir
    $env:EPSIMPLE_TMY_DIR = $WeatherTmyDir
    $env:PYTHONNOUSERSITE = '1'
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    $env:PATH = "$EnergyPlusDir;$env:PATH"

    Write-LogBlock -Title 'REPOSITORY RUNTIME ENVIRONMENT' -Lines @(
        "EPSIMPLE_RUNTIME_DIR    = $env:EPSIMPLE_RUNTIME_DIR",
        "IDRAGON_RUNTIME_DIR     = $env:IDRAGON_RUNTIME_DIR",
        "IDRAGON_ENERGYPLUS_DIR  = $env:IDRAGON_ENERGYPLUS_DIR",
        "ENERGYPLUS_DIR          = $env:ENERGYPLUS_DIR",
        "ENERGYPLUS_EXE          = $env:ENERGYPLUS_EXE",
        "EPSIMPLE_WEATHER_DIR    = $env:EPSIMPLE_WEATHER_DIR",
        "EPSIMPLE_TMY_DIR        = $env:EPSIMPLE_TMY_DIR",
        "PYTHONNOUSERSITE        = $env:PYTHONNOUSERSITE",
        "PATH head               = $($env:PATH.Split(';')[0])"
    )
}

function Invoke-ReleaseRuntimeSmokeTest {
    Write-ProgressLine 'Checking release Python runtime imports'

    Set-ReleaseEnvironment

    Invoke-LoggedCommand `
        -FilePath $ReleasePythonExe `
        -Arguments @(
            '-s',
            '-c',
            'import epsimple, idragon, pandas, numpy, tqdm, openpyxl; print(epsimple.__version__); print(idragon.__version__)'
        ) `
        -WorkingDirectory $ReleaseDir `
        -Description 'release runtime import check'
}

function Invoke-RegressionTest {
    if ($SkipRegressionTest) {
        Write-Step '[5/7] Skipping regression test.'
        return
    }

    Write-Step '[5/7] Running regression test with repository Python...'

    Set-RepositoryRuntimeEnvironment
    Remove-FileIfExists $RegressionLogLegacy

    Invoke-LoggedCommand `
        -FilePath $RepoPythonExe `
        -Arguments @('--version') `
        -WorkingDirectory $RepoRoot `
        -Description 'repository Python version check before regression'

    Invoke-LoggedCommand `
        -FilePath $EnergyPlusExe `
        -Arguments @('--version') `
        -WorkingDirectory $RepoRoot `
        -Description 'repository EnergyPlus version check'

    Invoke-LoggedCommand `
        -FilePath $RepoPythonExe `
        -Arguments @($RegressionTestScript) `
        -WorkingDirectory $RepoRoot `
        -Description 'Regression test using repository runtime'

    if (Test-Path -LiteralPath $RegressionLogLegacy -PathType Leaf) {
        $regLines = Get-Content -LiteralPath $RegressionLogLegacy -ErrorAction SilentlyContinue
        Write-LogBlock -Title 'REGRESSION TEST LOG FILE: regtest.log' -Lines @($regLines)
        Remove-FileIfExists $RegressionLogLegacy
    }

    Write-Log 'Regression test passed.'
}

function Write-ReleaseInfo {
    $today = Get-Date -Format 'yyyy.MM.dd.'
    $releaseInfoPath = Join-Path $DocsDir 'releaseinfo.tex'

    @"
\newcommand{\releaseversion}{$VersionString}
\newcommand{\releasedate}{$today}
"@ | Set-Content -LiteralPath $releaseInfoPath -Encoding UTF8

    Write-Log "Updated release info: $releaseInfoPath"
}

function Invoke-DocBuild {
    param(
        [string]$SourceName,
        [string]$DisplayName
    )

    $DocsBuildDir = Join-Path $DistDir 'docs'
    $ReleaseDocsDir = Join-Path $ReleaseDir 'docs'

    New-DirectoryIfMissing $DocsBuildDir
    New-DirectoryIfMissing $ReleaseDocsDir

    $texFile = "$SourceName.tex"
    $pdfFile = Join-Path $DocsBuildDir "$SourceName.pdf"
    $releasePdfFile = Join-Path $ReleaseDocsDir "$DisplayName.pdf"

    Invoke-LoggedCommand `
        -FilePath 'latexmk' `
        -Arguments @(
            '-silent',
            '-pdf',
            '-outdir=../dist/docs',
            $texFile
        ) `
        -WorkingDirectory $DocsDir `
        -Description "LaTeX build: $DisplayName"

    Test-FileExists -Path $pdfFile -Message "Expected PDF was not generated for $DisplayName."
    Copy-File -Source $pdfFile -Destination $releasePdfFile
}

function Invoke-DocumentationBuild {
    if ($SkipDocs) {
        Write-Step '[6/7] Skipping documentation build.'
        return
    }

    Write-Step '[6/7] Building documentation...'

    Write-ReleaseInfo

    Invoke-DocBuild -SourceName 'mainTRM' -DisplayName 'Technical Reference Manual'
    Invoke-DocBuild -SourceName 'mainRTR' -DisplayName 'Regression Test Report'
    Invoke-DocBuild -SourceName 'mainRN' -DisplayName 'Release Note'

    Write-Log 'Documentation build completed.'
}

function New-ReleaseArchive {
    Write-Step '[7/7] Creating release zip...'

    Remove-FileIfExists $OutputZip

    Invoke-LoggedCommand `
        -FilePath 'tar' `
        -Arguments @(
            '-a',
            '-c',
            '-f',
            $OutputZip,
            '.'
        ) `
        -WorkingDirectory $ReleaseDir `
        -Description 'Archive creation'

    Test-FileExists -Path $OutputZip -Message 'Release zip was not created.'
    Write-Log "Archive created: $OutputZip"
}

function Write-FailureReport {
    param([System.Management.Automation.ErrorRecord]$ErrorRecord)

    Write-LogBlock -Title 'RELEASE FAILED' -Lines @(
        "Current step   : $script:CurrentStep",
        "Exception type : $($ErrorRecord.Exception.GetType().FullName)",
        "Message        : $($ErrorRecord.Exception.Message)"
    )

    if ($null -ne $ErrorRecord.InvocationInfo) {
        Write-LogBlock -Title 'FAILURE LOCATION' -Lines @(
            "Script : $($ErrorRecord.InvocationInfo.ScriptName)",
            "Line   : $($ErrorRecord.InvocationInfo.ScriptLineNumber)",
            "Command: $($ErrorRecord.InvocationInfo.Line.Trim())"
        )
    }

    if (-not [string]::IsNullOrWhiteSpace($ErrorRecord.ScriptStackTrace)) {
        Write-LogBlock -Title 'POWERSHELL STACK TRACE' -Lines @($ErrorRecord.ScriptStackTrace)
    }

    Write-Host ''
    Write-Host '============================================================================' -ForegroundColor Red
    Write-Host ' [ERROR] Release failed.' -ForegroundColor Red
    Write-Host '============================================================================' -ForegroundColor Red
    Write-Host "Current step: $script:CurrentStep"
    Write-Host "Message     : $($ErrorRecord.Exception.Message)"
    Write-Host "Log         : $ReleaseLog"
    Write-Host ''
}

# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

$exitCode = 0

try {
    Open-ReleaseLog

    Write-Host ''
    Write-Host "Building $ProjectName $VersionString"
    Write-Host "Log: $ReleaseLog"
    Write-Host ''

    Test-ReleaseInputs
    Initialize-Dist
    Install-ReleasePythonRuntime
    Copy-RuntimeAndRootFiles
    Copy-SourceFiles
    Invoke-ReleaseRuntimeSmokeTest
    Invoke-RegressionTest
    Invoke-DocumentationBuild
    New-ReleaseArchive

    Write-LogBlock -Title 'RELEASE COMPLETED' -Lines @(
        "Release directory: $ReleaseDir",
        "Release archive  : $OutputZip",
        "Log              : $ReleaseLog",
        "Completed        : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    )

    Write-Host ''
    Write-Host 'Release completed.'
    Write-Host "Release directory: $ReleaseDir"
    Write-Host "Release archive  : $OutputZip"
    Write-Host "Log              : $ReleaseLog"
    Write-Host ''

    if (Test-Path -LiteralPath $TempLogDir -PathType Container) {
        Remove-DirectoryIfExists $TempLogDir
    }
} catch {
    $exitCode = 1
    Write-FailureReport -ErrorRecord $_
} finally {
    Close-ReleaseLog
}

exit $exitCode
