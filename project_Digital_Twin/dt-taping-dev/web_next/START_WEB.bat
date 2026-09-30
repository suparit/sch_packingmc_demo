@echo off
REM ==========================================================================
REM  START_WEB.bat - open the web_next Digital Twin site with one double-click
REM
REM  What it does:
REM    1. checks Node.js is installed
REM    2. runs "npm install" the first time (node_modules missing)
REM    3. starts the Next.js dev server on port 5173 in its own window
REM       (window title DT-web-next, so stop_all.bat / STOP_WEB.bat close it)
REM       - if 5173 is already serving, it just reuses it
REM    4. optional: starts the simulated gateway (python_backend\gateway_fsm.py,
REM       no real board) so /twin shows LIVE instead of DEMO
REM    5. waits until the page answers, then opens the browser
REM
REM  Usage:
REM    START_WEB.bat              menu (defaults to web only after 8 s)
REM    START_WEB.bat 1            web only          -> /twin runs the in-browser DEMO
REM    START_WEB.bat 2            web + gateway sim -> /twin is LIVE
REM    START_WEB.bat 1 twin       open /twin directly instead of the intro page
REM
REM  ASCII-only text on purpose - this machine's console is cp874.
REM ==========================================================================
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "PORT=5173"
set "URL=http://localhost:%PORT%/"
set "MODE=%~1"
if /i "%~2"=="twin" set "URL=http://localhost:%PORT%/twin"
if /i "%~1"=="twin" (set "MODE=" & set "URL=http://localhost:%PORT%/twin")

echo.
echo ==========================================================================
echo   DIGITAL TWIN - web_next   ^|   START_WEB.bat
echo ==========================================================================

REM ---- 1. Node.js -----------------------------------------------------------
where node >nul 2>&1
if errorlevel 1 (
  echo.
  echo  [X] Node.js not found. Install the LTS version from https://nodejs.org
  echo      then run this file again.
  goto end_pause
)
for /f "delims=" %%v in ('node -v') do echo  node %%v

REM ---- 2. first-time install ------------------------------------------------
if not exist "node_modules\next" (
  echo.
  echo  [..] first run: installing packages ^(npm install, 1-3 min^) ...
  call npm install --no-fund --no-audit
  if errorlevel 1 (
    echo  [X] npm install failed - check the internet connection and try again.
    goto end_pause
  )
)

REM ---- menu -----------------------------------------------------------------
if not defined MODE (
  echo.
  echo    1  web only            ^(/twin uses the in-browser DEMO simulator^)
  echo    2  web + gateway sim   ^(/twin is LIVE, gateway_fsm.py - no real board^)
  echo.
  choice /c 12 /t 8 /d 1 /n /m "  choose 1 or 2 [default 1 in 8 s]: "
  set "MODE=!errorlevel!"
)

REM ---- 3. web server --------------------------------------------------------
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo.
  echo  [OK] port %PORT% already serving - reusing it
) else (
  echo.
  echo  [..] starting web server on port %PORT% ^(window: DT-web-next^)
  start "DT-web-next" cmd /k "chcp 65001>nul & cd /d "%~dp0" & npm run dev"
)

REM ---- 4. optional gateway sim ----------------------------------------------
if "%MODE%"=="2" (
  netstat -ano | findstr /r /c:":8765 .*LISTENING" >nul
  if not errorlevel 1 (
    echo  [OK] port 8765 already has a gateway - reusing it
  ) else (
    where python >nul 2>&1
    if errorlevel 1 (
      echo  [!] python not found - skipping gateway, /twin will run the DEMO
    ) else (
      echo  [..] starting simulated gateway ^(window: DT-gateway-sim^)
      start "DT-gateway-sim" cmd /k "chcp 65001>nul & set PYTHONIOENCODING=utf-8 & cd /d "%~dp0..\python_backend" & python gateway_fsm.py"
    )
  )
)

REM ---- 5. wait for the page, then open the browser --------------------------
echo  [..] waiting for the site to answer ^(first load compiles, up to ~90 s^) ...
powershell -NoProfile -Command "for($i=0;$i -lt 90;$i++){try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 '%URL%' | Out-Null; exit 0}catch{Start-Sleep 1}}; exit 1"
if errorlevel 1 (
  echo  [!] the site did not answer in time - look at the DT-web-next window for errors.
  echo      Opening the browser anyway.
)
start "" "%URL%"

echo.
echo  [OK] opened %URL%
echo       intro page : http://localhost:%PORT%/
echo       test page  : http://localhost:%PORT%/twin
echo       other PCs / phone on the same Wi-Fi: see the "Network:" line in DT-web-next
echo       to stop: close the DT-web-next window, or run STOP_WEB.bat
echo.
timeout /t 6 >nul
exit /b 0

:end_pause
echo.
pause
exit /b 1
