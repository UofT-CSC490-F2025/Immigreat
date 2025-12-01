# PowerShell script to run tests with coverage
# Usage: .\run_tests.ps1 [-Unit] [-Integration] [-Fast] [-Html] [-Module <name>]

param(
    [switch]$Unit,
    [switch]$Integration,
    [switch]$Fast,
    [switch]$Html,
    [string]$Module,
    [switch]$Verbose,
    [switch]$FailFast
)

# Check if pytest is installed
try {
    $null = pytest --version 2>&1
} catch {
    Write-Host "Error: pytest not found. Install it with:" -ForegroundColor Red
    Write-Host "  pip install -r requirements-dev.txt" -ForegroundColor Yellow
    exit 1
}

# Build pytest command
$cmd = @('pytest')

# Add coverage options
$cmd += '--cov=src'
$cmd += '--cov-report=term-missing'
$cmd += '--cov-report=html'
$cmd += '--cov-report=xml'
$cmd += '--cov-report=json'

# Add verbosity
if ($Verbose) {
    $cmd += '-v'
} else {
    $cmd += '-q'
}

# Filter by test type
if ($Unit) {
    $cmd += '-m', 'unit'
} elseif ($Integration) {
    $cmd += '-m', 'integration'
}

# Skip slow tests
if ($Fast) {
    $cmd += '-m', 'not slow'
}

# Run specific module
if ($Module) {
    $cmd += "tests/unit/test_$Module.py"
}

# Fail fast
if ($FailFast) {
    $cmd += '-x'
}

# Run tests
Write-Host "Running: $($cmd -join ' ')" -ForegroundColor Cyan
Write-Host ('-' * 80)

& $cmd[0] $cmd[1..($cmd.Length-1)]
$exitCode = $LASTEXITCODE

# Open HTML report if requested
if ($Html -and $exitCode -eq 0) {
    $htmlReport = "htmlcov\index.html"
    if (Test-Path $htmlReport) {
        Write-Host "`nOpening coverage report: $htmlReport" -ForegroundColor Green
        Start-Process $htmlReport
    }
}

exit $exitCode
