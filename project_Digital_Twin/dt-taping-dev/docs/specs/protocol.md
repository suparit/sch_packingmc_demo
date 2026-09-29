# Protocol — สัญญาการรับส่งข้อมูลระหว่างเลเยอร์

> **เจ้าของไฟล์: agent `integration`** — `backend` / `stm32` / `frontend` อ่านอย่างเดียว
> แก้ไฟล์นี้แล้ว **ต้องแก้ทั้ง 3 ฝั่งพร้อมกัน** เพราะ compile ไม่ฟ้อง ระบบจะพังเงียบ ๆ
> สถานะ: ✅ **ไล่เทียบกับโค้ดจริงแล้ว 2026-08-07** ทุกแถวมีเลขบรรทัดอ้างอิง
> เอกสารนี้บันทึก **สิ่งที่โค้ดทำจริง** ไม่ใช่สิ่งที่อยากให้ทำ — ส่วนที่ควรแก้อยู่ข้อ 7
>
> **แก้ล่าสุด 2026-08-07** — เพิ่ม `predictive_warning` เข้า payload ของจอ (ข้อ 2) จาก 10 → **11 คีย์**
> เพื่อให้สองช่องทางส่งข้อมูลชุดเดียวกัน · ดูงานที่แต่ละฝั่งต้องทำต่อที่ **ข้อ 2.1**
> พร้อมกันนี้แก้เลขบรรทัดอ้างอิงที่ล้าสมัยของข้อ 2 และข้อ 3 ให้ตรงกับโค้ดปัจจุบัน
>
> **แก้ล่าสุด 2026-09-24 (สัญญาใหม่ — โค้ดยังไม่ได้ทำ)** — โหมด `step` + action `NEXT` + คีย์ใหม่ใน `LIVE_SYNC`
> (**ข้อ 8**) และสัญญาเต็มของสาย 8767 Python ↔ Rust รวมคำสั่ง feed มอเตอร์ (**ข้อ 9**)
> · payload จอ 8766 **ไม่เปลี่ยน ยัง 12 คีย์** · ข้อ 3/4/7 แก้ตาม · FSM ที่อยู่เบื้องหลังดู `fsm_spec.md` ข้อ 7–8

## 1. ภาพรวม

```
[TouchGFX HMI]  --TCP 8766-->  [Python Gateway]  --WebSocket 8765-->  [เว็บ 3D Twin]
                                      |                          └--> [กล้อง OpenMV (app_vision.py)]
                                --TCP 8767--> [Rust Modbus Bridge] --Modbus TCP 502--> บอร์ดจริง
```
พอร์ตและบทบาท server/client ดูที่ [`port_map.md`](port_map.md)

> 📄 **ช่วงสุดท้าย (Rust ↔ บอร์ด STM32 ที่ `192.168.0.100:502`) ไม่ได้อยู่ในไฟล์นี้**
> อยู่ที่ [`board_protocol.md`](board_protocol.md) — เฟรม Modbus, ข้อจำกัด **idle ~200 ms**,
> คำสั่งข้อความ (`*IDN?`) และ ⛔ ข้อห้ามเรื่องแฟลชบอร์ด (firmware ตัวนั้น **ไม่มี source code**)

> ⚠️ **payload ของ 8765 กับ 8766 คนละรูปทรงกัน** ไม่ใช่ก้อนเดียวกันที่ส่งสองทาง — ดูข้อ 2 กับ 3

---

## 2. Status payload → จอ TouchGFX (TCP 8766)

`hmi_link.build_state_payload()` — `hmi_link.py:290-304` · ส่งทุก **20 ms** · JSON แบน ปิดท้ายด้วย `\n`

| คีย์ | ชนิด | ความหมาย | หมายเหตุ |
|---|---|---|---|
| `current_state` | string | ชื่อ state ปัจจุบัน | ต้องตรง `state_name` ใน `state_table.csv` เป๊ะ |
| `fsm_state` | string | **alias ของ `current_state`** | ค่าเดียวกันเป๊ะ ส่งซ้ำเพื่อความเข้ากันได้ย้อนหลัง |
| `running` | bool | FSM กำลังเดินอยู่ไหม | |
| `pieces_count` | int | จำนวนชิ้นที่ทำได้ในรอบนี้ | |
| `actual_pcs` | int | **alias ของ `pieces_count`** | ค่าเดียวกันเป๊ะ |
| `target_pieces` | int | เป้าหมายชิ้นของ batch | |
| `pitch` | int | ระยะ pitch (mm) | default 24 |
| `current_temp` | int | อุณหภูมิปัจจุบัน (°C) | ค่าจำลอง ยังไม่ได้อ่านจาก sensor จริง |
| `cycles` | int | จำนวนรอบสะสม | |
| `step_allowed` | bool | FSM กำลังรอ operator ตัดสินอยู่ไหม | `true` = จอเด้ง overlay PASS/NG |
| `predictive_warning` | string | ข้อความสถานะ/เตือน/error ล่าสุดจาก FSM · ไม่มีเรื่องให้เตือน = `""` | ⚠️ **ห้ามสมมติว่าเป็น ASCII ล้วน** และมีเพดานความยาว — ดูข้อ 2.2 กับ 2.3 |
| `manual_seal` | string | สถานะสั่งกระบอกซีลด้วยมือ `"DOWN"` / `"UP"` | เพิ่ม 2026-09-23 · เป็นสถานะที่ **gateway ยอมรับแล้ว** (หลังผ่าน interlock ข้อ 4.1) ไม่ใช่แค่ปุ่มที่กด · ไม่มีเซนเซอร์ยืนยันตำแหน่งจริง |
| `cyl_c` | string | สถานะ Cylinder C (ปุ่ม INIT หน้า Main) `"ON"` / `"OFF"` | เพิ่ม 2026-09-24 · สถานะที่ gateway ยอมรับแล้ว (ข้อ 4.3) · จอใช้ตัดสินว่ากด INIT ครั้งถัดไปส่ง `ON` หรือ `OFF` · ไม่มีเซนเซอร์ยืนยัน |

**มีแค่ 13 คีย์นี้เท่านั้น** — ไม่มี `machine_params` (จออ่านค่าที่ตัวเองเซฟกลับมาไม่ได้ ดูข้อ 7)
`manual_seal` และ `cyl_c` **ไม่ได้อยู่ใน `system_data`** (เก็บใน `hmi_link.py`) จึงไม่โผล่ใน `LIVE_SYNC` ของข้อ 3 — จำนวนคีย์ฝั่ง WS คงเดิม (Cylinder C ดูบน WS ได้จาก `op1` bit 2)

> ℹ️ `predictive_warning` **ไม่ใช่คีย์ใหม่ของระบบ** — มีอยู่ในฝั่ง WS (ข้อ 3) มาตั้งแต่แรก
> การเพิ่มเข้ามาตรงนี้คือทำให้ **สองช่องทางส่งข้อมูลชุดเดียวกัน** ไม่ใช่ขยายสัญญาเพิ่ม
> ที่มาของค่า: `gateway_fsm.py:62-78` (ค่าเริ่มต้น) และจุดที่เขียนทับตลอด FSM

### 2.1 ใครต้องทำอะไรต่อ (เพิ่มคีย์ที่ 11 เมื่อ 2026-08-07)

| agent | ต้องทำ |
|---|---|
| `backend` | เพิ่ม `"predictive_warning": s.get("predictive_warning", "")` ใน `build_state_payload()` (`hmi_link.py:290-304`) · **ต้องทำตามข้อ 2.2 เรื่องการ serialize ด้วย** ไม่งั้นจอได้ข้อความแต่แสดงเป็นขยะ |
| `testing` | `testkit.py:38` `HMI_PAYLOAD_KEYS` เพิ่มคีย์นี้เข้า set (10 → 11 ตัว) · `test_get_state.py:118` ข้อความเช็ค "ครบ 10 คีย์ ไม่ขาดไม่เกิน" **ต้องแก้เป็น 11** · คอมเมนต์ `testkit.py:36` ที่เขียนว่า "10 คีย์ … (hmi_link.py:199-213)" ล้าสมัยทั้งบรรทัด |
| `stm32` | ✅ **ไม่ต้องทำอะไร** — `Model.cpp:102-106` มองหาคีย์นี้เป็นตัวสุดท้ายในสายอยู่แล้ว (`alarm_message` → `alarm_text` → `alarm` → `error` → `predictive_warning`) · ที่จอขึ้น `[ SYSTEM FAULT ]` (fallback ที่ `Model.cpp:125-130`) ตลอดมา เพราะไม่เจอคีย์ไหนเลย ไม่ใช่เพราะโค้ดรับผิด |

### 2.2 ⚠️ ค่านี้ไม่ใช่ ASCII ล้วน — และรูปแบบบนสาย (wire format) เป็นข้อบังคับ

