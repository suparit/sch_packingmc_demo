# Port Map — ใคร listen พอร์ตไหน

> อัปเดตล่าสุด: 2026-08-05 (เพิ่มรายละเอียดพอร์ต 502 จากการวัดบอร์ดจริง)

## ตารางหลัก

| พอร์ต | โปรโตคอล | **ใคร listen (server)** | ใครต่อเข้า (client) | เปิดเมื่อไร |
|---|---|---|---|---|
| 8765 | WebSocket | `gateway_fsm.py` / `gateway_fsm_upgrad.py` | `cad/index1.html`, `cad/analytics.html`, **`app_vision.py` (กล้อง OpenMV)** | ตลอดเวลาที่ gateway รัน |
| 8766 | TCP (JSON บรรทัดต่อบรรทัด) | gateway ผ่านโมดูล `hmi_link.py` | จอ TouchGFX — Simulator ต่อตรง / บอร์ดจริงผ่าน `serial_bridge.py` | ตลอดเวลาที่ gateway รัน |
| 8767 | TCP | `rust_bridge` (`rust_modbus_bridge.exe`) | `gateway_fsm_upgrad.py` | เฉพาะเมื่อตั้ง env `RUST_BRIDGE=1` |
| 8000 | HTTP | `python -m http.server 8000` (รันในโฟลเดอร์ `cad/`) | เบราว์เซอร์ → `http://localhost:8000/index1.html` | ตอนเปิดหน้าเว็บ local |
| **502** | **Modbus TCP + text command ปนสายเดียวกัน** | บอร์ด STM32 จริง (192.168.0.100) unit id `0x01` | `rust_bridge` (รับ client พร้อมกันได้ ≥4) | เฉพาะโหมดต่อบอร์ดจริง · 🔴 **บอร์ดตัดสายเองถ้าเงียบเกิน ~200 ms** → สเปกเต็มที่ [`board_protocol.md`](board_protocol.md) |
| **COM10** | USB VCP (binary) | บอร์ดกล้อง **OpenMV** (รัน `Cam/main.py`) | `app_vision.py` | เมื่อเสียบกล้อง |

> ห้ามเปิด `index1.html` ด้วยการดับเบิลคลิก — โหมด `file://` เบราว์เซอร์บล็อกการโหลด `.glb`

## กล้อง OpenMV — client ตัวที่ 3 ของพอร์ต 8765

โค้ดกล้องอยู่ **นอก repo นี้** ที่ `Digital-Twin-Taping Machine/Cam/` (เป็น git repo แยก)

```
[บอร์ด OpenMV: main.py] --USB VCP COM10--> [PC: app_vision.py] --WS 8765--> [gateway]
```

- **`Cam/main.py` รันบนบอร์ด ไม่ใช่บน PC** — ใช้ `sensor`/`image`/`pyb` ที่ฝังในเฟิร์มแวร์ OpenMV
  สั่ง `python main.py` บน Windows จะได้ `ModuleNotFoundError: No module named 'sensor'` เสมอ
- **โปรโตคอลบนสาย USB:** `<uint32 little-endian ขนาดภาพ><ไบต์ JPEG>` วนไปเรื่อย ๆ ทุก 20 ms
  ภาพเป็น GRAYSCALE QVGA 320×240 `compress(quality=50)` — ยืนยันของจริงแล้ว 2026-08-03
  (เจอ SOI ห่างกัน 3580 B = ขนาดภาพ 3576 + header 4)
- `app_vision.py` ต้อง**หาต้นเฟรมเอง**ตอนเริ่ม ปกติเสีย 10-15 เฟรมแรกแล้วค่อย sync ติด — ไม่ใช่บั๊ก
- ตั้ง `PRESENCE_SENSOR_MODE = True` → กล้องยิง `DECISION` เองที่สเต็ป `VISION` **แทนคนกด**
  (`app_vision_upgrad.py` ตั้ง `False`)
- ยิง `GET_STATE` ทุกช่วงเพื่อ sync สถานะ — **เป็น client เดียวที่ใช้คำสั่งนี้**

> ⚠️ ถ้า OpenMV IDE เชื่อมบอร์ดค้างอยู่ มันจอง COM10 ไว้ `app_vision.py` จะเปิดพอร์ตไม่ได้

## พอร์ต 502 — บอร์ด STM32 ตัวที่ไม่มี source code

📄 **สเปกเต็มอยู่ที่ [`board_protocol.md`](board_protocol.md)** — ที่นี่เขียนเฉพาะเรื่องพอร์ต

```
[gateway_fsm_upgrad.py] --TCP 8767--> [rust_bridge] --Modbus TCP 502--> [บอร์ด 192.168.0.100]
```

