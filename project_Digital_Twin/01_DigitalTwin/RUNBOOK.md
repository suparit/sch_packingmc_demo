# Digital Twin runbook

## Component classification

| Component | Entrypoint | Machine status | Dependency |
|---|---|---|---|
| Standard FSM | `python_backend/gateway_fsm.py` | Runnable | Python + websockets |
| Upgraded FSM (virtual) | `python_backend/gateway_fsm_upgrad.py` | Runnable | Python + websockets; `RUST_BRIDGE=0` |
| Web/Three.js | `cad/index1.html` via HTTP server | Runnable | Browser; local HTTP 8000 |
| Analytics | `cad/analytics.html` | Runnable | Gateway WebSocket 8765 |
| Safe lifecycle | `run_demo.ps1` | Runnable | PowerShell 5.1+ |
| Rust bridge binary | `rust_bridge` | Runnable | Cargo/Rust; SCH_XPLCV1 Modbus/TCP input reader and FSM output LED display |
| TouchGFX simulator | `..\02_HMI_Firmware\Appli\TouchGFX` | Buildable/runnable | TouchGFX host toolchain; manual visual acceptance |
| Boot/Appli firmware | `..\02_HMI_Firmware\gcc` | Buildable | ARM GNU toolchain; hardware needed only for flash/runtime |
| STM32 serial HMI | `python_backend/serial_bridge.py` | Hardware-only runtime | ST-LINK VCP and UART 115200 |

Firmware paths above are relative to this file's location (`01_DigitalTwin\`) and resolve into
the sibling project `Wab\02_HMI_Firmware\`, which is what this checkout's ancestry calls
"NOXCORE" elsewhere (e.g. in `build_firmware.ps1` comments and STM32CubeIDE project metadata).

## Preflight

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_python.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 check
```

The command validates Python, websockets, optional pyserial, `pip check`, the web entrypoint, GLB v2 headers/lengths, and reports listeners on 8765/8766/8767/8000. `start` additionally requires every port it owns to be free.

## Software-only operation

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 start                 # standard gateway
# or
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 start -Gateway upgraded

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 status
```

Acceptance:

1. 8765 and 8766 are owned by the gateway; 8000 is owned by the web server.
2. `http://127.0.0.1:8000/index1.html` returns HTTP 200.
3. The event log reports WebSocket connection and the 3D machine model loads.
4. STOP/RESET may be tested in virtual mode. Do not enable a hardware bridge during software-only acceptance.

## Shutdown

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 stop
```

The launcher verifies PID plus process start time before stopping anything. It never searches for or kills every `python.exe`. If a PID was reused or a port belongs to another process, it skips that process and reports the condition. Use `status` to inspect before retrying.

## Serial HMI mode

Prerequisites: board isolated from motion, ST-LINK VCP visible, correct COM port confirmed, operator authorization.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 start -Hardware serial -SerialPort <HMI_COM>
```

Order: gateway → web → serial bridge. The bridge connects to gateway TCP 8766 and the board at 115200 baud. The launcher aborts and cleans up its own processes if the serial bridge exits during startup.

## Rust/Modbus I/O display mode

Prerequisites: Rust binary built, I/O board reachable over Modbus/TCP, board IP confirmed, and no physical loads connected to the output terminals. Full mode reads `IP0`/`IP1` and writes the FSM output image to `OP0`/`OP1` for LED display.

```powershell
cargo build --locked --manifest-path .\rust_bridge\Cargo.toml
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 start -Gateway standard -Hardware rust -IoHost <BOARD_IP>
```

Order: Rust listens on 8767 → standard gateway starts with `IO_MONITOR=1` → web starts. The SCH_XPLCV1 bridge sends `*IDN?` every second, waits 50 ms, and spaces Modbus requests by 20 ms. The web dashboard displays IP0, IP1, OP0, OP1 and I/O online/offline status. If the Rust listener does not appear, the launcher stops only the processes it started and reports failure.

