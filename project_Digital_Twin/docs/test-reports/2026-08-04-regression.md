# Test Report — Regression baseline หลังย้าย repo

**วันที่:** 2026-08-04 10:44–10:47
**คนรัน:** ผู้พัฒนา
**commit ที่ทดสอบ:** `fee17fe` + การแก้ path ในเทสต์ที่ยังไม่ commit ตอนรัน
**เครื่อง:** Windows 11 / Python 3.13.2

---

## ⚠️ ข้อค้นพบสำคัญที่สุดของรอบนี้ — เทสต์พังมาตลอด ไม่มีใครรู้

`test_hmi_link.py:19` และ `test_ws.py:11` fix ค่า `BACKEND` ไว้เป็น

```
E:\work-TE-Project\test-HMI-STM32\TestWab-main-new\TestWab-main\python_backend
```

**path นี้ไม่มีอยู่บนเครื่องแล้ว** (โฟลเดอร์เดิมก่อนย้ายเข้า repo `dt-taping-dev`)
แปลว่านับตั้งแต่ย้าย repo **ไม่มีใครรันเทสต์ทั้ง 4 ชุดได้เลยสักครั้ง** —
"baseline 10 ข้อผ่าน" ที่ `HANDOFF.md` และ `test-reports/README.md` อ้างถึง เป็นผลของ
**โฟลเดอร์เก่า ไม่ใช่โค้ดที่อยู่ใน repo นี้**

**แก้แล้ว:** เปลี่ยนเป็นอ้างจากที่อยู่ของไฟล์เทสต์เอง ย้าย repo อีกกี่ครั้งก็ไม่พัง
```python
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```

> **นี่คือ regression report ฉบับแรกที่รันกับโค้ดใน `dt-taping-dev` จริง**

## ขอบเขต

**ทดสอบ:** FSM gateway ทั้ง 2 ตัว × 2 ช่องทาง (TCP 8766 ฝั่งจอ / WebSocket 8765 ฝั่งเว็บ)
**ไม่ได้ทดสอบ:** UI บนจอ TouchGFX, Rust bridge, บอร์ดจริงผ่าน UART, กล้อง OpenMV → gateway (ดูข้อ "ยังไม่ครอบ")

## วิธีรัน

ปิด demo stack ก่อน (`gateway_fsm.py` + `serial_bridge.py` + `http.server 8000` แย่งพอร์ต)

```bash
cd python_backend/tests && python test_hmi_link.py gateway_fsm.py
```
```bash
cd python_backend/tests && python test_hmi_link.py gateway_fsm_upgrad.py
```
```bash
cd python_backend/tests && python test_ws.py gateway_fsm.py
```
```bash
cd python_backend/tests && python test_ws.py gateway_fsm_upgrad.py
```

## ผล — 32/32 ผ่าน (exit code 0 ทั้ง 4 ชุด)

### TCP 8766 (ฝั่งจอ TouchGFX) — 11 ข้อ × 2 gateway

| ข้อทดสอบ | `gateway_fsm.py` | `gateway_fsm_upgrad.py` |
|---|---|---|
| ไม่ตายหลัง 2.5 วิ ตอน stdout ถูก redirect (encoding fix) | ✅ | ✅ |
| จอต่อ 8766 แล้วได้ payload สถานะ | ✅ | ✅ |
| payload มีคีย์ `step_allowed` | ✅ | ✅ |
| payload มีคีย์ `pitch` | ✅ | ✅ |
| `SET_PARAMS` จากจอมีผล + broadcast กลับ (target=77 pitch=12) | ✅ | ✅ |
| `START` จากจอ → `running=true` | ✅ | ✅ |
| หยุดรอ operator ที่เช็คพอยต์ (`step_allowed=true` ที่ `VISION`) | ✅ | ✅ |
| ค้างรอจริง 2 วิ ไม่หลุดเอง ไม่เด้ง ALARM | ✅ | ✅ |
| กด PASS บนจอแล้วเดินต่อ (`VISION → CHECK_TEMP`) | ✅ | ✅ |
| `REQ_REPORT_DATA` ตอบครบ 6 คีย์ | ✅ | ✅ |
| `EXPORT_CSV` เขียนไฟล์สำเร็จ | ✅ | ✅ |

### WebSocket 8765 (ฝั่งเว็บ) — 5 ข้อ × 2 gateway

