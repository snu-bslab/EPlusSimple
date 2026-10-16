# ============================================================================
# EPlusSimple runtime setup
# ============================================================================
#
# This script prepares a local runtime directory for EPlusSimple.
# It does not require system-wide Python, system-wide EnergyPlus, or system-wide Go.
#
# Expected repository layout:
#
# /
# |-- scripts/
# |   |-- setup/
# |   |   |-- setup.ps1
# |   |   `-- requirements-dev.txt
# |   `-- dev/
# |       |-- build-go.bat
# |       `-- build-go.ps1
# |-- src/
# `-- runtime/
#     |-- PythonV3-12-7/      Embedded Python runtime
#     |-- EnergyPlusV24-2-0/  Portable EnergyPlus 24.2 runtime
#     |-- Weather/
#     |   `-- TMY/            Korean TMY weather files
#     |-- GoV1-26-3/          Portable Go SDK
#     |-- .go/                Repository-local Go workspace and caches
#     |   |-- gopath/         Go GOPATH for this repository
#     |   |-- build-cache/    Go build cache for this repository
#     |   `-- mod-cache/      Go module cache for this repository
#     `-- downloads/          Temporary downloaded files
#
# Design notes:
#
# 1. runtime/PythonV3-12-7 is NOT a normal venv.
#    It is the official Windows embeddable Python distribution.
#
# 2. runtime/EnergyPlusV24-2-0 is NOT installed into Program Files.
#    It is extracted from the official EnergyPlus portable zip file.
#
# 3. runtime/Weather/TMY stores Korean TMY weather files downloaded from:
#    https://github.com/snu-bslab/EPlusSimple-resources/releases/tag/weather%2Fv1
#
# 4. runtime/GoV1-26-3 is NOT installed into Program Files.
#    It is extracted from the official Go Windows archive.
#
# 5. This PowerShell script is used instead of putting all logic in setup.bat
#    because PowerShell is safer for:
#    - downloading files,
#    - extracting zip archives,
#    - recursively locating executables,
#    - copying directory contents without robocopy parsing issues.
#
# 6. This file intentionally uses ASCII comments. This avoids code-page issues
#    when the file is opened or executed on different Windows environments.
#
# Recommended .gitignore entries:
#
# /runtime/
#
# ============================================================================

[CmdletBinding()]
param(
    # Force reinstallation of Python, EnergyPlus, Weather, and Go runtime directories.
    [switch]$Force,

    # Skip Python package installation from scripts/setup/requirements-dev.txt.
    [switch]$SkipRequirements,

    # Skip Korean TMY weather data setup.
    [switch]$SkipWeather,

    # Skip Go SDK installation.
    [switch]$SkipGo,

    # Keep the temporary EnergyPlus extraction directory for debugging.
    [switch]$KeepExtractedEnergyPlus,

    # Keep the temporary Weather extraction directory for debugging.
    [switch]$KeepExtractedWeather,

    # Keep the temporary Go extraction directory for debugging.
    [switch]$KeepExtractedGo,

    # Keep downloaded zip/bootstrap files after a successful setup.
    # By default, runtime/downloads is removed after all setup steps complete.
    [switch]$KeepDownloads
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

# ============================================================================
# [0] Common paths
# ============================================================================
# setup.ps1 is expected to be located at:
# /scripts/setup/setup.ps1
# Therefore, the repository root is two levels above $PSScriptRoot.
# ============================================================================

$SetupDir = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $SetupDir '..\..')).Path
$RuntimeDir = Join-Path $RepoRoot 'runtime'
$DownloadDir = Join-Path $RuntimeDir 'downloads'
$RequirementsPath = Join-Path $SetupDir 'requirements-dev.txt'

# ============================================================================
# [1] Python runtime configuration
# ============================================================================

$PythonVersionShort = '312'
$PythonVersionFull = '3.12.7'

$PythonDir = Join-Path $RuntimeDir 'PythonV3-12-7'
$PythonExe = Join-Path $PythonDir 'python.exe'
$PipExe = Join-Path $PythonDir 'Scripts\pip.exe'

$PythonZipFileName = "python-$PythonVersionFull-embed-amd64.zip"
$PythonZipPath = Join-Path $DownloadDir $PythonZipFileName
$PythonDownloadUrl = "https://www.python.org/ftp/python/$PythonVersionFull/$PythonZipFileName"

