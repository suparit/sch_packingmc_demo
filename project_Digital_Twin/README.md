# project_Digital_Twin — Taping Machine Controller System

ระบบควบคุมเครื่องแพ็กชิ้นงาน SMD ลง carrier tape — FSM gateway · กล้องตรวจชิ้นงาน (OCR) · เว็บ Digital Twin · สะพานบอร์ด I/O
พัฒนาโดยนักศึกษาสหกิจ พ.ค. – ก.ย. 2569 · **ส่งต่อให้รุ่นถัดไปทำต่อ — ยังไม่ใช่เครื่องที่เสร็จสมบูรณ์**

> ชุดนี้คัดมาจาก repo พัฒนาของนักศึกษา เฉพาะโค้ดและเอกสารที่ใช้เดินเครื่องจริง ·
> **ไม่มีข้อมูลบริษัท/ลูกค้า** — ข้อความบนชิ้นงานใน `03_Vision/ocr/ocr_config.json` เป็นค่าตัวอย่าง ต้องใส่ของจริงเองก่อนใช้

---

## ทำได้แค่ไหนแล้ว (ทดสอบบนเครื่องจริง 28 ก.ย. 2569)

**เดินครบ 1 batch:** เป้า 4 ชิ้น (ชิ้นงาน 2 รุ่น) → **ผ่าน 4/4** จากภาพนิ่งภาพแรกทุกชิ้น · ทั้ง batch 11 หลุม = 57 วินาที · ~6 วินาที/หลุมที่มีชิ้นงาน

| ส่วน | ของจริง / จำลอง | เวลาวัดจริง |
|---|---|---|
| มอเตอร์ feed เลื่อนเทปทีละหลุม (นับพัลส์ 156/หลุม) | ✅ จริง | ~1.6 s/หลุม |
| ซีล (โซลินอยด์กระบอก A + B) | ✅ จริง | ~1.0 s |
| กล้องตรวจชิ้นงาน 4 ข้อ + อ่านตัวหนังสือ (OCR) จากภาพนิ่ง | ✅ จริง | 1.7–2.7 s/ชิ้น |
| Cylinder C กดเทปแนบลูกกลิ้ง (ปุ่ม INIT) | ✅ จริง | — |
| อุณหภูมิหัวซีล · หยิบวางชิ้นงาน · ตรวจรอยซีล · ม้วนเก็บ · เซนเซอร์ carrier | ⚠️ **จำลองตามเวลา** (อุปกรณ์ยังไม่ครบ) | ~1.5 s รวม |

**ปัญหาที่ยังค้าง:**
- **เทปลื่น** — feed นับพัลส์อย่างเดียว ตำแหน่งคลาดได้หลาย mm · ทางแก้ถาวร = encoder ติดกับล้อที่เทปพาหมุน / เซนเซอร์ carrier
  (สอดคล้องกับแนวทาง encoder + pin ใน `docs/decisions/ADR_001_encoder_counter.md` ของ repo นี้)
- **กล้องไวต่อแสงสะท้อน** — ค่ากล้อง/ไฟจูนกับตำแหน่งวันที่ทดสอบ **ขยับไฟหรือกล้องต้องจูนใหม่** (`position_helper.py` → `exposure_sweep.py`)

---

## ระบบต่อกันยังไง

```
[จอ HMI บนบอร์ด MCU] ─USB serial─→ [serial_bridge.py] ─TCP 8766─┐
                                                                  ├─→ [gateway_fsm.py]  ← FSM 17 ขั้น + SQLite
[กล้อง USB3] ──→ [app_vision_ocr.py  หน้า :5000] ─WebSocket──────┤        │
                                                                  │        │ WebSocket 8765
[เว็บ Digital Twin  web_next :5173/twin] ←───────────────────────┘        │
                                                                           ↓
                                  [Rust bridge] ─Modbus TCP 192.168.0.100:502─→ [บอร์ด I/O] → โซลินอยด์ · Cylinder C · มอเตอร์ feed
```

