# Handoff Summary — SMD Packing Digital Twin + STM32 HMI

> อัปเดตล่าสุด: 2026-07-27 (รอบที่ 2)

## เป้าหมายโปรเจกต์

ระบบสาธิต Digital Twin เครื่องแพ็ก SMD reel แบบ 4 เลเยอร์:
```
[TouchGFX HMI บนบอร์ด STM32H7S78-DK] ↔ [Python FSM Gateway] ↔ [เว็บ Three.js 3D Twin]
                                              ↕
                                    [Rust Modbus Bridge → บอร์ดจริง (option)]
```
ควบคุมเครื่องจักรจำลอง (17-step FSM) ได้ทั้งจากจอ HMI บนบอร์ดจริงและจากเว็บ พร้อมกัน แบบ real-time สองทาง

## โครงสร้างไฟล์หลัก

**ฝั่ง Backend/Web** (`TestWab-main/`)
- `python_backend/hmi_link.py` — 🆕 **โมดูลกลาง**: TCP server 8766 คุยกับจอ TouchGFX (report / CSV / clear logs / alarm ledger) ใช้ร่วมกันทั้งสอง gateway
- `python_backend/gateway_fsm.py` — FSM loop + SQLite + WebSocket 8765 (ตัวมาตรฐาน ใช้ตัวนี้ถ้าไม่ต้องต่อบอร์ดจริง)
- `python_backend/gateway_fsm_upgrad.py` — เหมือนกันทุกอย่าง **บวก** สะพานไป Rust I/O Layer (พอร์ต 8767, เปิดด้วย `RUST_BRIDGE=1`)
- `python_backend/serial_bridge.py` — สะพาน UART↔TCP สำหรับจอบอร์ดจริง
- `cad/index1.html` — หน้าเว็บ 3D Digital Twin (Three.js) + ปุ่ม PASS/NG (`fsmDecision`)
- `cad/analytics.html` — หน้า Production Analytics
- `cad/gateway.py` — mock server ทดสอบ GUI เดี่ยว (ห้ามรันพร้อม gateway ตัวจริง พอร์ตชนกัน)
- `start_demo.bat` / `DEPLOY.md`

**ฝั่ง Firmware** (`NOXCORE/Appli/TouchGFX/`)
- `gui/src/load_screen/loadView.cpp` — หน้า splash ตอนเปิดเครื่อง (แถบโหลด 0-100% ใน 5 วินาที)
- `gui/src/mainscreen_screen/MainScreenView.cpp` — ปุ่ม Start/Stop/Reset + แป้นพิมพ์ตัวเลข + 🆕 overlay PASS/NG ของสเต็ป VISION
- `gui/src/settingsscreen_screen/SettingsScreenView.cpp` — แป้นพิมพ์ตัวเลข 10 ช่อง + 🆕 ปุ่ม SAVE PARAMS
- `gui/src/reportscreen_screen/ReportScreenView.cpp` — หน้ารายงาน + SQL Ledger real-time
- `gui/src/loginscreen_screen/LoginScreenView.cpp` — หน้า Login PIN 5 หลัก (`12345`)
- `gui/src/model/Model.cpp` — รับ/แกะ JSON จาก TCP (Simulator) หรือ UART (บอร์ดจริง)
- `Core/Src/uart_link.c` + `Core/Inc/uart_link.h` — UART4 driver

---

## 🔌 แผนผังพอร์ต (สำคัญ — เคยเป็นที่มาของบั๊กใหญ่)

| พอร์ต | ใคร listen | ใครต่อเข้า |
|---|---|---|
| 8765 (WebSocket) | gateway | `index1.html`, `analytics.html` |
| 8766 (TCP) | gateway (`hmi_link.py`) | จอ TouchGFX (Simulator ตรงๆ / บอร์ดจริงผ่าน `serial_bridge.py`) |
| 8767 (TCP) | `rust_bridge` | `gateway_fsm_upgrad.py` เมื่อตั้ง `RUST_BRIDGE=1` |

