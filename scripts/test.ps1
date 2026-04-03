[CmdletBinding()]
param(
    [switch]$Rebuild,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$testDepsPath = Join-Path $repoRoot ".test-deps"
$rebuildScriptPath = Join-Path $scriptDir "rebuild_test_deps.ps1"
$runScriptPath = Join-Path $scriptDir "run_pytest.ps1"

if (-not (Test-Path -LiteralPath $rebuildScriptPath -PathType Leaf)) {
    throw "Required script not found: $rebuildScriptPath"
}

if (-not (Test-Path -LiteralPath $runScriptPath -PathType Leaf)) {
    throw "Required script not found: $runScriptPath"
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $pythonCommand) {
    throw "Python executable not found in PATH"
}

$shouldRebuild = $Rebuild.IsPresent

if (-not $shouldRebuild) {
    if (-not (Test-Path -LiteralPath $testDepsPath -PathType Container)) {
        Write-Output "Dependency bundle is missing. Rebuilding .test-deps."
        $shouldRebuild = $true
    } else {
        $pytestPackagePath = Join-Path $testDepsPath "pytest"
        if (-not (Test-Path -LiteralPath $pytestPackagePath -PathType Container)) {
            Write-Output "pytest package is missing in .test-deps. Rebuilding dependency bundle."
            $shouldRebuild = $true
        } else {
            $originalPythonPath = $env:PYTHONPATH
            if ([string]::IsNullOrWhiteSpace($originalPythonPath)) {
                $env:PYTHONPATH = $testDepsPath
            } else {
                $env:PYTHONPATH = "$testDepsPath;$originalPythonPath"
            }

            & $pythonCommand.Source -c "import pytest" *> $null
            $canImportPytest = $LASTEXITCODE -eq 0

            if ([string]::IsNullOrWhiteSpace($originalPythonPath)) {
                if (Test-Path Env:PYTHONPATH) {
                    Remove-Item Env:PYTHONPATH
                }
            } else {
                $env:PYTHONPATH = $originalPythonPath
            }

            if (-not $canImportPytest) {
                Write-Output "Current Python cannot import pytest from .test-deps. Rebuilding dependency bundle."
                $shouldRebuild = $true
            }
        }
    }
}

if ($shouldRebuild) {
    & $rebuildScriptPath
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

& $runScriptPath @PytestArgs
exit $LASTEXITCODE
