@echo off
REM ==========================================================================
REM  stop_all.bat - shut down everything start_all.bat opened, in one click
REM
REM  Order:
REM    1. close the DT-* console windows (kills the child process with them)
REM    2. kill whoever still listens on 8765 / 8766 / 8767 / 8000
REM    3. kill leftover simulator.exe / rust_modbus_bridge.exe
REM    4. kill leftover python processes belonging to this project only
REM       (matched by command line, so unrelated python is left alone)
REM    5. verify the four ports are actually free again
REM
REM  Usage:  stop_all.bat            or   stop_all.bat --nopause
REM  ASCII-only text on purpose - the console here is cp874.
REM ==========================================================================
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1

set "NOPAUSE=0"
if /i "%~1"=="--nopause" set "NOPAUSE=1"

echo.
echo ==========================================================================
echo   DIGITAL TWIN - stop_all.bat
echo ==========================================================================

echo.
echo  [1/5] closing DT-* console windows ...
taskkill /F /FI "WINDOWTITLE eq DT-*" /T >nul 2>&1
if errorlevel 1 (echo        nothing matched) else (echo        done)

echo.
echo  [2/5] killing whoever listens on 8765 / 8766 / 8767 / 8000 ...
call :kill_port 8765
call :kill_port 8766
call :kill_port 8767
call :kill_port 8000

echo.
echo  [3/5] killing leftover simulator.exe / rust_modbus_bridge.exe ...
call :kill_image simulator.exe
call :kill_image rust_modbus_bridge.exe

echo.
echo  [4/5] killing leftover project python processes ...
REM  matched by command line so someone else's python keeps running
powershell -NoProfile -Command "$t=Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'gateway_fsm|serial_bridge|app_vision|http\.server\s+8000' }; if ($t) { $t | ForEach-Object { Write-Host ('       killing PID ' + $_.ProcessId + ' - ' + $_.CommandLine.Trim()); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } } else { Write-Host '       none left' }" 2>nul

REM  give Windows a moment to release the sockets before verifying
ping -n 3 127.0.0.1 >nul

echo.
echo  [5/5] verifying the ports are free ...
set "STILL_BUSY="
call :verify_port 8765
call :verify_port 8766
call :verify_port 8767
call :verify_port 8000

echo.
echo ==========================================================================
if defined STILL_BUSY (
  echo   RESULT: ports still in use:%STILL_BUSY%
  echo   Something outside this project owns them, or it needs admin rights.
  echo   Look them up with:  netstat -ano ^| findstr LISTENING
) else (
  echo   RESULT: all four ports 8765 / 8766 / 8767 / 8000 are free. Clean stop.
)
echo ==========================================================================

if "%NOPAUSE%"=="1" goto :eof
pause
goto :eof


REM ==========================================================================
REM  SUBROUTINES
REM ==========================================================================

:kill_port
set "KP_PID="
for /f "tokens=5" %%a in ('netstat -ano -p TCP ^| findstr /R /C:":%~1 " ^| findstr LISTENING') do set "KP_PID=%%a"
if defined KP_PID (
  echo        port %~1 - killing PID !KP_PID!
  taskkill /F /T /PID !KP_PID! >nul 2>&1
) else (
  echo        port %~1 - already free
)
goto :eof

:kill_image
tasklist /FI "IMAGENAME eq %~1" 2>nul | findstr /I /C:"%~1" >nul
if errorlevel 1 (
  echo        %~1 - not running
) else (
  taskkill /F /IM "%~1" >nul 2>&1
  echo        %~1 - killed
)
goto :eof

:verify_port
set "VP_PID="
for /f "tokens=5" %%a in ('netstat -ano -p TCP ^| findstr /R /C:":%~1 " ^| findstr LISTENING') do set "VP_PID=%%a"
if defined VP_PID (
  echo        port %~1 - STILL BUSY, PID !VP_PID!
  set "STILL_BUSY=!STILL_BUSY! %~1"
) else (
  echo        port %~1 - free
)
goto :eof
