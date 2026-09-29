@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo ปุ่มเดียวเปิดทุกอย่าง: gateway + เว็บใหม่ + จอ HMI + กล้อง + สายบอร์ด I/O
echo เริ่มในโหมดจำลองเสมอ -- กดปุ่ม Sync บอร์ด บนหน้าเว็บ /twin เพื่อสั่งเครื่องจริง
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_all.ps1" -Mode full %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo กดปุ่มใด ๆ เพื่อปิดหน้าต่างนี้...
pause >nul

exit /b %EXIT_CODE%
