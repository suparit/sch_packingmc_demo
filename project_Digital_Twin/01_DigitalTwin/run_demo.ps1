[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "status", "check")]
    [string]$Action = "start",

    [ValidateSet("standard", "upgraded")]
    [string]$Gateway = "standard",

    [ValidateSet("none", "serial", "rust", "serial-rust")]
    [string]$Hardware = "none",

    [ValidateSet("simulated", "camera")]
    [string]$VisionInput = "simulated",

    # feed   = dt-taping-dev/rust_bridge: also drives the feed motor pulses (2026-09-25)
    # legacy = our original rust_bridge: no pulses, FEED_CARRIER is timed (kept for rollback)
    [ValidateSet("feed", "legacy")]
    [string]$RustBridge = "feed",

    [string]$Python = "",
    [string]$SerialPort = "",
    [string]$IoHost = "",
    [int]$IoPort = 502,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$BackendRoot = Join-Path $ProjectRoot "python_backend"
$CadRoot = Join-Path $ProjectRoot "cad"
$RustRoot = Join-Path $ProjectRoot "rust_bridge"
$StateFile = Join-Path $ProjectRoot ".digital-twin-run.json"
$RequiredPorts = @(8765, 8766, 8000)

function Resolve-PythonExecutable {
    param([string]$Requested)

    if ($Requested) {
        if (Test-Path -LiteralPath $Requested -PathType Leaf) {
            return (Resolve-Path -LiteralPath $Requested).Path
        }
        $requestedCommand = Get-Command $Requested -ErrorAction SilentlyContinue
        if ($requestedCommand) { return $requestedCommand.Source }
        throw "Python executable not found: $Requested"
    }

    $localPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $localPython -PathType Leaf) {
        return (Resolve-Path -LiteralPath $localPython).Path
    }

    $pathPython = Get-Command python -ErrorAction SilentlyContinue
    if ($pathPython) { return $pathPython.Source }

    throw "Python not found. Create .venv or pass -Python <path>."
}

function Get-PortListenerPids {
    param([int]$Port)

    $rows = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $Port })
    if ($rows.Count -gt 0) {
        return @($rows.OwningProcess | Sort-Object -Unique)
    }

    $matches = @(netstat -ano -p tcp | Select-String -Pattern (":" + $Port + "\s+.*LISTENING"))
    $result = @()
    foreach ($match in $matches) {
        $parts = ($match.Line.Trim() -split "\s+")
        if ($parts.Count -gt 0) { $result += [int]$parts[-1] }
    }
    return @($result | Sort-Object -Unique)
}

function Assert-PortFree {
    param([int]$Port)
    $owners = @(Get-PortListenerPids -Port $Port)
    if ($owners.Count -gt 0) {
        throw "Port $Port is already in use by PID(s): $($owners -join ', '). No process was stopped."
    }
}

function Wait-PortListener {
    param([int]$Port, [int]$TimeoutSeconds = 15)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (@(Get-PortListenerPids -Port $Port).Count -gt 0) { return $true }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    return $false
}

function New-ProcessRecord {
    param([string]$Role, [System.Diagnostics.Process]$Process, [string]$Executable)
    return [pscustomobject]@{
        Role = $Role
        Id = $Process.Id
        StartTimeUtcTicks = $Process.StartTime.ToUniversalTime().Ticks
        Executable = $Executable
    }
}

function Get-OwnedProcess {
    param($Record)
    $candidate = Get-Process -Id ([int]$Record.Id) -ErrorAction SilentlyContinue
    if (-not $candidate) { return $null }
    try {
        if ($candidate.StartTime.ToUniversalTime().Ticks -ne [int64]$Record.StartTimeUtcTicks) {
            return $null
        }
    } catch {
        return $null
    }
    return $candidate
}

function Save-State {
    param([array]$Records)
    $state = [pscustomobject]@{
        ProjectRoot = $ProjectRoot
        StartedAt = (Get-Date).ToUniversalTime().ToString("o")
        Processes = @($Records)
    }
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $StateFile -Encoding UTF8
}

