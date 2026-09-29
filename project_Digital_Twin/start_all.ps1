# =====================================================================
# start_all.ps1
#
# จุดเริ่มต้นสำหรับเปิดระบบ Taping Machine Digital Twin — มี 2 โหมด เรียกผ่าน -Mode:
#
#   -Mode web   (START_WEB.bat)  : Gateway + เว็บ 3D เท่านั้น เป็นโหมดจำลองล้วน ๆ
#                                  ไม่แตะพอร์ต COM ใด ๆ ทั้งสิ้น (ไม่ตรวจ ไม่เชื่อมต่อ
#                                  จอ HMI ไม่เปิดกล้อง) ใช้เป็น diagnostic baseline
#
#   -Mode full  (START_FULL.bat) : Gateway + เว็บ 3D + จอ HMI (auto-detect STM32) + กล้อง
#
# กล้องเลือกด้วย -Camera (เฉพาะโหมด full):
#   hikrobot (ค่าเริ่มต้น) : ocr\app_vision_ocr.py ใช้ venv 03_Vision\.venv-ocr หน้าผลที่ :5000
#   openmv                 : app_vision.py ใช้ venv 03_Vision\.venv ผ่านพอร์ต COM (ของเดิม)
# กล้อง HIKROBOT ห้าม kill โปรเซส (กล้องค้างจนต้องถอดสาย USB) — stop_all.ps1 จึงปิดด้วยการ
# สร้างไฟล์ ocr\STOP ให้แอปปิดกล้องเองอย่างถูกวิธี
#
# เรียงลำดับตอน full: 1) Gateway + เว็บ 3D  2) จอ HMI (STM32 ผ่าน serial)  3) กล้อง
# ทำไมต้องเรียงลำดับแบบนี้: ทั้งจอ HMI และกล้องเป็น "ลูกค้า" ที่เชื่อมต่อเข้าหา
# Gateway ผ่าน WebSocket/Serial ดังนั้น Gateway ต้องพร้อมก่อนเสมอ ไม่เช่นนั้น
# ทั้งสองอย่างจะเชื่อมต่อไม่ติดตั้งแต่แรก
#
# สคริปต์นี้ไม่ได้ยิงคำสั่งอะไรใหม่เองสำหรับ Gateway/เว็บ/จอ HMI — งานนั้นให้
# 01_DigitalTwin\run_demo.ps1 เป็นเจ้าของ (มันมีระบบติดตาม PID ของมันเองอยู่แล้ว)
# ส่วนที่ไฟล์นี้เพิ่มเข้ามาคือ: เลือกโหมด, ตรวจหาพอร์ต COM ให้อัตโนมัติ (เฉพาะโหมด full),
# เปิด/ปิดกล้อง (เฉพาะโหมด full), และสรุปผลรวมทั้งหมดให้อ่านง่าย
# =====================================================================

