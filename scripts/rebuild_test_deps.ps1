[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$testDepsPath = Join-Path $repoRoot ".test-deps"
$requirementsPath = Join-Path $repoRoot "requirements-dev.txt"

if (-not (Test-Path -LiteralPath $requirementsPath -PathType Leaf)) {
    throw "Required file not found: $requirementsPath"
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $pythonCommand) {
    throw "Python executable not found in PATH"
}

Write-Output "Using Python: $($pythonCommand.Source)"
& $pythonCommand.Source --version
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if (Test-Path -LiteralPath $testDepsPath) {
    Write-Output "Removing existing dependency bundle: $testDepsPath"
    Remove-Item -LiteralPath $testDepsPath -Recurse -Force
}

New-Item -ItemType Directory -Path $testDepsPath | Out-Null

Write-Output "Installing test dependencies from $requirementsPath"
& $pythonCommand.Source -m pip install --upgrade --target $testDepsPath -r $requirementsPath
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $testDepsPath
} else {
    $env:PYTHONPATH = "$testDepsPath;$($env:PYTHONPATH)"
}

Write-Output "Validating pytest import from .test-deps"
& $pythonCommand.Source -c "import pytest; print(pytest.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw "Python cannot import pytest from $testDepsPath after installation."
}