$PythonPthFile = Join-Path $PythonDir "python$PythonVersionShort._pth"

# This path is written into python312._pth.
# It is relative to runtime/PythonV3-12-7/python.exe.
$SrcPathForPth = '..\..\src'

$GetPipUrl = 'https://bootstrap.pypa.io/get-pip.py'
$GetPipPath = Join-Path $DownloadDir 'get-pip.py'

# ============================================================================
# [2] EnergyPlus portable runtime configuration
# ============================================================================
# v24.2.0a is the bug-fix release for EnergyPlus 24.2.0.
# The official zip expands into a folder named roughly like:
# EnergyPlus-24.2.0-94a887817b-Windows-x86_64
#
# This script extracts it to a temporary folder, finds the real folder that
# contains energyplus.exe, and copies that folder's CONTENTS into:
#
# runtime/EnergyPlusV24-2-0
# ============================================================================

$EnergyPlusVersion = '24.2.0'
$EnergyPlusBuild = '94a887817b'
$EnergyPlusTag = 'v24.2.0a'
$EnergyPlusPlatform = 'Windows-x86_64'

$EnergyPlusFolderName = 'EnergyPlusV24-2-0'
$EnergyPlusDir = Join-Path $RuntimeDir $EnergyPlusFolderName
$EnergyPlusExe = Join-Path $EnergyPlusDir 'energyplus.exe'

$EnergyPlusZipFileName = "EnergyPlus-$EnergyPlusVersion-$EnergyPlusBuild-$EnergyPlusPlatform.zip"
$EnergyPlusZipPath = Join-Path $DownloadDir $EnergyPlusZipFileName
$EnergyPlusDownloadUrl = "https://github.com/NREL/EnergyPlus/releases/download/$EnergyPlusTag/$EnergyPlusZipFileName"

$EnergyPlusExtractDir = Join-Path $RuntimeDir '_energyplus_extract'
$EnergyPlusLegacyDir = Join-Path $RuntimeDir 'energyplus'

# ============================================================================
# [3] Korean TMY weather data configuration
# ============================================================================
# The weather release tag contains Korean TMY weather data.
# The script queries the GitHub Release API, selects the uploaded asset whose
# name looks like a Korean TMY zip archive, downloads it, and extracts it into:
#
# runtime/Weather/TMY
#
# If the release asset name changes later, update $WeatherAssetNamePattern.
# ============================================================================

$WeatherRootDir = Join-Path $RuntimeDir 'Weather'
$WeatherTmyDir = Join-Path $WeatherRootDir 'TMY'
$WeatherExtractDir = Join-Path $RuntimeDir '_weather_extract'
$WeatherZipPath = Join-Path $DownloadDir 'Korean_TMY.zip'

$WeatherReleaseApiUrl = 'https://api.github.com/repos/snu-bslab/EPlusSimple-resources/releases/tags/weather%2Fv1'

# Prefer assets containing both "Korean" or "Korea" and "TMY".
# Source-code archives are not returned as normal release assets by the release
# asset API, but the zip suffix check is kept explicit.
$WeatherAssetNamePattern = '(?i)(korean|korea).*tmy.*\.zip$|tmy.*(korean|korea).*\.zip$'

# ============================================================================
# [3b] Korean AMY weather data configuration (REB)
# ============================================================================
# The REB module simulates GR-before / GR-after / N-year cases with actual
# meteorological year (AMY) files named {station}_{year}.epw. They are
# downloaded from the same resources repository and extracted into:
#
# runtime/Weather/AMY
# ============================================================================

$WeatherAmyDir = Join-Path $WeatherRootDir 'AMY'
$WeatherAmyExtractDir = Join-Path $RuntimeDir '_weather_amy_extract'
$WeatherAmyZipPath = Join-Path $DownloadDir 'Korean_AMY.zip'

$WeatherAmyReleaseApiUrl = 'https://api.github.com/repos/snu-bslab/EPlusSimple-resources/releases/tags/weather%2Famy-v1'

$WeatherAmyAssetNamePattern = '(?i)(korean|korea).*amy.*\.zip$|amy.*(korean|korea).*\.zip$'

# ============================================================================
# [4] Go portable SDK configuration
# ============================================================================
# Use the official Windows amd64 zip archive instead of the MSI installer.
# This keeps Go fully portable under runtime/.
# ============================================================================