> เดิม `upgrad` ต่อออกไปที่ **8766** ซึ่งเป็นพอร์ตเดียวกับที่จอต่อเข้ามา → เป็น client ทั้งคู่ ต่อกันไม่ติด
> เปิด `upgrad` แล้วจอขึ้นเลข 0 หมดทุกช่อง ตอนนี้แยกเป็น 8766 (จอ) กับ 8767 (Rust) แล้ว
> **ถ้าจะใช้ Rust bridge ต้อง `cargo build` ใหม่** เพราะแก้ `PYTHON_BRIDGE_ADDR` ใน `rust_bridge/src/main.rs` เป็น 8767

## วิธีรัน

```bash
cd python_backend
python gateway_fsm.py                        # ปกติ
python gateway_fsm_upgrad.py                 # ตัวที่ซิงค์กับกล้อง/บอร์ดจริงได้ (ยังไม่ต่อ Rust)
set RUST_BRIDGE=1 && python gateway_fsm_upgrad.py   # + เปิดสะพานไปบอร์ดจริง
```
เลือกรันได้ทีละตัวเท่านั้น (ทั้งคู่ bind 8765 + 8766 เหมือนกัน)

---

## งานที่ทำในเซสชันล่าสุด (2026-07-27 รอบที่ 2)

### 1. แยก `hmi_link.py` ออกมาเป็นโมดูลกลาง ✅ ทดสอบผ่านแล้ว

ย้ายโค้ด TCP server ของจอทั้งก้อน (accept/แยกชนิด client/report/CSV/clear logs/alarm ledger)
ออกจาก `gateway_fsm.py` มาไว้ที่ `hmi_link.py` แล้วให้ทั้งสอง gateway `import` ตัวเดียวกัน
— แก้บั๊กครั้งเดียวได้ผลทั้งคู่ ไม่ต้องพอร์ตข้ามไฟล์อีก

โปรโตคอลของ 8766 (ไม่ได้เปลี่ยน แค่ย้ายที่อยู่):
- **live monitor** — จอต่อค้างไว้เงียบๆ → gateway stream JSON สถานะให้ทุก 20 ms
- **one-shot** — ต่อ → ยิงคำสั่ง → ปิด (ปุ่มกดทุกปุ่ม และ `REQ_REPORT_DATA` / `EXPORT_CSV` / `CLEAR_*`)
- แยกสองแบบด้วยการพักสายใหม่ไว้ 0.25 วิ ถ้าเงียบครบเวลา = live monitor

### 2. `gateway_fsm_upgrad.py` คุยกับจอ HMI ได้แล้ว ✅ ทดสอบผ่านแล้ว

- เปิด TCP server 8766 ผ่าน `hmi_link` เหมือน `gateway_fsm.py`
- ย้ายสะพาน Rust ไป 8767 + ปิดเป็นค่าเริ่มต้น (เปิดด้วย env `RUST_BRIDGE=1`) และเว้นจังหวะ retry 3 วิ
  ของเดิมพยายาม connect ใหม่ทุก 20 ms ตอนบอร์ดไม่ได้เสียบ
- เติมของที่ขาดจนเท่า `gateway_fsm.py`: `pitch`, `record_alarm()`, `REQ_REPORT_DATA`, `CLEAR_LOGS`, export CSV, `MODE`/`SPEED` จากจอ
- **แก้บั๊กกล้องทอยงานเสียรัวๆ**: ของเดิมเช็ค `step_allowed == True` ที่สเต็ป VISION → ทอยความน่าจะเป็นใหม่ทุก 20 ms ระหว่างรอคนกด เด้ง ALARM ~78% ภายใน 2 วินาที กด PASS แทบไม่ทัน ตอนนี้ทอยครั้งเดียวตอนกล้องตรวจเสร็จ (เหมือน `gateway_fsm.py`)

### 3. ปุ่ม PASS/NG บนจอ TouchGFX ✅ build ผ่าน / ⚠️ ยังไม่ได้ดูด้วยตา

เดิมมีแค่หน้าเว็บที่ส่ง `DECISION` ได้ → สั่ง START จากจออย่างเดียวแล้วเครื่องค้างที่ VISION ตลอดไป