- **บอร์ดเป็น server** · `rust_bridge` เป็น client ตัวเดียวที่ต่อเข้าไปตอนนี้
- 🔴🔴 **firmware บนบอร์ดตัวนี้ไม่มี source code อยู่ที่ไหนเลย ห้ามแฟลชทับเด็ดขาด**
  (`SCH_XPLCV1_18062026` · `FW:133` · `ID:218` — ยิง `*IDN?` ถามได้)
- 🔴 **บอร์ดตัดสายเองถ้าเว้นจังหวะระหว่างคำสั่งเกิน ~200 ms** (วัดซ้ำ 3/3: 200 ms รอด / 250 ms ตาย)
  → **client ต้องเลี้ยงสายด้วยทราฟฟิกถี่กว่านั้นตลอด และต้องมี reconnect เสมอ**
  ลูป FSM 20 ms เลี้ยงได้สบาย **แต่ตอน idle สายจะหลุดแล้วต่อใหม่วนไปเรื่อย ๆ = พฤติกรรมปกติ ไม่ใช่ error**
- **พอร์ตนี้มี 2 ช่องทางในสายเดียวกัน**: เฟรม Modbus กับ **คำสั่งข้อความ** (`*IDN?`)
  ปนกันได้ไม่ทำให้สายหลุด — ⛔ **แต่ห้ามยิงคำสั่งข้อความที่ไม่รู้จัก** (`*RST` รีบูตบอร์ดจริง)
- บอร์ดรับ client พร้อมกันได้ **อย่างน้อย 4 สาย** → เปิด client ตัวที่ 2 มาอ่านค่าคู่ขนานได้
  **แต่ถ้าเพิ่มจริงต้องมาจดในตารางข้างบนนี้ก่อน** (กฎ `protocol.md` ข้อ 6.5)

## ข้อจำกัดที่ต้องรู้

1. **`gateway_fsm.py` กับ `gateway_fsm_upgrad.py` bind 8765 + 8766 เหมือนกัน → รันได้ทีละตัว**
2. **`cad/gateway.py` เป็น mock server** สำหรับทดสอบหน้าเว็บเดี่ยว ๆ — ห้ามรันพร้อม gateway ตัวจริง
3. เทสต์ใน `python_backend/tests/` เปิด/ปิด gateway เอง → **ต้องไม่มี gateway อื่นค้างอยู่ก่อนรัน**

## พอร์ต 8766 มี client 2 ชนิดในพอร์ตเดียว

แยกด้วยการ **รอเงียบ 0.25 วินาที** หลัง accept:
- เงียบครบเวลา → **live monitor**: gateway stream JSON สถานะให้ทุก 20 ms จนกว่าจะตัดสาย
- มีข้อมูลเข้ามาก่อน → **one-shot**: รับคำสั่ง ตอบ แล้วปิดสาย
  (ทุกปุ่มบนจอ + `REQ_REPORT_DATA` / `EXPORT_CSV` / `CLEAR_SQL_HISTORY` / `CLEAR_ALARM_LOGS`)
  > แก้ 2026-08-05: บรรทัดนี้เคยเขียนว่า `CLEAR_LOGS` ซึ่ง **ไม่มีคำสั่งชื่อนี้จริง** — ตรงกับ `protocol.md` ข้อ 4

## ประวัติบั๊กเรื่องพอร์ต (อย่าให้เกิดซ้ำ)

**2026-07-27 — `gateway_fsm_upgrad.py` ต่อออกไปที่ 8766**
8766 คือพอร์ตที่จอ TouchGFX ต่อเข้ามาอยู่แล้ว → กลายเป็น client ทั้งคู่ ไม่มีใคร listen
อาการ: เปิด `upgrad` แล้วจอขึ้นเลข 0 หมดทุกช่อง
แก้: ย้ายสะพาน Rust ไป 8767 + ปิดเป็นค่าเริ่มต้น (เปิดด้วย `RUST_BRIDGE=1`) + retry ทุก 3 วิ
(ของเดิม reconnect ทุก 20 ms ตอนบอร์ดไม่ได้เสียบ)

> **บทเรียน: ทุกครั้งที่เพิ่มการเชื่อมต่อใหม่ ให้ตอบก่อนว่า "ใครเป็น server" แล้วจดลงตารางนี้**

## ค้างอยู่

- ⚠️ `rust_modbus_bridge.exe` ที่มีอยู่ยังเป็นตัวเก่าที่ bind **8766**
  แก้ `PYTHON_BRIDGE_ADDR` ใน `rust_bridge/src/main.rs` เป็น 8767 แล้ว แต่**ยังไม่ได้ `cargo build`**
  → ถ้ารัน .exe ตัวเก่าคู่กับ gateway จะแย่งพอร์ตกับจอ
