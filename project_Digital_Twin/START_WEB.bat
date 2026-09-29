@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo โหมด: WEB ONLY (จำลองอย่างเดียว ไม่แตะฮาร์ดแวร์ใด ๆ)
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_all.ps1" -Mode web %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo กดปุ่มใด ๆ เพื่อปิดหน้าต่างนี้...
pause >nul

exit /b %EXIT_CODE%
