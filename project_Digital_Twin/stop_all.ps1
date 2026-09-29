# =====================================================================
# stop_all.ps1
#
# จุดปิดระบบเดียวสำหรับ Taping Machine Digital Twin ทั้งชุด
# เรียงลำดับ (ย้อนกลับจากตอนเปิด): 1) กล้อง  2) Gateway/เว็บ/จอ HMI
#
# ทำไมต้องปิดกล้องก่อน: กล้องเป็น "ลูกค้า" ที่เชื่อมต่อเข้าหา Gateway ผ่าน
# WebSocket ถ้าปิด Gateway ก่อน กล้องจะพยายามเชื่อมต่อใหม่วนไปเรื่อย ๆ
# (ไม่ใช่เรื่องร้ายแรง แต่ปิดกล้องก่อนสะอาดกว่า)
#
# ห้ามใช้ taskkill /F /IM python.exe เด็ดขาด เพราะจะฆ่า python.exe ทุกโปรเซส
# ในเครื่อง ไม่ใช่แค่ของระบบนี้ (ดู 01_DigitalTwin\RUNBOOK.md)
# =====================================================================

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
. (Join-Path $RepoRoot "common_launcher.ps1")

$DigitalTwinDir = Join-Path $RepoRoot "01_DigitalTwin"
$RunDemo        = Join-Path $DigitalTwinDir "run_demo.ps1"
$DtStateFile    = Join-Path $DigitalTwinDir ".digital-twin-run.json"
$CamStateFile   = Join-Path $RepoRoot ".camera-run.json"

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host " ปิดระบบ Taping Machine Digital Twin (STOP.bat)" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

$somethingWasRunning = $false

# ----------------------------------------------------------------
# ขั้นที่ 1/3: ปิดกล้อง
# ----------------------------------------------------------------
Write-Host "[1/3] กล้องตรวจสอบชิ้นงาน" -ForegroundColor Yellow

$camStateRecord = Read-JsonStateFile -Path $CamStateFile
$camPortForCheck = if ($camStateRecord -and $camStateRecord.Port) { $camStateRecord.Port } else { "COM6" }
$camProc = Test-OwnedProcessAlive -Record $camStateRecord

if (-not $camProc) {
    # แผนสำรอง: ค้นหา process python.exe ที่ command line มีคำว่า app_vision
    # (กรณีไฟล์สถานะหาย หรือถูกเริ่มด้วยมือโดยไม่ผ่าน start_all.ps1)
    $candidates = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'app_vision' })
    if ($candidates.Count -gt 0) {
        $camProc = Get-Process -Id $candidates[0].ProcessId -ErrorAction SilentlyContinue
        if ($camProc) {
            Write-Host "      พบโปรแกรมกล้องที่ไม่มีไฟล์สถานะ (PID $($camProc.Id)) จากการค้นหา command line" -ForegroundColor DarkYellow
        }
    }
}

# กล้อง HIKROBOT ห้าม kill เด็ดขาด — ถ้าโปรเซสตายโดยไม่ได้เรียก cam.close() กล้องจะค้าง
# จนต้องถอดสาย USB (ดู 03_Vision\ocr\README.md) จึงสั่งปิดด้วยการสร้างไฟล์ ocr\STOP
# ซึ่ง app_vision_ocr.py เช็คทุกรอบลูป แล้วปิดกล้อง + เว็บ :5000 เองอย่างถูกวิธี
$ocrStopFile = Join-Path $RepoRoot "03_Vision\ocr\STOP"
$isHikrobot = ($camStateRecord -and $camStateRecord.Camera -eq "hikrobot")
if (-not $isHikrobot) {
    # ไม่มีไฟล์สถานะ (เปิดด้วยมือ) — ดูจาก command line ว่าเป็นแอป OCR หรือไม่
    $ocrProcs = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'app_vision_ocr' })
    if ($ocrProcs.Count -gt 0) {
        $isHikrobot = $true
        if (-not $camProc) { $camProc = Get-Process -Id $ocrProcs[0].ProcessId -ErrorAction SilentlyContinue }
    }
}

