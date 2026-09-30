# วิธีรันระบบ Taping Machine Digital Twin

เอกสารนี้เขียนไว้สำหรับ "ตัวเราในอีก 3 เดือนข้างหน้า" ที่ลืมไปหมดแล้วว่าเคยตั้งค่าอะไรไว้บ้าง
อ่านตั้งแต่ต้นถึงท้ายรอบแรก แล้วค่อยย้อนกลับมาเปิดเฉพาะหัวข้อที่ต้องใช้ในครั้งถัด ๆ ไป

---

## 1. ระบบมีกี่ส่วน และทำไมต้องเปิดตามลำดับนี้

ระบบทั้งหมดมี "ชิ้นส่วนที่ต้องรัน" อยู่ 4 ชิ้น:

| # | ชิ้นส่วน | ไฟล์ | ทำหน้าที่อะไร |
|---|---|---|---|
| 1 | **Gateway** | `01_DigitalTwin\python_backend\gateway_fsm.py` | สมองกลางของระบบ เก็บสถานะ FSM (LOAD_CARRIER → VISION → ... ) เปิด WebSocket พอร์ต 8765 และ TCP พอร์ต 8766 ให้ส่วนอื่นเชื่อมต่อเข้ามา |
| 2 | **เว็บ 3D** | `01_DigitalTwin\cad\index1.html` เสิร์ฟผ่าน `python -m http.server 8000` | แสดงโมเดล 3D ของเครื่องจักรในเบราว์เซอร์ เชื่อมต่อ Gateway ผ่าน WebSocket 8765 เหมือนกัน |
| 3 | **จอ HMI (บอร์ด STM32)** | `01_DigitalTwin\python_backend\serial_bridge.py` เชื่อมกับบอร์ดจริงผ่าน ST-LINK VCP | สะพานเชื่อมระหว่าง Gateway กับจอสัมผัสบนบอร์ด STM32H7S78-DK ผ่านสาย USB (serial 115200 baud) |
| 4 | **กล้อง** | `03_Vision\app_vision.py` (โปรเจกต์แยกต่างหาก มี venv ของตัวเอง) | อ่านภาพจากกล้อง (พอร์ต COM6) ตรวจว่ามีชิ้นงานในตำแหน่งหรือไม่ แล้วส่งผล PASS/FAIL กลับไปที่ Gateway ผ่าน WebSocket 8765 |

**ทำไมต้องเรียง Gateway ก่อนเสมอ:** ทั้งจอ HMI (ชิ้นที่ 3) และกล้อง (ชิ้นที่ 4) เป็นฝ่าย
"โทรออก" ไปหา Gateway (client ที่เชื่อมต่อเข้า WebSocket/TCP ของ Gateway) ไม่ใช่ Gateway
โทรหาพวกมัน ถ้า Gateway ยังไม่เปิด ทั้งจอ HMI และกล้องจะเชื่อมต่อไม่ติดตั้งแต่แรก (จอ HMI
จะค้างที่ "connecting..." ส่วนกล้องจะ print "waiting for FSM sync..." วนไปเรื่อย ๆ)

ลำดับที่ถูกต้องคือ **Gateway + เว็บ → จอ HMI → กล้อง** ซึ่งเป็นลำดับที่ `START_WEB.bat`/`START_FULL.bat`
ทำให้อัตโนมัติอยู่แล้ว ไม่ต้องจำเอง

---

## 2. ทางลัด: ดับเบิลคลิก (แนะนำให้ใช้ทางนี้เป็นหลัก)

