@echo off
REM ============================================================
REM  start_demo.bat - เปิดระบบ Digital Twin ครบชุดในคลิกเดียว
REM  1) gateway_fsm.py   (สมองกล FSM - พอร์ต 8765/8766)
REM  2) serial_bridge.py (สะพาน USB ไปจอบอร์ด STM32 - ถ้าเสียบบอร์ดไว้)
REM  3) Web server       (หน้าเว็บ 3D Twin - พอร์ต 8000)
REM ============================================================
cd /d "%~dp0"

echo [1/4] Starting FSM Gateway...
start "GATEWAY (FSM Core)" cmd /k "cd python_backend && python gateway_fsm.py"
timeout /t 2 >nul

echo [2/4] Starting Serial Bridge (STM32 board)...
start "SERIAL BRIDGE (STM32)" cmd /k "cd python_backend && python serial_bridge.py"

echo [3/4] Starting Web Server...
start "WEB SERVER (3D Twin)" cmd /k "python -m http.server 8000 -d cad"
timeout /t 2 >nul

echo [4/4] Opening Digital Twin dashboard...
start http://localhost:8000/index1.html

echo.
echo ============================================
echo  Ready! Close the 3 terminal windows to stop
echo  (or run: taskkill /F /IM python.exe)
echo ============================================
pause
