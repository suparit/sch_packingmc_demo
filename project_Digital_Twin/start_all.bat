@echo off
REM ==========================================================================
REM  start_all.bat - Digital Twin launcher (3 modes)
REM
REM  Console text is ASCII on purpose: this machine's console is cp874 and a
REM  .bat saved as UTF-8 breaks cmd parsing. Thai stays where it belongs -
REM  every child window gets "chcp 65001" so the python Thai logs render fine.
REM
REM  Usage:
REM    start_all.bat                 interactive menu
REM    start_all.bat 1               mode 1 - full demo, operator presses PASS/NG
REM    start_all.bat 2               mode 2 - mode 1 + OpenMV vision sends DECISION
REM    start_all.bat 3               mode 3 - light: gateway_fsm.py + web only
REM    start_all.bat 1 --kill        auto-answer YES to "kill busy port owner"
REM    start_all.bat 1 --nokill      auto-answer NO  - skip whatever is blocked
REM    start_all.bat 1 --write       allow Modbus coil writes (asks to confirm)
REM    start_all.bat 1 --nopause     do not pause at the end (for scripting)
REM
REM  Every prompt also accepts piped input:   echo y | start_all.bat 1
REM
REM  Overridable environment variables:
REM    DT_SIM_DIR  folder holding simulator.exe
REM    DT_CAM_DIR  folder holding app_vision.py and .venv
REM    DT_CAM_COM  COM port of the OpenMV camera (default COM10)
REM ==========================================================================
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1

set "ROOT=%~dp0"
set "BOARD_IP=192.168.0.100"
set "RUST_EXE=%ROOT%rust_bridge\target\debug\rust_modbus_bridge.exe"
if not defined DT_SIM_DIR set "DT_SIM_DIR=%ROOT%..\Digital-Twin-Taping Machine\NOXCORE\Appli\TouchGFX\build\bin\"
if not defined DT_CAM_DIR set "DT_CAM_DIR=%ROOT%..\Digital-Twin-Taping Machine\Cam\"
if not defined DT_CAM_COM set "DT_CAM_COM=COM10"
set "WEB_URL=http://localhost:8000/index1.html"

REM ---- argument parsing -----------------------------------------------------
set "MODE="
set "KILL_ANS="
set "ALLOW_WRITE=0"
set "NOPAUSE=0"
:argloop
if "%~1"=="" goto args_done
if "%~1"=="1" set "MODE=1"
if "%~1"=="2" set "MODE=2"
if "%~1"=="3" set "MODE=3"
if /i "%~1"=="--kill"    set "KILL_ANS=y"
if /i "%~1"=="--nokill"  set "KILL_ANS=n"
if /i "%~1"=="--write"   set "ALLOW_WRITE=1"
if /i "%~1"=="--nopause" set "NOPAUSE=1"
shift
goto argloop
:args_done

echo.
echo ==========================================================================
echo   DIGITAL TWIN - SMD REEL TAPING MACHINE    ^|    start_all.bat
echo ==========================================================================

if not defined MODE (
  echo.
  echo   [1] FULL DEMO     rust_bridge + gateway_fsm_upgrad + web + HMI simulator
  echo                     operator presses PASS / NG on the HMI
  echo   [2] VISION TEST   same as mode 1, plus Cam\app_vision.py
  echo                     the OpenMV camera sends DECISION instead of a human
  echo   [3] LIGHT         gateway_fsm.py + web server only
  echo                     no rust bridge, no simulator, no board I/O
  echo.
  set /p "MODE=Select mode [1/2/3]: "
)
if "%MODE%"=="1" goto mode_ok
if "%MODE%"=="2" goto mode_ok
if "%MODE%"=="3" goto mode_ok
echo.
echo   [ERROR] invalid mode "%MODE%" - expected 1, 2 or 3.
goto the_end
:mode_ok

set "MODE_NAME=FULL DEMO"
if "%MODE%"=="2" set "MODE_NAME=VISION TEST"
if "%MODE%"=="3" set "MODE_NAME=LIGHT"
echo.
echo   Mode %MODE% - %MODE_NAME%
echo.