$GoVersion = '1.26.3'
$GoFolderName = 'GoV1-26-3'

$GoDir = Join-Path $RuntimeDir $GoFolderName
$GoExe = Join-Path $GoDir 'bin\go.exe'

$GoZipFileName = "go$GoVersion.windows-amd64.zip"
$GoZipPath = Join-Path $DownloadDir $GoZipFileName
$GoDownloadUrl = "https://go.dev/dl/$GoZipFileName"

$GoExpectedSha256 = '20d2ceafb4ed41b96b879010927b28bc92a5be57a7c1801ce365a9ca51d3224a'

$GoExtractDir = Join-Path $RuntimeDir '_go_extract'
$GoLegacyDir = Join-Path $RuntimeDir 'go'

# Keep Go's user-level workspace and caches inside this repository's runtime directory.
# These environment variables are set for this setup process only.
# They do not modify the user's global Windows environment.

$GoDataDir = Join-Path $RuntimeDir '.go'
$GoPathDir = Join-Path $GoDataDir 'gopath'
$GoBuildCacheDir = Join-Path $GoDataDir 'build-cache'
$GoModCacheDir = Join-Path $GoDataDir 'mod-cache'

# ============================================================================
# Helper functions
# ============================================================================

function Write-Step {
    param([string]$Message)

    Write-Host ''
    Write-Host $Message
}

function New-DirectoryIfMissing {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Remove-DirectoryIfExists {
    param([string]$Path)

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Test-DirectoryHasFiles {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }

    $firstFile = Get-ChildItem -LiteralPath $Path -Recurse -ErrorAction SilentlyContinue |
        Where-Object { -not $_.PSIsContainer } |
        Select-Object -First 1

    return ($null -ne $firstFile)
}

function Save-RemoteFileIfMissing {
    param(
        [string]$Url,
        [string]$Destination
    )

    if (Test-Path -LiteralPath $Destination) {
        Write-Host " ...Using cached file: $Destination"
        return
    }

    Write-Host " ...Downloading: $Url"
    Write-Host "    Target     : $Destination"

    try {
        Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
    } catch {
        throw "Download failed. URL: $Url. Error: $($_.Exception.Message)"
    }

    if (-not (Test-Path -LiteralPath $Destination)) {
        throw "Downloaded file was not created: $Destination"
    }
}

function Expand-ZipClean {
    param(
        [string]$ZipPath,
        [string]$Destination
    )

    if (-not (Test-Path -LiteralPath $ZipPath)) {
        throw "Zip file does not exist: $ZipPath"
    }

    Remove-DirectoryIfExists $Destination
    New-DirectoryIfMissing $Destination

    Write-Host " ...Extracting zip: $ZipPath"
    Write-Host "    To          : $Destination"

    try {
        Expand-Archive -LiteralPath $ZipPath -DestinationPath $Destination -Force
    } catch {
        throw "Zip extraction failed. Zip: $ZipPath. Error: $($_.Exception.Message)"
    }
}

function Copy-DirectoryContents {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Source directory does not exist: $Source"
    }

    New-DirectoryIfMissing $Destination

    Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force
    }
}

function Add-UniqueLine {
    param(
        [string]$Path,
        [string]$Line
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Target file does not exist: $Path"
    }

    $lines = Get-Content -LiteralPath $Path -ErrorAction Stop

    if ($lines -contains $Line) {
        Write-Host " ...Already in ._pth: $Line"
    } else {
        Add-Content -LiteralPath $Path -Value $Line
        Write-Host " ...Added to ._pth: $Line"
    }
}

function Invoke-ExternalCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments = @()
    )

    Write-Host " ...Running: $FilePath $($Arguments -join ' ')"

    & $FilePath @Arguments

    $exitCode = $LASTEXITCODE

    if ($null -ne $exitCode -and $exitCode -ne 0) {
        throw "Command failed with exit code $exitCode`: $FilePath $($Arguments -join ' ')"
    }
}

function Assert-FileSha256 {
    param(
        [string]$Path,
        [string]$ExpectedSha256
    )

    if ([string]::IsNullOrWhiteSpace($ExpectedSha256)) {
        return
    }

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Cannot verify hash because file does not exist: $Path"
    }

    Write-Host " ...Verifying SHA256: $Path"

    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    $expected = $ExpectedSha256.ToLowerInvariant()

    if ($actual -ne $expected) {
        throw "SHA256 mismatch. File: $Path. Expected: $expected. Actual: $actual"
    }

    Write-Host " ...SHA256 verified."
}