- `hmi_link` ใส่คีย์ `step_allowed` ลงใน payload ที่ stream ให้จอ
- `Model.cpp` แกะคีย์นี้ → `ModelListener::onVisionGateChanged(bool)` (virtual ว่าง หน้าจออื่นไม่ต้องแก้)
- `MainScreenView` เด้ง overlay กล่องน้ำเงิน + ปุ่มเขียว **PASS** / แดง **NG** ยิง `{"action":"DECISION","value":true/false}`
- overlay ปิดเองเมื่อฝั่งเว็บกดตัดสินไปก่อน (payload กลับมาเป็น `step_allowed:false`)
- ⚠️ พิกัดข้อความบนปุ่มคำนวณจากฟอนต์ monospace ชิดขวาแบบเดา ๆ (`VG_*` บนหัวไฟล์) อาจต้องขยับหลังเห็นของจริง

### 4. ปุ่ม SAVE PARAMS บนหน้า Settings ✅ build ผ่าน / ⚠️ ยังไม่ได้ดูด้วยตา

- ผูก `BTN_Save` ด้วย `setAction()` ในโค้ด (Designer ไม่ได้ผูก Interaction ไว้)
- ยิงค่าทั้ง 10 ช่องเป็น `SET_PARAMS` ก้อนเดียว — gateway เอา `target_pieces` ไปใช้กับ FSM ตรงๆ ที่เหลือเก็บใน `system_data["machine_params"]` ให้หน้าเว็บ/รายงานใช้ต่อ
- **ไม่ส่ง `target_pieces` ถ้าค่าเป็น 0** เพราะ gateway ปัดขึ้นเป็น 1 แล้ว batch จะจบตั้งแต่ชิ้นแรก

### 5. แก้บั๊ก encoding ที่ทำให้รันเป็น background ไม่ได้ ✅ ทดสอบผ่านแล้ว

เติม `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` ท้าย import ทั้งสองไฟล์
ตอนนี้ redirect stdout ได้โดยไม่ตายด้วย `UnicodeEncodeError` (console ไทยเป็น cp874)
และข้อความ error ใน `hmi_link.start()` ไม่มี emoji แล้ว จะได้ไม่พังซ้อนแล้วรายงานผิดเป็น "bind 8766 ไม่ได้"

### 6. แก้เพิ่มระหว่างทาง

- รวมโค้ด `DECISION` ของ WebSocket กับของจอเป็นฟังก์ชัน `apply_decision()` ตัวเดียว
- `apply_decision()` ตอนกด NG จะจำ `last_state_before_alarm` ด้วย ของเดิมไม่จำ → กด RESET แล้วเด้งกลับไปสเต็ปค้างของ alarm ครั้งก่อน
- `RESET` ทั้งจากจอและจากเว็บ เคลียร์ `step_allowed` ด้วย ของเดิมค้างเป็น true ได้

---

## ✅ ผลทดสอบ (รันจริง ไม่ใช่แค่ compile)

สคริปต์เก็บไว้ที่ `python_backend/tests/` — รันซ้ำได้ทุกเมื่อ (สคริปต์เปิด/ปิด gateway ให้เอง ต้องไม่มี gateway ตัวอื่นรันค้างอยู่):

```bash
cd python_backend/tests
python test_hmi_link.py gateway_fsm.py          # จำลองจอ TouchGFX ด้วย TCP client
python test_hmi_link.py gateway_fsm_upgrad.py
python test_ws.py gateway_fsm.py                # ฝั่งเว็บ 3D Twin
python test_ws.py gateway_fsm_upgrad.py
```

รันผ่านครบทั้ง **สอง** gateway:

