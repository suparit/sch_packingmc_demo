# RUNBOOK — คู่มือรันระบบทั้งหมดพร้อมกัน

> **เอกสารนี้คือ "ของจริง"** — ทุกคำสั่งและทุกข้อความที่บอกว่าจะเห็นบนจอ มาจากการรัน
> กับฮาร์ดแวร์จริงเมื่อ **2026-08-05** ไม่ใช่ทฤษฎีหรือของที่คัดมาจากสเปก
> เขียนไว้ให้คนที่ **ไม่ได้อยู่ในห้องตอนรัน** อ่านแล้วทำตามได้ทีละบรรทัด

**เอกสารนี้ต่างจากของเดิมยังไง**

| ไฟล์ | ครอบคลุมอะไร |
|---|---|
| [`DEPLOY.md`](../DEPLOY.md) | **ติดตั้งเครื่องใหม่ครั้งแรก** — ลง Python / ไดรเวอร์ ST-LINK / ก๊อปโฟลเดอร์ |
| [`docs/USER_MANUAL.md`](USER_MANUAL.md) | **ตั้งค่า Static IP** ให้การ์ดแลน + **วิธีกดปุ่มบนหน้าเว็บ** (Start / Stop / Reset) |
| **RUNBOOK.md (ไฟล์นี้)** | **เปิดครบทั้ง 5 ชั้นพร้อมกัน** พร้อมของจริงที่ต้องเห็นในแต่ละชั้น + วิธีปิด + กับดัก |

ถ้ายังไม่เคยตั้ง Static IP `192.168.0.22/24` ให้การ์ด USB-to-LAN
ไปทำที่ [`USER_MANUAL.md` ข้อ 3](USER_MANUAL.md) ก่อน แล้วค่อยกลับมาที่ไฟล์นี้

---

## 1. เช็คก่อนเริ่ม — ห้ามข้าม

**สาเหตุอันดับหนึ่งที่รันแล้วไม่ขึ้นคือมีของเก่าค้างพอร์ตอยู่** ไม่ใช่โค้ดพัง
ตรวจก่อนเสมอ (รันใน Git Bash):

```bash
netstat -ano | grep -E ":8765|:8766|:8767|:8000"
```