- **gateway ต้องขึ้นก่อนเสมอ** — จอ กล้อง และเว็บ เป็นฝ่ายวิ่งเข้าหา gateway
- เปิดมา = **โหมดจำลองเสมอ** (บอร์ดได้เอาต์พุต 0) · กดปุ่ม **Sync บอร์ด** บนเว็บถึงจะสั่งเครื่องจริง
- ข้อความระหว่างส่วนต่างๆ: [`dt-taping-dev/docs/specs/protocol.md`](dt-taping-dev/docs/specs/protocol.md)

---

## แผนที่โฟลเดอร์

โค้ดมาจากนักศึกษา 2 คน (`dt-taping-dev/` = อีกคนหนึ่ง) **ระบบที่เดินเครื่องจริงใช้ของทั้งสองฝั่งผสมกัน:**

| ส่วน | ตัวที่ใช้งานจริง | หมายเหตุ |
|---|---|---|
| ปุ่มเปิด/ปิดระบบ | `START.bat` · `STOP.bat` | เรียก `start_all.ps1` → `01_DigitalTwin/run_demo.ps1` |
| gateway + FSM | **`01_DigitalTwin/python_backend/gateway_fsm.py`** | `gateway_fsm_upgrad.py` = ไฟล์ทดลอง ไม่ได้ใช้ |
| สะพานจอ HMI | `01_DigitalTwin/python_backend/serial_bridge.py` + `hmi_link.py` | |
| สะพานบอร์ด I/O + ส่งพัลส์มอเตอร์ | **`dt-taping-dev/rust_bridge/`** | `01_DigitalTwin/rust_bridge/` = ตัวเดิม (ส่งพัลส์มอเตอร์ไม่ได้) |
| กล้อง + OCR | **`03_Vision/ocr/app_vision_ocr.py`** · ค่าตั้งใน `ocr_config.json` / `cam_settings.json` | ดู [`03_Vision/ocr/README.md`](03_Vision/ocr/README.md) |
| เว็บ Digital Twin | **`dt-taping-dev/web_next/`** (Next.js) → `http://localhost:5173/twin` | `01_DigitalTwin/cad/index1.html` :8000 = เว็บเดิม ใช้สำรอง |
| เครื่องมือทดสอบฮาร์ดแวร์ | `01_DigitalTwin/tools/` · `03_Vision/ocr/*_helper.py` | **ห้ามรันพร้อมระบบหลัก** — บอร์ดรับการเชื่อมต่อได้ทีละตัว |
| ผัง wiring ชุดทดสอบ | [`06_Docs/wiring/`](06_Docs/wiring/) — `test_rig_wiring.svg` / `.png` · สร้างใหม่ด้วย `gen_wiring.py` | เส้นประแดง = ส่วนที่ยังไม่ได้บันทึก ต้องดูสายจริง |
| firmware จอ HMI | ⏳ **ยังไม่ได้ใส่ในชุดนี้** (TouchGFX ~380 ไฟล์) | รอพี่เลี้ยงยืนยันว่าต้องการไหม |

---

## เปิดเครื่อง

**ก่อนเริ่ม:** ตั้ง IP การ์ด LAN ของ PC เป็นวง `192.168.0.x` (เช่น `192.168.0.55`) · ปิดโปรแกรม MVS ของกล้อง · เตรียมของตามหัวข้อถัดไป

1. ดับเบิลคลิก **`START.bat`** → รอหน้าเว็บ `/twin` เปิดเอง
2. ร้อยเทป → เปิดลม
3. บนเว็บ `/twin` กด **Sync บอร์ด** (ยืนยัน → ป้ายเขียว)
4. กด **INIT** (Cylinder C กดเทป) → กด **STEP** จนหลุมตรงเส้นในการ์ดกล้อง
5. ตั้งเป้า batch (กด "ตั้ง") → **START** · หลุม 1–3 เดินว่าง · วางชิ้นงานตั้งแต่หลุม 4 (วางล่วงหน้า)

