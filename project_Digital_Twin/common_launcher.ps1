# =====================================================================
# common_launcher.ps1
# ฟังก์ชันช่วยเหลือที่ start_all.ps1 และ stop_all.ps1 ใช้ร่วมกัน
#
# ไฟล์นี้ไม่ได้ถูกออกแบบให้รันตรง ๆ — ให้ dot-source เข้าไปในสคริปต์อื่น เช่น
#   . (Join-Path $PSScriptRoot "common_launcher.ps1")
# =====================================================================

# ทำให้ Write-Host พิมพ์ภาษาไทยออกทาง console ได้ถูกต้อง (คอนโซลของ Windows
# เริ่มต้นมักใช้ code page 437/1252 ซึ่งไม่รองรับภาษาไทย)
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # ถ้าตั้งค่าไม่ได้ (เช่นถูกเรียกในบริบทที่ไม่มี console) ก็ปล่อยผ่าน ไม่ใช่ข้อผิดพลาดร้ายแรง
}

function Get-STM32DisplayPort {
    <#
        ค้นหาพอร์ต COM ของ "จอแสดงผล HMI" (บอร์ด STM32H7S78-DK) โดยอัตโนมัติ
        โดยมองหาอุปกรณ์ Plug-and-Play ที่ชื่อมีทั้งคำว่า STMicroelectronics และ STLink
        (Windows ตั้งชื่อพอร์ตนี้ว่า "STMicroelectronics STLink Virtual COM Port (COMn)")

        คืนค่า "COMn" ถ้าเจอ, หรือ $null ถ้าไม่เจอ
    #>
    $devices = @(Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match 'STMicroelectronics' -and
            $_.Name -match 'STLink' -and
            $_.Name -match 'COM(\d+)'
        })
    if ($devices.Count -gt 0) {
        $m = [regex]::Match($devices[0].Name, 'COM(\d+)')
        if ($m.Success) { return "COM$($m.Groups[1].Value)" }
    }
    return $null
}

function Get-ComPortStatus {
    <#
        ตรวจสอบสถานะของพอร์ต COM หนึ่งตัว คืนค่าเป็นสตริงอย่างใดอย่างหนึ่ง:
          "absent" - ไม่มีอุปกรณ์นี้เสียบอยู่ในเครื่องเลย (ต้องเสียบสาย/เปิดอุปกรณ์)
          "busy"   - มีอุปกรณ์เสียบอยู่ แต่มีโปรแกรมอื่นเปิดพอร์ตนี้ค้างไว้อยู่ก่อนแล้ว
          "ok"     - มีอุปกรณ์เสียบอยู่ และพอร์ตว่าง เปิดใช้งานได้
    #>
    param([Parameter(Mandatory)][string]$PortName)

    $present = @(Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match [regex]::Escape("($PortName)") })
    if ($present.Count -eq 0) { return "absent" }

    $sp = $null
    try {
        $sp = New-Object System.IO.Ports.SerialPort $PortName
        $sp.Open()
        $sp.Close()
        return "ok"
    } catch {
        return "busy"
    } finally {
        if ($sp) { $sp.Dispose() }
    }
}

function Get-PortListenerOwners {
    <# คืนรายการ PID ที่กำลัง LISTEN อยู่บนพอร์ต TCP ที่ระบุ (array ว่างถ้าไม่มี) #>
    param([Parameter(Mandatory)][int]$Port)

    $rows = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $Port })
    if ($rows.Count -gt 0) {
        return @($rows.OwningProcess | Sort-Object -Unique)
    }

    $netstatMatches = @(netstat -ano -p tcp | Select-String -Pattern (":" + $Port + "\s+.*LISTENING"))
    $result = @()
    foreach ($match in $netstatMatches) {
        $parts = ($match.Line.Trim() -split "\s+")
        if ($parts.Count -gt 0) { $result += [int]$parts[-1] }
    }
    return @($result | Sort-Object -Unique)
}

function Test-OwnedProcessAlive {
    <#
        ตรวจสอบ record ที่เคยบันทึกไว้ (Id + StartTimeUtcTicks) ว่ายังเป็น process
        ตัวเดิมที่ยังทำงานอยู่จริงหรือไม่ (ป้องกันกรณี Windows นำ PID เดิมไปให้โปรแกรมอื่น
        ใช้ต่อหลัง reboot หรือหลัง process เดิมตายไปแล้ว)

        คืนค่า System.Diagnostics.Process ถ้ายังมีชีวิตอยู่จริง มิฉะนั้นคืน $null
    #>
    param($Record)
    if (-not $Record) { return $null }
    $proc = Get-Process -Id ([int]$Record.Id) -ErrorAction SilentlyContinue
    if (-not $proc) { return $null }
    try {
        if ($proc.StartTime.ToUniversalTime().Ticks -ne [int64]$Record.StartTimeUtcTicks) { return $null }
    } catch {
        return $null
    }
    return $proc
}

function Read-JsonStateFile {
    <# อ่านไฟล์สถานะ JSON อย่างปลอดภัย คืน $null ถ้าไม่มีไฟล์หรืออ่านไม่ได้ #>
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try {
        return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
    } catch {
        return $null
    }
}