if ($camProc -and $isHikrobot) {
    $somethingWasRunning = $true
    Write-Host "      กำลังปิดกล้อง HIKROBOT PID $($camProc.Id) ด้วยไฟล์ STOP (ไม่ kill)..." -ForegroundColor Green
    New-Item -ItemType File -Path $ocrStopFile -Force | Out-Null
    # หนึ่งรอบลูปใช้ราว 1 วินาที (เฉลี่ย 16 เฟรม + OCR) เผื่อไว้ 20 วินาที
    if ($camProc.WaitForExit(20000)) {
        Write-Host "      ปิดกล้องเรียบร้อย" -ForegroundColor Green
    } else {
        Write-Host "      กล้องยังไม่ปิดภายใน 20 วินาที -- ไม่บังคับปิด เพราะจะทำให้กล้องค้าง" -ForegroundColor Red
        Write-Host "      ไปที่หน้าต่างของโปรแกรมกล้องแล้วกด Ctrl+C หรือรอสักครู่แล้วรัน STOP.bat อีกครั้ง" -ForegroundColor Red
    }
} elseif ($camProc) {
    $somethingWasRunning = $true
    Write-Host "      กำลังปิดโปรแกรมกล้อง PID $($camProc.Id)..." -ForegroundColor Green
    Stop-Process -Id $camProc.Id -ErrorAction SilentlyContinue
    if (-not $camProc.WaitForExit(5000)) {
        Write-Host "      โปรแกรมกล้องไม่ยอมปิดปกติ กำลังบังคับปิด..." -ForegroundColor DarkYellow
        Stop-Process -Id $camProc.Id -Force -ErrorAction SilentlyContinue
        $camProc.WaitForExit(5000) | Out-Null
    }
    Write-Host "      ปิดโปรแกรมกล้องแล้ว" -ForegroundColor Green
} else {
    Write-Host "      ไม่พบโปรแกรมกล้องที่กำลังทำงานอยู่" -ForegroundColor DarkGray
}

if (Test-Path -LiteralPath $CamStateFile -PathType Leaf) {
    Remove-Item -LiteralPath $CamStateFile -Force -ErrorAction SilentlyContinue
}
Write-Host ""

# ----------------------------------------------------------------
# ขั้นที่ 2/3: ปิด Gateway + เว็บ 3D + จอ HMI
# ----------------------------------------------------------------
Write-Host "[2/3] Gateway + เว็บ 3D + จอ HMI" -ForegroundColor Yellow

if (Test-Path -LiteralPath $DtStateFile -PathType Leaf) {
    $somethingWasRunning = $true
    try {
        & $RunDemo stop
        Write-Host "      ปิด Gateway/เว็บ/จอ HMI แล้ว" -ForegroundColor Green
    } catch {
        Write-Host "      ปิด Gateway/เว็บ ไม่สำเร็จทั้งหมด: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "      ตรวจสอบด้วยมือด้วย: powershell -File 01_DigitalTwin\run_demo.ps1 status" -ForegroundColor Red
    }
} else {
    Write-Host "      ไม่พบ Gateway/เว็บ ที่กำลังทำงานอยู่ (ไม่มีไฟล์สถานะ)" -ForegroundColor DarkGray
}
Write-Host ""

# ----------------------------------------------------------------
# เว็บ Digital Twin ตัวใหม่ (web_next · Next.js :5173) — start_all.ps1 เปิดไว้ในหน้าต่าง DT-web-next
# ----------------------------------------------------------------
Write-Host "[2b] เว็บ Digital Twin ตัวใหม่ (web_next :5173)" -ForegroundColor Yellow
$webNextStateFile = Join-Path $RepoRoot ".web-next-run.json"
$webTargets = @()
$webRec = Test-OwnedProcessAlive -Record (Read-JsonStateFile -Path $webNextStateFile)
if ($webRec) { $webTargets += $webRec.Id }
# แผนสำรอง: node ที่ถือพอร์ต 5173 และเป็นของ next (เช่นเปิดจาก START_WEB.bat ของเพื่อน / ไฟล์สถานะหาย)
foreach ($ownerPid in @(Get-PortListenerOwners -Port 5173)) {
    $cl = (Get-CimInstance Win32_Process -Filter "ProcessId=$ownerPid" -ErrorAction SilentlyContinue).CommandLine
    if ($cl -and $cl -match 'next') { $webTargets += [int]$ownerPid }
}
if ($webTargets.Count -gt 0) {
    $somethingWasRunning = $true
    foreach ($t in ($webTargets | Sort-Object -Unique)) {
        # ปิดทั้งต้นไม้ (cmd -> npm -> node) เฉพาะ PID นี้ — ไม่ใช่ /IM node.exe ที่ฆ่า node ทุกตัวในเครื่อง
        # PID จากไฟล์สถานะกับ PID จากพอร์ต 5173 อยู่ต้นไม้เดียวกัน ตัวแรกปิดไปแล้วตัวที่สองจะไม่เหลือ —
        # ข้ามถ้าไม่มีแล้ว + กัน error ของ taskkill ไม่ให้หยุดทั้งสคริปต์ ($ErrorActionPreference = Stop)
        if (-not (Get-Process -Id $t -ErrorAction SilentlyContinue)) { continue }
        try { & taskkill.exe /PID $t /T /F 2>&1 | Out-Null } catch { }
    }
    Write-Host "      ปิดเว็บใหม่แล้ว" -ForegroundColor Green
} else {
    Write-Host "      ไม่พบเว็บใหม่ที่กำลังทำงานอยู่" -ForegroundColor DarkGray
}
if (Test-Path -LiteralPath $webNextStateFile -PathType Leaf) {
    Remove-Item -LiteralPath $webNextStateFile -Force -ErrorAction SilentlyContinue
}
Write-Host ""

