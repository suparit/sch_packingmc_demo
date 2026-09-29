@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo โหมด: FULL (พร้อมฮาร์ดแวร์เต็มรูปแบบ)
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_all.ps1" -Mode full %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo กดปุ่มใด ๆ เพื่อปิดหน้าต่างนี้...
pause >nul

exit /b %EXIT_CODE%