ปิด: **`STOP.bat`** · ⚠️ ห้ามกด X ที่หน้าต่างดำของแอปกล้อง / ห้าม kill python — กล้องจะค้างจนต้องถอดสาย USB

ไม่มีเครื่อง/ดูอย่างเดียว: **`START_WEB.bat`** (ไม่แตะพอร์ตใดๆ) หรือเว็บ DEMO ออนไลน์ https://tapingmachinenexcore.netlify.app

รายละเอียด: [`06_Docs/HOWTO_RUN.md`](06_Docs/HOWTO_RUN.md) · [`01_DigitalTwin/RUNBOOK.md`](01_DigitalTwin/RUNBOOK.md)

---

## ต้องเตรียมก่อนรัน (ไม่อยู่ใน repo)

| ของ | วิธีได้มา |
|---|---|
| Rust bridge `.exe` | `cargo build --release --manifest-path dt-taping-dev/rust_bridge/Cargo.toml` |
| โมเดล 3D `Machine.glb` | คัดลอก `cad/export/machine.glb` ของ repo นี้ไปที่ `project_Digital_Twin/01_DigitalTwin/cad/export/Machine.glb` และ `project_Digital_Twin/dt-taping-dev/cad/export/Machine.glb` |
| แพ็กเกจเว็บ | `npm install` ใน `dt-taping-dev/web_next` |
| Python ของกล้อง | สร้าง venv `03_Vision/.venv-ocr` ตาม [`03_Vision/ocr/README.md`](03_Vision/ocr/README.md) |
| Python ของ gateway | `01_DigitalTwin/setup.bat` |
| ข้อความบนชิ้นงานจริง | แก้ช่อง `fields` ใน `03_Vision/ocr/ocr_config.json` |

---

## ลำดับการอ่าน

1. **ไฟล์นี้**
2. [`06_Docs/HANDOVER/LESSONS.md`](06_Docs/HANDOVER/LESSONS.md) — บทเรียน/กับดักที่เสียเวลาไปแล้ว **อ่านก่อนลงมือ**
3. README ของส่วนที่จะทำ: [`03_Vision/ocr/README.md`](03_Vision/ocr/README.md) (กล้อง) ·
   [`01_DigitalTwin/README.md`](01_DigitalTwin/README.md) (gateway/FSM) · [`dt-taping-dev/web_next/README.md`](dt-taping-dev/web_next/README.md) (เว็บ)
4. [`dt-taping-dev/docs/specs/protocol.md`](dt-taping-dev/docs/specs/protocol.md) — ข้อความระหว่างส่วนต่างๆ

---

## ข้อควรระวังที่พังบ่อยที่สุด

- **path ที่มีอักษรที่ไม่ใช่ภาษาอังกฤษ** → `pip install` บางตัวพัง / build firmware พัง — วางโปรเจกต์ใน path ภาษาอังกฤษ
- **บอร์ด I/O รับการเชื่อมต่อทีละตัว** และตัดสายถ้าเงียบเกิน ~0.2 วินาที — ห้ามรันเครื่องมือทดสอบพร้อมระบบหลัก
- **บอร์ด I/O อ่านค่าเอาต์พุตกลับไม่ได้** — อย่าใช้การอ่านกลับเป็นหลักฐานว่าสั่งสำเร็จ
- **อ่านเซนเซอร์ไม่ขึ้น → ดูกลไกจริงก่อน** (กระบอกถึงสุดทางไหม ลมเข้าไหม) ก่อนโทษโปรแกรม
- **ตัวเลขในรายงาน** ต้องบอกเสมอว่าส่วนไหนจำลอง

---

## ผู้พัฒนา

- Thanpisittha — gateway/FSM · กล้อง + OCR · launcher
- TONTIKORN — เว็บ `web_next` · Rust bridge · ผัง wiring
- พี่เลี้ยง — system architecture and guidance
