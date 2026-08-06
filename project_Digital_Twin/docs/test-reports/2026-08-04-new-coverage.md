# Test Report — เทสต์ชุดใหม่: ESTOP / GET_STATE / กล้องยิง DECISION

**วันที่:** 2026-08-04 13:07–13:20
**คนรัน:** ผู้พัฒนา
**commit ฐาน:** `854d17d`
**⚠️ สภาพต้นไม้ตอนรัน:** มีงานของ `backend` ค้างอยู่ยังไม่ commit (`gateway_fsm.py` +8, `gateway_fsm_upgrad.py` +118, `rust_bridge/src/main.rs` +427)

---

## 🔴 สรุปหัวข้อเดียวที่สำคัญที่สุด

**E-STOP ถูกปลดล็อกได้ด้วยคำสั่ง `DECISION` — และกล้อง OpenMV ยิง `DECISION` เองอัตโนมัติได้**

เจอเหมือนกันเป๊ะทั้งสอง gateway ไม่ใช่ของหลุดเฉพาะตัวใดตัวหนึ่ง

## ผล

| ชุดเทสต์ | `gateway_fsm.py` | `gateway_fsm_upgrad.py` |
|---|---|---|
| `test_estop.py` | 🔴 **24/27** | 🔴 **24/27** |
| `test_get_state.py` | ✅ 15/15 | ✅ 15/15 |
| `test_cam_decision.py` | ✅ 19/19 | ✅ 19/19 |
| **regression baseline เดิม** | ✅ 16/16 | ✅ 16/16 |

รวมของใหม่ **116/122 ผ่าน** · baseline เดิม **32/32 ยังผ่านครบ** (ของ `backend` ไม่ได้ทำอะไร regress)

---

## ข้อที่ไม่ผ่าน — 3 ข้อ เหมือนกันทั้งสอง gateway

### 🔴 1. `[safety]` ยิง `DECISION` ตอน E-STOP ค้าง แล้วเครื่องหลุดจาก ALARM ได้

**คาดหวัง:** E-STOP กดแล้ว latch อยู่ที่ `ALARM` — คำสั่งอื่นต้องปลดไม่ได้ ต้อง `RESET` เท่านั้น
**ได้จริง:** ยิง `DECISION` เข้าไป เครื่องรับและเดินต่อ

log จริงจาก gateway:
```
🚨 [COMMAND]: EMERGENCY STOP! Saved break step: VISION
[RECV DECISION] value=True meta=None | step_allowed=True
🕹️ [DECISION]: Operator Clicked OK
```

**สาเหตุที่น่าจะเป็น:** `ESTOP` **ไม่ได้เคลียร์ `step_allowed`**
ถ้ากด E-STOP ตอนเครื่องค้างอยู่ที่ `VISION` (ซึ่ง `step_allowed=true` อยู่แล้ว) ธงนั้นยังเป็น `true`
→ `apply_decision()` จึงรับคำสั่ง → พาเครื่องออกจาก ALARM

**ทำไมถึงอันตรายกว่าที่เห็น:** `PRESENCE_SENSOR_MODE=True` ทำให้กล้อง OpenMV
ยิง `DECISION` **เองอัตโนมัติ** เมื่อเห็นชิ้นงาน (ยืนยันแล้วใน `test_cam_decision.py` ว่ายิงได้จริง)
แปลว่า **E-STOP อาจถูกปลดโดยไม่มีคนแตะอะไรเลย**

ขัดกับ `machine_spec.md` ข้อ 6 ที่ระบุว่า E-STOP → ตัดกำลังขับทันที เป็นเงื่อนไขที่ห้ามละเมิด

### 🔴 2. `[spec]` `RESET` ไม่เคลียร์ `step_allowed` (ทาง WS หลัง ESTOP ที่ `VISION`)

`protocol.md` ข้อ 4 และ `fsm_spec.md` ข้อ 2.3 ระบุตรงกันว่า `RESET` ต้องเคลียร์ `step_allowed`
ไม่งั้นค้างเป็น `true` ข้ามรอบ แล้วรอบถัดไปจะข้ามการรอ operator

### 🔴 3. `[spec]` `RESET` ทาง TCP ไม่กลับไป state ที่ค้าง

```
ก่อน ESTOP = INDEX_CARRIER    หลัง RESET = LOAD_CARRIER
```

**RESET ทาง TCP กับทาง WS ทำงานคนละอย่าง** — เห็นจาก log ว่าทาง TCP วิ่งเข้า
`🧹 [TOUCHGFX CMD]: RESET BATCH` → `FULL RESET` (ล้าง counter กลับต้นรอบ)
ส่วนทาง WS วิ่งเข้า `🔄 [RESUME EXACT STEP]` / `🔄 [CMD: RESET] Resuming step -> [INDEX_CARRIER]` ตามสเปก

เป็นปัญหาตระกูลเดียวกับ `SET_PARAMS` ที่สองช่องทางทำงานไม่เหมือนกัน (`protocol.md` ข้อ 7.1)
ขัดหลัก "logic การตัดสินต้องมีที่เดียว" ใน `fsm_spec.md` ข้อ 2.5