| ข้อทดสอบ | `gateway_fsm.py` | `gateway_fsm_upgrad.py` |
|---|---|---|
| ไม่ตายตอน stdout ถูก redirect | ✅ | ✅ |
| จอต่อ 8766 แล้วได้ payload สถานะ | ✅ | ✅ |
| payload มี `step_allowed` + `pitch` | ✅ | ✅ |
| `SET_PARAMS` จากจอ → broadcast กลับ | ✅ | ✅ |
| `START` จากจอ | ✅ | ✅ |
| หยุดรอ operator ที่ VISION จริง 2 วิ ไม่เด้ง ALARM | ✅ | ✅ |
| กด PASS จากจอแล้วเดินต่อ (`VISION → CHECK_TEMP`) | ✅ | ✅ |
| `REQ_REPORT_DATA` / `EXPORT_CSV` | ✅ | ✅ |
| WebSocket: START / VISION gate / DECISION / GET_HISTORY | ✅ | ✅ |
| `DECISION` ตอน FSM ไม่ได้รอ → ปฏิเสธ ไม่กระโดดสเต็ปมั่ว | ✅ | ✅ |

นอกจากนี้ยังรัน `simulator.exe` ตัวจริงคู่กับ `gateway_fsm_upgrad.py` แล้ว ขึ้น
`🔌 [TOUCHGFX LINK] : GUI CONNECTED (live monitor)` — จอต่อกับ upgrad ติดแล้วจริง

---

## กับดัก build ที่เจอซ้ำๆ (อ่านก่อนแก้โค้ด)

1. **`has no member named 'bind'`** — สร้างหน้าจอใหม่ใน Designer ทุกครั้งจะเจอ เพราะ Designer generate `newPresenter->bind(model)` แต่ไม่ generate เมธอด `bind()` ให้ ต้องเติมเองใน `XxxPresenter.hpp`:
   ```cpp
   class Model;                                  // forward declaration
   void bind(Model* m) { model = m; }            // public
   Model* model = nullptr;                       // private
   ```

2. **เมธอด `gotoXxxScreenNoTransition()` หายไปดื้อๆ** — Designer generate เมธอด `goto...` ให้เฉพาะ transition ที่มี Interaction ใช้งานจริง ตอนย้าย startup screen จาก LoginScreen ไป load เมธอด `gotoLoginScreenScreenNoTransition()` **หายทันที** ต้องเปลี่ยนไปใช้ `gotoLoginScreenScreenBlockTransition()` ที่ผูกกับปุ่ม `Yes_logout` บนหน้า logout แทน (เมธอดที่ผูกกับ Interaction จริงจะไม่หาย)

3. **ตัวเลขยาวโดนตัด** — Designer เรียก `resizeToCurrentText()` ทำให้กล่องกว้างเท่าข้อความตัวอย่าง (`"0"`, `"50"`, `"0 %"`) พอใส่เลขยาวขึ้นจะโดนตัด ต้องขยายกล่องเองใน `setupScreen()` (ดูตัวอย่าง `widenNumberBox()` ใน MainScreen/SettingsScreen)

4. **`Unicode::snprintf` ไม่รองรับ `%%`** — ต้องใช้ `snprintf` ปกติก่อน แล้ว `Unicode::fromUTF8` ตาม

5. `KP_X`/`KP_Y` ชนกับ macro ใน `wincrypt.h` → ใช้ชื่อ `KEYPAD_POS_X/Y`

6. Designer เปลี่ยนชื่อคลาสหน้า Report เป็น `ReportScreen*` (S ใหญ่) — ไฟล์ gui/ ต้องตามให้ตรง

7. `SOCKET sock` ต้องอยู่ใน `#if WIN32` เสมอ ไม่งั้นพังตอน build ลงบอร์ด (ARM ไม่มี winsock)

8. ปุ่มที่ Designer ไม่ได้ผูก Interaction ไว้ (เช่น `BTN_Save`) ผูกเองในโค้ดด้วย `setAction()` ได้เลย ไม่ต้องเปิด Designer

---

## วิธี build simulator จาก command line (ไม่ต้องเปิด Designer)

Designer อยู่ที่ `E:\TouchGFX\4.26.1` — toolchain อยู่ใน `env\MinGW`