| ข้อทดสอบ | `gateway_fsm.py` | `gateway_fsm_upgrad.py` |
|---|---|---|
| `START` ผ่าน WS | ✅ | ✅ |
| หยุดรอ operator ที่ `VISION` | ✅ | ✅ |
| `DECISION` PASS ผ่าน WS แล้วเดินต่อ (`VISION → CHECK_TEMP`) | ✅ | ✅ |
| `DECISION` ตอน FSM ไม่ได้รอ → ปฏิเสธ `accepted=false` `reason=not_allowed` | ✅ | ✅ |
| `GET_HISTORY` ตอบประวัติ SQL | ✅ 26 rows | ✅ 33 rows |

log จริงที่ได้:
```
PASS  กด PASS บนจอแล้วเครื่องเดินต่อ   VISION -> CHECK_TEMP
PASS  DECISION ตอนไม่ได้รอ ถูกปฏิเสธ (accepted=false)
      {'type': 'DECISION_ACK', 'accepted': False, 'reason': 'not_allowed'}
PASS  EXPORT_CSV เขียนไฟล์ CSV สำเร็จ
      {"status":"saved","file":"report_2026-08-04_104500.csv"}
```

## ข้อที่ไม่ผ่าน

**ไม่มี** — แต่มี 1 เหตุการณ์ที่ควรบันทึก

รอบ `test_hmi_link.py gateway_fsm.py` เจอ **fault injection สุ่มเด้ง `ALARM`** ก่อนถึง `VISION`
(เครื่องสุ่มความเสียหาย SENSOR_CHECK 1.5% / VISION 2% ≈ 3.5% ต่อรอบ — จงใจใส่ไว้)
เทสต์ `RESET` แล้วลองใหม่ ผ่านในรอบถัดไป **เป็นพฤติกรรมที่ออกแบบไว้ ไม่ใช่บั๊ก**
อีก 3 ชุดไม่เจอ — ยืนยันว่าเป็นการสุ่มจริง

## ยังไม่ครอบ (พูดตรง ๆ)

จาก `protocol.md` ที่เพิ่งไล่เทียบกับโค้ดจริง — มีของที่ไม่มีเทสต์จับเลย

| # | เรื่อง | ทำไมสำคัญ |
|---|---|---|
| 1 | **กล้อง OpenMV ยิง `DECISION`** | สเต็ป `VISION` ตัดสินได้ **3 ทาง** (จอ/เว็บ/กล้อง) เทสต์ครอบแค่ 2 — และกล้องตัดสิน**แทนคน**ได้เมื่อ `PRESENCE_SENSOR_MODE=True` |
| 2 | **`SET_PARAMS` ทาง WebSocket ทิ้ง 9 ช่อง** | `gateway_fsm.py:465-468` ต่างจากทาง TCP ที่เก็บครบ ไม่มีเทสต์จับความต่างนี้ |
| 3 | `ESTOP` | มีในโค้ดทั้ง 2 ช่องทาง ไม่มีเทสต์เลย — เป็น safety interlock ตาม `machine_spec.md` ข้อ 6 |
| 4 | `CLEAR_SQL_HISTORY` / `CLEAR_ALARM_LOGS` | ไม่มีเทสต์ (และสเปกเดิมเขียนชื่อผิดเป็น `CLEAR_LOGS`) |
| 5 | `GET_STATE` | ไม่มีเทสต์ — เป็นคำสั่งที่มีแต่กล้องใช้ |
| 6 | `MODE` / `SPEED` | ไม่มีเทสต์ยืนยันว่ามีผลจริง |

## ที่ต้องตรวจด้วยตา (คนต้องไปกดเอง)

- **จอ TouchGFX** — `simulator.exe` build ใหม่ 2026-08-03 16:01 แต่ยังไม่มีใครดู
  เน้น overlay PASS/NG ของสเต็ป `VISION` และปุ่ม SAVE PARAMS
  ⚠️ ต้องเปิด Designer กด **Generate Code** ก่อน เพราะ `NOXCORE.touchgfx` (31 ก.ค.) ยังไม่ถูก generate
- **หน้าเว็บ 3D** — เปิด `http://localhost:8000/index1.html` ดู console error + โมเดล `.glb` โหลดครบไหม
- **Rust bridge** — ยังไม่ได้ `cargo build` ใหม่ (พอร์ตเปลี่ยนเป็น 8767 แล้ว)