function Read-State {
    if (-not (Test-Path -LiteralPath $StateFile -PathType Leaf)) { return $null }
    return Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Stop-OwnedRecords {
    param([array]$Records)
    $recordsToStop = @($Records)
    [array]::Reverse($recordsToStop)
    $failed = @()
    foreach ($record in $recordsToStop) {
        $owned = Get-OwnedProcess -Record $record
        if (-not $owned) {
            Write-Host "[$($record.Role)] already stopped or PID identity changed; skipped PID $($record.Id)."
            continue
        }
        Write-Host "Stopping $($record.Role) PID $($record.Id)..."
        Stop-Process -Id $owned.Id -ErrorAction SilentlyContinue
        if (-not $owned.WaitForExit(5000)) {
            Stop-Process -Id $owned.Id -Force -ErrorAction SilentlyContinue
            if (-not $owned.WaitForExit(5000)) { $failed += $record }
        }
    }
    return @($failed)
}

function Test-GlbFile {
    param([string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 12) { throw "Invalid GLB (too short): $Path" }
    $magic = [System.Text.Encoding]::ASCII.GetString($bytes, 0, 4)
    $version = [BitConverter]::ToUInt32($bytes, 4)
    $declaredLength = [BitConverter]::ToUInt32($bytes, 8)
    if ($magic -ne "glTF" -or $version -ne 2 -or $declaredLength -ne $bytes.Length) {
        throw "Invalid GLB header/length: $Path"
    }
}

function Invoke-DependencyCheck {
    param([string]$PythonExecutable, [bool]$NeedSerial)
    & $PythonExecutable --version
    if ($LASTEXITCODE -ne 0) { throw "Python version check failed." }
    & $PythonExecutable -c "import websockets; print('websockets=' + websockets.__version__)"
    if ($LASTEXITCODE -ne 0) { throw "websockets import failed." }
    if ($NeedSerial) {
        & $PythonExecutable -c "import serial; print('pyserial=' + serial.VERSION)"
        if ($LASTEXITCODE -ne 0) { throw "pyserial import failed." }
    }
    & $PythonExecutable -m pip check
    if ($LASTEXITCODE -ne 0) { throw "pip check failed." }

    $indexPath = Join-Path $CadRoot "index1.html"
    $machinePath = Join-Path $CadRoot "export\Machine.glb"
    if (-not (Test-Path -LiteralPath $indexPath -PathType Leaf)) { throw "Missing web entrypoint: $indexPath" }
    if (-not (Test-Path -LiteralPath $machinePath -PathType Leaf)) { throw "Missing required model: $machinePath" }
    Get-ChildItem -LiteralPath (Join-Path $CadRoot "export") -File -Filter *.glb |
        ForEach-Object { Test-GlbFile -Path $_.FullName }
    Write-Host "Web entrypoint and all tracked GLB assets are valid."
}

function ConvertTo-ProcessArgumentString {
    param([string[]]$Arguments)
    $quoted = foreach ($argument in $Arguments) {
        '"' + $argument.Replace('"', '\"') + '"'
    }
    return ($quoted -join " ")
}

function Start-OwnedProcess {
    param(
        [string]$Role,
        [string]$Executable,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $Executable
    $startInfo.Arguments = ConvertTo-ProcessArgumentString -Arguments $Arguments
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $true
    $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $process = [System.Diagnostics.Process]::Start($startInfo)
    if (-not $process) { throw "Failed to start $Role." }
    Write-Host "Started $Role PID $($process.Id)."
    return $process
}

if ($Action -eq "status") {
    $state = Read-State
    if ($state) {
        foreach ($record in @($state.Processes)) {
            $owned = Get-OwnedProcess -Record $record
            $status = if ($owned) { "RUNNING" } else { "STOPPED/STALE" }
            Write-Host ("{0,-12} PID {1,-7} {2}" -f $record.Role, $record.Id, $status)
        }
    } else {
        Write-Host "No launcher state file."
    }
    foreach ($port in @(8765, 8766, 8767, 8000)) {
        $owners = @(Get-PortListenerPids -Port $port)
        $ownerText = if ($owners.Count) { $owners -join "," } else { "free" }
        Write-Host "Port $port`: $ownerText"
    }
    exit 0
}

if ($Action -eq "stop") {
    $state = Read-State
    if (-not $state) {
        Write-Host "Nothing to stop: launcher state does not exist."
        exit 0
    }
    $failed = @(Stop-OwnedRecords -Records @($state.Processes))
    if ($failed.Count -gt 0) {
        Save-State -Records $failed
        throw "Could not stop one or more owned processes; state file retained."
    }
    Remove-Item -LiteralPath $StateFile -Force
    Write-Host "Digital Twin processes started by this launcher are stopped."
    exit 0
}

$pythonExecutable = Resolve-PythonExecutable -Requested $Python
$needSerial = $Hardware -in @("serial", "serial-rust")
Invoke-DependencyCheck -PythonExecutable $pythonExecutable -NeedSerial $needSerial

if ($Action -eq "check") {
    foreach ($port in @(8765, 8766, 8767, 8000)) {
        $owners = @(Get-PortListenerPids -Port $port)
        $ownerText = if ($owners.Count) { "occupied by PID(s) " + ($owners -join ",") } else { "free" }
        Write-Host "Port $port`: $ownerText"
    }
    Write-Host "Dependency and asset checks passed."
    exit 0
}

$existingState = Read-State
if ($existingState) {
    $live = @($existingState.Processes | Where-Object { Get-OwnedProcess -Record $_ })
    if ($live.Count -gt 0) { throw "Launcher already owns running processes. Run stop or status first." }
    Remove-Item -LiteralPath $StateFile -Force
}

foreach ($port in $RequiredPorts) { Assert-PortFree -Port $port }
if ($Hardware -in @("rust", "serial-rust")) {
    Assert-PortFree -Port 8767
}

$started = @()
$oldRustBridge = $env:RUST_BRIDGE
$oldIoMonitor = $env:IO_MONITOR
$oldIoHost = $env:H7_IP
$oldIoPort = $env:H7_PORT
$oldIoOutputMode = $env:IO_OUTPUT_MODE
$oldBoardAddr = $env:BOARD_ADDR
$oldFeedMotor = $env:FEED_MOTOR
$oldSimFaults = $env:SIM_FAULTS
$oldSimStep = $env:SIM_STEP_S
$oldFeedHalfMs = $env:FEED_HALF_MS

try {
    # The gateway process inherits this.  Web-only runs simulate VISION;
    # the full launcher selects camera so VISION waits for OpenMV DECISION.
    $env:VISION_INPUT = $VisionInput

    if ($Hardware -in @("rust", "serial-rust")) {
        # The Rust child inherits this configuration. It WRITES physical outputs (OP0 lights, OP1 solenoids /
        # Cylinder C) and, with -RustBridge feed, drives the feed motor pulses. Not monitor-only (fixed 2026-09-27).
        if ($IoHost) { $env:H7_IP = $IoHost }
        $env:H7_PORT = "$IoPort"
        $env:IO_OUTPUT_MODE = "display"
        # Random simulated faults stay available for the unsynced (simulation) state; the gateway turns them off
        # by itself while the web Sync button drives the real board (hw_active, 2026-09-27).
        $env:SIM_FAULTS = "1"
        # Simulated steps only wait on a timer; shorten them so a cycle is ~4 s instead of ~8.7 s.
        $env:SIM_STEP_S = "0.15"
        # Feed pulse half-period: 2 ms (~205 pulses/s, 156 pulses ~0.76 s) instead of the gateway default 5 ms (~1.64 s).
        # Friend measured 205.6 pulses/s at 2 ms on the real board. Roll back: set this to "5".
        # 2026-09-28: rolled back to 5 -- at 2 ms the carrier stopped +1.09/+1.04/+0.41/-0.35 mm off index
        # (tolerance 0.3) on the real machine; 25 Sep at 5 ms: 9/10 pockets within 0.13 mm.
        $env:FEED_HALF_MS = "5"
        if ($RustBridge -eq "feed") {
            # This bridge always writes outputs (no IO_OUTPUT_MODE) and reads the board address from BOARD_ADDR.
            $boardHost = if ($IoHost) { $IoHost } else { "192.168.0.100" }
            $env:BOARD_ADDR = "${boardHost}:$IoPort"
            $env:FEED_MOTOR = "1"
            $bridgeRoot = Join-Path (Split-Path -Parent $ProjectRoot) "dt-taping-dev\rust_bridge"
            $rustExecutable = Join-Path $bridgeRoot "target\release\rust_modbus_bridge.exe"
            $buildHint = "cargo build --release --manifest-path dt-taping-dev/rust_bridge/Cargo.toml"
        } else {
            $env:FEED_MOTOR = "0"
            $bridgeRoot = $RustRoot
            $rustExecutable = Join-Path $RustRoot "target\debug\rust_modbus_bridge.exe"
            $buildHint = "cargo build --locked --manifest-path rust_bridge/Cargo.toml"
        }
        if (-not (Test-Path -LiteralPath $rustExecutable -PathType Leaf)) {
            throw "Rust bridge binary missing ($RustBridge). Run: $buildHint"
        }
        Write-Host "Rust bridge: $RustBridge ($rustExecutable)"
        $rustProcess = Start-OwnedProcess -Role "rust" -Executable $rustExecutable -Arguments @() -WorkingDirectory $bridgeRoot
        $started += New-ProcessRecord -Role "rust" -Process $rustProcess -Executable $rustExecutable
        Save-State -Records $started
        if (-not (Wait-PortListener -Port 8767 -TimeoutSeconds 15)) {
            throw "Rust bridge did not listen on 8767. Check the STM32 connection before retrying."
        }
        $env:RUST_BRIDGE = "1"
        $env:IO_MONITOR = "1"
    } else {
        $env:RUST_BRIDGE = "0"
        $env:IO_MONITOR = "0"
        $env:FEED_MOTOR = "0"
        $env:SIM_FAULTS = "1"
        $env:SIM_STEP_S = ""
        $env:FEED_HALF_MS = ""
    }

    $gatewayScript = if ($Gateway -eq "upgraded") { "gateway_fsm_upgrad.py" } else { "gateway_fsm.py" }
    $gatewayProcess = Start-OwnedProcess -Role "gateway" -Executable $pythonExecutable -Arguments @($gatewayScript) -WorkingDirectory $BackendRoot
    $started += New-ProcessRecord -Role "gateway" -Process $gatewayProcess -Executable $pythonExecutable
    Save-State -Records $started
    if (-not (Wait-PortListener -Port 8765) -or -not (Wait-PortListener -Port 8766)) {
        throw "Gateway did not acquire ports 8765/8766."
    }

    $webProcess = Start-OwnedProcess -Role "web" -Executable $pythonExecutable `
        -Arguments @("-m", "http.server", "8000", "--bind", "127.0.0.1") `
        -WorkingDirectory $CadRoot
    $started += New-ProcessRecord -Role "web" -Process $webProcess -Executable $pythonExecutable
    Save-State -Records $started
    if (-not (Wait-PortListener -Port 8000)) { throw "Web server did not acquire port 8000." }

    if ($Hardware -in @("serial", "serial-rust")) {
        $serialArguments = @("serial_bridge.py")
        if ($SerialPort) { $serialArguments += $SerialPort }
        $serialProcess = Start-OwnedProcess -Role "serial" -Executable $pythonExecutable -Arguments $serialArguments -WorkingDirectory $BackendRoot
        $started += New-ProcessRecord -Role "serial" -Process $serialProcess -Executable $pythonExecutable
        Save-State -Records $started
        Start-Sleep -Seconds 1
        if ($serialProcess.HasExited) { throw "Serial bridge exited. Check ST-LINK COM availability." }
    }

    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/index1.html" -UseBasicParsing -TimeoutSec 5
    if ($response.StatusCode -ne 200) { throw "Web smoke check returned HTTP $($response.StatusCode)." }

    Write-Host "Digital Twin ready: http://127.0.0.1:8000/index1.html"
    Write-Host "Stop only launcher-owned processes with: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 stop"
    if ($OpenBrowser) { Start-Process "http://127.0.0.1:8000/index1.html" }
} catch {
    $failure = $_
    if ($started.Count -gt 0) { Stop-OwnedRecords -Records $started | Out-Null }
    if (Test-Path -LiteralPath $StateFile) { Remove-Item -LiteralPath $StateFile -Force }
    throw $failure
} finally {
    $env:RUST_BRIDGE = $oldRustBridge
    $env:IO_MONITOR = $oldIoMonitor
    $env:H7_IP = $oldIoHost
    $env:H7_PORT = $oldIoPort
    $env:IO_OUTPUT_MODE = $oldIoOutputMode
    $env:BOARD_ADDR = $oldBoardAddr
    $env:FEED_MOTOR = $oldFeedMotor
    $env:SIM_FAULTS = $oldSimFaults
    $env:SIM_STEP_S = $oldSimStep
    $env:FEED_HALF_MS = $oldFeedHalfMs
}