function Set-GoEnvironmentForCurrentProcess {
    # These variables affect this PowerShell process only.
    # They do not modify the user's global Windows environment.

    $env:GOROOT = $GoDir
    $env:GOPATH = $GoPathDir
    $env:GOCACHE = $GoBuildCacheDir
    $env:GOMODCACHE = $GoModCacheDir
    $env:PATH = "$(Join-Path $GoDir 'bin');$env:PATH"
}

function Set-PythonEnvironmentForCurrentProcess {
    # Avoid accidentally using user-level site-packages such as:
    # C:\Users\<user>\AppData\Roaming\Python\Python312\site-packages

    $env:PYTHONNOUSERSITE = '1'
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
}

function Get-GitHubReleaseAsset {
    param(
        [string]$ReleaseApiUrl,
        [string]$NamePattern
    )

    Write-Host " ...Querying GitHub release API:"
    Write-Host "    $ReleaseApiUrl"

    $headers = @{
        'User-Agent' = 'EPlusSimple-setup'
        'Accept'     = 'application/vnd.github+json'
    }

    try {
        $release = Invoke-RestMethod -Uri $ReleaseApiUrl -Headers $headers -UseBasicParsing
    } catch {
        throw "Failed to query GitHub release API. URL: $ReleaseApiUrl. Error: $($_.Exception.Message)"
    }

    if ($null -eq $release.assets) {
        throw "GitHub release API response did not include assets."
    }

    $assets = @($release.assets)

    if ($assets.Count -eq 0) {
        throw "No uploaded release assets were found in GitHub release: $ReleaseApiUrl"
    }

    Write-Host ' ...Available uploaded release assets:'
    foreach ($asset in $assets) {
        Write-Host "    - $($asset.name)"
    }

    $matched = $assets |
        Where-Object { $_.name -match $NamePattern } |
        Select-Object -First 1

    if ($null -eq $matched) {
        $names = ($assets | ForEach-Object { $_.name }) -join ', '
        throw "No release asset matched pattern '$NamePattern'. Available assets: $names"
    }

    if ([string]::IsNullOrWhiteSpace($matched.browser_download_url)) {
        throw "Matched release asset does not include browser_download_url: $($matched.name)"
    }

    Write-Host " ...Selected weather asset: $($matched.name)"
    Write-Host "    Size: $($matched.size) bytes"

    return $matched
}

# ============================================================================
# Setup steps
# ============================================================================

function Initialize-PythonRuntime {
    Write-Step '[1/6] Checking Python runtime...'

    if ($Force -and (Test-Path -LiteralPath $PythonDir)) {
        Write-Host " ...Force enabled. Removing existing Python runtime: $PythonDir"
        Remove-DirectoryIfExists $PythonDir
    }

    if (Test-Path -LiteralPath $PythonExe) {
        Write-Host " ...Found Python runtime: $PythonExe"
        return
    }

    Save-RemoteFileIfMissing -Url $PythonDownloadUrl -Destination $PythonZipPath

    Remove-DirectoryIfExists $PythonDir
    New-DirectoryIfMissing $PythonDir

    Write-Host ' ...Extracting Python package.'
    Expand-Archive -LiteralPath $PythonZipPath -DestinationPath $PythonDir -Force

    if (-not (Test-Path -LiteralPath $PythonExe)) {
        throw "python.exe was not found after extraction. Expected: $PythonExe"
    }
}

function Set-PythonPaths {
    Write-Step '[2/6] Configuring Python runtime paths...'

    if (-not (Test-Path -LiteralPath $PythonPthFile)) {
        throw "Python ._pth file was not found: $PythonPthFile"
    }

    Add-UniqueLine -Path $PythonPthFile -Line 'Lib\site-packages'
    Add-UniqueLine -Path $PythonPthFile -Line $SrcPathForPth
    Add-UniqueLine -Path $PythonPthFile -Line 'import site'

    Write-Host " ...Configured: $PythonPthFile"
}

