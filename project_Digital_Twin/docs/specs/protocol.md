# Protocol — สัญญาการรับส่งข้อมูลระหว่างเลเยอร์

> `backend` / `stm32` / `frontend` อ่านอย่างเดียว
> แก้ไฟล์นี้แล้ว **ต้องแก้ทั้ง 3 ฝั่งพร้อมกัน** เพราะ compile ไม่ฟ้อง ระบบจะพังเงียบ ๆ
> สถานะ: ✅ **ไล่เทียบกับโค้ดจริงแล้ว 2026-08-03** ทุกแถวมีเลขบรรทัดอ้างอิง
> เอกสารนี้บันทึก **สิ่งที่โค้ดทำจริง** ไม่ใช่สิ่งที่อยากให้ทำ — ส่วนที่ควรแก้อยู่ข้อ 7

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

`hmi_link.build_state_payload()` — `hmi_link.py:199-213` · ส่งทุก **20 ms** · JSON แบน ปิดท้ายด้วย `\n`

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

**มีแค่ 10 คีย์นี้เท่านั้น** — ไม่มี `machine_params` (จออ่านค่าที่ตัวเองเซฟกลับมาไม่ได้ ดูข้อ 7)

## 3. Status payload → เว็บ + กล้อง (WebSocket 8765)

`broadcast_state()` — `gateway_fsm.py:507-514` · ส่งทุก **50 ms** · **มี wrapper ครอบ**

```json
{"type": "LIVE_SYNC", "system": { ...system_data ทั้งก้อน... }}
```

`system_data` — `gateway_fsm.py:37-53` (ฝั่งเว็บต้องแกะ `.system` ก่อนถึงจะเจอคีย์)

| คีย์ | ชนิด | หมายเหตุ |
|---|---|---|
| `current_state` | string | ตรงกับของ 8766 |
| `running`, `step_allowed`, `cycles`, `pieces_count`, `target_pieces`, `pitch`, `current_temp` | | ตรงกับของ 8766 |
| `mode` | string | `"auto"` เริ่มต้น — **ไม่มีใน payload ของจอ** |
| `speed_mul` | float | ตัวคูณความเร็ว (1.0 = ปกติ) — **ไม่มีใน payload ของจอ** |
| `ip0`, `ip1`, `op0`, `op1` | int | สถานะ I/O ดิบ 8 บิต — **ไม่มีใน payload ของจอ** · ⚠️ มีแค่ **`op0` (เขียนลง coil) กับ `ip0` (อ่านจากขาอินพุตจริง)** ที่วิ่งลงถึงบอร์ดผ่าน Rust · `ip1`/`op1` ไม่เคยออกจาก Python — ดู [`board_protocol.md`](board_protocol.md) ข้อ 9 |
| `camera1_count`, `encoder_count` | int | ตัวนับ — **ไม่มีใน payload ของจอ** |
| `predictive_warning` | string | ข้อความเตือนล่วงหน้า — **ไม่มีใน payload ของจอ** |
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
| `MODE` | ✅ | ✅ | — | `value` | เปลี่ยนโหมดทำงาน |
| `SPEED` | ✅ | ✅ | — | `value` | ปรับความเร็ว |
| `DECISION` | ✅ | ✅ | ✅ | `value`: bool (+`meta` ไม่บังคับ) | PASS=`true` / NG=`false` — **FSM ไม่ได้รอ = ปฏิเสธ ห้ามกระโดดสเต็ป** |
| `SET_PARAMS` | ✅ | ⚠️ | — | 10 ช่อง (ดูข้อ 5) | ⚠️ สองทางทำงานไม่เหมือนกัน — ดูข้อ 7 |
| `GET_STATE` | ❌ | ✅ | ✅ | — | ตอบ `LIVE_SYNC` กลับทันที 1 ครั้ง |
| `GET_HISTORY` | ❌ | ✅ | — | — | ตอบ `HISTORY_RESPONSE` (100 แถวล่าสุด) |

อ้างอิง: จอ `gateway_fsm.py:102-153` · เว็บ `gateway_fsm.py:417-499` · หน้าเว็บยิงจริง `index1.html:413-530` · กล้อง `app_vision.py:116,192`

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
| 7 | **สาย 8767 (Python ↔ Rust) ยังไม่มีสัญญาเขียนไว้ในไฟล์นี้** | ของจริงคือ Python ส่ง `system_data` เข้าไป แล้ว Rust ตอบกลับ `{"ip0":<int>}\n` คีย์เดียว (`rust_bridge/src/main.rs:301`) — **รูปทรงนี้ห้ามเปลี่ยน** ปลายทางอีกฝั่งของ Rust ดู [`board_protocol.md`](board_protocol.md) |

> แก้ข้อไหนต้องแก้ทั้งสองฝั่งพร้อมกัน และอัปเดตไฟล์นี้ในรอบเดียวกัน