อยู่ที่ root ของ repo (`Wab\`) — มี **2 โหมดให้เลือก** แล้วปิดด้วยไฟล์เดียวกัน

| ไฟล์ | เปิดอะไร | แตะพอร์ต COM มั้ย | ใช้ตอนไหน |
|---|---|---|---|
| **`START_WEB.bat`** | Gateway + เว็บ 3D | **ไม่แตะเลย** | เดโม/พัฒนาโดยไม่ต้องต่อเครื่อง · **แยกปัญหา** |
| **`START_FULL.bat`** | Gateway + เว็บ + จอ HMI + กล้อง | หา STM32 อัตโนมัติ + COM6 | ใช้งานจริงกับเครื่อง; สเต็ป VISION รอผลจริงจากกล้อง |
| **`STOP.bat`** | — ปิดทั้งหมด | คืนพอร์ตให้หมด | ทั้งสองโหมด |

ดับเบิลคลิกได้จาก File Explorer โดยตรง ไม่ต้องเปิด terminal เอง หน้าต่างจะค้างรอกด
ปุ่มก่อนปิด เพื่อให้อ่านผลลัพธ์ทัน (ไม่ใช่กะพริบแล้วหายไป)

> 💡 คลิกขวา → **Send to → Desktop (create shortcut)** ทั้ง 3 ไฟล์ จะได้กดจากหน้าจอเลย

### ทำไมต้องแยก 2 โหมด — ไม่ใช่แค่ความสะดวก

`START_WEB.bat` **รับประกันว่าจะไม่เปิดพอร์ต COM แม้แต่พอร์ตเดียว** นั่นทำให้มันเป็น
**ตัวควบคุมที่สะอาด (clean baseline)** สำหรับแยกว่าปัญหาอยู่ที่ฮาร์ดแวร์หรือซอฟต์แวร์:

```
เจออาการแปลก ๆ (เช่น FSM ค้าง, ESTOP วนไม่หยุด)
   │
   ├─ กด START_WEB.bat แล้วอาการหาย   →  ปัญหาอยู่ที่บอร์ด/สาย/กล้อง
   └─ กด START_WEB.bat แล้วยังเป็นเหมือนเดิม  →  ปัญหาอยู่ในโค้ด (gateway_fsm.py)
```

ถ้าไม่มีโหมดนี้ ต้องมานั่งถอดสายทีละเส้นเพื่อเดา ซึ่งช้าและไม่แน่นอน

### `START_FULL.bat` จะ:
1. หาพอร์ต COM ของบอร์ด STM32 ให้อัตโนมัติ (ไม่ต้อง hardcode COM7 — เผื่อเสียบพอร์ตอื่นแล้ว
   เลขจะเปลี่ยน) ถ้าไม่เจอบอร์ด จะบอกตรง ๆ ว่า "ไม่พบบอร์ด STM32 -- รันโหมดจำลองอย่างเดียว"
   แล้วรันต่อแบบ software-only (ไม่ error, ไม่หยุดทำงาน)
2. ตรวจว่ามี `03_Vision\.venv\Scripts\python.exe` และพอร์ตกล้อง (ปกติ COM6) เปิดได้จริงไหม
   ก่อนจะพยายามเปิดกล้อง ถ้าไม่พร้อม จะข้ามและอธิบายเหตุผลเป็นภาษาไทย ระบบส่วนอื่นทำงาน
   ต่อได้ตามปกติ กล้องไม่ใช่ของบังคับ
3. ถ้ารันซ้ำตอนระบบยังทำงานอยู่ จะตรวจพบและไม่เปิดซ้ำซ้อน (บอกว่า "กำลังทำงานอยู่แล้ว")
4. เปิดเบราว์เซอร์ไปที่ `http://127.0.0.1:8000/index1.html` ให้เองตอนจบ พร้อมสรุปผลว่า
   ส่วนไหนเปิดสำเร็จ ส่วนไหนข้ามไปและเพราะอะไร

`START_WEB.bat` ทำข้อ 3-4 เหมือนกัน แต่**ข้ามข้อ 1-2 โดยตั้งใจ** และบอกไว้ชัดในหน้าจอ

`STOP.bat` จะ:
1. ปิดกล้องก่อน (ด้วย PID ที่บันทึกไว้ตอน start; ถ้าหาไม่เจอจะ fallback ไปค้นหา
   process python ที่รัน `app_vision.py` อยู่)
2. ปิด Gateway/เว็บ/จอ HMI ต่อ (ผ่าน `run_demo.ps1 stop` เดิม)
3. ตรวจสอบซ้ำหลังปิดว่าพอร์ต 8000/8765/8766/8767 ว่างจริง และพอร์ต COM ของจอ HMI/กล้อง
   ถูกปล่อยจริง แล้วรายงานเป็นภาษาไทย
4. ถ้าไม่มีอะไรรันอยู่เลย จะบอกว่า **"ไม่มีอะไรรันอยู่"** เฉย ๆ ไม่ error

**ข้อสำคัญที่ต้องรู้:** `STOP.bat` (และ `stop_all.ps1` ข้างใน) **ไม่มีวันใช้**
`taskkill /F /IM python.exe` เด็ดขาด เพราะคำสั่งนั้นจะฆ่า python.exe **ทุกตัว**ในเครื่อง
ไม่ใช่แค่ของระบบนี้ — ถ้าเผลอมี Jupyter, VS Code Python extension หรือโปรแกรมอื่นที่ใช้
python อยู่ด้วย จะโดนฆ่าไปด้วยทั้งหมด `RUNBOOK.md` เดิมก็เตือนเรื่องนี้ไว้ชัดเจน สคริปต์
ในนี้ปิดเฉพาะ PID ที่ตัวเองบันทึกไว้ หรือ PID ที่ค้นด้วย command line ที่มี `app_vision` เท่านั้น

### ไฟล์ที่อยู่เบื้องหลัง

```
Wab\
├── START_WEB.bat          <- เปิดแบบเว็บอย่างเดียว (ไม่แตะ COM)
├── START_FULL.bat         <- เปิดพร้อมจอ HMI + กล้อง
├── STOP.bat                <- ดับเบิลคลิกอันนี้เพื่อปิด
├── start_all.ps1            (ทั้งสอง START_*.bat เรียกอันนี้ ต่างกันที่ parameter)
├── stop_all.ps1              (STOP.bat เรียกอันนี้)
├── common_launcher.ps1        (ฟังก์ชันช่วยเหลือที่ทั้งสองไฟล์ข้างบนใช้ร่วมกัน)
├── .digital-twin-run.json    <- Gateway/เว็บ/จอ HMI สร้างเก็บ PID ของตัวเอง (ไม่ commit)
│                                 (จริง ๆ อยู่ใต้ 01_DigitalTwin\ ไม่ใช่ root)
└── .camera-run.json          <- start_all.ps1 สร้างเก็บ PID ของกล้อง (ไม่ commit)
```

---

## 3. ทางที่ทำเอง (manual): เวลาต้อง debug ทีละส่วน

บางทีอยากรันแค่บางส่วนเพื่อดู error หรือ log แบบเห็นเต็ม ๆ (ไม่ถูกซ่อนหน้าต่างเหมือนตอนรัน
ผ่าน `START_WEB.bat`/`START_FULL.bat`) ให้ทำแบบนี้แทน — **ต้องเรียงลำดับเดียวกับด้านบนเสมอ**

### 3.1 Gateway + เว็บ 3D (+ จอ HMI ถ้าต้องการ)

```powershell
cd 01_DigitalTwin

# เช็คก่อนว่าพร้อมไหม (python, websockets, pyserial, pip check, ไฟล์ GLB ครบ)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 check

# ซอฟต์แวร์อย่างเดียว ไม่มีจอ HMI จริง
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 start -OpenBrowser

# มีจอ HMI จริงด้วย (ต้องรู้ COM port ของบอร์ดก่อน ดูหัวข้อ 4)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 start -Hardware serial -SerialPort <HMI_COM> -OpenBrowser

# ดูสถานะปัจจุบัน
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 status

# ปิด (เฉพาะ process ที่ launcher นี้เริ่มเอง)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1 stop
```

รายละเอียดเพิ่มเติม (เช่นโหมด Rust/Modbus, การ build firmware) ดูที่ `01_DigitalTwin\RUNBOOK.md`

### 3.2 กล้อง

ต้องรันหลังจาก Gateway พร้อมแล้วเท่านั้น (ไม่งั้นจะเชื่อมต่อไม่ติด):

```powershell
cd 03_Vision
$env:PYTHONUTF8 = "1"        # จำเป็น! ไม่งั้นจะเจอ UnicodeEncodeError เพราะสคริปต์ print ภาษาไทย/อีโมจิ
.\.venv\Scripts\python.exe app_vision.py
```

จะมีหน้าต่างวิดีโอเปิดขึ้นมา 2 บาน: "Main Camera Screen" (ภาพเต็ม) และ "Target ROI"
(กรอบพื้นที่ที่ใช้ตรวจจับ) กด `q` ในหน้าต่างวิดีโอเพื่อปิดโปรแกรม, กด `t` เพื่อบันทึก
template ของชิ้นงานที่ถูกต้อง (ใช้เมื่อ `PRESENCE_SENSOR_MODE = False` เท่านั้น
ตอนนี้ในโค้ดตั้งเป็น `True` คือใช้แค่ "มี/ไม่มีชิ้นงาน" ไม่ได้เทียบรูป)

ถ้า venv ยังไม่มี ให้สร้างก่อน:

```powershell
cd 03_Vision
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

ดูหมายเหตุสำคัญเรื่อง Python version ใน `requirements.txt` ที่หัวข้อ 5 (troubleshooting)

---

## 4. แผนที่พอร์ต COM

| อุปกรณ์ | ชื่อที่ Windows ตั้งให้ | พอร์ตปกติ (วันนี้) |
|---|---|---|
| จอ HMI (บอร์ด STM32H7S78-DK) | `STMicroelectronics STLink Virtual COM Port` | ปัจจุบัน COM8; launcher ตรวจหาอัตโนมัติ |
| กล้อง | (hardcode ไว้ในโค้ด `03_Vision\app_vision.py` บรรทัด `port='COM6'`) | COM6 |

เลข COM **เปลี่ยนได้** ทุกครั้งที่ถอด-เสียบสาย USB ใหม่ หรือเสียบเข้าช่อง USB คนละช่อง
บนเครื่อง โดยเฉพาะถ้ามีอุปกรณ์ serial อื่นเสียบอยู่ด้วย (เช่น Bluetooth serial ที่เห็น
เป็น COM4/COM5 อยู่ตอนนี้)

`START_FULL.bat` หาพอร์ตของจอ HMI ให้อัตโนมัติอยู่แล้ว (ไม่ต้องทำอะไร) ส่วนกล้องใช้ค่า
default COM6 แต่ override ได้ถ้าจำเป็น:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File start_all.ps1 -CameraPort <OPENMV_COM>
```

**วิธีเช็คว่าตอนนี้เลข COM คืออะไรบ้าง** (ใช้เวลาเลขเพี้ยนไปจากตารางข้างบน):

```powershell
Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match 'COM\d+' }
```

จะได้รายชื่ออุปกรณ์ทั้งหมดที่มีพอร์ต COM พร้อมชื่อเต็ม แล้วดูว่าตัวไหนคือบอร์ด STM32
(ชื่อจะมีคำว่า STMicroelectronics/STLink) ตัวไหนคือกล้อง (โมดูล USB-serial ทั่วไป
เช่น CH340, CP210x, หรือชื่อ OpenMV ถ้าใช้ driver เฉพาะ) ถ้ากล้องเปลี่ยนพอร์ตถาวร
ให้แก้ที่ `03_Vision\app_vision.py` บรรทัด `camera = OpenMV_Serial_Receiver(port='COM6')`
ในฟังก์ชัน `__main__` ด้วย ไม่ใช่แก้แค่ตอนรัน `start_all.ps1 -CameraPort`

---

## 5. Troubleshooting

| อาการ | สาเหตุที่พบจริง | วิธีแก้ |
|---|---|---|
| `Port 8000/8765/8766 is already in use by PID(s): ...` ตอน start | รอบก่อนไม่ได้ปิดให้เรียบร้อย (ปิด terminal ตรง ๆ แทนการกด stop) หรือมีโปรแกรมอื่นชนพอร์ตพอดี | รัน `STOP.bat` ก่อนเสมอ ถ้ายังฟ้องอยู่ ให้ดู PID ที่ error บอก แล้วเช็คว่าเป็นโปรแกรมอะไรด้วย `Get-Process -Id <PID>` — ถ้าไม่ใช่ของระบบนี้ ให้ปิดโปรแกรมนั้นเอง (**ห้าม** ใช้ `run_demo.ps1`/สคริปต์นี้ไปฆ่ามันแทน มันจะปฏิเสธและไม่ทำอะไรให้ ต้องจัดการเอง) |
| `pip check failed` ตอนรัน `run_demo.ps1 check`/`start` | เครื่องมี Python "ตัวหลัก" (global) ที่ลง package จาก project อื่นทับกันอยู่ปนกับ venv หรือ venv เพี้ยนบางส่วน | ต้องรันผ่าน `.venv\Scripts\python.exe` ของ `01_DigitalTwin\` เท่านั้น อย่ารันด้วย `python` เฉย ๆ (จะไปเจอ python global) ถ้ายังพังให้ลบ `.venv` แล้วรัน `setup_python.ps1` สร้างใหม่ |
| `UnicodeEncodeError` ตอนรันกล้องหรือ build package จาก source | path ของ repo มีอักษรไทย (`สหกิจ`) เมื่อ pip พยายาม build wheel จาก source มันมักพังเพราะ default codepage ของ Windows ไม่ใช่ UTF-8 | ต้องใช้ package ที่มี **wheel สำเร็จรูปเท่านั้น** (ห้าม build จาก source) — ดู `03_Vision\requirements.txt` มีคอมเมนต์เตือนไว้แล้วว่าต้องใช้ Python 3.13 (cp313) ที่มี wheel ตรงเวอร์ชัน และก่อนรันสคริปต์ที่ print ภาษาไทย/อีโมจิ ต้องตั้ง `$env:PYTHONUTF8 = "1"` ก่อนเสมอ (สคริปต์ในนี้ตั้งให้อัตโนมัติแล้ว ถ้ารันเองต้องตั้งเอง) |
| หน้ากล้องขึ้น `step_allowed=False` ตลอดเวลา | **ปกติ** ไม่ใช่ bug — กล้องจะ "ตรวจจริง" (ยอมส่งผล PASS/FAIL กลับ Gateway) เฉพาะตอนที่ FSM อยู่ใน state `VISION` เท่านั้น ตอน idle/state อื่น Gateway จะไม่อนุญาต (`step_allowed=False`) เพื่อกันไม่ให้กล้องส่งผลตัดสินตอนที่เครื่องยังไม่ถึงจังหวะตรวจ | ไม่ต้องแก้อะไร ถ้าอยากเห็น `step_allowed=True` ให้ขยับ FSM (ผ่านเว็บ/จอ HMI) ไปที่ state VISION ก่อน |
| **ESTOP วนไม่หยุด** — กด Reset แล้ว `[ESTOP TRIGGERED] Safety barrier engaged!` เด้งกลับมาทันทีทุกครั้ง หัวจอขึ้น `EMERGENCY STOP ENGAGED (SOFT INTERLOCK)` ปุ่ม Start/Stop กดไม่ได้ FSM ค้างที่ `LOAD_CARRIER` ไปไม่ถึง `VISION` | **ยังไม่สรุปสาเหตุ** — เป็นได้ทั้งปุ่ม E-Stop จริงบนเครื่องถูกกดค้าง, จอ HMI ส่งสัญญาณ ESTOP ค้างมาทางพอร์ต HMI, เซนเซอร์นิรภัยยังไม่พร้อม, หรือ bug ที่ reset ไม่เคลียร์ flag | **ใช้ `START_WEB.bat` แยกก่อน** (ดูหัวข้อ 2): กดแล้วลอง `▶ Start` บนเว็บ — ถ้า FSM เดินได้ปกติ แปลว่า ESTOP มาจากฮาร์ดแวร์ (บอร์ด/ปุ่ม/เซนเซอร์) ไม่ใช่โค้ด; ถ้ายังวนเหมือนเดิมทั้งที่ไม่ได้ต่ออะไรเลย แปลว่าเป็น bug ใน `gateway_fsm.py` ให้ไล่ดูเงื่อนไขที่ set ESTOP flag และตรงที่ Reset ควรเคลียร์มัน |
| เปิด `cad/index1.html` แล้วโมเดล 3D ไม่ขึ้น (จอดำ) | ดับเบิลคลิกเปิดไฟล์ตรง ๆ ผ่าน `file://` — เบราว์เซอร์บล็อกการโหลด asset ข้าม origin แบบนี้ | ต้องเข้าผ่าน `http://127.0.0.1:8000/index1.html` ที่ `run_demo.ps1`/`START_WEB.bat`/`START_FULL.bat` เปิดให้เท่านั้น อย่าดับเบิลคลิกไฟล์ html ตรง ๆ |
| `START_FULL.bat` บอกว่าไม่พบบอร์ด/กล้อง ทั้งที่เสียบสายอยู่ | ไดรเวอร์ยังไม่ขึ้น COM port หรือเสียบเข้า USB hub ที่มีปัญหา | เช็คด้วยคำสั่งในหัวข้อ 4 ว่า Windows เห็นอุปกรณ์จริงไหม ถ้าไม่เห็นเลยใน Device Manager ให้ลองสาย/พอร์ต USB อื่น หรือลง driver (ST-LINK VCP / STSW-LINK009 สำหรับบอร์ด) |
| กล้อง exit ทันทีหลัง `START_FULL.bat` เริ่มให้ | มักเป็นเพราะพอร์ต COM6 ถูกโปรแกรมอื่นจับอยู่ในจังหวะที่เช็คผ่านแต่พอเปิดจริงกลับชนกัน (race เล็กน้อย) หรือ error อื่นในสคริปต์ | รันด้วยมือตามหัวข้อ 3.2 เพื่อเห็น error เต็ม ๆ (เวลารันผ่าน `START_FULL.bat` หน้าต่าง console ของกล้องจะถูกย่อไว้ ไม่เห็น error) |

### จะรู้ได้ยังไงว่า "ยังไม่เริ่ม" กับ "พังจริง" ต่างกันตรงไหน

- **ยังไม่เริ่ม (ปกติ)**: `STOP.bat` รายงาน "ไม่มีอะไรรันอยู่", `run_demo.ps1 status`
  รายงานทุกพอร์ตเป็น `free` และไม่มีบรรทัด process ใด ๆ, ไม่มีไฟล์
  `01_DigitalTwin\.digital-twin-run.json` หรือ `.camera-run.json` ที่ root
- **พังระหว่างเริ่ม (ต้องดู error)**: `START_*.bat` พิมพ์ข้อความสีแดง บอกสาเหตุตรง ๆ
  (พอร์ตชนกัน / dependency ไม่ครบ / GLB เสีย ฯลฯ) แล้ว exit code ไม่ใช่ 0 — สคริปต์
  จะ cleanup process ที่ตัวเองเพิ่งเริ่มไปแล้วให้อัตโนมัติ ไม่ปล่อยค้าง แต่จะไม่เปิด
  เบราว์เซอร์ให้ และในสรุปผลท้ายสคริปต์บรรทัด "Gateway + เว็บ 3D" จะขึ้นว่า "ล้มเหลว"
- **รันอยู่แต่มีปัญหาบางส่วน (degraded)**: เช่น Gateway/เว็บ/จอ HMI ขึ้นปกติ (สีเขียว)
  แต่กล้องขึ้น "ข้าม" พร้อมเหตุผล — แบบนี้ระบบส่วนที่เหลือใช้งานได้ปกติ กล้องเป็น
  ส่วนเสริมที่ไม่บล็อกส่วนอื่น ไม่ใช่ความล้มเหลวของทั้งระบบ

ถ้าไม่แน่ใจว่าอะไรกำลังรันอยู่จริง ให้เชื่อคำสั่งนี้เป็นแหล่งความจริงเสมอ (ไม่ใช่ความจำ
ตัวเอง เพราะหน้าต่าง console ของ Gateway/เว็บ/จอ HMI จะถูกซ่อนไว้เมื่อรันผ่าน launcher):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File 01_DigitalTwin\run_demo.ps1 status
```