function Initialize-PipAndPackages {
    Write-Step '[3/6] Installing pip and Python packages...'

    Set-PythonEnvironmentForCurrentProcess

    if (-not (Test-Path -LiteralPath $PipExe)) {
        Save-RemoteFileIfMissing -Url $GetPipUrl -Destination $GetPipPath
        Invoke-ExternalCommand -FilePath $PythonExe -Arguments @($GetPipPath)
    } else {
        Write-Host " ...Found pip: $PipExe"
    }

    Invoke-ExternalCommand -FilePath $PythonExe -Arguments @(
        '-m',
        'pip',
        'install',
        '--upgrade',
        'setuptools',
        'wheel'
    )

    if ($SkipRequirements) {
        Write-Host ' ...SkipRequirements enabled. Skipping development requirements installation.'
    } elseif (Test-Path -LiteralPath $RequirementsPath) {
        Invoke-ExternalCommand -FilePath $PythonExe -Arguments @(
            '-m',
            'pip',
            'install',
            '-r',
            $RequirementsPath
        )
    } else {
        Write-Warning "Development requirements file was not found. Skipping package installation: $RequirementsPath"
    }
}

function Initialize-EnergyPlusRuntime {
    Write-Step '[4/6] Checking EnergyPlus runtime...'

    if ($Force -and (Test-Path -LiteralPath $EnergyPlusDir)) {
        Write-Host " ...Force enabled. Removing existing EnergyPlus runtime: $EnergyPlusDir"
        Remove-DirectoryIfExists $EnergyPlusDir
    }

    if (Test-Path -LiteralPath $EnergyPlusExe) {
        Write-Host " ...Found EnergyPlus runtime: $EnergyPlusExe"
        & $EnergyPlusExe --version
        return
    }

    # Remove the older unversioned layout produced by an earlier setup draft.
    if (Test-Path -LiteralPath $EnergyPlusLegacyDir) {
        Write-Host " ...Removing legacy EnergyPlus folder: $EnergyPlusLegacyDir"
        Remove-DirectoryIfExists $EnergyPlusLegacyDir
    }

    Save-RemoteFileIfMissing -Url $EnergyPlusDownloadUrl -Destination $EnergyPlusZipPath

    Expand-ZipClean -ZipPath $EnergyPlusZipPath -Destination $EnergyPlusExtractDir

    # Locate the real EnergyPlus executable inside the extracted zip.
    # Do NOT use .Count here because a single result may be treated as a scalar
    # object under some Windows PowerShell configurations.
    # Also avoid the -File switch for broader compatibility.

    $candidate = Get-ChildItem -LiteralPath $EnergyPlusExtractDir -Recurse -ErrorAction Stop |
        Where-Object {
            (-not $_.PSIsContainer) -and ($_.Name -ieq 'energyplus.exe')
        } |
        Select-Object -First 1

    if ($null -eq $candidate) {
        throw "energyplus.exe was not found inside the extracted package: $EnergyPlusExtractDir"
    }

    $sourceDir = $candidate.Directory.FullName

    Write-Host ' ...Found EnergyPlus source directory:'
    Write-Host "    $sourceDir"

    Remove-DirectoryIfExists $EnergyPlusDir
    New-DirectoryIfMissing $EnergyPlusDir

    Write-Host ' ...Copying EnergyPlus files to:'
    Write-Host "    $EnergyPlusDir"

    # Copy the contents of the source folder, not the wrapper folder itself.
    Get-ChildItem -LiteralPath $sourceDir -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $EnergyPlusDir -Recurse -Force
    }

    if (-not $KeepExtractedEnergyPlus) {
        Remove-DirectoryIfExists $EnergyPlusExtractDir
    } else {
        Write-Host " ...Keeping extracted EnergyPlus directory for debugging: $EnergyPlusExtractDir"
    }

    if (-not (Test-Path -LiteralPath $EnergyPlusExe)) {
        throw "EnergyPlus executable was not found after setup. Expected: $EnergyPlusExe"
    }

    Write-Host ' ...EnergyPlus setup complete.'
    & $EnergyPlusExe --version
}