ค่าจริงที่ FSM ใส่มามี **อีโมจิ** ปนอยู่แทบทุกตัว และในอนาคตอาจมี **ภาษาไทย** ด้วย เช่น

```
⚠️ ERROR: OPERATOR REJECTION (SEMI-AUTO NG)
🚨 CRITICAL: HEATER OVERHEATED (OVER 200°C)
🎉 SUCCESS: PRODUCTION BATCH COMPLETED!
```

ฝั่งจอเตรียมรับเรื่องนี้ไว้แล้ว: `sanitizeAlarmText()` (`MainScreenView.cpp:363-389`)
กรองเหลือเฉพาะ **ASCII 0x20..0x7E** เพราะฟอนต์ `monosb_12` มีแค่ช่วงนั้น
(ถ้ากรองแล้วไม่เหลืออะไรเลย จอใช้ `[ CHECK MACHINE ]` แทน — `MainScreenView.cpp:429-432`)

> 🔴 **ข้อบังคับ: บนสาย 8766 ค่านี้ต้องเป็น UTF-8 ดิบ ห้ามเป็น escape `\uXXXX`**
>
> `Model.cpp:108-122` แกะค่าด้วยการหา `"` คู่แรกใน buffer ดิบ **ไม่มีขั้นตอน unescape JSON**
> `json.dumps()` ของ Python ตั้ง `ensure_ascii=True` เป็นค่าเริ่มต้น → อีโมจิ `⚠️` บนสายจะกลายเป็น
> **ข้อความ 12 ตัวอักษร** `\u26a0\ufe0f` ซึ่งเป็น **ASCII ล้วนทุกตัว** (`\`, `u`, เลขฐานสิบหก)
> จึงรอด `sanitizeAlarmText()` มาได้ทั้งดุ้น ไม่โดนกรองทิ้งอย่างที่ตั้งใจ
> ผลคือจอขึ้น `[ \u26a0\ufe0f ERROR: OPERATOR REJECTION (SEMI-AUTO NG) ]` — อ่านไม่รู้เรื่องเหมือนเดิม
>
> ฝั่ง `backend` เลือกทางแก้ได้ 2 ทาง (สัญญานี้สนใจแค่ผลบนสาย):
> 1. serialize payload 8766 ด้วย `ensure_ascii=False` → อีโมจิไปเป็นไบต์ UTF-8 ดิบ จอกรองทิ้งเองสะอาด
> 2. strip อักขระ non-ASCII ทิ้งตั้งแต่ฝั่ง Python ก่อนใส่ลง payload
>
> ทางที่ 1 ตรงกับที่ firmware ออกแบบไว้ (คอมเมนต์ `MainScreenView.cpp:360-362` เขียนว่า
> "อีโมจิที่หลุดมาจาก backend") และไม่กระทบอีก 10 คีย์ที่เป็น ASCII อยู่แล้ว

### 2.3 ⚠️ เพดานความยาว — ยาวเกินคือ **หายทั้งก้อน** ไม่ใช่โดนตัดครึ่ง

`Model.cpp:116` รับเฉพาะ `len > 0 && len < 63` และ `alarmBuf` เป็น `char[64]`
**ถ้าเกิน เงื่อนไขไม่ผ่าน → ไม่เขียนอะไรลง `alarmBuf` เลย** ค่าเดิม (`NONE`) ค้างอยู่
แล้วตกไปเข้า fallback `[ SYSTEM FAULT ]` — อาการเดียวกับตอนไม่ส่งคีย์มาเลย แยกไม่ออกด้วยตา

- `len` นับ **ไบต์บนสาย** ไม่ใช่จำนวนตัวอักษรที่คนมองเห็น
  · อีโมจิ 1 ตัว = **6 ไบต์** ถ้าส่งเป็น UTF-8 ดิบ (ทางที่ 1 ข้างบน) หรือ **12 ไบต์** ถ้าเป็น `\uXXXX`
  · `°` = 2 ไบต์ (UTF-8) / 6 ไบต์ (escape) · อักษรไทย 1 ตัว = 3 ไบต์ / 6 ไบต์
- จอห่อด้วย `"[ %.*s ]"` (`Model.cpp:117`) = **+4 ไบต์** ลงกล่อง 64 → ข้อความ 60+ ไบต์
  ถึงผ่านเงื่อนไขก็โดน `snprintf` ตัดท้าย ` ]` หายไป

> 📏 **สเปกกำหนด: ข้อความ `predictive_warning` ควรยาว ≤ 60 ไบต์บนสาย** (ปลอดภัยจริง ๆ คือ ≤ 59)
> `backend` ต้องนับก่อนทุกครั้งที่เพิ่มข้อความใหม่ — **นับความยาวหลัง serialize ไม่ใช่นับตัวอักษรในซอร์ส**
> ข้อความที่มีอยู่แล้วตัวหนึ่งเกินเพดานนี้ ดูข้อ 7 รายการที่ 8

## 3. Status payload → เว็บ + กล้อง (WebSocket 8765)

`broadcast_state()` — `gateway_fsm.py:562-570` · ส่งทุก **50 ms** · **มี wrapper ครอบ**

```json
{"type": "LIVE_SYNC", "system": { ...system_data ทั้งก้อน... }}
```

`system_data` — `gateway_fsm.py:62-78` (ฝั่งเว็บต้องแกะ `.system` ก่อนถึงจะเจอคีย์) · **17 คีย์**
→ **25 คีย์หลังทำข้อ 8** (เพิ่ม `step_wait` + `feed_*` 7 ตัว — ตารางข้อ 8.4 · ทั้งสอง gateway ต้องมีครบ)

| คีย์ | ชนิด | หมายเหตุ |
|---|---|---|
| `current_state` | string | ตรงกับของ 8766 |
| `running`, `step_allowed`, `cycles`, `pieces_count`, `target_pieces`, `pitch`, `current_temp` | | ตรงกับของ 8766 |
| `mode` | string | `"auto"` เริ่มต้น · ค่าที่ถูกต้อง `"auto"` \| `"semi"` \| `"step"` (step เพิ่ม 2026-09-24 ข้อ 8) — **ไม่มีใน payload ของจอ** |
| `speed_mul` | float | ตัวคูณความเร็ว (1.0 = ปกติ) — **ไม่มีใน payload ของจอ** |
| `ip0`, `ip1`, `op0`, `op1` | int | สถานะ I/O ดิบ 8 บิต — **ไม่มีใน payload ของจอ** · วิ่งลงถึงบอร์ดผ่าน Rust: **`op0` → coil addr 64** (ไฟสถานะ FSM) · **`op1` → coil addr 72** (โซลินอยด์กระบอกซีล — เริ่ม 2026-09-23) · **`ip0`** อ่านจากขาอินพุตจริง · `ip1` ยังไม่ออกจาก Python — ดู [`board_protocol.md`](board_protocol.md) ข้อ 9 · ⚠️ **`op1` ในนี้คือบิตที่ Python สั่ง ไม่มี PUL (bit 4) เด็ดขาด** — พัลส์ feed สร้างใน `rust_bridge` (ข้อ 9.6) ดูความคืบหน้าจาก `feed_*` แทน |
| `camera1_count`, `encoder_count` | int | ตัวนับ — **ไม่มีใน payload ของจอ** |
| `predictive_warning` | string | ข้อความสถานะ/เตือน/error ล่าสุดจาก FSM — **ตรงกับของ 8766 ตั้งแต่ 2026-08-07** (เดิมมีแค่ฝั่งนี้ จึงมีแต่เว็บที่แสดงข้อความจริงได้ ส่วนจอตกไปใช้ fallback) · ฝั่งเว็บได้อีโมจิเต็ม ๆ เพราะเบราว์เซอร์ `JSON.parse` ให้ ต่างจากจอที่แกะสตริงดิบ — ดูข้อ 2.2 |
| `machine_params` | object | **โผล่เฉพาะหลังจอส่ง `SET_PARAMS` มาแล้ว** ตอนเริ่มต้นไม่มีคีย์นี้ — ดูข้อ 5 |

> ❌ **ไม่มีคีย์ชื่อ `state` อยู่ในระบบเลย** ทั้งสองช่องทาง ใครเขียนโค้ดอ่าน `state` จะได้ `undefined`

## 4. คำสั่ง client → gateway

รูปแบบ: `{"action": "<ชื่อคำสั่ง>", ...}`

| action | จอ (8766) | เว็บ (8765) | กล้อง (8765) | payload เพิ่ม | ผล |
|---|---|---|---|---|---|
| `START` | ✅ | ✅ | — | — | เริ่มรอบทำงาน |
| `STOP` | ✅ | ✅ | — | — | หยุด |
| `RESET` | ✅ | ✅ | — | — | ออกจาก ALARM กลับ state ที่ค้าง + **เคลียร์ `step_allowed`** |
| `ESTOP` | ✅ | ✅ | — | — | ตัดกำลังขับ → เข้า `ALARM` ทันที |
| `MODE` | ✅ | ✅ | — | **`mode`**: `"auto"` \| `"semi"` \| `"step"` | เปลี่ยนโหมดทำงาน · ⚠️ **คีย์คือ `mode` ไม่ใช่ `value`** (สเปกฉบับก่อนเขียนผิด — โค้ดทั้งสอง gateway และ `index1.html:413` ใช้ `mode`) · กติกา + `MODE_ACK` ข้อ 8.3 |
| `NEXT` | ✅ (logic พร้อม แต่ firmware ยังไม่ส่ง) | ✅ | — | `expect_state`: string (ไม่บังคับ) | โหมด `step` — ปล่อยสเต็ปที่ค้าง `step_wait` · ตอบ `NEXT_ACK` ทาง WS — ข้อ 8.1–8.2 (เพิ่ม 2026-09-24) |
| `SPEED` | ✅ | ✅ | — | `value` | ปรับความเร็ว |
| `DECISION` | ✅ | ✅ | ✅ | `value`: bool (+`meta` ไม่บังคับ) | PASS=`true` / NG=`false` — **FSM ไม่ได้รอ = ปฏิเสธ ห้ามกระโดดสเต็ป** |
| `SET_PARAMS` | ✅ | ⚠️ | — | 10 ช่อง (ดูข้อ 5) | ⚠️ สองทางทำงานไม่เหมือนกัน — ดูข้อ 7 |
| `MANUAL_SEAL` | ✅ | ❌ | — | `value`: `"DOWN"` \| `"UP"` | สั่งกระบอกซีล A+B (Welding Mechanism) **กดลงค้าง / ขึ้นค้าง** จากหน้า Maintenance — ดูข้อ 4.1 |
| `SERVICE_MODE` | ✅ | ❌ | — | `value`: bool | `true` = เข้าหน้า Maintenance/Settings → **หยุดเครื่อง + ล็อก START ทุกช่องทาง** · `false` = ออกแล้ว ปลดล็อก — ดูข้อ 4.2 |
| `CYL_C` | ✅ | ❌ | — | `value`: `"ON"` \| `"OFF"` | ปุ่ม **INIT** หน้า Main — Cylinder C ค้าง / ปล่อย (`op1` bit 2) — ดูข้อ 4.3 (เพิ่ม 2026-09-24) |
| `SINGLE_CYCLE` | ✅ | ❌ | — | — | ปุ่ม **STEP** หน้า Main — เดินครบ 1 รอบ (16 สเต็ป) แล้วหยุดที่ `LOAD_CARRIER` — ดูข้อ 4.4 (เพิ่ม 2026-09-24) · **คนละเรื่องกับโหมด `step`/`NEXT` ข้อ 8** |
| `GET_STATE` | ❌ | ✅ | ✅ | — | ตอบ `LIVE_SYNC` กลับทันที 1 ครั้ง |
| `GET_HISTORY` | ❌ | ✅ | — | — | ตอบ `HISTORY_RESPONSE` (100 แถวล่าสุด) |

อ้างอิง: จอ `gateway_fsm.py:102-153` · เว็บ `gateway_fsm.py:417-499` · หน้าเว็บยิงจริง `index1.html:413-530` · กล้อง `app_vision.py:116,192`

### 4.1 `MANUAL_SEAL` — สั่งกระบอกซีลด้วยมือ (เพิ่ม 2026-09-23) 🔴 safety

ปุ่ม ▲ UP / ▼ DOWN แถว "Welding Mechanism" หน้า Maintenance · logic อยู่ที่ `hmi_link.py`
ที่เดียว (`manual_seal_command()` + `manual_seal_bits()`) สอง gateway เรียกตัวเดียวกัน

| เรื่อง | กติกา |
|---|---|
| บิตที่ขับ | **`op1`** bit0 = โซลินอยด์ A, bit1 = โซลินอยด์ B (coil addr **72** = แผ่น OP1) → `DOWN` = `op1 = 0x03` · `UP` = `op1 = 0x00` (สปริงดันกลับ) · **ย้ายจาก `op0` มา `op1` เมื่อ 2026-09-23** ตามที่ user สั่ง — `op0` เป็นไฟแสดงสถานะ FSM (FEED/SEAL/TAKEUP/ALARM) อยู่แล้ว โซลินอยด์ที่ไปต่อบนแผ่นเดียวกันจึงถูก FSM ขับไปด้วยตอนเดิน auto · ⚠️ **สายโซลินอยด์ต้องย้ายไปแผ่น OP1 ช่อง 0/1 ด้วย** · ลงถึงล่าง 0.68 s (วัด 2026-09-02) |
| `op0` ไม่ถูกแตะ | ปุ่มนี้ไม่เปลี่ยน `op0` เลย — `op0` เป็นของ FSM ล้วน |
| "ค้าง" | เป็น **latch** — กดครั้งเดียวค้างสถานะไว้ ไม่ต้องกดแช่ จนกว่าจะกดอีกปุ่ม หรือโดนปลดอัตโนมัติ |
| รับคำสั่งเมื่อ | `running == false` **และ** `current_state != "ALARM"` เท่านั้น |
| ปฏิเสธเมื่อเครื่องเดิน | ไม่เปลี่ยนเอาต์พุต + ตั้ง `predictive_warning` = `MANUAL JOG REJECTED: STOP MACHINE FIRST` |
| ปฏิเสธเมื่อ ALARM | ไม่เปลี่ยนเอาต์พุต + log อย่างเดียว (ห้ามทับ `predictive_warning` เพราะเป็นเหตุของ alarm อยู่) |
| ปลดอัตโนมัติ → `UP` | ทันทีที่ `running` เป็น true (กด START) หรือเข้า `ALARM` (ESTOP / NG / fault) — เช็คในลูปหลักทุกรอบ ไม่พึ่งทางเข้าแต่ละทาง · RESET ออกจาก ALARM แล้ว**ไม่กลับลงเอง** |
| สถานะย้อนกลับจอ | คีย์ `manual_seal` ใน payload 8766 (ข้อ 2) |

### 4.2 `SERVICE_MODE` — ล็อก START ระหว่างอยู่ในหน้าตั้งค่า (เพิ่ม 2026-09-23) 🔴 safety

หน้า Maintenance / Settings บนจอต้องใส่รหัสทุกครั้งที่เข้า และระหว่างอยู่ในสองหน้านี้เครื่องต้องไม่เดิน
logic อยู่ `hmi_link.py` ที่เดียว (`service_mode_command()` + `start_blocked_by_service()`)

| เรื่อง | กติกา |
|---|---|
| จอส่ง `true` เมื่อ | เปิดหน้า Maintenance หรือ Settings (ส่งทันทีก่อนขึ้นช่องใส่รหัส) |
| จอส่ง `false` เมื่อ | เปิดหน้า Main / Report / Login / logout — ส่งซ้ำได้ ไม่มีผลเสีย |
| `true` → gateway | ถ้าเครื่องเดินอยู่ ตั้ง `running = false` (เหมือน `STOP` — คง state/ยอดชิ้นไว้ กด START ต่อได้) + ตั้งล็อก |
| ระหว่างล็อก | `START` จาก **ทุกช่องทาง** (จอ 8766 + เว็บ 8765) ถูกปฏิเสธ + `predictive_warning` = `START BLOCKED: EXIT SETTINGS/MAINTENANCE` |
| ไม่กระทบ | `STOP` `ESTOP` `RESET` `MANUAL_SEAL` `SET_PARAMS` ใช้ได้ตามปกติ |
| ล็อกค้างถ้าจอหลุด? | ล็อกอยู่ในหน่วยความจำ gateway · ปลดได้ด้วย: จอกลับ MainScreen, จอรีบูต (ผ่านหน้า Login), หรือรีสตาร์ต gateway |
| สถานะย้อนกลับจอ | ไม่มีคีย์ใหม่ใน payload — จอรู้เองว่าตัวเองอยู่หน้าไหน |

### 4.3 `CYL_C` — Cylinder C ค้าง/ปล่อย จากปุ่ม INIT (เพิ่ม 2026-09-24) 🔴 safety

logic อยู่ `hmi_link.py` ที่เดียว (`cyl_c_command()` + `cyl_c_bits()`) สอง gateway เรียกตัวเดียวกัน

| เรื่อง | กติกา |
|---|---|
| บิตที่ขับ | **`op1` bit 2** (coil addr 72 แผ่น OP1 ช่อง 2) — user กำหนด 2026-09-24 · gateway OR เข้ากับบิตซีล: `op1 = manual_seal_bits \| cyl_c_bits` · ไม่ชน PUL bit 4 (ข้อ 9.6 ใช้ `op1 & 0xEF` ไม่แตะ bit 2) |
| `op0` ไม่ถูกแตะ | เหมือน `MANUAL_SEAL` |
| "ค้าง" | latch — จอส่ง `ON`/`OFF` **ตรงข้ามกับคีย์ `cyl_c` ล่าสุด** (ไม่มีคำสั่ง TOGGLE ฝั่ง gateway กันคำสั่งซ้ำ/หลุดแล้วสลับผิดข้าง) |
| รับคำสั่งเมื่อ | `ON`: ทุกเวลายกเว้น `current_state == "ALARM"` — **ค้างได้ระหว่างเครื่องเดิน** (user เลือก ต่างจาก `MANUAL_SEAL`) · `OFF`: รับเสมอ |
| ปฏิเสธเมื่อ ALARM | log อย่างเดียว ไม่ทับ `predictive_warning` |
| ปลดอัตโนมัติ → `OFF` | ทันทีที่เข้า `ALARM` (ESTOP / NG / fault) · ESTOP ตั้ง `op1 = 0` ทันทีอยู่แล้ว · RESET ออกจาก ALARM แล้ว**ไม่กลับค้างเอง** |
| ไม่ปลดเมื่อ | START / STOP / `SINGLE_CYCLE` / `SERVICE_MODE` |
| สถานะย้อนกลับจอ | คีย์ `cyl_c` ใน payload 8766 (ข้อ 2) · จอโชว์แถบเขียวใต้ปุ่ม INIT ตอน `ON` |

### 4.4 `SINGLE_CYCLE` — เดิน 1 รอบแล้วหยุด จากปุ่ม STEP (เพิ่ม 2026-09-24)

logic อยู่ `hmi_link.py` (`single_cycle_command()` / `_tick()` / `_cancel()` / `_finish()`)

| เรื่อง | กติกา |
|---|---|
| 1 รอบ | `LOAD_CARRIER` → … → `TAKEUP_REEL` = 16 สเต็ปปกติ (สเต็ปที่ 17 `ALARM` เข้าเฉพาะตอนผิดปกติ) · จบ `TAKEUP_REEL` แล้ว `cycles += 1` → ไป `LOAD_CARRIER` + `running = false` |
| จุดเริ่ม | **`LOAD_CARRIER` เสมอ** (user เลือก) — รับเมื่อหยุดอยู่ที่ `LOAD_CARRIER` หรือ `READY` (READY → ย้ายไป LOAD_CARRIER ก่อนเดิน) |
| ปฏิเสธเมื่อ | อยู่ `ALARM` (log อย่างเดียว ไม่ทับข้อความ alarm) · เครื่องเดินอยู่ (`STEP REJECTED: MACHINE RUNNING` — เพิ่ม 2026-09-24 หลังลองกับจอจริงแล้วเงียบ) · ล็อก `SERVICE_MODE` (ข้อความเดียวกับ START) · batch ครบเป้า (`⚠️ CANNOT START: BATCH DONE - PRESS RESET FIRST`) · ค้างกลางรอบ (`STEP REJECTED: PRESS RESET FIRST`) |
| ระหว่างรอบ | เหมือน START ปกติทุกอย่าง — `VISION` ยังหยุดรอ PASS/NG · โหมด `semi` ยังหยุดทุกเช็คพอยต์ · fault → ALARM ตามเดิม |
| ยกเลิกรอบเดี่ยว | เครื่องหยุดก่อนจบรอบด้วยเหตุใดก็ตาม (STOP / ESTOP / ALARM / SERVICE_MODE / batch ครบ) → แฟล็กหาย · `START` (ทั้งจอและเว็บ) ล้างแฟล็กเสมอ = เดินต่อเนื่อง |
| ลำดับเขียน | ตอนจบรอบตั้ง `current_state = LOAD_CARRIER` **ก่อน** `running = false` — กลับลำดับแล้ว WS เห็นเฟรม "หยุดที่ TAKEUP_REEL" |
| ชื่อ action | ไม่ใช้ `STEP` เพราะชนกับโหมด `step` (หยุดทุกสเต็ปรอ `NEXT`) ข้อ 8 |
| สถานะย้อนกลับจอ | ไม่มีคีย์ใหม่ — ดูจาก `running` / `current_state` |

### คำสั่ง one-shot ของจอ (TCP 8766 เท่านั้น)

`hmi_link.py:266-278` — **จับด้วยการหาสตริงย่อยใน raw ไม่ได้ parse JSON** ส่งเป็นข้อความเปล่า ๆ ก็ติด

| คำสั่ง | ผล |
|---|---|
| `REQ_REPORT_DATA` | ขอข้อมูลหน้ารายงาน |
| `EXPORT_CSV` | export CSV ลง `python_backend/exports/` |
| `CLEAR_SQL_HISTORY` | ล้างประวัติ SQL |
| `CLEAR_ALARM_LOGS` | ล้าง alarm ledger |

> ⚠️ **ไม่มีคำสั่งชื่อ `CLEAR_LOGS`** — มีแยกเป็นสองตัวข้างบน (สเปกฉบับก่อนเขียนผิด)

## 5. `machine_params` — 10 ช่องจากหน้า Settings

ยิงจาก `SettingsScreenView.cpp:180-207` เป็น `SET_PARAMS` ก้อนเดียว
9 ช่องแรกส่งเสมอ · `target_pieces` **ส่งเฉพาะตอน > 0** (ถ้าเป็น 0 gateway ปัดขึ้น 1 → batch จบตั้งแต่ชิ้นแรก)

| คีย์ | ช่องที่ (`s_paramValue[]`) | หน่วย | ใครใช้จริงแล้ว |
|---|---|---|---|
| `motor_speed` | 0 | — | ❌ เก็บเฉย ๆ (แผน: → `speed_mul`) |
| `motor_accel` | 1 | — | ❌ เก็บเฉย ๆ |
| `motor_decel` | 2 | — | ❌ เก็บเฉย ๆ |
| `camera_pos` | 3 | — | ❌ เก็บเฉย ๆ |
| `load_pos` | 4 | — | ❌ เก็บเฉย ๆ |
| `temperature` | 5 | °C | ❌ เก็บเฉย ๆ (แผน: ช่วงที่ยอมรับใน `CHECK_TEMP`) |
| `welding` | 6 | — | ❌ เก็บเฉย ๆ |
| `target_pieces` | **7** | ชิ้น | ✅ FSM ใช้จริง |
| `tape` | 8 | — | ❌ เก็บเฉย ๆ |
| `reel` | 9 | — | ❌ เก็บเฉย ๆ |

> หน่วยของ 8 ช่องที่เป็น `—` **ยังไม่มีใครระบุ** ต้องรอ `machine_spec.md` (ผิดกฎข้อ 6.4 อยู่ตอนนี้)

## 6. กฎที่ห้ามละเมิด

1. **ชื่อ state ต้องมาจาก `state_table.csv` เท่านั้น** ห้ามพิมพ์สตริงเองในโค้ดฝั่งใดฝั่งหนึ่ง
2. **เพิ่มคีย์ใหม่ = แก้ไฟล์นี้ก่อน** แล้วค่อยไปแก้โค้ด ไม่ใช่แก้โค้ดแล้วมาอัปเดตทีหลัง
3. **การเปลี่ยนชื่อคีย์คือ breaking change** ต้องแก้ backend + firmware + frontend ในรอบเดียวกัน
4. ทุกคีย์ต้องระบุ **ชนิดข้อมูลและหน่วย**
5. **เพิ่ม client ใหม่บนพอร์ตเดิม ต้องจดลง `port_map.md`** — กล้อง OpenMV ต่อ 8765 มาตั้งแต่แรกโดยไม่มีในสัญญา ไม่มีใครรู้ว่ามันยิง `DECISION` ได้จนถึง 2026-08-03
6. **ก่อนแตะโค้ดที่คุยกับบอร์ดจริง ต้องอ่าน [`board_protocol.md`](board_protocol.md) ก่อน** — firmware บนบอร์ดนั้น **ไม่มี source code** และบอร์ดตัดสายเองถ้าเงียบเกิน ~200 ms · ⛔ ห้ามแฟลชทับ ห้ามยิงคำสั่งข้อความที่ไม่รู้จัก

## 7. ส่วนต่างที่รู้แล้วแต่ยังไม่แก้ (โค้ดเป็นแบบนี้จริง)

| # | เรื่อง | รายละเอียด |
|---|---|---|
| 1 | **`SET_PARAMS` สองทางทำงานไม่เหมือนกัน** | ทาง TCP (`gateway_fsm.py:142-153`) เก็บ 9 ช่องลง `machine_params` · ทาง WebSocket (`:465-468`) อ่านแค่ `target_pieces` + `pitch` **ทิ้งที่เหลือ** — ขัดหลัก "logic ต้องมีที่เดียว" ใน `fsm_spec.md` ข้อ 2.5 |
| 2 | **จออ่าน `machine_params` กลับไม่ได้** | payload 8766 ไม่มีคีย์นี้ → กด SAVE PARAMS แล้วรีจอ ค่าหายจากมุมมองของจอ |
| 3 | **8765 ส่งถี่กว่า 8766** | เว็บได้ทุก 50 ms จอได้ทุก 20 ms — ยังไม่มีเหตุผลที่จดไว้ว่าทำไมต่างกัน |
| 4 | **คีย์ alias ซ้ำซ้อน** | `fsm_state` = `current_state` และ `actual_pcs` = `pieces_count` ส่งค่าเดิมสองชื่อทุก 20 ms |
| 5 | **one-shot จับด้วย substring** | ส่งข้อความอะไรก็ได้ที่มีคำว่า `EXPORT_CSV` ปนอยู่ก็สั่งงานได้ ไม่ได้ตรวจว่าเป็น JSON ที่ถูกต้อง |
| 6 | **ยังไม่ได้ระบุพฤติกรรม disconnect/reconnect** | ของทุกพอร์ต — ยกเว้นสาย Modbus 502 ที่ตอนนี้รู้แล้วว่า **reconnect เป็นพฤติกรรมปกติ** (บอร์ดตัดสายเองเมื่อเงียบ ~200 ms ดู [`board_protocol.md`](board_protocol.md) ข้อ 7) |
| 7 | ~~สาย 8767 (Python ↔ Rust) ยังไม่มีสัญญาเขียนไว้ในไฟล์นี้~~ | ✅ **มีสัญญาแล้ว 2026-09-24 → ข้อ 9** · ของเดิม Rust ตอบ `{"ip0":<int>}\n` คีย์เดียว — ข้อ 9 **ขยายแบบเพิ่มคีย์** (`board`, `feed`) Python ตัวเก่าที่อ่าน `.get("ip0")` ยังใช้ได้ |
| 8 | **มีข้อความ `predictive_warning` 1 ตัวที่เกินเพดานข้อ 2.3 อยู่แล้ว** | `⚠️ CANNOT START: BATCH ALREADY DONE! PLEASE PRESS RESET FIRST` (`gateway_fsm.py:498`, `gateway_fsm_upgrad.py`) = **65 ไบต์แบบ UTF-8 ดิบ / 71 ไบต์แบบ escape** ทั้งสองแบบ **เกิน 63** → พอ `backend` เพิ่มคีย์นี้เข้า payload จอแล้ว เคสนี้จะยังขึ้น `[ SYSTEM FAULT ]` อยู่ดี ส่วนอีก 10 ข้อความที่เหลือผ่านหมด (ยาวสุด 58 ไบต์แบบ escape) · **ทางแก้อยู่ฝั่ง `backend`: เขียนข้อความให้สั้นลง** เช่น `CANNOT START: BATCH DONE - PRESS RESET` — ⛔ ห้ามแก้ `Model.cpp` ให้กล่องใหญ่ขึ้นแทน เพราะ 63/64 ผูกกับ `alarmBuf` และกล่องข้อความบนจอ |
| 9 | **framing ของสาย 8767 พังได้ทั้งสองฝั่ง** (เจอตอนอ่านโค้ด 2026-09-24) | Python `gateway_fsm_upgrad.py:234-237` `recv(1024)` แล้ว `json.loads(resp.strip())` ทั้งก้อน → ถ้าคำตอบ 2 บรรทัดมาติดกัน (rust ตอบช้ากว่า select 20 ms รอบก่อน) = `Extra data` → **ตัดสาย + รอ 3 วิ** · Rust `main.rs:303-316` `read` 1024 ไบต์แล้ว `split('\n')` → บรรทัดที่ขาดกลางก้อน**ทิ้งเงียบ** · ข้อ 9.1 บังคับให้แก้ทั้งคู่ (ต้องแก้ก่อนเปิด feed — ระหว่าง feed ถ้า rust ช้า อาการนี้ทำ feed ALARM F5 ทันที) |
| 10 | **`MODE` รับสตริงอะไรก็ได้** | `data.get("mode", "auto")` → ส่ง `{"action":"MODE","value":"semi"}` (ตามสเปกเก่า) ได้โหมด `auto` เงียบ ๆ · ค่าแปลก ๆ ถูกตั้งตรง ๆ · ข้อ 8.3 บังคับตรวจค่า — **gateway เก่าที่ได้ `"step"` จะตั้ง mode เป็น `"step"` แล้ววิ่งต่อเนื่องไม่หยุดเลย** (เว็บเข้าใจว่าเป็นโหมดทีละสเต็ป) → frontend ต้อง feature-detect ข้อ 8.5 |

> แก้ข้อไหนต้องแก้ทั้งสองฝั่งพร้อมกัน และอัปเดตไฟล์นี้ในรอบเดียวกัน


---

## 8. โหมด `step` + `NEXT` — เว็บ ↔ gateway (WebSocket 8765) (เพิ่ม 2026-09-24)

> พฤติกรรม FSM เบื้องหลัง (เมื่อไรค้าง / guard / ALARM) อยู่ที่ `fsm_spec.md` ข้อ 7 — ข้อนี้กำหนดแค่ **รูปแบบบนสาย**
> **ต้องทำในทั้งสอง gateway** (`gateway_fsm.py` + `gateway_fsm_upgrad.py`) ไม่งั้นหน้าเว็บจะเจอพฤติกรรมต่างกันตามว่าเปิดตัวไหน

### 8.1 `NEXT` — คำขอ + คำตอบ (ชุดเดียวกับ `DECISION` / `DECISION_ACK`)

**เว็บ → gateway**
```json
{"action": "NEXT", "expect_state": "LOAD_CARRIER"}
```

| คีย์ | ชนิด | บังคับ | ความหมาย |
|---|---|---|---|
| `action` | string | ✅ | `"NEXT"` |
| `expect_state` | string (ชื่อ state ตาม `state_table.csv`) | ไม่บังคับ แต่ **`frontend` ต้องส่งเสมอ** | state ที่ operator เห็นบนจอตอนกด · ไม่ตรงกับ `current_state` → ปฏิเสธ `state_mismatch` (กันกดซ้ำ/กดจากภาพที่ค้าง) |

**gateway → เว็บ** (ส่งกลับ**เฉพาะ client ที่ยิงมา** ไม่ broadcast · ส่งทุกครั้ง ทั้งรับและปฏิเสธ)
```json
{"type": "NEXT_ACK", "accepted": true,  "state": "LOAD_CARRIER"}
{"type": "NEXT_ACK", "accepted": false, "state": "FEED_CARRIER", "reason": "not_waiting"}
```

| คีย์ | ชนิด | ความหมาย |
|---|---|---|
| `type` | string | `"NEXT_ACK"` |
| `accepted` | bool | ผ่าน guard ไหม |
| `state` | string | `current_state` **ตอนตัดสิน** (accepted = สเต็ปที่ถูกปล่อย · transition จริงเกิดในรอบลูปถัดไป ≤ 20 ms ให้ดูจาก `LIVE_SYNC`) |
| `reason` | string | มีเฉพาะ `accepted: false` — ค่าตามข้อ 8.2 |

- ทาง TCP 8766: รับ `{"action":"NEXT"}` ด้วย logic เดียวกัน (**ไม่มี ACK** เหมือน `DECISION` ทาง TCP) —
  firmware รอบนี้ **ยังไม่ส่ง** สัญญาเขียนไว้ล่วงหน้าเพื่อให้เพิ่มปุ่มบนจอทีหลังได้โดยไม่ต้องแก้ gateway
- กล้อง (`app_vision.py`) **ห้ามส่ง `NEXT`** — `NEXT` เป็นคำสั่งของคนเท่านั้น

### 8.2 `reason` ของ `NEXT_ACK` (สตริงคงที่ — เรียงตามลำดับที่ gateway เช็ค)

| ลำดับ | `reason` | เกิดเมื่อ | เว็บควรบอก operator |
|---|---|---|---|
| 1 | `alarm` | `current_state == "ALARM"` — **NEXT ปลด ALARM ไม่ได้** | "อยู่ใน ALARM — กด RESET" |
| 2 | `not_step_mode` | `mode != "step"` | "ไม่ได้อยู่โหมด Step" |
| 3 | `not_running` | `running == false` (STOP / batch จบ / มีคนอยู่หน้า Maintenance-Settings) | "กด START ก่อน" |
| 4 | `use_decision` | อยู่ `VISION` | "สเต็ปนี้ใช้ PASS / NG" |
| 5 | `state_mismatch` | `expect_state` ไม่ตรง `current_state` | "สเต็ปเปลี่ยนไปแล้ว ลองใหม่" |
| 6 | `not_waiting` | `step_wait == false` (งานยังไม่เสร็จ เช่น feed กำลังหมุน หรือกดซ้ำ) | "รอให้สเต็ปทำงานเสร็จ" |

### 8.3 `MODE` — ค่าใหม่ `"step"` + ตรวจค่า + `MODE_ACK`

**เว็บ → gateway:** `{"action": "MODE", "mode": "step"}` (คีย์ **`mode`** — ไม่ใช่ `value`)

**gateway → เว็บ** (ใหม่ · เฉพาะ client ที่ยิงมา · ทุกครั้ง)
```json
{"type": "MODE_ACK", "accepted": true,  "mode": "step"}
{"type": "MODE_ACK", "accepted": false, "mode": "auto", "reason": "step_switch_while_running"}
```
`mode` = ค่า **หลัง** ตัดสิน (ปฏิเสธ = ค่าเดิม)

| `reason` | เกิดเมื่อ |
|---|---|
| `invalid_mode` | ค่าไม่อยู่ใน `"auto"`/`"semi"`/`"step"` หรือไม่มีคีย์ `mode` (เดิมโค้ดตั้งเป็น `"auto"` เงียบ ๆ) |
| `step_switch_while_running` | สลับเข้าหรือออก `"step"` ขณะ `running == true` — ต้อง STOP ก่อน · (`auto` ↔ `semi` ขณะเดินยังรับตามเดิม) |

ทาง TCP 8766: กติกาเดียวกัน ไม่มี ACK มี log · firmware ปัจจุบัน**ไม่ส่ง** `MODE` อยู่แล้ว (ตรวจ `NOXCORE` 2026-09-24)

### 8.4 คีย์ใหม่ใน `LIVE_SYNC.system` (WS 8765 เท่านั้น — **ห้ามเข้า payload จอ 8766**)

| คีย์ | ชนิด | ค่า | ความหมาย |
|---|---|---|---|
| `step_wait` | bool | | งานของสเต็ปปัจจุบันเสร็จแล้ว รอ `NEXT` · เป็น `true` ได้เฉพาะ `mode=="step"` ∧ `running` ∧ state ∉ {ALARM, VISION} |
| `feed_src` | string | `""` \| `"SIM"` \| `"REAL"` | แหล่งของ feed ครั้งล่าสุด (ตัดสินตอนเข้า `FEED_CARRIER` — `fsm_spec.md` 8.10) · **`"SIM"` เฉพาะตอน `RUST_BRIDGE` ปิด** (และ `gateway_fsm.py` เสมอ) · `RUST_BRIDGE=1` = `"REAL"` เสมอ ถ้าส่งจริงไม่ได้จะเป็น ALARM + `feed_state="error"` ไม่ตกไป SIM · `""` = ยังไม่เคย feed ตั้งแต่เปิด gateway |
| `feed_state` | string | `"idle"` \| `"running"` \| `"done"` \| `"aborted"` \| `"error"` | สถานะ feed ครั้งล่าสุดในมุมของ gateway (SIM ก็ใช้ `running` → `done`) |
| `feed_sent` | int พัลส์ | ≥ 0 | พัลส์ที่ส่งครบ (ขอบขึ้น+ลง ack แล้ว) ของ feed ครั้งล่าสุด · SIM: 0 ระหว่างจับเวลา → เท่ากับ `feed_total` ตอนเสร็จ |
| `feed_total` | int พัลส์ | ≥ 0 | N ที่สั่งใน feed ครั้งล่าสุด (115/114 หรือส่วนที่เหลือหลัง abort) |
| `feed_index` | int pitch | ≥ 0 | k — จำนวน pitch ที่ผ่าน `FEED_CARRIER` ไปแล้วในแผนปัจจุบัน (รีเซ็ตเฉพาะ RESET เริ่ม batch ใหม่) |
| `feed_half_ms` | number ms | 0–50 | (เพิ่มตาม user 2026-09-24) ครึ่งคาบพัลส์ที่ gateway ใช้ = ค่า env `FEED_HALF_MS` (ค่าตั้งต้น 5 ≈ 90.9 พัลส์/วิ) · แสดงผลอย่างเดียว **รอบนี้เว็บยังไม่มีปุ่มตั้ง** |
| `feed_pulses` | int พัลส์ | ≥ 0 | P — พัลส์สะสมในแผนปัจจุบัน (ของจริงที่ ack แล้ว + ของ SIM ที่ถือว่าส่ง) |

> 🔴 **คำที่ UI ต้องใช้:** `feed_state == "done"` แปลว่า **"ส่งพัลส์ครบ"** ไม่ใช่ "เทปเดินครบ" —
> ไดรเวอร์ ALM ไม่ได้ต่อ + open loop (`fsm_spec.md` 8.1) · `feed_src == "SIM"` ต้องแสดงให้เห็นชัดว่าไม่ได้หมุนจริง

### 8.5 กติกาฝั่งเว็บ (`cad/index1.html`)

| เรื่อง | กติกา |
|---|---|
| **feature detection** | แสดงปุ่ม Step / NEXT **เฉพาะเมื่อ `"step_wait" in sys`** — gateway รุ่นเก่าไม่มีคีย์นี้ และถ้าได้ `MODE "step"` จะ**ตั้ง mode เป็น "step" แล้ววิ่งต่อเนื่องไม่หยุด** (ข้อ 7 รายการ 10) = operator เข้าใจผิดว่าเดินทีละสเต็ป |
| ปุ่มโหมด | 3 ปุ่ม auto / semi / step ไฮไลต์ตาม `sys.mode` (ตอนนี้โค้ดคิดแค่ `mode === 'semi'`) · ปุ่ม step กดได้เมื่อ `!sys.running` · รับ `MODE_ACK` ที่ปฏิเสธแล้วแสดง reason ห้ามเงียบ |
| ปุ่ม NEXT | enable เมื่อ `sys.mode==="step" && sys.running && sys.step_wait && sys.current_state!=="ALARM" && sys.current_state!=="VISION"` · ส่ง `expect_state = sys.current_state` · กดแล้ว disable จนกว่าจะได้ `NEXT_ACK` หรือ `LIVE_SYNC` รอบใหม่ · แสดง `reason` ของ `NEXT_ACK` ที่ปฏิเสธ |
| ปุ่ม OK / NG | enable เมื่อ `sys.step_allowed` (**ทุกโหมด**) — ตอนนี้โค้ดบังคับ `isSemiAutoMode` ด้วย (`index1.html:583-584`) ทำให้โหมด step (และ auto) กด PASS ที่ VISION จากเว็บไม่ได้ = ตัน · guard จริงอยู่ที่ gateway (ข้อ 6.3 ใน `fsm_spec.md`) การเปิดปุ่มกว้างขึ้นไม่ลดความปลอดภัย |
| สถานะ | `step_wait` → ข้อความ "รอ NEXT" · `feed_src` เป็นป้าย SIM/REAL (`""` → "—") · `feed_sent/feed_total` เป็นแถบคืบหน้า · `feed_half_ms` แสดงความเร็วที่ใช้ (อ่านอย่างเดียว — ยังไม่มีปุ่มตั้ง) · `feed_state` `error`/`aborted` แสดงคู่กับ `predictive_warning` |
| ห้าม | ห้ามอนุมานว่ารอ operator จาก `isCheck && isSemiAutoMode` ในโหมด step · ห้ามตั้ง `op1` หรือส่งคำสั่งพัลส์ใด ๆ จากเว็บ |

### 8.6 จอ HMI (8766) — ไม่เปลี่ยน

- payload **12 คีย์เดิม** (`testkit.HMI_PAYLOAD_KEYS` ตรวจเท่ากันพอดี) — `step_wait` / `feed_*` / `mode` **ไม่เข้า**
  (`build_state_payload()` สร้าง dict เองไม่ได้ dump `system_data` ทั้งก้อน จึงเพิ่มคีย์ใน `system_data` ได้โดยไม่กระทบจอ)
- จอในโหมด step: เห็น `running=true` กับ state ค้าง · popup PASS/NG ที่ VISION ใช้ได้ · START/STOP/RESET ใช้ได้ ·
  ส่ง NEXT / MODE ไม่ได้ → ต้องมีหน้าเว็บเปิดอยู่ · ปลอดภัยเพราะระหว่างรอไม่มีอะไรขยับ (`fsm_spec.md` 7.8)

---

## 9. สาย 8767 — gateway ↔ `rust_bridge` (สัญญาเต็ม + คำสั่ง feed) (เพิ่ม 2026-09-24)

> ของเดิมไม่มีสัญญาเขียนไว้ (ข้อ 7 รายการ 7) · ข้อนี้บันทึกของเดิมที่ยังใช้ + ขยายแบบ**เพิ่มคีย์อย่างเดียว**
> ปลายทางอีกฝั่งของ Rust (Modbus 502) ดู `board_protocol.md` · FSM ที่ใช้ feed ดู `fsm_spec.md` ข้อ 8

### 9.1 บทบาท + framing

| | |
|---|---|
| server | `rust_bridge` bind `127.0.0.1:8767` (env `BRIDGE_ADDR`) |
| client | `gateway_fsm_upgrad.py` เมื่อ `RUST_BRIDGE=1` · ต่อใหม่ทุก 3 วิเมื่อหลุด (เดิม) |
| รูปแบบ | JSON UTF-8 **หนึ่งอ็อบเจกต์ต่อบรรทัด** ปิดด้วย `\n` ทั้งสองทิศ |
| จังหวะ | Python ส่ง 1 บรรทัดต่อรอบลูป FSM (~20 ms) · Rust ตอบ **1 บรรทัดต่อ 1 บรรทัดที่รับ ตามลำดับ** |
| 🔴 ผู้รับต้อง buffer | TCP เป็น stream — ผู้รับ**ต้องสะสมไบต์แล้วตัดทีละ `\n`** เก็บเศษท้ายไว้รอบหน้า · Python ใช้**บรรทัดสมบูรณ์บรรทัดสุดท้าย**ที่ได้ในรอบนั้น (ทิ้งบรรทัดเก่ากว่าได้ เพราะแต่ละบรรทัดเป็นสถานะเต็ม) · Rust ต้อง**ประมวลทุกบรรทัดตามลำดับ** (ห้ามทิ้งบรรทัดที่มี `abort`) · ❌ โค้ดปัจจุบันผิดทั้งสองฝั่ง — ข้อ 7 รายการ 9 |
| ขนาดบรรทัด | ≤ 1 KB (ปกติ ~200 ไบต์) |

### 9.2 Python → Rust

```json
{"current_state":"FEED_CARRIER","running":true,"op0":1,"op1":0,"ip0":0,"cycles":3,
 "feed_cmd":{"id":12,"pulses":115,"half_ms":5,"abort":false}}
