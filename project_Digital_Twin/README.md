# Digital Twin — เครื่อง taping SMD reel

ระบบ Digital Twin ของเครื่องบรรจุชิ้นงาน SMD ลง carrier tape ควบคุมได้ทั้งจากจอ HMI
บนบอร์ด STM32 จริงและจากหน้าเว็บ 3D พร้อมกัน สื่อสารสองทางแบบ real-time

```
[TouchGFX HMI บน STM32H7S78-DK]  ←COM/UART→  ┐
                                              ├→ [Python FSM Gateway] ←ws→ [เว็บ Three.js 3D]
[กล้อง OpenMV ตัดสิน PASS/NG]     ←ws→        ┘          ↓
                                              [Rust Modbus Bridge] → [บอร์ด I/O จริง]
```

เป้าหมายคือทำ Controller System ให้ใกล้เคียงเครื่องอุตสาหกรรมในต้นทุนที่ต่ำกว่า
โดยศึกษาจากเครื่อง taping ต้นแบบที่ใช้งานจริงในสายการผลิตเป็นแนวทางออกแบบ

---

## เริ่มยังไง

**ถ้าอยากเห็นระบบทำงานเร็วที่สุด** — โหมดจำลอง ไม่ต้องมีบอร์ด ไม่ต้องมีกล้อง

เปิดหน้าต่างที่ 1 รันสมองกลหลัก

```bash
cd python_backend && python gateway_fsm.py
```

เปิดหน้าต่างที่ 2 เสิร์ฟหน้าเว็บ

```bash
cd cad && python -m http.server 8000
```

แล้วเปิดเบราว์เซอร์ไปที่ `http://localhost:8000/index1.html`

> ⚠️ **ห้ามดับเบิลคลิกเปิด `index1.html` ตรง ๆ** เบราว์เซอร์จะบล็อกการโหลดไฟล์ `.glb`
> ในโหมด `file://` ต้องเสิร์ฟผ่าน http เท่านั้น

**ถ้าจะต่อบอร์ดจริง เปิดกล้อง เปิดจอ STM32 ด้วย** → อ่าน [`docs/RUNBOOK.md`](docs/RUNBOOK.md)
อย่าใช้คำสั่งย่อข้างบน เพราะขาด `RUST_BRIDGE=1` แล้วค่าที่เห็นจะเป็นของจำลองทั้งหมด

---

## เอกสาร — อ่านตามลำดับนี้