function Initialize-WeatherRuntime {
    Write-Step '[5/6] Checking Korean TMY weather data...'

    if ($SkipWeather) {
        Write-Host ' ...SkipWeather enabled. Skipping Korean TMY weather data setup.'
        return
    }

    if ($Force -and (Test-Path -LiteralPath $WeatherTmyDir)) {
        Write-Host " ...Force enabled. Removing existing weather data directory: $WeatherTmyDir"
        Remove-DirectoryIfExists $WeatherTmyDir
    }

    if (Test-DirectoryHasFiles -Path $WeatherTmyDir) {
        Write-Host " ...Found existing weather data: $WeatherTmyDir"
        return
    }

    New-DirectoryIfMissing $WeatherRootDir
    New-DirectoryIfMissing $WeatherTmyDir

    $asset = Get-GitHubReleaseAsset `
        -ReleaseApiUrl $WeatherReleaseApiUrl `
        -NamePattern $WeatherAssetNamePattern

    # Use a stable local filename even if the GitHub asset name contains spaces
    # or non-ASCII characters.
    if (Test-Path -LiteralPath $WeatherZipPath) {
        Write-Host " ...Using cached weather archive: $WeatherZipPath"
    } else {
        Save-RemoteFileIfMissing -Url $asset.browser_download_url -Destination $WeatherZipPath
    }

    Expand-ZipClean -ZipPath $WeatherZipPath -Destination $WeatherExtractDir

    Remove-DirectoryIfExists $WeatherTmyDir
    New-DirectoryIfMissing $WeatherTmyDir

    # If the archive contains one top-level directory, copy its contents.
    # Otherwise, copy the extracted contents as-is.
    $topLevelItems = @(Get-ChildItem -LiteralPath $WeatherExtractDir -Force)

    if ($topLevelItems.Count -eq 1 -and $topLevelItems[0].PSIsContainer) {
        $sourceDir = $topLevelItems[0].FullName
    } else {
        $sourceDir = $WeatherExtractDir
    }

    Write-Host ' ...Copying Korean TMY weather files to:'
    Write-Host "    $WeatherTmyDir"

    Copy-DirectoryContents -Source $sourceDir -Destination $WeatherTmyDir

    if (-not $KeepExtractedWeather) {
        Remove-DirectoryIfExists $WeatherExtractDir
    } else {
        Write-Host " ...Keeping extracted weather directory for debugging: $WeatherExtractDir"
    }

    if (-not (Test-DirectoryHasFiles -Path $WeatherTmyDir)) {
        throw "Weather data setup completed but no files were found in: $WeatherTmyDir"
    }

    $weatherFileCount = @(
        Get-ChildItem -LiteralPath $WeatherTmyDir -Recurse -ErrorAction Stop |
            Where-Object { -not $_.PSIsContainer }
    ).Count

    Write-Host " ...Korean TMY weather data setup complete. File count: $weatherFileCount"
}

function Initialize-AmyWeatherRuntime {
    Write-Step '[5b/6] Checking Korean AMY weather data (REB)...'

    if ($SkipWeather) {
        Write-Host ' ...SkipWeather enabled. Skipping Korean AMY weather data setup.'
        return
    }

    if ($Force -and (Test-Path -LiteralPath $WeatherAmyDir)) {
        Write-Host " ...Force enabled. Removing existing weather data directory: $WeatherAmyDir"
        Remove-DirectoryIfExists $WeatherAmyDir
    }

    if (Test-DirectoryHasFiles -Path $WeatherAmyDir) {
        Write-Host " ...Found existing weather data: $WeatherAmyDir"
        return
    }

    New-DirectoryIfMissing $WeatherRootDir
    New-DirectoryIfMissing $WeatherAmyDir

    $asset = Get-GitHubReleaseAsset `
        -ReleaseApiUrl $WeatherAmyReleaseApiUrl `
        -NamePattern $WeatherAmyAssetNamePattern

    if (Test-Path -LiteralPath $WeatherAmyZipPath) {
        Write-Host " ...Using cached weather archive: $WeatherAmyZipPath"
    } else {
        Save-RemoteFileIfMissing -Url $asset.browser_download_url -Destination $WeatherAmyZipPath
    }

    Expand-ZipClean -ZipPath $WeatherAmyZipPath -Destination $WeatherAmyExtractDir

    Remove-DirectoryIfExists $WeatherAmyDir
    New-DirectoryIfMissing $WeatherAmyDir

    $topLevelItems = @(Get-ChildItem -LiteralPath $WeatherAmyExtractDir -Force)

    if ($topLevelItems.Count -eq 1 -and $topLevelItems[0].PSIsContainer) {
        $sourceDir = $topLevelItems[0].FullName
    } else {
        $sourceDir = $WeatherAmyExtractDir
    }

    Write-Host ' ...Copying Korean AMY weather files to:'
    Write-Host "    $WeatherAmyDir"

    Copy-DirectoryContents -Source $sourceDir -Destination $WeatherAmyDir

    if (-not $KeepExtractedWeather) {
        Remove-DirectoryIfExists $WeatherAmyExtractDir
    } else {
        Write-Host " ...Keeping extracted weather directory for debugging: $WeatherAmyExtractDir"
    }

    if (-not (Test-DirectoryHasFiles -Path $WeatherAmyDir)) {
        throw "Weather data setup completed but no files were found in: $WeatherAmyDir"
    }

    $weatherFileCount = @(
        Get-ChildItem -LiteralPath $WeatherAmyDir -Recurse -ErrorAction Stop |
            Where-Object { -not $_.PSIsContainer }
    ).Count

    Write-Host " ...Korean AMY weather data setup complete. File count: $weatherFileCount"
}