REM ---- safety: Modbus coil write (0x0F) stays OFF unless asked for ----------
set "RO_FLAG=1"
if "%MODE%"=="3" goto safety_done
if "%ALLOW_WRITE%"=="0" goto safety_done
echo   ##################################################################
echo   #  WARNING - you passed --write                                  #
echo   #  rust_modbus_bridge would send Write Multiple Coils 0x0F to    #
echo   #  the REAL board at %BOARD_IP%. The firmware on that       #
echo   #  board has NO source backup on this PC - overwrite it and it   #
echo   #  cannot be rebuilt. Continue only if you are sure.             #
echo   ##################################################################
set "WCONF="
set /p "WCONF=Type WRITE in capitals to allow coil writes: "
if /i "%WCONF%"=="WRITE" (
  set "RO_FLAG=0"
  echo   -^> coil writes ENABLED for this run.
) else (
  echo   -^> not confirmed. Staying READ-ONLY.
)
:safety_done
if not "%MODE%"=="3" if "%RO_FLAG%"=="1" echo   [SAFETY] RUST_READ_ONLY=1 - read-only run, no coil write reaches the board.
echo.

REM ==========================================================================
REM  PRE-FLIGHT CHECKS
REM  Anything missing gets skipped with a printed reason. The launcher itself
REM  must never abort because one piece is absent.
REM ==========================================================================
echo --------------------------------------------------------------------------
echo  PRE-FLIGHT CHECKS
echo --------------------------------------------------------------------------

set "ST_RUST="
set "ST_GW="
set "ST_WEB="
set "ST_SIM="
set "ST_CAM="
set "ST_SER="
set "ST_BROWSER=not opened"

REM -- python ----------------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
  echo  [FAIL] python not found in PATH - every python component will be skipped
  set "ST_GW=SKIPPED - python not found in PATH"
  set "ST_WEB=SKIPPED - python not found in PATH"
  set "ST_SER=SKIPPED - python not found in PATH"
) else (
  for /f "tokens=*" %%v in ('python -V 2^>^&1') do echo  [ OK ] python in PATH - %%v
)

REM -- rust bridge exe -------------------------------------------------------
if "%MODE%"=="3" (
  set "ST_RUST=NOT USED - mode 3 runs without the rust bridge"
) else (
  if exist "%RUST_EXE%" (
    echo  [ OK ] rust_modbus_bridge.exe found
  ) else (
    echo  [SKIP] rust_modbus_bridge.exe NOT found at %RUST_EXE%
    echo         build it first:  cd rust_bridge   then   cargo build
    set "ST_RUST=SKIPPED - exe missing. Build it: cd rust_bridge then cargo build"
  )
)

REM -- board reachability ----------------------------------------------------
if not "%MODE%"=="3" (
  ping -n 1 -w 1000 %BOARD_IP% | findstr /C:"TTL=" >nul
  if errorlevel 1 (
    echo  [WARN] no ping reply from %BOARD_IP%
    echo         the rust bridge still starts, but values come back tagged
    echo         [SIM] instead of [REAL] until the board answers.
  ) else (
    echo  [ OK ] board %BOARD_IP% answers ping
  )
)

REM -- TouchGFX simulator ----------------------------------------------------
if "%MODE%"=="3" (
  set "ST_SIM=NOT USED - mode 3 runs headless, no HMI simulator"
) else (
  if exist "%DT_SIM_DIR%simulator.exe" (
    echo  [ OK ] TouchGFX simulator.exe found
  ) else (
    echo  [SKIP] simulator.exe NOT found in %DT_SIM_DIR%
    set "ST_SIM=SKIPPED - simulator.exe not found. Rebuild the TouchGFX simulator"
  )
)

REM -- vision app, mode 2 only -----------------------------------------------
if not "%MODE%"=="2" (
  set "ST_CAM=NOT USED - the vision app only runs in mode 2"
) else (
  call :check_vision
)