```

| คีย์ | ชนิด | ใหม่? | ความหมาย |
|---|---|---|---|
| `current_state` | string | เดิม | ใช้ใน log ฝั่ง Rust |
| `running` | bool | เดิม | |
| `op0` | int 0–255 | เดิม | เขียน coil addr 64 ทั้งไบต์ |
| `op1` | int 0–255 | เดิม (2026-09-23) | บิตของ Python สำหรับ coil addr 72 · 🔴 **bit 4 ต้องเป็น 0 เสมอ** (PUL เป็นของ Rust — ข้อ 9.6) |
| `ip0` | int | เดิม | ค่าเดิมที่ Python ถือ — Rust ใช้สะท้อนกลับตอนไม่มีบอร์ด |
| `cycles` | int | เดิม | ใช้ใน log |
| **`feed_cmd`** | object \| null \| ไม่มีคีย์ | **ใหม่** | คำสั่ง feed · **ไม่มี/`null` = ไม่มีคำสั่งในบรรทัดนี้ — ไม่ใช่ abort** (feed ที่กำลังทำเดินต่อ) |
| `feed_cmd.id` | int ≥ 1 | ใหม่ | Python นับขึ้นทีละ 1 ต่อ feed หนึ่งครั้ง ภายในโปรเซส gateway |
| `feed_cmd.pulses` | int 1–1000 | ใหม่ | N — จำนวนพัลส์ที่ต้องส่ง (นอกช่วง → Rust ตอบ `error` `bad_pulses`) |
| `feed_cmd.half_ms` | number (ms) ช่วง **0–50** · ไม่มีคีย์ = 0 | ใหม่ (user 2026-09-24) | ครึ่งคาบพัลส์ — ความหมายข้อ 9.5 ข้อ 4 · 0 = เร็วสุดตาม ack · gateway ส่งค่า env `FEED_HALF_MS` (ค่าตั้งต้น **5**) **ทุกครั้ง** · Rust **ปฏิเสธ** ค่านอกช่วง/ไม่ใช่ตัวเลข → `error` `bad_half_ms` ไม่เริ่ม feed (ไม่ clamp — ค่าผิดต้องเห็น ไม่ใช่ถูกแก้เงียบ) · ค่านี้ผูกกับ id ตอนเริ่ม เปลี่ยนกลาง feed ไม่มีผล |
| `feed_cmd.abort` | bool (default `false`) | ใหม่ | `true` = ยกเลิก feed id นี้ |

### 9.3 idempotent — คำสั่งเดิมซ้ำทุก 20 ms ต้องไม่ทำให้ feed ซ้ำ

**Rust** (สถานะต่อ 1 สาย Python):
1. จำ `last_id` = id ล่าสุดที่รับไว้ (เริ่มสายใหม่ = ไม่มี)
2. บรรทัดที่มี `feed_cmd`:
   - `id == last_id` และ `abort == false` → **ไม่ทำอะไร** (คำสั่งซ้ำ)
   - `id == last_id` และ `abort == true` → ถ้ายัง `running` ให้หยุดตามข้อ 9.5 · ถ้าจบแล้ว ไม่ทำอะไร (รายงานสถานะจบเดิม)
   - `id != last_id` และ feed ปัจจุบัน**จบแล้วหรือไม่มี** → `last_id = id` แล้ว: `abort == true` → จบทันทีเป็น `aborted` `sent 0` ·
     ไม่งั้นเริ่ม feed ใหม่ (ตรวจ `pulses` / `board` / read-only ก่อน)
   - `id != last_id` แต่ feed เดิมยัง `running` → **ไม่รับ** log เตือน (Python ต้องไม่ทำแบบนี้ — ต้องรอ id เดิมจบก่อน)
3. สาย Python หลุดระหว่าง feed → **abort ทันที** (ไม่มีใครคุมแล้ว) · สายใหม่เริ่ม `last_id` ใหม่

**Python**:
1. ออก id ใหม่เฉพาะเมื่อ id ก่อนหน้าได้สถานะจบ (`done`/`aborted`/`error`) แล้ว หรือถูก retire
2. ส่ง `feed_cmd` ของ id ปัจจุบัน**ทุกบรรทัด**จนได้สถานะจบของ id นั้น (บรรทัดหายหนึ่งบรรทัดไม่เป็นไร บรรทัดถัดไปแทน) แล้วเลิกส่ง
3. 🔴 **สาย 8767 หลุดแล้วต่อใหม่ → ห้ามส่ง id ที่ค้างอยู่ซ้ำเด็ดขาด** (Rust สายใหม่จำ id ไม่ได้ จะหมุนซ้ำ) —
   ถือเป็น F5 (`fsm_spec.md` 8.6) · feed ครั้งถัดไปต้องเป็น id ใหม่ที่คำนวณ N จาก P ล่าสุด

### 9.4 Rust → Python

```json
{"ip0":0,"board":true,"feed":{"id":12,"state":"running","sent":57,"total":115,"err":""}}
```

| คีย์ | ชนิด | ใหม่? | ความหมาย |
|---|---|---|---|
| `ip0` | int 0–255 | เดิม | อินพุตจริงจากบอร์ด (หรือค่าที่ Python ส่งมา สะท้อนกลับ ถ้า `board == false`) · ระหว่าง feed อายุไม่เกิน 50 ms (ข้อ 9.7) |
| **`board`** | bool | ใหม่ | สาย Modbus 502 ใช้งานได้ ณ ตอนตอบ (= ป้าย `[REAL]` ใน log ของ Rust) · Python ใช้ตัดสิน SIM/REAL (`fsm_spec.md` 8.10) |
| **`feed`** | object | ใหม่ | **มีทุกบรรทัด** ใน Rust รุ่นที่รองรับ feed — ไม่มีคีย์นี้ = Rust รุ่นเก่า (Python ต้องเข้า ALARM F7b `FEED BRIDGE HAS NO FEED SUPPORT` เมื่อถึง FEED_CARRIER — ห้ามจำลอง) |
| `feed.id` | int | ใหม่ | id ของ feed ล่าสุดในสายนี้ · `0` = ยังไม่มี |
| `feed.state` | string | ใหม่ | `idle` (ยังไม่มี) \| `running` \| `done` \| `aborted` \| `error` · **สถานะจบ (`done`/`aborted`/`error`) ต้องรายงานซ้ำทุกบรรทัดจนกว่าจะเริ่ม id ใหม่** |
| `feed.sent` | int | ใหม่ | พัลส์ที่**ขอบขึ้นและขอบลง ack ครบทั้งคู่** · `done` ⇔ `sent == total` |
| `feed.total` | int | ใหม่ | `pulses` ที่รับไว้ |
| `feed.err` | string | ใหม่ | `""` ยกเว้น `state == "error"` — รหัสสั้นตามตารางล่าง |

| `feed.err` | เมื่อ |
|---|---|
| `board_down` | ได้คำสั่งตอนไม่มีสายบอร์ด / สายบอร์ดหลุดกลาง feed |
| `read_only` | รันด้วย `RUST_READ_ONLY=1` (ห้ามเขียน coil) |
| `bad_pulses` | `pulses` < 1 หรือ > 1000 |
| `bad_half_ms` | `half_ms` < 0, > 50 หรือไม่ใช่ตัวเลข |
| `ack_timeout` | ack ไม่มาใน `BOARD_IO_TIMEOUT` (500 ms เดิม) |
| `ack_bad_fc` | ack ไบต์ index 7 ≠ `0x0F` (parser ข้อความแทรก — `board_protocol.md` 11 ข้อ 10) |
| `io_error` | error อื่นของ socket |

error ใด ๆ ที่เกี่ยวกับสายบอร์ด → Rust **ทิ้งสายบอร์ด** ให้ supervisor ต่อใหม่ (ห้าม resync ในสายเดิม) ·
Python แปลงเป็นข้อความ ALARM `⚠️ ERROR: FEED BRIDGE <err>` (≤ 59 ไบต์ ตรวจแล้ว)

### 9.5 การส่งพัลส์ของ Rust (ข้อบังคับ)

1. 1 พัลส์ = เขียน addr 72 ค่า `base | 0x10` → รอ ack → เขียน `base` → รอ ack · `base = op1 ล่าสุดจาก Python & !0x10`
2. ทุกเฟรม: TID `00 00` · อ่าน ack **ครบ 12 ไบต์** (`read_exact` ไม่ใช่ `read` ครั้งเดียว) · ตรวจ `ack[7] == 0x0F`
   (`board_protocol.md` 11 ข้อ 9–10 — `write_bank()` ตอนนี้ยังไม่ตรวจ ต้องแก้ก่อนใช้ส่งพัลส์)
3. `sent += 1` หลัง ack ของ**ขอบลง**เท่านั้น
4. **ความเร็ว (`half_ms`)** — ส่งขอบถัดไปไม่เร็วกว่า `t_เริ่มส่งขอบก่อนหน้า + half_ms` (รอนับจาก**ตอนเริ่มส่งเฟรม** เหมือน
   `tools/feed_pulse_test.py` `_sleep_until(t_edge + half_s)` ⇒ เวลาไป-กลับของเฟรมซ้อนอยู่ในช่วงรอ) · `half_ms = 0` = ไม่รอ
   · วัดจริง: 0 → ~285 พัลส์/วิ · 2 → 205.6 · 5 → 90.9 · **ระหว่างรอต้องยังเช็ค abort และแทรก op0/ip0 ได้** (ช่วงรอไม่ใช่ส่วนของเฟรม+ack)
5. **abort:** เช็คธง abort **ก่อนส่งขอบขึ้นทุกครั้ง** → ไม่ส่งขอบขึ้นใหม่ · ถ้าขอบขึ้นออกไปแล้วต้องส่งขอบลงให้จบก่อน
   ⇒ หยุดภายใน ≤ 1 พัลส์ และ **PUL ค้างต่ำ** · รายงาน `aborted` (หรือ `done` ถ้าครบพอดี)
6. สายบอร์ดพังกลาง feed → `error` · PUL อาจค้างสูงจนกว่าสายใหม่จะเขียน `op1` ที่ bit 4 = 0 (ไดรเวอร์นับที่ขอบ
   ระดับค้างไม่ทำให้หมุน) · พัลส์ที่ขอบขึ้นออกไปแต่ไม่ได้ ack ขอบลง **ไม่นับ** (คลาดได้ ±1)
7. ⛔ ห้ามรัน `tools/feed_*` คู่กัน (ทั้งคู่เขียน addr 72 ทั้งไบต์ — `board_protocol.md` 11 ข้อ 11)

### 9.6 `op1` ที่ลงบอร์ด = บิตของ Python OR PUL ของ Rust — คำนวณที่ Rust ที่เดียว

```
ไบต์ที่เขียน addr 72 = (op1_จาก_Python & 0xEF) | (PUL_สูง ? 0x10 : 0x00)
```
- Python **ห้ามตั้ง bit 4** · Rust **mask ทิ้งอีกชั้น** (defense in depth) — ถ้าเจอ bit 4 จาก Python ให้ log เตือน
- ตอนไม่มี feed: เขียน `op1 & 0xEF` เหมือนเดิมทุกรอบ → PUL ต่ำเสมอ
- รอบนี้ bit 0/1 (โซลินอยด์) = 0 ตอนเครื่องเดินเสมอ (`manual_seal_bits()` ปลดเองเมื่อ running) → ระหว่าง feed
  ไบต์จะสลับ `0x10` / `0x00` · ถ้าวันหน้าโซลินอยด์ต้องทำงานพร้อม feed สูตรนี้รองรับแล้ว ไม่ต้องแก้สัญญา

### 9.7 เวลา (ข้อบังคับของ Rust)

| เรื่อง | ต้องได้ | เหตุผล |
|---|---|---|
| ตอบ 1 บรรทัดของ Python | **ไม่รอ feed จบ** · เป้า ≤ 20 ms | ถ้าตอบหลัง feed จบ (0.4 s) คำตอบจะกองแล้ว Python หลุดตาม ข้อ 7 รายการ 9 และ ESTOP จาก Python จะไปไม่ถึง |
| abort มีผล | ≤ 1 พัลส์ (≤ `2×half_ms + 7` ms · ค่าตั้งต้น ≈ 11–17 ms) หลังอ่านบรรทัดที่มี `abort: true` | `fsm_spec.md` 8.7 · Python ให้เวลายืนยัน 1000 ms (F6) |
| `op0` + `op1(base)` ลงบอร์ดระหว่าง feed | ค่าใหม่จาก Python ถึงบอร์ด ≤ **50 ms** (แทรกเขียน `op0` **ตามเวลา** ทุก ≤ 30 ms ไม่ใช่นับพัลส์ — เพราะคาบพัลส์เปลี่ยนตาม `half_ms`) · `op1(base)` ไปกับทุกเฟรมพัลส์อยู่แล้ว | ไฟ ALARM (`op0=0x08`) ตอน ESTOP ต้องไม่ค้างรอ feed 0.4 s |
| อ่าน `ip0` ระหว่าง feed | ทุก ≤ 50 ms (แทรกพร้อม `op0`) | ค่าเซนเซอร์ไม่ค้าง |
| เฟรม+ack | atomic — ห้าม heartbeat/เฟรมอื่นแทรกระหว่างเฟรมกับ ack ของมัน | สายเดียวไม่มี TID แยก (TID `00 00` คงที่) |
| idle ของบอร์ด | ทราฟฟิกห่างไม่เกิน ~150 ms (เดิม) | ระหว่าง feed พัลส์เลี้ยงสายอยู่แล้ว |

แนะนำ (ไม่บังคับ): ให้ task เดียวเป็นเจ้าของสายบอร์ด วนเขียน/อ่านตาม "สถานะที่ต้องการล่าสุด" ที่ handler ของ Python
อัปเดต แล้ว handler ตอบกลับทันทีจากค่าที่ cache ไว้ — handler **ห้าม await** การส่งพัลส์

### 9.8 ความเข้ากันได้ข้ามรุ่น

| Python | Rust | ผล |
|---|---|---|
| ใหม่ | ใหม่ | ✅ ครบ |
| ใหม่ | **เก่า** (`.exe` ที่ยังไม่ `cargo build`) | Rust ไม่รู้จัก `feed_cmd` (serde ข้ามคีย์เกิน — `PythonSystemData` ไม่ได้ `deny_unknown_fields`) · คำตอบไม่มี `feed` → ถึง FEED_CARRIER แล้ว **ALARM F7b** (`fsm_spec.md` 8.10 — user ตัดสินห้ามจำลองเมื่อ `RUST_BRIDGE=1`) · ส่วนอื่นของระบบ (op0/op1/ip0) ยังทำงาน |
| **เก่า** | ใหม่ | Python เก่าไม่ส่ง `feed_cmd` → Rust ไม่ส่งพัลส์ · คำตอบมีคีย์เกิน Python เก่า `.get("ip0")` ใช้ได้ (แต่ปัญหา framing เดิมยังอยู่) |

> ⚠️ `rust_bridge` แก้แล้ว **ต้อง `cargo build --release` ใหม่** ไม่งั้น `.exe` เก่ายังรันอยู่ (บทเรียนพอร์ต 8766 — `port_map.md` "ค้างอยู่")