if (-not $somethingWasRunning) {
    Write-Host "ไม่มีอะไรรันอยู่" -ForegroundColor DarkGray
    Write-Host ""
}

# ----------------------------------------------------------------
# ขั้นที่ 3/3: ตรวจสอบผลหลังปิดระบบ
# ----------------------------------------------------------------
Write-Host "[3/3] ตรวจสอบสถานะหลังปิดระบบ" -ForegroundColor Yellow

$allPortsFree = $true
foreach ($port in 8000, 8765, 8766, 8767, 5173) {
    $owners = @(Get-PortListenerOwners -Port $port)
    if ($owners.Count -eq 0) {
        Write-Host ("      พอร์ต {0,-5}: ว่างแล้ว" -f $port) -ForegroundColor Green
    } else {
        $allPortsFree = $false
        Write-Host ("      พอร์ต {0,-5}: ยังถูกใช้งานอยู่โดย PID {1}" -f $port, ($owners -join ",")) -ForegroundColor Red
    }
}

$stmPort = Get-STM32DisplayPort
if ($stmPort) {
    $stmStatus = Get-ComPortStatus -PortName $stmPort
    if ($stmStatus -eq "ok") {
        Write-Host "      พอร์ตจอ HMI ($stmPort): ว่างแล้ว" -ForegroundColor Green
    } elseif ($stmStatus -eq "busy") {
        $allPortsFree = $false
        Write-Host "      พอร์ตจอ HMI ($stmPort): ยังถูกใช้งานอยู่ (อาจมีโปรแกรมอื่นเปิดค้าง หรือ process ยังไม่ปิดสนิท)" -ForegroundColor Red
    }
} else {
    Write-Host "      พอร์ตจอ HMI: ไม่พบบอร์ด STM32 เสียบอยู่ในขณะนี้ (ข้ามการตรวจสอบ)" -ForegroundColor DarkGray
}

$camPortStatus = Get-ComPortStatus -PortName $camPortForCheck
if ($isHikrobot) {
    # กล้อง HIKROBOT ไม่ใช้พอร์ต COM — ตรวจพอร์ตเว็บ :5000 ของแอปแทน
    $camPortStatus = "skip"
    $owners5000 = @(Get-PortListenerOwners -Port 5000)
    if ($owners5000.Count -eq 0) {
        Write-Host "      พอร์ตกล้อง HIKROBOT (เว็บ 5000): ว่างแล้ว" -ForegroundColor Green
    } else {
        $allPortsFree = $false
        Write-Host "      พอร์ตกล้อง HIKROBOT (เว็บ 5000): ยังถูกใช้งานอยู่โดย PID $($owners5000 -join ',')" -ForegroundColor Red
    }
}
if ($camPortStatus -eq "skip") {
} elseif ($camPortStatus -eq "ok") {
    Write-Host "      พอร์ตกล้อง ($camPortForCheck): ว่างแล้ว" -ForegroundColor Green
} elseif ($camPortStatus -eq "busy") {
    $allPortsFree = $false
    Write-Host "      พอร์ตกล้อง ($camPortForCheck): ยังถูกใช้งานอยู่" -ForegroundColor Red
} else {
    Write-Host "      พอร์ตกล้อง ($camPortForCheck): ไม่พบอุปกรณ์เสียบอยู่ในขณะนี้ (ข้ามการตรวจสอบ)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Cyan
if ($allPortsFree) {
    Write-Host " ปิดระบบเรียบร้อย ทุกพอร์ตว่างแล้ว" -ForegroundColor Cyan
} else {
    Write-Host " ปิดระบบบางส่วนไม่สำเร็จ ดูรายละเอียดสีแดงด้านบน" -ForegroundColor Cyan
}
Write-Host "=======================================================" -ForegroundColor Cyan