REM -- ST-LINK VCP for serial_bridge.py --------------------------------------
REM  serial_bridge.py feeds the HMI on the PHYSICAL board over UART. Modes 1
REM  and 2 are the "real hardware" modes so it belongs there; mode 3 is the
REM  deliberately hardware-free mode, so it is left out on purpose.
if "%MODE%"=="3" (
  set "ST_SER=NOT USED - mode 3 is the hardware-free mode"
) else (
  if not defined ST_SER call :check_stlink
)

REM ---- port availability ---------------------------------------------------
echo.
echo --------------------------------------------------------------------------
echo  PORT CHECK
echo --------------------------------------------------------------------------
set "BUSY_LIST="
set "BUSY_PIDS="
set "P8765="
set "P8766="
set "P8767="
set "P8000="

call :check_port 8765 P8765 "websocket - gateway to web page"
call :check_port 8766 P8766 "tcp - HMI link"
if not "%MODE%"=="3" call :check_port 8767 P8767 "tcp - rust bridge"
call :check_port 8000 P8000 "http - web server"

if defined BUSY_LIST call :handle_busy_ports

REM -- map ports that are STILL busy onto the component that has to be skipped
if defined P8765 if not defined ST_GW   set "ST_GW=SKIPPED - port 8765 still held by PID %P8765%"
if defined P8766 if not defined ST_GW   set "ST_GW=SKIPPED - port 8766 still held by PID %P8766%"
if defined P8767 if not defined ST_RUST set "ST_RUST=SKIPPED - port 8767 still held by PID %P8767%. Gateway will talk to that one"
if defined P8000 if not defined ST_WEB  set "ST_WEB=SKIPPED - port 8000 still held by PID %P8000%. Reusing that web server"

REM ==========================================================================
REM  LAUNCH - order matters: rust listens on 8767, the gateway is its client
REM ==========================================================================
echo.
echo --------------------------------------------------------------------------
echo  LAUNCHING
echo --------------------------------------------------------------------------

REM -- 1) rust bridge, must be up BEFORE the gateway -------------------------
if not defined ST_RUST (
  set "RO_TXT=READ-ONLY"
  if "%RO_FLAG%"=="0" set "RO_TXT=WRITE ENABLED"
  echo  [1] rust_modbus_bridge  listens on 8767   !RO_TXT!
  start "DT-RUST-BRIDGE 8767" /D "%ROOT%rust_bridge" cmd /k "chcp 65001>nul&set RUST_READ_ONLY=%RO_FLAG%&target\debug\rust_modbus_bridge.exe"
  set "ST_RUST=STARTED - window DT-RUST-BRIDGE 8767, RUST_READ_ONLY=%RO_FLAG%"
  REM it dials the board first, give it a moment before 8767 opens
  ping -n 4 127.0.0.1 >nul
) else (
  echo  [1] rust_modbus_bridge  %ST_RUST%
)

REM -- 2) gateway -------------------------------------------------------------
if not defined ST_GW (
  if "%MODE%"=="3" (
    echo  [2] gateway_fsm.py      listens on 8765 + 8766
    start "DT-GATEWAY 8765-8766 fsm" /D "%ROOT%python_backend" cmd /k "chcp 65001>nul&python gateway_fsm.py"
    set "ST_GW=STARTED - gateway_fsm.py, window DT-GATEWAY 8765-8766 fsm"
  ) else (
    echo  [2] gateway_fsm_upgrad.py  RUST_BRIDGE=1  listens on 8765 + 8766
    start "DT-GATEWAY 8765-8766 upgrad+rust" /D "%ROOT%python_backend" cmd /k "chcp 65001>nul&set RUST_BRIDGE=1&python gateway_fsm_upgrad.py"
    set "ST_GW=STARTED - gateway_fsm_upgrad.py RUST_BRIDGE=1, window DT-GATEWAY 8765-8766 upgrad+rust"
  )
  ping -n 4 127.0.0.1 >nul
) else (
  echo  [2] gateway             %ST_GW%
)