[CmdletBinding()]
param(
    # web  = Gateway + เว็บเท่านั้น ห้ามแตะพอร์ต COM เด็ดขาด (diagnostic baseline)
    # full = ของเดิมทั้งหมด: auto-detect จอ HMI + serial bridge + กล้อง
    [Parameter(Mandatory = $true)]
    [ValidateSet("web", "full")]
    [string]$Mode,

    # เลือกกล้อง (มีผลเฉพาะ -Mode full)
    #   hikrobot = กล้อง HIKROBOT + PaddleOCR (03_Vision\ocr\app_vision_ocr.py) — ค่าเริ่มต้นตั้งแต่ 23 ก.ย. 2026
    #   openmv   = กล้อง OpenMV เดิมที่ต่อผ่าน COM (03_Vision\app_vision.py) — เก็บไว้เผื่อย้อนกลับ
    [ValidateSet("hikrobot", "openmv")]
    [string]$Camera = "hikrobot",

    # พอร์ต COM ของกล้อง OpenMV (ปกติคือ COM6) ใช้เฉพาะ -Camera openmv
    # กล้อง HIKROBOT ต่อ USB3 Vision ผ่าน MVS SDK ไม่มีพอร์ต COM
    [string]$CameraPort = "COM6",

    # เลือกเวอร์ชัน Gateway (standard = ปกติ, upgraded = FSM รุ่นใหม่)
    [ValidateSet("standard", "upgraded")]
    [string]$Gateway = "standard"
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
. (Join-Path $RepoRoot "common_launcher.ps1")

$DigitalTwinDir = Join-Path $RepoRoot "01_DigitalTwin"
$RunDemo        = Join-Path $DigitalTwinDir "run_demo.ps1"
$DtStateFile    = Join-Path $DigitalTwinDir ".digital-twin-run.json"
$CamDir         = Join-Path $RepoRoot "03_Vision"
$CamStateFile   = Join-Path $RepoRoot ".camera-run.json"
$DashboardUrl   = "http://127.0.0.1:8000/index1.html"   # เว็บเดิม — ใช้เป็นตัวสำรองถ้าเว็บใหม่ไม่ขึ้น
# เว็บ Digital Twin ตัวใหม่ของ Tontikorn (Next.js) — ค่าตั้งต้นตั้งแต่ 27 ก.ย. 2569 ต่อ gateway เดียวกันทาง WS 8765
$WebNextDir       = Join-Path $RepoRoot "dt-taping-dev\web_next"
$WebNextStateFile = Join-Path $RepoRoot ".web-next-run.json"
$WebNextUrl       = "http://localhost:5173/twin"
$VisionInput    = if ($Mode -eq "full") { "camera" } else { "simulated" }
$IoBoardHost   = "192.168.0.100" # SCH_XPLCV1 Modbus/TCP I/O board — เขียนเอาต์พุตจริง (ไฟ/โซลินอยด์/Cylinder C/มอเตอร์ feed) ไม่ใช่ monitor-only

Write-Host "=======================================================" -ForegroundColor Cyan
if ($Mode -eq "web") {
    Write-Host " เริ่มระบบ Taping Machine Digital Twin" -ForegroundColor Cyan
    Write-Host " โหมด: WEB ONLY (จำลองอย่างเดียว ไม่แตะฮาร์ดแวร์ใด ๆ)" -ForegroundColor Cyan
} else {
    Write-Host " เริ่มระบบ Taping Machine Digital Twin" -ForegroundColor Cyan
    Write-Host " โหมด: FULL (พร้อมฮาร์ดแวร์เต็มรูปแบบ)" -ForegroundColor Cyan
}
Write-Host "=======================================================" -ForegroundColor Cyan
if ($Mode -eq "web") {
    Write-Host " โหมดนี้เปิด Gateway + เว็บ 3D เท่านั้น เป็นการจำลอง (simulation) ล้วน ๆ" -ForegroundColor Gray
    Write-Host " จะไม่แตะพอร์ต COM ใด ๆ ทั้งสิ้น -- ไม่ตรวจหาบอร์ด ไม่เชื่อมต่อจอ HMI ไม่เปิดกล้อง" -ForegroundColor Gray
    Write-Host " ใช้โหมดนี้เพื่อแยกปัญหา: ถ้า FSM ทำงานปกติตอนไม่มีฮาร์ดแวร์เสียบเลย แปลว่าปัญหา" -ForegroundColor Gray
    Write-Host " อยู่ที่บอร์ด/สาย ถ้ายังมีปัญหาเหมือนเดิม แปลว่าปัญหาอยู่ใน gateway_fsm.py" -ForegroundColor Gray
}
Write-Host ""

# ----------------------------------------------------------------
# ขั้นที่ 1/3: Gateway + เว็บ 3D (+ จอ HMI ถ้าเป็นโหมด full และพบบอร์ด STM32)
# ----------------------------------------------------------------
Write-Host "[1/4] Gateway + เว็บ 3D$(if ($Mode -eq 'full') { ' + จอ HMI' })" -ForegroundColor Yellow

$dtStateRecord = Read-JsonStateFile -Path $DtStateFile
$dtAlreadyRunning = $false
if ($dtStateRecord) {
    foreach ($record in @($dtStateRecord.Processes)) {
        if (Test-OwnedProcessAlive -Record $record) { $dtAlreadyRunning = $true; break }
    }
}

$gatewayOk = $false
$hardwareSummary = ""

if ($dtAlreadyRunning) {
    # ตรวจว่าระบบที่รันอยู่จริง ๆ ตอนนี้เป็นโหมดไหน (serial bridge หรือกล้องมีชีวิตอยู่ไหม)
    # เพื่อเตือนผู้ใช้ตรง ๆ ถ้าโหมดที่เรียกกับโหมดที่รันอยู่จริงไม่ตรงกัน แทนที่จะเงียบ
    $serialAlive = $false
    foreach ($record in @($dtStateRecord.Processes)) {
        if ($record.Role -eq "serial" -and (Test-OwnedProcessAlive -Record $record)) { $serialAlive = $true }
    }
    $camAliveNow = [bool](Test-OwnedProcessAlive -Record (Read-JsonStateFile -Path $CamStateFile))
    $actualModeText = if ($serialAlive -or $camAliveNow) { "FULL (มีจอ HMI และ/หรือกล้องเชื่อมต่ออยู่)" } else { "WEB ONLY (ไม่มีฮาร์ดแวร์เชื่อมต่อ)" }

    Write-Host "      ระบบกำลังทำงานอยู่แล้วจากการรันครั้งก่อน ในโหมด: $actualModeText" -ForegroundColor DarkYellow
    Write-Host "      ข้ามการเริ่มใหม่ เพื่อไม่ให้เกิดโปรแกรมซ้ำซ้อน" -ForegroundColor DarkYellow

    if ($Mode -eq "web" -and ($serialAlive -or $camAliveNow)) {
        Write-Host "      หมายเหตุ: คุณเรียก START_WEB.bat แต่ระบบที่รันอยู่ตอนนี้เป็นโหมด FULL" -ForegroundColor DarkYellow
        Write-Host "      ถ้าต้องการทดสอบโหมด WEB ONLY จริง ๆ (ไม่แตะฮาร์ดแวร์) ให้รัน STOP.bat ก่อนแล้วค่อยรัน START_WEB.bat ใหม่" -ForegroundColor DarkYellow
    } elseif ($Mode -eq "full" -and -not ($serialAlive -or $camAliveNow)) {
        Write-Host "      หมายเหตุ: คุณเรียก START_FULL.bat แต่ระบบที่รันอยู่ตอนนี้เป็นโหมด WEB ONLY" -ForegroundColor DarkYellow
        Write-Host "      ถ้าต้องการฮาร์ดแวร์จริง ๆ ให้รัน STOP.bat ก่อนแล้วค่อยรัน START_FULL.bat ใหม่" -ForegroundColor DarkYellow
    }

    $gatewayOk = $true
    $hardwareSummary = "ของเดิมที่รันอยู่ก่อนแล้ว (โหมดจริง: $actualModeText)"
} elseif ($Mode -eq "web") {
    Write-Host "      โหมด WEB ONLY: ข้ามการตรวจหาบอร์ดโดยตั้งใจ จะไม่แตะพอร์ต COM ใด ๆ เลย" -ForegroundColor Gray
    try {
        & $RunDemo start -Gateway $Gateway -Hardware none -VisionInput $VisionInput
        # หมายเหตุ: run_demo.ps1 ไม่ได้ตั้งรหัส exit ที่ชัดเจนตอน start สำเร็จ (ต่างจากตอน stop/status)
        # จึงใช้หลักการว่า "ถ้าไม่มี exception หลุดออกมา แปลว่าสำเร็จ" แทนการเช็ค $LASTEXITCODE
        $gatewayOk = $true
        $hardwareSummary = "ปิดโดยตั้งใจ (โหมด WEB ONLY ไม่แตะฮาร์ดแวร์เลย)"
        Write-Host "      Gateway + เว็บ 3D พร้อมใช้งานแล้ว (ไม่มีจอ HMI/กล้อง)" -ForegroundColor Green
    } catch {
        $gatewayOk = $false
        $hardwareSummary = "ไม่มี (เว็บล้มเหลว)"
        Write-Host "      เริ่ม Gateway/เว็บ ไม่สำเร็จ: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "      (สาเหตุที่พบบ่อย: พอร์ต 8000/8765/8766 ถูกใช้งานอยู่ก่อนแล้วโดยโปรแกรมอื่น ลองรัน STOP.bat แล้วเช็คด้วย" -ForegroundColor Red
        Write-Host "       powershell -File 01_DigitalTwin\run_demo.ps1 status)" -ForegroundColor Red
    }
} else {
    $stmPort = Get-STM32DisplayPort
    $hwArgs = @{}
    if ($stmPort) {
        Write-Host "      พบบอร์ดจอแสดงผล STM32 ที่พอร์ต $stmPort -> เปิดจอ HMI + I/O monitor" -ForegroundColor Green
        $hwArgs = @{ Hardware = "serial-rust"; SerialPort = $stmPort; IoHost = $IoBoardHost }
        $hardwareSummary = "จอ HMI จริงผ่าน $stmPort"
    } else {
        Write-Host "      ไม่พบบอร์ด STM32 -- รันโหมดจำลองอย่างเดียว (software-only)" -ForegroundColor DarkYellow
        Write-Host "      (ถ้าคาดว่าควรมีบอร์ด ให้เช็คสาย USB แล้วลองใหม่ ดูวิธีตรวจใน 06_Docs\HOWTO_RUN.md)" -ForegroundColor DarkYellow
        $hwArgs = @{ Hardware = "rust"; IoHost = $IoBoardHost }
        $hardwareSummary = "ไม่มี (ไม่พบบอร์ด)"
    }

    try {
        & $RunDemo start -Gateway $Gateway @hwArgs -VisionInput $VisionInput
        $gatewayOk = $true
        Write-Host "      Gateway + เว็บ 3D พร้อมใช้งานแล้ว" -ForegroundColor Green
    } catch {
        $gatewayOk = $false
        Write-Host "      เริ่ม Gateway/เว็บ ไม่สำเร็จ: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "      (สาเหตุที่พบบ่อย: พอร์ต 8000/8765/8766 ถูกใช้งานอยู่ก่อนแล้วโดยโปรแกรมอื่น ลองรัน STOP.bat แล้วเช็คด้วย" -ForegroundColor Red
        Write-Host "       powershell -File 01_DigitalTwin\run_demo.ps1 status)" -ForegroundColor Red
    }
}
Write-Host ""

# ----------------------------------------------------------------
# ขั้นที่ 2/3: กล้อง (HIKROBOT: ocr\app_vision_ocr.py / OpenMV: app_vision.py) -- เฉพาะโหมด full
# ----------------------------------------------------------------
Write-Host "[2/4] กล้องตรวจสอบชิ้นงาน$(if ($Mode -eq 'full') { " ($Camera)" })" -ForegroundColor Yellow

$cameraSummary = ""

if ($Mode -eq "web") {
    Write-Host "      โหมด WEB ONLY: ข้ามกล้องโดยตั้งใจ จะไม่แตะพอร์ต COM ใด ๆ เลย" -ForegroundColor Gray
    $cameraSummary = "ข้าม (โหมด WEB ONLY ไม่เปิดกล้องโดยการออกแบบ)"
} else {
    $camStateRecord = Read-JsonStateFile -Path $CamStateFile
    $camAliveProc = Test-OwnedProcessAlive -Record $camStateRecord

    if ($camAliveProc) {
        Write-Host "      กล้องกำลังทำงานอยู่แล้ว (PID $($camAliveProc.Id)) -- ข้ามการเริ่มใหม่" -ForegroundColor DarkYellow
        $cameraSummary = "ทำงานอยู่แล้ว (PID $($camAliveProc.Id))"
    } elseif (-not $gatewayOk) {
        Write-Host "      ข้ามการเปิดกล้อง เพราะ Gateway ยังไม่พร้อม (กล้องต้องต่อกับ Gateway ผ่าน WebSocket)" -ForegroundColor DarkYellow
        $cameraSummary = "ข้าม (Gateway ยังไม่พร้อม)"
    } elseif ($Camera -eq "hikrobot") {
        # กล้อง HIKROBOT ต่อ USB3 Vision ไม่มีพอร์ต COM ให้ตรวจก่อนเปิด — ถ้ากล้องยังไม่เสียบ
        # app_vision_ocr.py จะลองเปิดใหม่ทุก 2 วินาทีเอง (หน้า :5000 ขึ้น CAMERA RECONNECTING)
        # จึงตรวจเฉพาะสิ่งที่ทำให้ "เปิดไม่ได้แน่นอน" ก่อน: venv, roi.json และโปรแกรม MVS ที่แย่งกล้อง
        $camPython = Join-Path $CamDir ".venv-ocr\Scripts\python.exe"
        $ocrDir    = Join-Path $CamDir "ocr"
        $mvsProc   = @(Get-Process -Name "MVS" -ErrorAction SilentlyContinue)
        if (-not (Test-Path -LiteralPath $camPython -PathType Leaf)) {
            Write-Host "      ไม่พบ venv ของกล้องที่ 03_Vision\.venv-ocr\Scripts\python.exe -- ข้ามการเปิดกล้อง" -ForegroundColor DarkYellow
            Write-Host "      (วิธีติดตั้งดู 03_Vision\ocr\README.md หัวข้อ 'การติดตั้ง')" -ForegroundColor DarkYellow
            $cameraSummary = "ข้าม (ไม่พบ venv-ocr)"
        } elseif (-not (Test-Path -LiteralPath (Join-Path $ocrDir "roi.json") -PathType Leaf)) {
            Write-Host "      ยังไม่มี 03_Vision\ocr\roi.json -- ข้ามการเปิดกล้อง" -ForegroundColor DarkYellow
            Write-Host "      (รัน ocr_roi.py --select เลือกกรอบก่อน ดู 03_Vision\ocr\README.md)" -ForegroundColor DarkYellow
            $cameraSummary = "ข้าม (ไม่มี roi.json)"
        } elseif ($mvsProc.Count -gt 0) {
            Write-Host "      โปรแกรม MVS เปิดอยู่ (PID $($mvsProc[0].Id)) -- กล้องเปิดได้ทีละโปรแกรม ข้ามการเปิดกล้อง" -ForegroundColor DarkYellow
            Write-Host "      (ปิด MVS แล้วรัน START_FULL.bat ใหม่ ส่วนอื่นของระบบทำงานต่อได้ตามปกติ)" -ForegroundColor DarkYellow
            $cameraSummary = "ข้าม (MVS เปิดอยู่ แย่งกล้อง)"
        } else {
            Write-Host "      กำลังเริ่มกล้อง HIKROBOT + OCR (โหลดโมเดลราว 10 วินาที)..." -ForegroundColor Green
            $oldPythonUtf8 = $env:PYTHONUTF8
            try {
                $env:PYTHONUTF8 = "1"   # path มีอักษรไทย + สคริปต์พิมพ์ข้อความไทย/อีโมจิ

                # ลบไฟล์ STOP ที่อาจค้างจากรอบก่อน ไม่งั้นแอปจะปิดตัวเองทันทีที่เข้าลูป
                Remove-Item -LiteralPath (Join-Path $ocrDir "STOP") -Force -ErrorAction SilentlyContinue

                $psi = New-Object System.Diagnostics.ProcessStartInfo
                $psi.FileName = $camPython
                $psi.Arguments = '"ocr\app_vision_ocr.py"'
                $psi.WorkingDirectory = $CamDir
                $psi.UseShellExecute = $true
                # ไม่ย่อหน้าต่าง: ต้องเห็น log ตอนโหลดโมเดล/เปิดกล้อง และกด Ctrl+C ปิดได้เอง
                $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
                $camProcess = [System.Diagnostics.Process]::Start($psi)

                # รอจนเว็บ :5000 ขึ้น (แอปเปิดเว็บหลังโหลดโมเดลเสร็จ) หรือจนโปรเซสตาย สูงสุด 60 วินาที
                # เคยเช็คแค่ 3 วินาทีแล้วรายงานว่าสำเร็จ ทั้งที่แอปตายตอนโหลดโมเดลทีหลัง (23 ก.ย. 2026)
                $deadline = (Get-Date).AddSeconds(60)
                $webUp = $false
                while ((Get-Date) -lt $deadline -and -not $camProcess.HasExited) {
                    if (@(Get-PortListenerOwners -Port 5000).Count -gt 0) { $webUp = $true; break }
                    Start-Sleep -Milliseconds 1000
                }
                if (-not $camProcess.HasExited -and -not $webUp) {
                    Write-Host "      โปรแกรมกล้องยังไม่เปิดเว็บ :5000 ภายใน 60 วินาที -- ดู log ในหน้าต่างของโปรแกรมกล้อง" -ForegroundColor DarkYellow
                }
                if ($camProcess.HasExited) {
                    Write-Host "      โปรแกรมกล้องหยุดทำงานทันทีหลังเปิด (exit code $($camProcess.ExitCode))" -ForegroundColor Red
                    Write-Host "      ลองรันด้วยมือเพื่อดู error เต็ม ๆ: cd 03_Vision ; .\.venv-ocr\Scripts\python.exe ocr\app_vision_ocr.py" -ForegroundColor Red
                    $cameraSummary = "ล้มเหลว (ปิดตัวเองทันที ดู error ด้วยการรันมือ)"
                } else {
                    $camState = [pscustomobject]@{
                        Id                = $camProcess.Id
                        StartTimeUtcTicks = $camProcess.StartTime.ToUniversalTime().Ticks
                        Executable        = $camPython
                        Camera            = "hikrobot"
                        StopFile          = (Join-Path $ocrDir "STOP")
                        StartedAtUtc      = (Get-Date).ToUniversalTime().ToString("o")
                    }
                    $camState | ConvertTo-Json | Set-Content -LiteralPath $CamStateFile -Encoding UTF8
                    Write-Host "      กล้องเริ่มทำงานแล้ว PID $($camProcess.Id) -- ดูผลตรวจที่ http://127.0.0.1:5000" -ForegroundColor Green
                    $cameraSummary = "HIKROBOT ทำงานอยู่ (PID $($camProcess.Id)) ผลตรวจที่ :5000"
                }
            } catch {
                Write-Host "      เริ่มโปรแกรมกล้องไม่สำเร็จ: $($_.Exception.Message)" -ForegroundColor Red
                $cameraSummary = "ล้มเหลว: $($_.Exception.Message)"
            } finally {
                $env:PYTHONUTF8 = $oldPythonUtf8
            }
        }
    } else {
        $camPython = Join-Path $CamDir ".venv\Scripts\python.exe"
        if (-not (Test-Path -LiteralPath $camPython -PathType Leaf)) {
            Write-Host "      ไม่พบ Python venv ของกล้องที่ 03_Vision\.venv\Scripts\python.exe -- ข้ามการเปิดกล้อง" -ForegroundColor DarkYellow
            Write-Host "      (ต้องสร้าง venv และ pip install -r 03_Vision\requirements.txt ก่อน ดู 06_Docs\HOWTO_RUN.md)" -ForegroundColor DarkYellow
            $cameraSummary = "ข้าม (ไม่พบ venv ของกล้อง)"
        } else {
            $portStatus = Get-ComPortStatus -PortName $CameraPort
            if ($portStatus -eq "absent") {
                Write-Host "      ไม่พบกล้อง -- ไม่มีอุปกรณ์เสียบอยู่ที่พอร์ต $CameraPort -- ข้ามการเปิดกล้อง" -ForegroundColor DarkYellow
                Write-Host "      (ระบบส่วนอื่นยังทำงานต่อได้ตามปกติ ต่อกล้องแล้วรัน START_FULL.bat ใหม่เมื่อพร้อม)" -ForegroundColor DarkYellow
                $cameraSummary = "ข้าม (ไม่พบอุปกรณ์ที่ $CameraPort)"
            } elseif ($portStatus -eq "busy") {
                Write-Host "      พอร์ต $CameraPort ถูกใช้งานอยู่ก่อนแล้วโดยโปรแกรมอื่น -- ข้ามการเปิดกล้อง" -ForegroundColor DarkYellow
                Write-Host "      (ปิดโปรแกรมที่เปิดพอร์ตนี้ค้างอยู่ เช่น Arduino IDE Serial Monitor แล้วลองใหม่)" -ForegroundColor DarkYellow
                $cameraSummary = "ข้าม (พอร์ต $CameraPort ถูกใช้งานอยู่)"
            } else {
                Write-Host "      พบกล้องที่พอร์ต $CameraPort -- กำลังเริ่มโปรแกรมกล้อง..." -ForegroundColor Green
                $oldPythonUtf8 = $env:PYTHONUTF8
                try {
                    $env:PYTHONUTF8 = "1"   # กันปัญหา UnicodeEncodeError จากข้อความไทย/อีโมจิที่สคริปต์กล้องพิมพ์ออกมา

                    $psi = New-Object System.Diagnostics.ProcessStartInfo
                    $psi.FileName = $camPython
                    $psi.Arguments = '"app_vision.py"'
                    $psi.WorkingDirectory = $CamDir
                    $psi.UseShellExecute = $true
                    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Minimized
                    $camProcess = [System.Diagnostics.Process]::Start($psi)

                    Start-Sleep -Milliseconds 1200
                    if ($camProcess.HasExited) {
                        Write-Host "      โปรแกรมกล้องหยุดทำงานทันทีหลังเปิด (exit code $($camProcess.ExitCode))" -ForegroundColor Red
                        Write-Host "      ลองรันด้วยมือเพื่อดู error เต็ม ๆ: cd 03_Vision ; .\.venv\Scripts\python.exe app_vision.py" -ForegroundColor Red
                        $cameraSummary = "ล้มเหลว (ปิดตัวเองทันที ดู error ด้วยการรันมือ)"
                    } else {
                        $camState = [pscustomobject]@{
                            Id                = $camProcess.Id
                            StartTimeUtcTicks = $camProcess.StartTime.ToUniversalTime().Ticks
                            Executable        = $camPython
                            Camera            = "openmv"
                            Port              = $CameraPort
                            StartedAtUtc      = (Get-Date).ToUniversalTime().ToString("o")
                        }
                        $camState | ConvertTo-Json | Set-Content -LiteralPath $CamStateFile -Encoding UTF8
                        Write-Host "      กล้องเริ่มทำงานแล้ว PID $($camProcess.Id) (จะมีหน้าต่างวิดีโอ 2 บานเปิดขึ้นมา)" -ForegroundColor Green
                        $cameraSummary = "ทำงานอยู่ (PID $($camProcess.Id))"
                    }
                } catch {
                    Write-Host "      เริ่มโปรแกรมกล้องไม่สำเร็จ: $($_.Exception.Message)" -ForegroundColor Red
                    $cameraSummary = "ล้มเหลว: $($_.Exception.Message)"
                } finally {
                    $env:PYTHONUTF8 = $oldPythonUtf8
                }
            }
        }
    }
}
Write-Host ""

# ----------------------------------------------------------------
# ขั้นที่ 3/4: เว็บ Digital Twin ตัวใหม่ (dt-taping-dev\web_next · Next.js dev server :5173)
# ----------------------------------------------------------------
# ไม่เรียก START_WEB.bat ของเพื่อน — ตัวเลือก 2 ในนั้นเปิด gateway ของเพื่อน ชนพอร์ต 8765 กับ gateway ของเรา
# โหมด full + มีบอร์ด: หน้า /twin ขึ้น LIVE + แถบแดง "ต่อบอร์ดจริง" = ปุ่มบนเว็บสั่งเครื่องจริง
Write-Host "[3/4] เว็บ Digital Twin ตัวใหม่ (web_next :5173)" -ForegroundColor Yellow
$webNextOk = $false
$webNextSummary = "ไม่ได้เปิด (Gateway ไม่พร้อม)"
if ($gatewayOk) {
    try {
        if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
            throw "ไม่พบ Node.js — ติดตั้งรุ่น LTS จาก https://nodejs.org แล้วเปิดใหม่"
        }
        # โมเดล 3D ไม่เข้า git — ใช้ไฟล์เดียวกับเว็บเดิม (26 MB)
        $glbDst = Join-Path $RepoRoot "dt-taping-dev\cad\export\Machine.glb"
        if (-not (Test-Path -LiteralPath $glbDst -PathType Leaf)) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $glbDst) | Out-Null
            Copy-Item -LiteralPath (Join-Path $DigitalTwinDir "cad\export\Machine.glb") -Destination $glbDst
            Write-Host "      คัดลอกโมเดล Machine.glb ให้เว็บใหม่แล้ว" -ForegroundColor Gray
        }
        if (-not (Test-Path -LiteralPath (Join-Path $WebNextDir "node_modules\next"))) {
            Write-Host "      ครั้งแรก: ติดตั้งแพ็กเกจ (npm install ประมาณ 1-3 นาที ต้องมีอินเทอร์เน็ต) ..." -ForegroundColor Gray
            Push-Location -LiteralPath $WebNextDir
            try {
                & npm.cmd install --no-fund --no-audit | Out-Host
                if ($LASTEXITCODE -ne 0) { throw "npm install ล้มเหลว — เช็กอินเทอร์เน็ตแล้วลองใหม่" }
            } finally { Pop-Location }
        }
        if (@(Get-PortListenerOwners -Port 5173).Count -gt 0) {
            Write-Host "      พอร์ต 5173 มีเว็บเปิดอยู่แล้ว -- ใช้ตัวเดิม" -ForegroundColor DarkYellow
        } else {
            # หน้าต่างย่อไว้ (ชื่อ DT-web-next) — ปิดด้วย STOP.bat · ใช้ Start-Process เพราะ cmd /c start กับ path ไทยเงียบไม่เปิดอะไร
            $webProc = Start-Process -FilePath "cmd.exe" -ArgumentList '/k', 'title DT-web-next & npm run dev' `
                -WorkingDirectory $WebNextDir -WindowStyle Minimized -PassThru
            [pscustomobject]@{
                Id                = $webProc.Id
                StartTimeUtcTicks = $webProc.StartTime.ToUniversalTime().Ticks
                Executable        = "cmd.exe (npm run dev)"
                StartedAtUtc      = (Get-Date).ToUniversalTime().ToString("o")
            } | ConvertTo-Json | Set-Content -LiteralPath $WebNextStateFile -Encoding UTF8
        }
        # รอจนหน้า /twin ตอบ — ครั้งแรกหลังเปิด Next.js คอมไพล์หน้า ~10-30 วินาที
        $deadline = (Get-Date).AddSeconds(90)
        while ((Get-Date) -lt $deadline) {
            try {
                Invoke-WebRequest -Uri $WebNextUrl -UseBasicParsing -TimeoutSec 15 | Out-Null
                $webNextOk = $true
                break
            } catch { Start-Sleep -Seconds 1 }
        }
        if ($webNextOk) {
            Write-Host "      เว็บใหม่พร้อมแล้ว: $WebNextUrl" -ForegroundColor Green
            $webNextSummary = "พร้อมใช้งาน ($WebNextUrl)"
        } else {
            Write-Host "      เว็บใหม่ยังไม่ตอบภายใน 90 วินาที -- ดู error ในหน้าต่าง DT-web-next" -ForegroundColor Red
            $webNextSummary = "ไม่ตอบ (ดูหน้าต่าง DT-web-next) -- ใช้เว็บเดิมแทน"
        }
    } catch {
        Write-Host "      เปิดเว็บใหม่ไม่สำเร็จ: $($_.Exception.Message)" -ForegroundColor Red
        $webNextSummary = "ล้มเหลว -- ใช้เว็บเดิมแทน"
    }
}
Write-Host ""

# ----------------------------------------------------------------
# ขั้นที่ 4/4: เปิดหน้าเว็บแดชบอร์ด + สรุปผล
# ----------------------------------------------------------------
Write-Host "[4/4] สรุปผลและเปิดหน้าเว็บ" -ForegroundColor Yellow
if ($gatewayOk) {
    $openUrl = if ($webNextOk) { $WebNextUrl } else { $DashboardUrl }
    Write-Host "      เปิดเบราว์เซอร์ไปที่ $openUrl ..." -ForegroundColor Green
    Start-Process $openUrl
} else {
    Write-Host "      ไม่เปิดเบราว์เซอร์ เพราะเว็บยังไม่พร้อม (ดูสาเหตุด้านบน)" -ForegroundColor Red
}
Write-Host ""

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host " สรุปผลการเริ่มระบบ -- โหมด: $($Mode.ToUpper())" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ("  Gateway + เว็บ 3D : {0}" -f $(if ($gatewayOk) { "พร้อมใช้งาน" } else { "ล้มเหลว" }))
Write-Host ("  จอ HMI (STM32)    : {0}" -f $hardwareSummary)
Write-Host ("  กล้อง             : {0}" -f $cameraSummary)
Write-Host ("  เว็บใหม่ web_next  : {0}" -f $webNextSummary)
Write-Host ("  เว็บเดิม (สำรอง)   : {0}" -f $DashboardUrl)
if ($Mode -eq "full") {
    Write-Host ""
    Write-Host "  เริ่มในโหมดจำลอง: บอร์ดยังไม่ถูกสั่ง -- กดปุ่ม Sync บอร์ด บนหน้า /twin เพื่อสั่งเครื่องจริง" -ForegroundColor Yellow
}
Write-Host ""
if (-not $gatewayOk) {
    Write-Host "มีบางส่วนเริ่มไม่สำเร็จ กรุณาอ่านข้อความสีแดงด้านบนเพื่อแก้ไข" -ForegroundColor Red
    exit 1
}
exit 0
