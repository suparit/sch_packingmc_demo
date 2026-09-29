@echo off
REM ==========================================================================
REM  STOP_WEB.bat - stop what START_WEB.bat opened (web server + gateway sim)
REM  ASCII-only text on purpose - this machine's console is cp874.
REM ==========================================================================
setlocal EnableExtensions
echo.
echo  closing DT-web-next / DT-gateway-sim windows ...
taskkill /F /FI "WINDOWTITLE eq DT-web-next*" /T >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq DT-gateway-sim*" /T >nul 2>&1

REM whoever still listens on 5173 (web) - the gateway port 8765 is left alone on purpose:
REM it may be a gateway you started yourself with start_all.bat
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":5173 .*LISTENING"') do (
  echo  killing pid %%p on port 5173
  taskkill /F /PID %%p >nul 2>&1
)
echo  done.
timeout /t 3 >nul