REM -- 3) web server ----------------------------------------------------------
if not defined ST_WEB (
  echo  [3] http.server         port 8000, serving the cad folder
  start "DT-WEB 8000" /D "%ROOT%" cmd /k "chcp 65001>nul&python -m http.server 8000 -d cad"
  set "ST_WEB=STARTED - window DT-WEB 8000, serving cad"
  ping -n 3 127.0.0.1 >nul
) else (
  echo  [3] http.server         %ST_WEB%
)

REM -- 4) TouchGFX simulator --------------------------------------------------
if not defined ST_SIM (
  echo  [4] simulator.exe       HMI screen, connects out to 8766
  start "DT-HMI-SIMULATOR" /D "%DT_SIM_DIR%" "%DT_SIM_DIR%simulator.exe"
  set "ST_SIM=STARTED - TouchGFX simulator.exe"
) else (
  echo  [4] simulator.exe       %ST_SIM%
)

REM -- 5) serial bridge to the HMI on the physical board ----------------------
if not defined ST_SER (
  echo  [5] serial_bridge.py    UART !STLINK! to tcp 8766
  start "DT-SERIAL-BRIDGE board HMI" /D "%ROOT%python_backend" cmd /k "chcp 65001>nul&python serial_bridge.py"
  set "ST_SER=STARTED - window DT-SERIAL-BRIDGE board HMI on !STLINK!"
) else (
  echo  [5] serial_bridge.py    %ST_SER%
)

REM -- 6) vision app ----------------------------------------------------------
if not defined ST_CAM (
  echo  [6] app_vision.py       %DT_CAM_COM% camera, sends DECISION to 8765
  start "DT-VISION OpenMV %DT_CAM_COM%" /D "%DT_CAM_DIR%" cmd /k "chcp 65001>nul&.venv\Scripts\python.exe app_vision.py"
  set "ST_CAM=STARTED - window DT-VISION OpenMV %DT_CAM_COM%, venv python"
) else (
  echo  [6] app_vision.py       %ST_CAM%
)

REM -- 7) browser -------------------------------------------------------------
echo  [7] browser             %WEB_URL%
start "" "%WEB_URL%"
set "ST_BROWSER=OPENED - %WEB_URL%"

REM ==========================================================================
REM  SUMMARY
REM ==========================================================================
echo.
echo ==========================================================================
echo   SUMMARY - mode %MODE% - %MODE_NAME%
echo ==========================================================================
echo   rust bridge   : %ST_RUST%
echo   gateway       : %ST_GW%
echo   web server    : %ST_WEB%
echo   HMI simulator : %ST_SIM%
echo   serial bridge : %ST_SER%
echo   vision app    : %ST_CAM%
echo   browser       : %ST_BROWSER%
echo --------------------------------------------------------------------------
if not "%MODE%"=="3" (
  if "%RO_FLAG%"=="1" (
    echo   SAFETY        : RUST_READ_ONLY=1 - the board is only being READ.
  ) else (
    echo   SAFETY        : RUST_READ_ONLY=0 - COIL WRITES TO THE BOARD ARE LIVE.
  )
)
echo   Ports listening right now:
netstat -ano -p TCP | findstr /R /C:":8765 " /C:":8766 " /C:":8767 " /C:":8000 " | findstr LISTENING
echo --------------------------------------------------------------------------
echo   Shut everything down with:  stop_all.bat
echo ==========================================================================

:the_end
if "%NOPAUSE%"=="1" goto :eof
pause
goto :eof


REM ==========================================================================
REM  SUBROUTINES
REM ==========================================================================

REM  :check_port <port> <out_var> <label>
REM  Sets <out_var> to the listening PID, empty when the port is free, and
REM  appends to BUSY_LIST / BUSY_PIDS.
:check_port
set "CP_PID="
for /f "tokens=5" %%a in ('netstat -ano -p TCP ^| findstr /R /C:":%~1 " ^| findstr LISTENING') do set "CP_PID=%%a"
if defined CP_PID (
  echo  [BUSY] port %~1  %~3  - owned by PID !CP_PID!
  set "%~2=!CP_PID!"
  set "BUSY_LIST=!BUSY_LIST! %~1"
  echo !BUSY_PIDS! | findstr /C:" !CP_PID! " >nul || set "BUSY_PIDS=!BUSY_PIDS! !CP_PID! "
) else (
  echo  [FREE] port %~1  %~3
  set "%~2="
)
goto :eof


