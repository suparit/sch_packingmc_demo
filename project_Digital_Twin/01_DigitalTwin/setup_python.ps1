[CmdletBinding()]
param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$VenvRoot = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
$Requirements = Join-Path $ProjectRoot "python_backend\requirements.txt"

function Resolve-BootstrapPython {
    param([string]$Requested)

    if ($Requested) {
        if (Test-Path -LiteralPath $Requested -PathType Leaf) {
            return [pscustomobject]@{ Executable = (Resolve-Path -LiteralPath $Requested).Path; Prefix = @() }
        }
        $requestedCommand = Get-Command $Requested -ErrorAction SilentlyContinue
        if ($requestedCommand) {
            return [pscustomobject]@{ Executable = $requestedCommand.Source; Prefix = @() }
        }
        throw "Python executable not found: $Requested"
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        # "-3" = newest installed 3.x; "-3.10" failed on PCs without exactly 3.10.
        return [pscustomobject]@{ Executable = $pyLauncher.Source; Prefix = @("-3") }
    }

    $pathPython = Get-Command python -ErrorAction SilentlyContinue
    if ($pathPython) {
        return [pscustomobject]@{ Executable = $pathPython.Source; Prefix = @() }
    }

    throw "Python 3.10+ not found. Install Python or pass -Python <path>."
}

if (-not (Test-Path -LiteralPath $Requirements -PathType Leaf)) {
    throw "Requirements file not found: $Requirements"
}

$oldPythonUtf8 = $env:PYTHONUTF8
$oldProgressBar = $env:PIP_PROGRESS_BAR
try {
    # Process-scoped UTF-8 avoids pip/Rich failures when the checkout path
    # contains Thai or other characters outside the active Windows code page.
    $env:PYTHONUTF8 = "1"
    $env:PIP_PROGRESS_BAR = "off"

    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        $bootstrap = Resolve-BootstrapPython -Requested $Python
        Write-Host "Creating project-local environment with $($bootstrap.Executable)..."
        & $bootstrap.Executable @($bootstrap.Prefix) -m venv $VenvRoot
        if ($LASTEXITCODE -ne 0) { throw "venv creation failed with exit code $LASTEXITCODE." }
    }

    & $VenvPython -m pip install --disable-pip-version-check --progress-bar off -r $Requirements
    if ($LASTEXITCODE -ne 0) { throw "pip install failed with exit code $LASTEXITCODE." }

    & $VenvPython --version
    & $VenvPython -c "import websockets, serial; print('websockets=' + websockets.__version__); print('pyserial=' + serial.VERSION)"
    if ($LASTEXITCODE -ne 0) { throw "Dependency import check failed." }
    & $VenvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw "pip check failed." }

    Write-Host "Python environment ready: $VenvPython"
} finally {
    $env:PYTHONUTF8 = $oldPythonUtf8
    $env:PIP_PROGRESS_BAR = $oldProgressBar
}