function Initialize-GoRuntime {
    Write-Step '[6/6] Checking Go portable SDK...'

    if ($SkipGo) {
        Write-Host ' ...SkipGo enabled. Skipping Go SDK setup.'
        return
    }

    if ($Force -and (Test-Path -LiteralPath $GoDir)) {
        Write-Host " ...Force enabled. Removing existing Go SDK: $GoDir"
        Remove-DirectoryIfExists $GoDir
    }

    if ($Force -and (Test-Path -LiteralPath $GoDataDir)) {
        Write-Host " ...Force enabled. Removing existing Go workspace/cache directory: $GoDataDir"
        Remove-DirectoryIfExists $GoDataDir
    }

    if (Test-Path -LiteralPath $GoExe) {
        Write-Host " ...Found Go SDK: $GoExe"

        New-DirectoryIfMissing $GoDataDir
        New-DirectoryIfMissing $GoPathDir
        New-DirectoryIfMissing $GoBuildCacheDir
        New-DirectoryIfMissing $GoModCacheDir

        Set-GoEnvironmentForCurrentProcess

        & $GoExe version
        return
    }

    # Remove the unversioned Go layout if it exists.
    if (Test-Path -LiteralPath $GoLegacyDir) {
        Write-Host " ...Removing legacy Go folder: $GoLegacyDir"
        Remove-DirectoryIfExists $GoLegacyDir
    }

    Save-RemoteFileIfMissing -Url $GoDownloadUrl -Destination $GoZipPath

    Assert-FileSha256 -Path $GoZipPath -ExpectedSha256 $GoExpectedSha256

    Expand-ZipClean -ZipPath $GoZipPath -Destination $GoExtractDir

    # The official Go Windows zip normally expands into:
    # /go/bin/go.exe
    # Locate go.exe explicitly to avoid relying on the outer folder name.

    $candidate = Get-ChildItem -LiteralPath $GoExtractDir -Recurse -ErrorAction Stop |
        Where-Object {
            (-not $_.PSIsContainer) -and ($_.Name -ieq 'go.exe')
        } |
        Select-Object -First 1

    if ($null -eq $candidate) {
        throw "go.exe was not found inside the extracted package: $GoExtractDir"
    }

    $sourceDir = Split-Path $candidate.Directory.FullName -Parent

    Write-Host ' ...Found Go source directory:'
    Write-Host "    $sourceDir"

    Remove-DirectoryIfExists $GoDir
    New-DirectoryIfMissing $GoDir

    Write-Host ' ...Copying Go SDK files to:'
    Write-Host "    $GoDir"

    # Copy the contents of the source folder, not the wrapper folder itself.
    # This produces:
    # runtime/GoV1-26-3/bin/go.exe
    # rather than:
    # runtime/GoV1-26-3/go/bin/go.exe

    Get-ChildItem -LiteralPath $sourceDir -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $GoDir -Recurse -Force
    }

    if (-not $KeepExtractedGo) {
        Remove-DirectoryIfExists $GoExtractDir
    } else {
        Write-Host " ...Keeping extracted Go directory for debugging: $GoExtractDir"
    }

    if (-not (Test-Path -LiteralPath $GoExe)) {
        throw "Go executable was not found after setup. Expected: $GoExe"
    }

    New-DirectoryIfMissing $GoDataDir
    New-DirectoryIfMissing $GoPathDir
    New-DirectoryIfMissing $GoBuildCacheDir
    New-DirectoryIfMissing $GoModCacheDir

    Set-GoEnvironmentForCurrentProcess

    Write-Host ' ...Go setup complete.'
    & $GoExe version
}

