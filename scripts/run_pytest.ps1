[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$testDepsPath = Join-Path $repoRoot ".test-deps"

if (-not (Test-Path -LiteralPath $testDepsPath -PathType Container)) {
    throw "Required dependency directory not found: $testDepsPath"
}

$pytestPackagePath = Join-Path $testDepsPath "pytest"
if (-not (Test-Path -LiteralPath $pytestPackagePath -PathType Container)) {
    throw "pytest package is missing in $testDepsPath"
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $pythonCommand) {
    throw "Python executable not found in PATH"
}

if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $testDepsPath
} else {
    $env:PYTHONPATH = "$testDepsPath;$($env:PYTHONPATH)"
}

# Validate that the current Python interpreter can import pytest from .test-deps.
& $pythonCommand.Source -c "import pytest" *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Python cannot import pytest from $testDepsPath. Ensure .test-deps matches the active Python version."
}

Set-Location -LiteralPath $repoRoot
& $pythonCommand.Source -m pytest @PytestArgs
exit $LASTEXITCODE