REM  :handle_busy_ports - ask once for every busy port, then re-check
:handle_busy_ports
echo.
echo  [BUSY] ports already taken:%BUSY_LIST%
echo         owner PIDs:%BUSY_PIDS%
if not defined KILL_ANS (
  set "KILL_ANS=n"
  set /p "KILL_ANS=Kill those owners and take the ports over? [y/N]: "
) else (
  echo         answer supplied on the command line: %KILL_ANS%
)
if /i not "%KILL_ANS%"=="y" (
  echo         leaving the existing processes alone - whatever needs those
  echo         ports will be skipped below.
  goto :eof
)
for %%p in (%BUSY_PIDS%) do (
  echo         killing PID %%p ...
  taskkill /F /T /PID %%p >nul 2>&1
)
REM close leftover console windows from an earlier start_all run
taskkill /F /FI "WINDOWTITLE eq DT-*" >nul 2>&1
REM let Windows release the sockets
ping -n 3 127.0.0.1 >nul
set "BUSY_LIST="
set "BUSY_PIDS="
set "P8765="
set "P8766="
set "P8767="
set "P8000="
echo         re-checking ports...
call :check_port 8765 P8765 "websocket - gateway to web page"
call :check_port 8766 P8766 "tcp - HMI link"
if not "%MODE%"=="3" call :check_port 8767 P8767 "tcp - rust bridge"
call :check_port 8000 P8000 "http - web server"
goto :eof


REM  :check_vision - app_vision.py needs its own venv python plus the camera
:check_vision
set "CAM_FAIL="
if not exist "%DT_CAM_DIR%app_vision.py" set "CAM_FAIL=app_vision.py not found in %DT_CAM_DIR%"
if defined CAM_FAIL goto check_vision_report
if not exist "%DT_CAM_DIR%.venv\Scripts\python.exe" set "CAM_FAIL=Cam venv missing. Rebuild: py -m venv .venv then .venv\Scripts\pip install opencv-python numpy pyserial websocket-client"
if defined CAM_FAIL goto check_vision_report
set "COM_OK=0"
for /f %%i in ('powershell -NoProfile -Command "if ([System.IO.Ports.SerialPort]::getportnames() -contains '%DT_CAM_COM%') {1} else {0}" 2^>nul') do set "COM_OK=%%i"
if not "%COM_OK%"=="1" set "CAM_FAIL=%DT_CAM_COM% is not present - the OpenMV camera is unplugged or powered off"
:check_vision_report
if defined CAM_FAIL (
  echo  [SKIP] vision app - %CAM_FAIL%
  echo         mode 2 keeps running without it: press PASS / NG on the HMI by hand.
  set "ST_CAM=SKIPPED - %CAM_FAIL%"
) else (
  echo  [ OK ] app_vision.py + Cam venv + %DT_CAM_COM% all present
)
goto :eof


REM  :check_stlink - find the ST-LINK virtual COM port used by serial_bridge.py
:check_stlink
set "STLINK="
for /f "tokens=*" %%i in ('powershell -NoProfile -Command "$d=Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match 'STLink' -and $_.Name -match 'COM' } | Select-Object -First 1; if ($d) { [regex]::Match($d.Name,'COM\d+').Value }" 2^>nul') do set "STLINK=%%i"
if defined STLINK (
  echo  [ OK ] ST-LINK virtual COM port found - %STLINK%
) else (
  echo  [SKIP] no ST-LINK virtual COM port - the board USB cable is not connected
  echo         serial_bridge.py only feeds the HMI on the physical board,
  echo         everything else in this mode still works.
  set "ST_SER=SKIPPED - no ST-LINK COM port, board USB not connected"
)
goto :eof