> **ไม่ได้แก้โค้ดให้เทสต์ผ่าน** ตามกฎใน `test-reports/README.md` — และไฟล์ทั้งสองกำลังถูก `backend` แก้อยู่พอดี

---

## ข้อที่ผ่าน — ของที่ยืนยันได้แล้ว

### `test_cam_decision.py` — สเต็ป `VISION` ตัดสินได้ 3 ทางจริง

ข้อสงสัยที่ตั้งไว้ใน `2026-08-04-regression.md` ได้คำตอบแล้ว **กล้องเป็นผู้ตัดสินได้เต็มตัว**

- กล้องยิง `DECISION` PASS → `DECISION_ACK accepted=true` → **เว็บและจอเห็นผลเหมือนกัน** (`VISION → COUNT_CHECK`)
- ลำดับหลัง PASS ตรง `state_table.csv`: `VISION → CHECK_TEMP → FEED_CARRIER → COUNT_PROCESS`
- กล้องยิง NG → `VISION → ALARM` ตรงกับคอลัมน์ `next_state_ng` แถว 7 และบันทึกเหตุผลเป็น
  `⚠️ ERROR: OPERATOR REJECTION (SEMI-AUTO NG)`
- `DECISION_ACK` ส่งกลับ**เฉพาะตัวที่ยิง** ไม่กระจายให้ client อื่น
- จอ TouchGFX ไม่หลุดตลอดการทดสอบ (ได้ stream 240 / 232 เฟรม)
- ยิงตอน FSM ไม่ได้รอ → `⚠️ [DECISION IGNORED] FSM not accepting decisions now.` ถูกปฏิเสธตามสเปก

meta ที่กล้องแนบมาถูกบันทึกจริง: `meta={'src': 'openmv', 'conf': 0.97, 'mode': 'presence'}`

### `test_get_state.py` — ยืนยัน `protocol.md` ที่เพิ่งเขียนใหม่ถูกต้องทุกข้อ

- TCP 8766 = JSON **แบน 10 คีย์ ไม่ขาดไม่เกิน** (ขาด=[] เกิน=[]) ตรง `protocol.md` ข้อ 2 เป๊ะ
- WS 8765 = **มี wrapper `.system` ครอบ** 17 คีย์ ตรงข้อ 3
- **ไม่มีคีย์ชื่อ `state`** อยู่จริงตามที่สเปกระบุ
- `GET_STATE` ทาง TCP 8766 **ไม่มีคำตอบ** (ตรงกับ ❌ ในตารางข้อ 4) และไม่ทำให้ stream จอหลุด
- `machine_params` **ไม่มีตอนบูต โผล่หลัง `SET_PARAMS` เท่านั้น** ตรงข้อ 3
- `GET_STATE` ตอบรายตัวจริง (ตัวที่ยิงได้ 16 เฟรม / ตัวที่เงียบได้ 4 เฟรม ใน 0.25 วิ)

## วิธีรันซ้ำ

```bash
cd python_backend/tests && python test_estop.py gateway_fsm.py
```
```bash
cd python_backend/tests && python test_get_state.py gateway_fsm.py
```
```bash
cd python_backend/tests && python test_cam_decision.py gateway_fsm.py
```
> สลับ argument เป็น `gateway_fsm_upgrad.py` เพื่อรันกับอีกตัว · ต้องไม่มี gateway อื่นค้างอยู่

## ที่ต้องทำต่อ

| ลำดับ | ใคร | อะไร |
|---|---|---|
| 1 | `fsm` | ตัดสินว่า `ESTOP` ต้องเคลียร์ `step_allowed` ไหม และ ALARM จาก E-STOP ต้อง latch แน่นแค่ไหน — **เป็นเรื่อง safety ต้องนิยามใน `fsm_spec.md` ก่อน ไม่ใช่ให้ backend เดาแก้** |
| 2 | `backend` | แก้ตามที่ `fsm` นิยาม + รวม RESET ของ TCP กับ WS ให้เป็น logic เดียว |
| 3 | `testing` | รันซ้ำยืนยัน 3 ข้อกลับมาเป็น PASS |

## ที่ยังตรวจไม่ได้

- **จอ TouchGFX ของจริง** — ยังไม่มีใครดูด้วยตา (`simulator.exe` 8/3 16:01 + ยังไม่ได้ Generate Code รอบ 31 ก.ค.)
- **Rust bridge ↔ บอร์ดจริง** — `backend` กำลังทำอยู่ ยังไม่มีผล
- **กล้อง OpenMV ตัวจริงยิงเข้า gateway** — เทสต์นี้**จำลอง**พฤติกรรมด้วย WS client ไม่ได้ต่อกล้องจริง
  (โปรโตคอล USB ของกล้องยืนยันแยกไว้แล้วใน `docs/worklog/2026-08-04-integration.md`)