| # | ไฟล์ | อ่านเมื่อ |
|---|---|---|
| 1 | [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) | อยากเข้าใจว่าระบบทำงานยังไง + ติดตั้ง Python/ไลบรารี |
| 2 | [`DEPLOY.md`](DEPLOY.md) | ติดตั้งบนเครื่องใหม่ + **วิธีเปิดโหมดเขียน coil ลงบอร์ดจริง** |
| 3 | [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | ⭐ เปิดครบทั้ง 5 ชั้นพร้อมกัน + กับดักจากการรันจริง |
| 4 | [`docs/specs/`](docs/specs/) | จะแก้โค้ด — สเปกที่โค้ดต้องทำตาม |

**ถ้ากดรันแล้วบอร์ดไม่ตอบสนอง ไฟไม่ติด** อ่าน [`DEPLOY.md`](DEPLOY.md) หัวข้อ
"การสั่งงานเอาต์พุตลงบอร์ดจริง" ก่อน — ค่าตั้งต้นของสคริปต์เปิดระบบคือ **read-only
โดยเจตนา** ต้องใส่ flag เพิ่มถึงจะเขียนลงบอร์ดได้ ซึ่งเป็นจุดที่คนหลงทางบ่อยที่สุด

---

## โครงสร้าง repo

```
python_backend/       Python FSM gateway (สมองกลหลัก) + ชุดทดสอบ
  gateway_fsm.py        ตัวมาตรฐาน ใช้ตอนไม่ต่อบอร์ด
  gateway_fsm_upgrad.py ตัวที่ต่อ Rust bridge ไปบอร์ดจริงได้
  hmi_link.py           โมดูลกลาง คุยกับจอ TouchGFX
  serial_bridge.py      สะพาน UART ↔ TCP สำหรับจอบนบอร์ดจริง
  tests/                ชุดทดสอบอัตโนมัติ
cad/                  หน้าเว็บ 3D Twin (Three.js) + โมเดล GLB
rust_bridge/          สะพาน Modbus TCP ไปบอร์ด I/O จริง
firmware/             โปรเจกต์ TouchGFX / STM32H7S78-DK
vision_prototype/     โปรแกรมกล้อง OpenMV ตัดสิน PASS/NG
  openmv_board/         โค้ดที่รันบนตัวกล้อง (MicroPython) ไม่ใช่บน PC
docs/
  RUNBOOK.md            ⭐ เปิดครบ 5 ชั้น + กับดักจากการรันจริง
  USER_MANUAL.md        คู่มือระบบ + ตั้ง Static IP + วิธีกดปุ่มบนเว็บ
  PROJECT_PLAN.md       แผนงานและความคืบหน้า
  specs/                สเปกที่โค้ดทุกฝั่งต้องทำตาม
    machine_spec.md       สเปกเครื่อง — ต้นน้ำของทุกอย่าง
    fsm_spec.md           คำอธิบาย state machine
    state_table.csv       ตาราง state ที่โค้ดต้องตรงเป๊ะ
    protocol.md           JSON schema ระหว่างเลเยอร์
    port_map.md           ใคร listen พอร์ตไหน
    board_protocol.md     ⭐ สเปกบอร์ด Modbus จากการวัดจริง
    motion_*.md           การออกแบบ feed / takeup
  adr/                  บันทึกการตัดสินใจเชิงสถาปัตยกรรม
  test-reports/         ผลทดสอบพร้อมหลักฐาน
  bom/                  รายการอุปกรณ์
  thesis/               ของสะสมไว้ทำรูปเล่มโครงงาน
start_all.bat         เปิดระบบทั้งหมดในทีเดียว (มีเมนูเลือกโหมด)
stop_all.bat          ปิดระบบทั้งหมด
```

---

## แผนผังพอร์ต

| พอร์ต | ใคร listen | ใครต่อเข้า |
|---|---|---|
| 8765 | gateway (WebSocket) | หน้าเว็บ 3D · กล้อง OpenMV |
| 8766 | gateway (`hmi_link.py`) | จอ TouchGFX |
| 8767 | `rust_bridge` | `gateway_fsm_upgrad.py` เมื่อ `RUST_BRIDGE=1` |
| 8000 | `python -m http.server` (รันในโฟลเดอร์ `cad/`) | เบราว์เซอร์ |
| 502 | บอร์ด I/O จริง (Modbus TCP) | `rust_bridge` |

**รัน gateway ได้ทีละตัวเท่านั้น** — `gateway_fsm.py` กับ `gateway_fsm_upgrad.py`
bind พอร์ตชุดเดียวกัน · รายละเอียด [`docs/specs/port_map.md`](docs/specs/port_map.md)
· วิธีเช็คของค้างพอร์ต [`docs/RUNBOOK.md`](docs/RUNBOOK.md)

---

## ข้อควรรู้ก่อนแตะฮาร์ดแวร์

🔴 **firmware ที่รันอยู่บนบอร์ด I/O ไม่มี source code สำรองอยู่ที่ใดเลย**
แฟลชทับแล้วสร้างกลับไม่ได้ ทุกอย่างที่รู้เกี่ยวกับบอร์ดตัวนั้นถูกบันทึกไว้ที่
[`docs/specs/board_protocol.md`](docs/specs/board_protocol.md) จากการวัดจริง — อ่านก่อนเขียนโค้ดคุยกับบอร์ด

สรุปข้อจำกัดสำคัญ

- รองรับ Modbus แค่ `0x01` (read coils) และ `0x0F` (write coils) — **ไม่มี register**
- **ตัดสาย TCP เองถ้าเว้นจังหวะเกิน ~200 ms** ต้องมีทราฟฟิกเลี้ยงตลอด
- ฟิลด์ length ของเฟรมตอบไม่ตรงมาตรฐาน ใช้ไลบรารี Modbus ทั่วไปตรง ๆ ไม่ได้
- **ห้ามยิงคำสั่งข้อความที่ไม่รู้จักใส่บอร์ด** — `*RST` รีบูตบอร์ดจริง

---

## กติกาเนื้อหา

- ❌ ห้ามใส่ข้อมูลบริษัทหรือลูกค้าในไฟล์ใด ๆ รวมถึงยี่ห้อ/รุ่นของชิ้นงานที่นำมาบรรจุ
- ❌ ห้ามคัดลอกโค้ดจากโปรเจกต์ภายในบริษัท
- ✅ เฉพาะงานต้นฉบับหรือ open-source-safe เท่านั้น

**เครดิต:** นักศึกษา = ผู้ลงมือพัฒนา · พี่เลี้ยง = system architecture และคำแนะนำเชิงระบบ