```bash
export PATH="/e/TouchGFX/4.26.1/env/MinGW/bin:/e/TouchGFX/4.26.1/env/MinGW/msys/1.0/bin:$PATH"
export ADDITIONAL_LIBRARIES=ws2_32
cd "E:/work-TE-Project/test-HMI-STM32/NOXCORE/Appli/TouchGFX"
make -r -f generated/simulator/gcc/Makefile -s build_executable
```

- ต้องใช้ target `build_executable` **ไม่ใช่ `all`** เพราะ `all` จะไปเรียกขั้น `assets` ที่ต้องใช้ **ruby ซึ่งไม่ได้ติดตั้งบนเครื่องนี้** (Designer มี ruby ในตัว จึงกด Generate Code ได้ปกติ) — ข้ามได้เพราะ assets generate ไว้แล้ว จะต้องรันผ่าน Designer เฉพาะตอนแก้ texts/images
- ต้อง `export ADDITIONAL_LIBRARIES=ws2_32` เอง เพราะ flag `-r` ตัด export จาก Makefile แม่ ไม่งั้น link ไม่ผ่าน (undefined reference `_imp__socket` ฯลฯ)
- ปิด `simulator.exe` ก่อน build ไม่งั้น link ไม่ได้ (`Permission denied`)

---

## ปัญหาที่ยังค้าง / ยังไม่ได้ตรวจสอบ

- **งานฝั่งจอยังไม่ได้ดูด้วยตา** — ยืนยันได้แค่ว่า compile + link ผ่านสะอาด และจอต่อ gateway ติด
  - ที่ต้องดูด้วยตา: หน้า load เดิน 0-100%, แป้นพิมพ์บนหน้า Settings ทั้ง 10 ช่อง, **ตำแหน่ง/ขนาดของ overlay PASS/NG**, ปุ่ม SAVE PARAMS
  - ส่ง input เข้าหน้าต่าง SDL จากสคริปต์ไม่ได้ (คลิกไม่เข้า, `SetForegroundWindow` ก็ดึงหน้าต่างขึ้นมาไม่ได้) ต้องกด ▶ Run Simulator ใน Designer แล้วกดเอง
- **ยังไม่ได้ทดสอบ Rust bridge จริง** — แก้พอร์ตใน `main.rs` เป็น 8767 แล้ว แต่ยังไม่ได้ `cargo build` ใหม่ (`rust_modbus_bridge.exe` ที่มีอยู่ยังเป็นตัวเก่าที่ bind 8766 — ถ้ารันตัวเก่าคู่กับ gateway จะแย่งพอร์ตกับจอ)
- **โฟลเดอร์นี้ไม่ใช่ git repository** — ลิงก์ GitHub Pages `https://thanpisittha.github.io/TestWab/cad/index1.html` เป็นคนละชุดกับไฟล์ในเครื่อง การแก้ทั้งหมดยังไม่ถูก push
- ยังไม่ได้ทดสอบ CSV export (`SAVE DATA`) และ `CLEAR LOGS` บนจอบอร์ดจริงผ่าน UART (ทดสอบผ่านแค่ TCP ตอน dev)
- ค่าจาก SAVE PARAMS 9 ตัวที่ไม่ใช่ `target_pieces` ถูกเก็บใน `machine_params` เฉยๆ ยังไม่มีใครเอาไปใช้จริง (FSM ยังไม่อ่าน motor_speed/temperature ฯลฯ)

## ขั้นตอนต่อไปที่แนะนำ

1. **กด ▶ Run Simulator ดูด้วยตา** — เน้นที่ overlay PASS/NG (ขนาด/ตำแหน่งข้อความ) แล้วขยับค่า `VG_*` บนหัว `MainScreenView.cpp` ตามที่เห็น
2. ถ้าจะใช้บอร์ดจริง: `cd rust_bridge && cargo build` แล้วรันด้วย `RUST_BRIDGE=1`
3. ต่อ `machine_params` เข้ากับ FSM จริง (เช่น `motor_speed` → `speed_mul`, `temperature` → ช่วงที่ยอมรับใน `CHECK_TEMP`)
4. ถ้าจะ deploy ผ่าน GitHub Pages: ตั้งค่า git repo แล้ว push
