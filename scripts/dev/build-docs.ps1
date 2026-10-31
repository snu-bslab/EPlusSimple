# ============================================================================
# EPlusSimple documentation build
# ============================================================================
# Location:
#   scripts\dev\build-docs.ps1
#
# Usage:
#   run build-docs
#   run build-docs -Document trm
#   run build-docs -Document rtr
#   run build-docs -Document rn
#
# Builds the existing TeX sources with latexmk into dist\docs.
# Version/date metadata and regression results are used as they currently exist.
# ============================================================================

[CmdletBinding()]
param(
    [ValidateSet('all', 'trm', 'rtr', 'rn')]
    [string]$Document = 'all'
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$exitCode = 0

try {
    # scripts/dev/build-docs.ps1 -> repository root = ../..
    $RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
    $DocsDir = Join-Path $RepoRoot 'docs'
    $DocsBuildDir = Join-Path $RepoRoot 'dist\docs'

    $Documents = [ordered]@{
        'trm' = @{
            SourceName = 'mainTRM'
            DisplayName = 'Technical Reference Manual'
            IncludeDirectory = 'TechnicalReferenceManual'
        }
        'rtr' = @{
            SourceName = 'mainRTR'
            DisplayName = 'Regression Test Report'
            IncludeDirectory = 'RegressionTestReport'
        }
        'rn' = @{
            SourceName = 'mainRN'
            DisplayName = 'Release Note'
            IncludeDirectory = 'Release-Note'
        }
    }

    $documentNames = @($Documents.Keys)
    if ($Document -ne 'all') {
        $documentNames = @($Document.ToLowerInvariant())
    }

    # Check all selected source files before starting the first build.
    foreach ($name in $documentNames) {
        $definition = $Documents[$name]
        $texFile = Join-Path $DocsDir ($definition.SourceName + '.tex')

        if (-not (Test-Path -LiteralPath $texFile -PathType Leaf)) {
            throw "Documentation source was not found: $texFile"
        }
    }

    $latexmkCommand = Get-Command -Name 'latexmk' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($null -eq $latexmkCommand) {
        throw 'latexmk was not found in PATH. Install a TeX distribution with latexmk before building documentation.'
    }

    $LatexmkExe = $latexmkCommand.Source

    New-Item -ItemType Directory -Force -Path $DocsBuildDir | Out-Null

    # \include writes auxiliary files using the source subdirectory names.
    foreach ($name in $documentNames) {
        $definition = $Documents[$name]
        $includeBuildDir = Join-Path $DocsBuildDir $definition.IncludeDirectory
        New-Item -ItemType Directory -Force -Path $includeBuildDir | Out-Null
    }

    Write-Host '=============================='
    Write-Host 'Building documentation'
    Write-Host "Repo root : $RepoRoot"
    Write-Host "latexmk   : $LatexmkExe"
    Write-Host "Output    : $DocsBuildDir"
    Write-Host '=============================='

    # All TeX inputs, figures and bibliography paths are relative to docs.
    Push-Location -LiteralPath $DocsDir

    try {
        foreach ($name in $documentNames) {
            $definition = $Documents[$name]
            $texFile = $definition.SourceName + '.tex'
            $pdfFile = Join-Path $DocsBuildDir ($definition.SourceName + '.pdf')

            Write-Host ''
            Write-Host ("[build] {0}" -f $definition.DisplayName)

            $latexArguments = @(
                '-silent'
                '-pdf'
                '-interaction=nonstopmode'
                '-halt-on-error'
                '-file-line-error'
                '-outdir=../dist/docs'
                $texFile
            )

            # Native stderr output alone must not become a terminating error in
            # Windows PowerShell 5.1. The process exit code determines success.
            $previousErrorActionPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = 'Continue'
                $global:LASTEXITCODE = $null
                & $LatexmkExe @latexArguments
                $nativeExitCode = $global:LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $previousErrorActionPreference
            }

            if ($null -eq $nativeExitCode) {
                throw "latexmk did not return an exit code for $texFile."
            }

            if ($nativeExitCode -ne 0) {
                $exitCode = [int]$nativeExitCode
                throw "LaTeX build failed for $($definition.DisplayName). Exit code: $exitCode. Build logs: $DocsBuildDir"
            }

            if (-not (Test-Path -LiteralPath $pdfFile -PathType Leaf)) {
                throw "Expected PDF was not generated: $pdfFile"
            }

            if ((Get-Item -LiteralPath $pdfFile).Length -eq 0) {
                throw "Generated PDF is empty: $pdfFile"
            }

            Write-Host "Generated: $pdfFile"
        }
    }
    finally {
        Pop-Location
    }

    Write-Host ''
    Write-Host 'Documentation build completed successfully.'
}
catch {
    Write-Host "[ERROR] $($_.Exception.Message)"

    if ($exitCode -eq 0) {
        $exitCode = 1
    }
}

exit $exitCode