- **ไม่มีบรรทัดขึ้นเลย** = สะอาด เริ่มได้
- **มีบรรทัดขึ้น** = มีของค้าง → ไปทำ [ข้อ 4 วิธีปิดระบบ](#4-วิธีปิดระบบ) ก่อน แล้วเช็คซ้ำ

ถ้าอยู่ใน PowerShell ใช้บรรทัดนี้แทน:

```powershell
netstat -ano | Select-String ":8765|:8766|:8767|:8000"
```

### กติกาข้อเดียวที่ห้ามลืม

**รัน gateway ได้ทีละตัวเท่านั้น** — `gateway_fsm.py` กับ `gateway_fsm_upgrad.py`
bind พอร์ต **8765 + 8766 ชุดเดียวกัน** เปิดพร้อมกันไม่ได้
ใน RUNBOOK นี้เราใช้ **`gateway_fsm_upgrad.py`** เพราะเป็นตัวเดียวที่ต่อ Rust bridge ได้

---

## 2. ลำดับการเปิด 5 ชั้น

เปิด **เรียงตามลำดับนี้** แต่ละชั้นใช้หน้าต่าง Terminal ของตัวเอง (เปิดทิ้งไว้ ห้ามปิด)
**ทุกชั้นมีหัวข้อ "สำเร็จแล้วจะเห็นอะไร" — ถ้าไม่เห็นอย่าเดินต่อ**

```
ชั้น 1  rust_bridge         ─┐
ชั้น 2  gateway_fsm_upgrad  ─┤ แกนหลัก ต้องมี
ชั้น 3  serial_bridge (จอ)  ─┘
ชั้น 4  app_vision (กล้อง)   ← เปิดเสริม
ชั้น 5  http.server (เว็บ)   ← เปิดเสริม
```

---

### ชั้นที่ 1 — Rust bridge (สะพานไปบอร์ดจริง)

```bash
cd "E:/work-TE-Project/project_Digital_Twin/dt-taping-dev/rust_bridge" && RUST_READ_ONLY=1 ./target/debug/rust_modbus_bridge.exe
```

**สำเร็จแล้วจะเห็น**

```
[REAL] BOARD LINK UP at <เวลา> - connected to STM32 at 192.168.0.100:502
```

🔴 **ถ้าขึ้น `[SIM]` แทน `[REAL]` แปลว่าไม่ติดบอร์ด** — ค่าที่ไหลผ่านทั้งระบบหลังจากนี้
เป็น **ของปลอมทั้งหมด** (Rust สะท้อนค่าที่ Python ส่งมากลับไปเฉย ๆ)
อย่าเพิ่งรันต่อ ให้ไปเช็คสาย LAN / IP ของการ์ดแลนก่อน

`RUST_READ_ONLY=1` = ห้าม Rust เขียน coil (`0x0F`) ลงบอร์ด ส่งแต่คำสั่งอ่าน
ใช้ตอนยังไม่มั่นใจ ปลอดภัยที่สุด

> **จะสั่งเอาต์พุตลงบอร์ดจริง (ให้ไฟบนบอร์ดติด) ต้องเปิดโหมดเขียน** — ถ้าใช้ `start_all.bat`
> ค่าตั้งต้นคือ read-only และ**ไม่ถามอะไรเลย** ต้องใส่ flag `--write` เอง
> วิธีทำทีละขั้น + วิธียืนยันว่าติดจริง → [`DEPLOY.md` หัวข้อ "การสั่งงานเอาต์พุตลงบอร์ดจริง"](../DEPLOY.md#การสั่งงานเอาต์พุตลงบอร์ดจริง-modbus-coil-write)

---

### ชั้นที่ 2 — Gateway (สมองกลหลัก)

```bash
cd "E:/work-TE-Project/project_Digital_Twin/dt-taping-dev/python_backend" && PYTHONUTF8=1 RUST_BRIDGE=1 python -u gateway_fsm_upgrad.py
```

**สำเร็จแล้วจะเห็น 2 บรรทัดนี้**

```
[REAL] [HARDWARE LINK] ต่อ Rust I/O Layer (127.0.0.1:8767) ได้แล้ว
[REAL] FAULT SIM: OFF (ค่าเริ่มต้นตาม RUST_BRIDGE)
```

- ถ้าขึ้น `[SIM] [HARDWARE LINK] ... ไม่ติด` → ชั้นที่ 1 ยังไม่ได้เปิด หรือเปิดแล้วตายไปแล้ว
- ถ้าขึ้น `I/O MODE : SIMULATED ทั้งหมด (ไม่ได้ตั้ง RUST_BRIDGE=1)` → ลืมใส่ `RUST_BRIDGE=1`

---

### ชั้นที่ 3 — จอ STM32 (TouchGFX HMI)

```bash
cd "E:/work-TE-Project/project_Digital_Twin/dt-taping-dev/python_backend" && PYTHONUTF8=1 python -u serial_bridge.py
```

⚠️ **ไม่ต้องระบุ `COM7` หรือเลข COM ใด ๆ ต่อท้าย** — สคริปต์เดินหาพอร์ต ST-Link เองอัตโนมัติ
(ฟังก์ชัน `find_stlink_port()` ที่ `python_backend/serial_bridge.py:46` กวาด `comports()`
แล้วจับคำว่า `STLink` / `ST-Link` / `STMicroelectronics` จาก description)
การใส่เลข COM เองคือวิธีทำให้พังตอนเสียบสายคนละช่อง

**สำเร็จแล้วจะเห็น** — ไปดูที่หน้าต่าง **ชั้นที่ 2 (gateway)** จะมีบรรทัดนี้เด้งขึ้นมา

```
🔌 [TOUCHGFX LINK] : GUI CONNECTED (live monitor)
```

จอบนบอร์ดจะเริ่มขึ้นตัวเลขจริงแทนที่จะเป็น 0 หมดทุกช่อง

---

### ชั้นที่ 4 — กล้อง OpenMV (เปิดเสริม)

🔴 **venv ของกล้องยังอยู่นอก repo** — ต้องรันจากที่เดิมไปก่อน

```bash
cd "E:/work-TE-Project/project_Digital_Twin/Digital-Twin-Taping Machine/Cam" && PYTHONUTF8=1 ./.venv/Scripts/python.exe -u app_vision.py
```

**สำเร็จแล้วจะเห็น 2 บรรทัดนี้**

```
Connected to OpenMV Stream on Port: COM10
✅ WebSocket connected to gateway
```

> **หมายเหตุเรื่องที่อยู่ของโค้ด:** source ของกล้องถูกคัดลอกเข้า repo แล้วที่
> [`vision_prototype/`](../vision_prototype/) (`app_vision.py`, `app_vision_upgrad.py`,
> `openmv_board/`) **แต่ `.venv` ขนาด 182 MB ยังอยู่ที่เดิมและไม่ได้ย้ายเข้ามา**
> จึงยังต้องรันจากโฟลเดอร์เดิมไปก่อน จนกว่าจะสร้าง venv ใหม่ใน repo

ปกติ **ต้องเสีย 10-15 เฟรมแรก** ก่อนภาพจะ sync ติด — **ไม่ใช่บั๊ก**
(`app_vision.py` ต้องไล่หาต้นเฟรมจากสตรีม USB เอง)

---

### ชั้นที่ 5 — เว็บ 3D Twin (เปิดเสริม)

```bash
cd "E:/work-TE-Project/project_Digital_Twin/dt-taping-dev/cad" && python -m http.server 8000
```

แล้วเปิดเบราว์เซอร์ (Chrome / Edge) ไปที่:

```
http://localhost:8000/index1.html
```

**สำเร็จแล้วจะเห็น** โมเดลเครื่องจักร 3D โหลดขึ้นจอ และกล่อง Event Log ด้านล่างเริ่มไหล

🔴 **ห้ามดับเบิลคลิกเปิด `index1.html` ตรง ๆ** — โหมด `file://` เบราว์เซอร์บล็อกการโหลด
ไฟล์โมเดล `.glb` ผลคือจอดำไม่มีอะไรขึ้น แล้วจะไปนั่งไล่บั๊กผิดที่

---

## 3. ตัวแปรสภาพแวดล้อม (Environment Variables)

| ตัวแปร | ใส่ที่ชั้นไหน | ทำอะไร | ไม่ใส่แล้วเป็นยังไง |
|---|---|---|---|
| `RUST_BRIDGE=1` | ชั้น 2 (gateway) | ให้ gateway ต่อออกไปที่ Rust bridge พอร์ต 8767 | 🔴 **ค่าทั้งหมดเป็นของจำลอง** — ระบบเดินสวยงามแต่ไม่ได้แตะบอร์ดเลย |
| `FAULT_SIM=0` / `=1` | ชั้น 2 (gateway) | ปิด/เปิดการสุ่มโยน error ปลอมเข้าลูป FSM | **ไม่ต้องใส่** — ใส่ `RUST_BRIDGE=1` แล้ว **ปิดให้เองอัตโนมัติ** เพราะ error ปลอมจะปนกับ log ของจริงจนแยกไม่ออก · `FAULT_SIM=1` บังคับเปิดไว้เดโมได้ |
| `RUST_READ_ONLY=1` | ชั้น 1 (rust) | ห้าม Rust เขียน coil (`0x0F`) ลงบอร์ด ส่งแต่คำสั่งอ่าน | Rust จะเขียน coil จริงลงบอร์ด — ใช้ตอนพร้อมขับเอาต์พุตจริงเท่านั้น |
| `PYTHONUTF8=1` | **ทุกชั้นที่เป็น Python** | บังคับ console เป็น UTF-8 | 🔴 log ภาษาไทยพังด้วย `UnicodeEncodeError` **แล้วรายงานผิดออกมาเป็น "bind 8766 ไม่ได้"** ทำให้ไล่บั๊กผิดทางไปหลายชั่วโมง — เคยเจอมาแล้ว |
| `-u` (flag ของ python) | **ทุกชั้นที่เป็น Python** | ปิด buffer ของ stdout | ไม่เห็น output อะไรเลยบนจอ เพราะ Python อมไว้ในบัฟเฟอร์ นึกว่าโปรแกรมค้าง |

**สรุปสั้น: `PYTHONUTF8=1` กับ `-u` ต้องมีทุกครั้ง ไม่มีข้อยกเว้น**

---

## 4. วิธีปิดระบบ

🔴🔴 **ห้ามใช้ `taskkill /F /IM python.exe`** — คำสั่งนั้นฆ่า Python **ทุกตัวในเครื่อง**
รวมงานอื่นที่ไม่เกี่ยวกับโปรเจกต์นี้ด้วย (เอกสารเก่าบางไฟล์ยังเขียนคำสั่งนี้อยู่ — **อย่าใช้**)

ใช้คำสั่ง PowerShell นี้แทน — เลือกฆ่าเฉพาะ process ของโปรเจกต์:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='pythonw.exe'" | Where-Object { $_.CommandLine -match 'gateway_fsm|app_vision|serial_bridge|http\.server' } | ForEach-Object { Write-Host ('killing PID ' + $_.ProcessId + ' - ' + $_.CommandLine.Trim()); Stop-Process -Id $_.ProcessId -Force }
```

ปิด Rust bridge แยกต่างหาก:

```powershell
Get-Process rust_modbus_bridge -ErrorAction SilentlyContinue | Stop-Process -Force
```

ปิดเสร็จแล้ว **เช็คซ้ำเสมอ** ว่าไม่มีอะไรค้างพอร์ต:

```bash
netstat -ano | grep -E ":8765|:8766|:8767|:8000"
```

> มีสคริปต์สำเร็จรูปที่ [`stop_all.bat`](../stop_all.bat) ใช้ตรรกะ match เดียวกันนี้

---

## 5. วิธีรันเทสต์

🔴 **ต้องไม่มี gateway รันอยู่** — ชุดเทสต์ **เปิดและปิด gateway เอง**
ถ้ามี gateway ค้างอยู่ เทสต์จะ bind พอร์ตไม่ได้แล้วล้มทั้งชุด
ปิดตาม [ข้อ 4](#4-วิธีปิดระบบ) ก่อนเสมอ

เทสต์มี **5 ไฟล์ × 2 gateway = 10 รอบ** (แต่ละไฟล์รับชื่อ gateway เป็น argument)

```bash
cd "E:/work-TE-Project/project_Digital_Twin/dt-taping-dev/python_backend/tests" && python test_estop.py gateway_fsm.py
```

```bash
cd "E:/work-TE-Project/project_Digital_Twin/dt-taping-dev/python_backend/tests" && python test_estop.py gateway_fsm_upgrad.py
```

```bash
cd "E:/work-TE-Project/project_Digital_Twin/dt-taping-dev/python_backend/tests" && python test_get_state.py gateway_fsm.py
```

```bash
cd "E:/work-TE-Project/project_Digital_Twin/dt-taping-dev/python_backend/tests" && python test_get_state.py gateway_fsm_upgrad.py
```

```bash
cd "E:/work-TE-Project/project_Digital_Twin/dt-taping-dev/python_backend/tests" && python test_ws.py gateway_fsm.py
```

```bash
cd "E:/work-TE-Project/project_Digital_Twin/dt-taping-dev/python_backend/tests" && python test_ws.py gateway_fsm_upgrad.py
```

```bash
cd "E:/work-TE-Project/project_Digital_Twin/dt-taping-dev/python_backend/tests" && python test_hmi_link.py gateway_fsm.py
```

```bash
cd "E:/work-TE-Project/project_Digital_Twin/dt-taping-dev/python_backend/tests" && python test_hmi_link.py gateway_fsm_upgrad.py
```

```bash
cd "E:/work-TE-Project/project_Digital_Twin/dt-taping-dev/python_backend/tests" && python test_cam_decision.py gateway_fsm.py
```

```bash
cd "E:/work-TE-Project/project_Digital_Twin/dt-taping-dev/python_backend/tests" && python test_cam_decision.py gateway_fsm_upgrad.py
```

### ผลที่ควรได้ ณ 2026-08-05 (รันยืนยันจริงแล้ว)

| ไฟล์เทสต์ | `gateway_fsm.py` | `gateway_fsm_upgrad.py` |
|---|---|---|
| `test_estop.py` | **27/27** | **27/27** |
| `test_get_state.py` | **15/15** | **15/15** |
| `test_cam_decision.py` | **19/19** | **19/19** |
| `test_ws.py` | ผ่านหมด | ผ่านหมด |
| `test_hmi_link.py` | ผ่านหมด | ผ่านหมด |

🔴 **ได้น้อยกว่านี้ = มีอะไรถอยหลัง** ไม่ใช่ "เทสต์เพี้ยน" — ให้ไปหาว่าอะไรเปลี่ยน
ก่อนจะรันต่อ อย่าปล่อยผ่าน

---

## 6. กับดักที่เจอมาแล้ว

หัวข้อนี้สำคัญที่สุดในไฟล์ ทุกข้อคือของที่เสียเวลาไปจริงแล้ว

### 6.1 เปิดโปรแกรมซ้อนกันโดยไม่รู้ตัว

เคยเจอ **`app_vision.py` ขึ้นมา 2 process พร้อมกันแย่ง COM10 กัน** — ตัวหนึ่งจอง
พอร์ตไว้ อีกตัวเปิดไม่ได้แล้วพ่น error ที่อ่านแล้วเหมือนกล้องพัง

**กฎ: ปิดของเก่าก่อนเปิดใหม่เสมอ** อย่าเปิดหน้าต่างใหม่ทับโดยคิดว่าของเก่าตายไปแล้ว
เช็คด้วย `netstat` ([ข้อ 1](#1-เช็คก่อนเริ่ม--ห้ามข้าม)) และปิดด้วย [ข้อ 4](#4-วิธีปิดระบบ)

> เรื่องเดียวกัน: ถ้า **OpenMV IDE** ยังเชื่อมบอร์ดค้างอยู่ มันจอง COM10 ไว้เหมือนกัน
> `app_vision.py` จะเปิดพอร์ตไม่ได้ — ปิด IDE ก่อน

### 6.2 `❌ Heartbeat disconnected` รัว ๆ ไม่ได้แปลว่าบอร์ดพัง

**บอร์ดตัดสายเองถ้าเว้นจังหวะระหว่างคำสั่งเกิน ~200 ms** — เป็นสเปกของบอร์ด ไม่ใช่บั๊ก
(วัดซ้ำ 3/3: 200 ms รอด / 250 ms ตาย)

- ตอน **idle** ไม่มีใครสั่งงาน → heartbeat ช้ากว่าเพดาน → **สายหลุดแล้วต่อใหม่วนไปเรื่อย ๆ**
  = พฤติกรรมปกติ
- พอ **Python ต่อเข้ามา** ลูป FSM 20 ms จะ**เลี้ยงสายไว้เอง** ข้อความก็หายไป

🔴 **ห้ามสรุปว่า "ต่อบอร์ดไม่ได้" จากข้อความนี้อย่างเดียว**
รายละเอียดเต็ม → [`docs/specs/board_protocol.md`](specs/board_protocol.md) หัวข้อ Idle timeout

### 6.3 กด RESET บนจอแล้วไม่มีอะไรเกิดขึ้น

**ต้องกด STOP ก่อน** ถึงจะเริ่ม batch ใหม่ได้ — RESET ตอนเครื่องกำลังเดินอยู่จะถูกเมิน

log ฝั่ง gateway บอกเหตุผลให้เสมอ ด้วยโทเคน 3 แบบ:

| โทเคนใน log | แปลว่า |
|---|---|
| `RESET/ALARM-CLEAR` | มี alarm ค้างอยู่ → เคลียร์ alarm แล้วกลับไป state เดิม |
| `RESET/NEW-BATCH` | เครื่องหยุดแล้วจริง → เริ่ม batch ใหม่ counter = 0 |
| `RESET/IGNORED-RUNNING` | 🔴 **เครื่องยังเดินอยู่ (`running=true`) → ไม่ทำอะไรเลย** ให้กด STOP ก่อน |

เห็น `RESET/IGNORED-RUNNING` แล้วอย่ากด RESET ซ้ำ ๆ — กด STOP แล้วค่อยกด RESET

### 6.4 กล้องโหวต NG ตลอด

**ปกติ** ถ้าไม่มีชิ้นงานวางให้มันเห็น — log จะขึ้น `PRESENCE: EMPTY`
วางชิ้นงาน (อุปกรณ์อิเล็กทรอนิก Noise Filter) ให้กล้องเห็นก่อน แล้วค่อยดูผลโหวต

### 6.5 ระบบขึ้นครบทุกอย่าง ต่อบอร์ดติด แต่ไฟบนบอร์ดไม่ติดสักดวง

**ไม่ใช่บอร์ดเสีย** — ถ้าเปิดด้วย `start_all.bat` โดยไม่ใส่ flag `--write`
ค่าตั้งต้นคือ read-only (`RUST_READ_ONLY=1`) ซึ่ง**บล็อกเฟรม `0x0F` ทุกเฟรม**
และสคริปต์จะ**ข้ามคำถามยืนยันไปเงียบ ๆ ไม่ถามอะไรสักคำ** จึงไม่มีอะไรเตือนว่ากำลังอยู่โหมดอ่านอย่างเดียว

อาการที่เจอ: หน้าต่างขึ้นครบ กล้องทำงาน จอ STM32 ขึ้นตัวเลข FSM เดินครบทุกชิ้น
`ESTABLISHED` ไป `192.168.0.100:502` — **แต่ไม่มีไฟติดเลย**

วิธีเปิดโหมดเขียน + วิธียืนยัน + ตารางว่าไฟดวงไหนติดที่สเตปไหน
→ [`DEPLOY.md` หัวข้อ "การสั่งงานเอาต์พุตลงบอร์ดจริง"](../DEPLOY.md#การสั่งงานเอาต์พุตลงบอร์ดจริง-modbus-coil-write)

> เปิดโหมดเขียนได้แล้ว **ไฟจะกระพริบ ไม่ใช่ติดค้าง** — มีแค่ 3 สเตปจาก 17 ที่ส่งสัญญาณออก
> ราว 70% ของเวลาไฟดับหมดทุกดวงเป็นเรื่องปกติ

### 6.6 🔴🔴 ห้ามแตะ firmware บนบอร์ด `192.168.0.100`

- **ห้ามแฟลช firmware ทับบอร์ดนี้เด็ดขาด** — **ไม่มี source code อยู่ที่ไหนเลย**
  แฟลชทับแล้วจบเลย เอาคืนไม่ได้ (`SCH_XPLCV1_18062026` · `FW:133` · `ID:218`)
- **ห้ามยิงคำสั่งข้อความที่ไม่รู้จักใส่บอร์ด** — โดยเฉพาะ **`*RST` ซึ่งรีบูตบอร์ดจริง**
  (เคยพลาดมาแล้ว)
- **ที่ปลอดภัยมีแค่ 2 อย่าง**: Modbus function `0x01` (Read Coils) และ `*IDN?`

---

## 7. ตารางสรุปพอร์ต

| พอร์ต | ใคร listen | ใครต่อเข้า |
|---|---|---|
| 8765 (WebSocket) | gateway | หน้าเว็บ 3D, analytics, **กล้อง `app_vision.py`** |
| 8766 (TCP) | gateway (`hmi_link.py`) | จอ TouchGFX ผ่าน `serial_bridge.py` |
| 8767 (TCP) | `rust_bridge` | `gateway_fsm_upgrad.py` เมื่อ `RUST_BRIDGE=1` |
| 8000 (HTTP) | `python -m http.server` (รันในโฟลเดอร์ `cad/`) | เบราว์เซอร์ |
| 502 (Modbus TCP) | บอร์ด STM32 จริง (192.168.0.100) | `rust_bridge` |
| COM10 (USB VCP) | บอร์ดกล้อง OpenMV | `app_vision.py` |

ฉบับเต็ม (รวมประวัติบั๊กพอร์ตชนกัน + กติกาการเพิ่ม client ใหม่)
→ [`docs/specs/port_map.md`](specs/port_map.md) 

---

## 8. เช็คลิสต์ก่อนบอกว่า "ระบบขึ้นครบแล้ว"

- [ ] `netstat` ก่อนเริ่ม ไม่มีบรรทัดค้าง
- [ ] ชั้น 1 ขึ้น `[REAL] BOARD LINK UP` (ไม่ใช่ `[SIM]`)
- [ ] ชั้น 2 ขึ้น `[REAL] [HARDWARE LINK] ... ได้แล้ว` + `FAULT SIM: OFF`
- [ ] ชั้น 3 ทำให้ฝั่ง gateway ขึ้น `GUI CONNECTED`
- [ ] ชั้น 4 ขึ้น `Connected to OpenMV Stream on Port: COM10` + `✅ WebSocket connected to gateway`
- [ ] ชั้น 5 เปิด `http://localhost:8000/index1.html` แล้วโมเดล 3D ขึ้นจริง (ไม่ใช่จอดำ)