function Clear-DownloadsAfterSuccess {
    Write-Step '[cleanup] Checking downloaded setup files...'

    if ($KeepDownloads) {
        Write-Host " ...KeepDownloads enabled. Keeping: $DownloadDir"
        return
    }

    if (Test-Path -LiteralPath $DownloadDir) {
        Write-Host " ...Removing downloaded setup files: $DownloadDir"
        Remove-DirectoryIfExists $DownloadDir
    } else {
        Write-Host ' ...No downloads directory to remove.'
    }
}

# ============================================================================
# Main
# ============================================================================

try {
    Write-Host ''
    Write-Host '============================================================================'
    Write-Host ' EPlusSimple runtime setup'
    Write-Host '============================================================================'
    Write-Host ''
    Write-Host "Repository   : $RepoRoot"
    Write-Host "Setup dir    : $SetupDir"
    Write-Host "Requirements : $RequirementsPath"
    Write-Host "Runtime      : $RuntimeDir"
    Write-Host "Weather TMY  : $WeatherTmyDir"
    Write-Host "Weather AMY  : $WeatherAmyDir"
    Write-Host ''

    New-DirectoryIfMissing $RuntimeDir
    New-DirectoryIfMissing $DownloadDir

    Initialize-PythonRuntime
    Set-PythonPaths
    Initialize-PipAndPackages
    Initialize-EnergyPlusRuntime
    Initialize-WeatherRuntime
    Initialize-AmyWeatherRuntime
    Initialize-GoRuntime
    Clear-DownloadsAfterSuccess

    Write-Host ''
    Write-Host '============================================================================'
    Write-Host ' Runtime setup is complete.'
    Write-Host '============================================================================'
    Write-Host ''
    Write-Host "Python       : $PythonExe"
    Write-Host "EnergyPlus   : $EnergyPlusExe"
    Write-Host "Weather TMY  : $WeatherTmyDir"
    Write-Host "Weather AMY  : $WeatherAmyDir"

    if (-not $SkipGo) {
        Write-Host "Go           : $GoExe"
        Write-Host "Go data      : $GoDataDir"
        Write-Host "Go GOPATH    : $GoPathDir"
        Write-Host "Go cache     : $GoBuildCacheDir"
        Write-Host "Go modules   : $GoModCacheDir"
    }

    Write-Host "Runtime      : $RuntimeDir"
    Write-Host ''
    Write-Host 'To check Python packages:'
    Write-Host "  & `"$PythonExe`" -s -c `"import importlib; mods=['pandas','numpy','tqdm','openpyxl','jinja2']; [print(m, importlib.import_module(m).__file__) for m in mods]`""
    Write-Host ''
    Write-Host 'To check Go from PowerShell:'
    Write-Host "  & `"$GoExe`" version"
    Write-Host ''
    Write-Host 'To check Korean TMY weather files:'
    Write-Host "  dir `"$WeatherTmyDir`""
    Write-Host ''
    Write-Host 'To check Korean AMY weather files (REB):'
    Write-Host "  dir `"$WeatherAmyDir`""
    Write-Host ''

    exit 0
} catch {
    Write-Host ''
    Write-Host '============================================================================' -ForegroundColor Red
    Write-Host ' [ERROR] Runtime setup failed.' -ForegroundColor Red
    Write-Host '============================================================================' -ForegroundColor Red
    Write-Host ''
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ''
    Write-Host 'Suggested checks:'
    Write-Host ' 1. Delete runtime/downloads if a cached zip file is corrupted.'
    Write-Host ' 2. Delete runtime/_energyplus_extract if a previous extraction was interrupted.'
    Write-Host ' 3. Delete runtime/_weather_extract if a previous weather extraction was interrupted.'
    Write-Host ' 4. Delete runtime/_go_extract if a previous Go extraction was interrupted.'
    Write-Host ' 5. Re-run runscript setup from the repository root.'
    Write-Host ''
    Write-Host 'Note:'
    Write-Host ' runtime/downloads is intentionally kept when setup fails so that you can'
    Write-Host ' inspect or reuse the downloaded files during troubleshooting.'
    Write-Host ''

    exit 1
}
