@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_all.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo กดปุ่มใด ๆ เพื่อปิดหน้าต่างนี้...
pause >nul

exit /b %EXIT_CODE%