Current mapping: OP0.0 Feed Carrier, OP0.1 Seal Process, OP0.2 Take-up Reel, OP0.3 Alarm; OP1 is unused. Do not connect motors, heaters, solenoids or other loads directly. Review the output mapping, driver/relay/SSR isolation and safety interlock before connecting physical loads.

## Build commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build_firmware.ps1 firmware          # Boot + Appli, generated assets
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build_firmware.ps1 simulator         # TouchGFX simulator, generated assets
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build_firmware.ps1 firmware-assets   # regenerate assets with bundled Ruby + firmware
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build_firmware.ps1 simulator-assets  # regenerate assets with bundled Ruby + simulator
```

`build_firmware.ps1` separates compiling from asset generation on purpose: the `-assets`
targets run `all`, which regenerates TouchGFX assets and therefore legitimately invokes Ruby
(the bundled TouchGFX Ruby, never a globally installed one). The plain targets only compile.

Corrected 2026-08-11: this section used to say the aggregate target was
`make -f gcc/Makefile build_executable`. There is no such target — `gcc/Makefile` forwards
only `all clean assets flash intflash` to `makefile_boot` and `makefile_appli`, so the
`firmware` target failed with "No rule to make target". Adding it to `gcc/Makefile` would not
work either: that wrapper invokes the sub-makefiles with `-C gcc/`, while the
`build_executable` rule inside them assumes the working directory is the application root.
`build_firmware.ps1` now calls `gcc/makefile_boot` and `gcc/makefile_appli` directly from the
application root instead. Verified only as far as target resolution (`make -n`); a full
firmware compile has not been run since the fix.

## Rebuild firmware from a fresh clone

A fresh clone does **not** contain everything the firmware build needs. Most of what is missing is
reproducible and is left out of git on purpose; one directory was being excluded by accident.

| Path | In git | Size | Where it comes from |
|---|---|---|---|
| `Appli/TouchGFX/assets/images/*.png` | yes, since 2026-08-11 | 5.4 MB | hand-made UI artwork — **not reproducible**, which is why it is tracked |
| `Appli/TouchGFX/assets/fonts/*.ttf`, `assets/texts/texts.xml` | yes | small | source assets |
| `Appli/TouchGFX/NOXCORE.touchgfx` | yes | 96 KB | the Designer project — the input everything else is generated from |
| `Appli/TouchGFX/generated/` | no | 143 MB | TouchGFX Designer, Generate Code |
| `Appli/TouchGFX/config/` | no | 5 KB | TouchGFX Designer, Generate Code |
| `Appli/Middlewares/ST/touchgfx/` | no | 128 MB | copied verbatim from the TouchGFX 4.26.1 installer |
| `Appli/Middlewares/ST/touchgfx_components/` | no | 2 MB | ditto, the `*_NemaP_m7_r01` variants, renamed |
| `Appli/TouchGFX/build/` | no | 264 MB | build output |

The rule applied here is: **what can be regenerated gets documented, what cannot gets committed.**
The `assets/images` PNGs are the one thing on this list that no tool can recreate, and the global
`*.png` rule in the root `.gitignore` was silently excluding them. They are now exempted there,
next to the existing `06_Docs` exemption.

Checked on 2026-08-11: `Middlewares/ST/touchgfx` is byte-identical to `C:\TouchGFX\4.26.1\touchgfx`
(`diff -rq` reports no differing files — the installer only carries extra Cortex variants this
project does not use), and `touchgfx_components/gpu2d/NemaGFX` / `TouchGFXNema` are byte-identical
to the installer's `NemaGFX_NemaP_m7_r01` / `TouchGFXNema_NemaP_m7_r01`. Nothing in either tree has
been hand-modified, so regenerating them loses nothing.

### Prerequisites

- **TouchGFX 4.26.1** (this machine: `C:\TouchGFX\4.26.1`) — supplies the Designer, the middleware,
  and a bundled MinGW/MSYS carrying make, Ruby 3.0 and arm-none-eabi-gcc
- **STM32CubeIDE 2.1.1** (this machine: `C:\ST\STM32CubeIDE_2.1.1`) — `build_firmware.ps1` takes
  `arm-none-eabi-gcc` from here, not from the TouchGFX copy
- **STM32CubeProgrammer** (this machine: the default location under `C:\Program Files`) — needed
  only to flash, not to build. The external loader `MX66UW1G45G_STM32H7S78-DK.stldr` ships with it.

The version numbers matter. TouchGFX regenerates `generated/` against the middleware it ships with,
so a different TouchGFX version produces a project that no longer matches this one.

### Step 0 — the build path must not contain non-ASCII characters

The repository normally lives at `D:\Work\<Thai folder name>\Wab`. The bundled MSYS make cannot
handle the Thai directory name: it splits the path at that component and fails with
`D:/Work/: Permission denied` followed by `/Wab/...: No such file or directory`. This hits the
firmware and the simulator equally, and no 8.3 short name is available on that volume to work
around it.

Map an ASCII drive letter and build through that:

```powershell
subst W: "D:\Work\<Thai folder name>\Wab"   # once per Windows session
# ...build against W:\02_HMI_Firmware...
subst W: /D                                   # release when finished
```

`subst` is a per-session alias, not a copy, so there is still exactly one source of truth. Do not
work around this by copying the tree somewhere else — this project has already paid for duplicated
copies drifting apart.

### Step 1 — regenerate what is not in git

Open `02_HMI_Firmware/Appli/TouchGFX/NOXCORE.touchgfx` in TouchGFX Designer 4.26.1 and press
**Generate Code**. That recreates `generated/`, `config/`, and both `Middlewares/ST/touchgfx*`
trees. Nothing under `generated/` should ever be edited by hand — the Designer marks those files
read-only and overwrites them on every generate. Hand-written UI code belongs in
`Appli/TouchGFX/gui/`, which is tracked.

### Step 2 — build

Run the build commands above from `W:\01_DigitalTwin` so the script resolves the firmware through
the ASCII path. Use a `-assets` target after changing `texts.xml`, fonts or images; the plain
targets only recompile sources.

### Firmware backup before flashing

`RUNBOOK` already requires a recoverable backup before any flash. The images read back from the
board belong in `02_HMI_Firmware/firmware_backup/` with the date in the filename:

- internal flash (Boot): `0x08000000`, length `0x10000` (64 KB)
- external flash (Appli + fonts + texts + images): `0x70000000`, length `0x1810000` (~24 MB) —
  the highest address actually used is `0x7180F688`, from `readelf -S` on `target.elf`

Both are read with `STM32_Programmer_CLI -c port=SWD ap=1`, the external one additionally needing
`-el <path>\MX66UW1G45G_STM32H7S78-DK.stldr`. Reading the external flash loads the loader into SRAM
and therefore stops the running application; press NRST afterwards.

These `.bin` files stay out of git — the root `.gitignore` excludes `*.bin` everywhere, and a 24 MB
opaque blob per backup is not worth the repository growth. Copy them to the shared drive alongside
the project archive instead, and note the location here when that archive is set up.

## Repeatable integration tests

Stop the launcher, check 8765/8766, then run one combination at a time:

```powershell
cd .\python_backend\tests
..\..\.venv\Scripts\python.exe test_hmi_link.py gateway_fsm.py
..\..\.venv\Scripts\python.exe test_hmi_link.py gateway_fsm_upgrad.py
..\..\.venv\Scripts\python.exe test_ws.py gateway_fsm.py
..\..\.venv\Scripts\python.exe test_ws.py gateway_fsm_upgrad.py
```

## Hardware-only acceptance still required

- Confirm ST-LINK VCP identity and UART 115200 8-N-1 traffic.
- Visually inspect TouchGFX load screen, Settings keypad/save, PASS/NG overlay and Report page.
- Validate physical START/STOP/RESET and emergency-stop behavior with motion/output isolation.
- Validate Rust 8767 to STM32 Modbus 502 mapping and disconnect/reconnect behavior.
- Validate CSV/report/clear-log commands over the real UART bridge.
- Flash only under a separate approved procedure with a recoverable firmware backup.
