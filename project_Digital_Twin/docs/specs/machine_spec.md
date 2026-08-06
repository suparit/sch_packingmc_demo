# Machine Specification — เครื่อง taping SMD reel

> เป็น single source of truth ของทั้งโปรเจกต์
> `fsm` / `bom-cost` / `excel` / `frontend` อ่านไฟล์นี้ แก้แล้วต้องแจ้งเซสชัน + เขียนลง STATUS.md
> สถานะ: 🔶 **เติมบางส่วนแล้ว (2026-08-05, แก้รอบสาม)** — ชิ้นงาน (อุปกรณ์อิเล็กทรอนิก Noise Filter), pocket pitch 18mm,
> ความเร็วเป้าหมาย <30 ชิ้น/นาที, takeup torque control ยืนยันจาก user แล้ว
> **รอบสาม (2026-08-05):** user ยืนยันความถูกต้องของเอกสารออกแบบ motion ทั้งฉบับ
> (`motion-design-feed-takeup.md`) → **ปิด Open Question เรื่องที่มาของ 18mm** + เติม hardware ฝั่ง feed/takeup
> + เขียน [ADR-008](../adr/ADR_008_takeup_servo_torque_control.md) + เขียนหัวข้อ 6 Safety ใหม่ทั้งหัวข้อ (STO)
> ⚠️ **รอบแรกของวันนี้เคยลง tape pitch = 4mm และ tape width = 8mm ไว้ผิด — ถอนออกแล้ว** ถ้ามีใครคัดลอกไปใช้
> ระหว่างวัน ให้กลับมาเช็คค่าปัจจุบันในไฟล์นี้ (บันทึกการถอนอยู่ใน `docs/worklog/2026-08-05-machine-design.md`)
> ⚠️ **รอบสามถอน `sprocket hole pitch = 4mm` ออกด้วย** — ค่านั้นอ้างมาตรฐาน EIA-481 แต่ตอนนี้ยืนยันแล้วว่า
> เทปตัวนี้เป็นเทปเฉพาะทาง ไม่ผูกกับ EIA-481 จึงอ้าง 4mm ต่อไม่ได้ (ดูข้อ 2.2 + Open Questions ข้อ 1)
> ที่เหลือ (tape width, sprocket hole pitch จริง, sealing parameters) ยังเป็น Open Question — ดูข้อ 7

---

## 1. ภาพรวมเครื่อง

เครื่องบรรจุชิ้นงาน SMD ลง carrier tape ปิดด้วย cover tape แล้วม้วนเก็บเป็นรีล

**วัตถุดิบเข้า:** carrier tape (ม้วน), cover tape (ม้วน), ชิ้นงาน SMD
**ผลลัพธ์ออก:** รีลที่บรรจุและซีลเรียบร้อยตามจำนวนที่ตั้งไว้

### หลักการสำคัญ (ห้ามขัด — เป็นข้อสรุปจาก ADR-001)

```
[Stepper Motor] → [Incremental Encoder] → [RS PRO Counter] → [Control Logic] → [Pin Mechanism]
```

> **ความแม่นยำตำแหน่งสุดท้ายมาจาก pin กลไกที่เสียบรู sprocket ไม่ใช่จาก encoder อย่างเดียว**
> encoder ใช้ track การเคลื่อนที่ + เข้า slow zone ใกล้เป้า แล้วให้ pin ล็อกตำแหน่ง

ลำดับการทำงานหนึ่งรอบ:
1. มอเตอร์เดินเทปไปข้างหน้า
2. encoder สร้างพัลส์
3. counter นับตำแหน่ง
4. ควบคุมเข้า slow zone เมื่อใกล้เป้า
5. pin กลไกเสียบรู sprocket
6. ตำแหน่งถูกล็อกแม่นยำ
7. counter reset รอรอบถัดไป

---

## 2. Mechanical Parameters

### 2.1 ชิ้นงานที่บรรจุ (ยืนยันแล้ว)

**อุปกรณ์อิเล็กทรอนิก Noise Filter** — **user ยืนยัน 2026-08-05** ตรงกับชิ้นงานที่
`motion_design_source_mentor.md` §2 อ้างอิงไว้ตลอดทั้งเอกสาร

> 🔴 **ห้ามระบุยี่ห้อ/รุ่นของชิ้นงานที่ลูกค้าให้มาบรรจุลงใน repo นี้** (กติกา กติกาเนื้อหาของ repo —
> repo นี้จะถูกยกไปรวมกับ repo สาธารณะ) ให้เรียกว่า "อุปกรณ์อิเล็กทรอนิก Noise Filter" เท่านั้น
> **ตัวเลขสเปกด้านล่างเก็บไว้ได้ทั้งหมด ไม่ใช่ข้อมูลลับ** · ยี่ห้ออุปกรณ์ที่เราซื้อเอง
> (MISUMI / Omron / Delta / DKM) ไม่อยู่ใต้ข้อห้ามนี้

| พารามิเตอร์ | ค่า | หน่วย | ที่มา |
|---|---|---|---|
| ขนาดชิ้นงาน (L×W×H) | 20 × 15 × 10 | mm | user ยืนยัน 2026-08-05 + `motion_design_source_mentor.md` §2 |
| น้ำหนักต่อชิ้น | 4 | g | user ยืนยัน 2026-08-05 + mentor doc §2 |
| จำนวนต่อ carrier | 225 | ชิ้น | user ยืนยัน 2026-08-05 + mentor doc §2 — **ใช้เป็นค่าตั้งต้นของ `target_pieces` ฝั่ง backend** |
| น้ำหนักรวมต่อ carrier | ≈ 0.9 | kg | 225 ชิ้น × 4 g = 900 g (mentor doc §2) — มวลม้วนโตจาก 0 → 0.9 kg ระหว่างรอบ กระทบ takeup tension control โดยตรง |
| ความยาวเทปต่อ carrier | ≈ 4.05 | m | 225 ชิ้น × 18 mm pocket pitch = 4,050 mm (mentor doc §2) |

### 2.2 พารามิเตอร์เทป / กระบวนการ

| พารามิเตอร์ | ค่า | หน่วย | ที่มา / การคำนวณ |
|---|---|---|---|
| tape pitch (pocket pitch) | 18 | mm | ✅ **ปิดประเด็นแล้ว 2026-08-05 (รอบสาม)** — user ยืนยันความถูกต้องของเอกสารออกแบบ motion ทั้งฉบับ (`motion_design_source_mentor.md` §3.2 มีเนื้อหาเดียวกัน): **18 = ด้านกว้างชิ้นงาน 15mm ที่วางตามแนวเทป + clearance ผนัง pocket ข้างละ 1.5mm** และ**เทปตัวนี้เป็น carrier tape เฉพาะทางสำหรับชิ้นงานนี้ ไม่ได้ผูกกับกฎ EIA-481 ที่ pocket pitch ต้องเป็นผลคูณของ 4mm** ⇒ ข้อกังวลเดิมที่ว่า 18 ÷ 4 = 4.5 ไม่ลงตัว **ตกไป** เพราะไม่ใช่เทปมาตรฐาน · เป็นระยะ feed ต่อรอบที่ระบบต้อง achieve ให้แม่นยำและ repeatable ทุกรอบ |
| tape width | _ยังไม่มีข้อมูล_ | mm | คำนวณจากข้อมูลที่มีตอนนี้ไม่ได้แน่นอน — **ข้อจำกัดขั้นต่ำที่รู้แล้ว:** ชิ้นงานวางด้าน 15mm ตามแนวเทป (ตาม mentor doc §3.2) เหลือด้าน **20mm วางขวางแนวเทป** ⇒ tape width ต้อง **มากกว่า 20mm** บวกผนัง pocket สองข้าง + แถบรู sprocket ⇒ เทป 8mm/12mm/16mm ใช้ไม่ได้เด็ดขาด · ⚠️ **แก้ 2026-08-05 (รอบสาม):** เดิมเขียนว่าผู้สมัครคือ 24mm หรือ 32mm ตาม EIA-481 — **ใช้เหตุผลนั้นไม่ได้แล้ว** เพราะยืนยันแล้วว่าเทปตัวนี้เป็นเทปเฉพาะทางที่ไม่อยู่ใต้ EIA-481 จึง**ไม่จำเป็นต้องเป็นค่ามาตรฐาน** ⇒ **ต้องวัดจากเทปจริงหรือขอ drawing เท่านั้น ห้ามเดา** |
| pocket depth | ≥ 10 (ขั้นต่ำ) | mm | ชิ้นงานสูง (H) = 10mm (user ยืนยัน 2026-08-05) ⇒ pocket ลึกอย่างน้อย 10mm ไม่งั้น cover tape ปิดไม่ลงและชิ้นงานโผล่พ้นผิวเทป — **ค่าใช้จริงต้องมากกว่า 10mm** เผื่อ clearance แนวดิ่ง แต่ระยะเผื่อจริงยังไม่มีที่มา (mentor doc ให้ clearance เฉพาะแนวเทป 1.5mm/ข้าง ไม่ได้ให้แนวดิ่ง) |
| sprocket hole pitch | _ยังไม่มีข้อมูล_ | mm | ⛔ **ถอนค่า 4mm ออก 2026-08-05 (รอบสาม) — ห้ามใช้ค่าเดิม** เหตุผล: ค่า 4mm อ้างมาจากมาตรฐาน EIA-481 ล้วน ๆ แต่รอบสามยืนยันแล้วว่า**เทปตัวนี้เป็นเทปเฉพาะทาง ไม่อยู่ใต้ EIA-481** (ดูแถว tape pitch) ⇒ ข้ออ้างที่ใช้ค้ำเลข 4mm หายไปทั้งข้อ จะเหลือ 4mm หรือไม่ต้องดูจากเทปจริงเท่านั้น · **จำเป็นต่อ ADR-005 (pin mechanism) โดยตรง** เพราะหลักการข้อ 1 ระบุว่าความแม่นยำสุดท้ายมาจาก pin เสียบรู sprocket — ถ้า 18mm ไม่ลงตัวกับ sprocket pitch จริง pin จะเสียบตรงได้ไม่ทุกรอบ ดู Open Questions ข้อ 1 |
| ความเร็วผลิตเป้าหมาย | < 30 | ชิ้น/นาที | **user confirm 2026-08-05** — ใช้กำหนดทิศทางเลือก motor/motion profile แบบ deterministic เน้นความแม่นยำมากกว่า throughput |
| แรงกดซีล | _ยังไม่มีข้อมูล_ | N | |
| อุณหภูมิซีล | _ยังไม่มีข้อมูล_ | °C | |
| เวลาซีล | _ยังไม่มีข้อมูล_ | ms | |

---

## 3. Motion Profile

| แกน | ระยะต่อสเต็ป | ความเร็ว | accel | วิธีหยุดให้ตรงตำแหน่ง |
|---|---|---|---|---|
| feed (carrier) | 18 mm/รอบ — user ยืนยันชิ้นงาน 2026-08-05 + `motion_design_source_mentor.md` §3.2 (ตรวจแล้ว ตัวเลขชุดนี้ใช้ได้) | เพดาน < 30 ชิ้น/นาที → cycle time ≥ 2.0 วินาที/ชิ้น (คำนวณ 60s ÷ 30, user confirm 2026-08-05) — deterministic, เน้นความแม่นยำมากกว่า throughput | _ยังไม่มีข้อมูล_ (ต้องคำนวณ torque-speed curve ของ closed-loop stepper เทียบ load จริงของ feed roller ก่อน — ดู Open Questions) | slow zone + pin ล็อก (ADR-001) — ปิด loop ด้วย **position + encoder feedback ที่ตำแหน่งเทปจริง** ไม่ trust จำนวน step ของมอเตอร์เฉยๆ (ที่มา: `motion_design_source_mentor.md` §3.3) · ลำดับหนึ่งรอบ: `Feed ON → drive roller หมุน → measuring roller encoder นับระยะ → ถึง 18.00mm → Feed OFF → settle` (§3.1) |
| cover tape | _ยังไม่มีข้อมูล_ | _ยังไม่มีข้อมูล_ | _ยังไม่มีข้อมูล_ | _ยังไม่มีข้อมูล_ (mentor doc ไม่ได้แยกรายละเอียด cover tape motion ออกจาก feed carrier) |
| takeup (ม้วนเก็บ) | N/A — ไม่ใช่ position-controlled axis (ที่มา: `motion_design_source_mentor.md` §4.1) | N/A — ไม่ควบคุมความเร็วโดยตรง (servo ลด RPM เองเมื่อรัศมีโต) | N/A — ไม่มี accel profile เพราะไม่ได้สั่ง speed/position · torque setpoint จริงยังไม่มี ต้องได้จาก empirical calibration ([`motion_takeup_tension.md`](motion_takeup_tension.md)) | ปรับตามเส้นผ่านศูนย์กลางที่โตขึ้น — **ควบคุมด้วย closed-loop tension feedback (torque control mode) ไม่ใช่ speed-follow** (user confirm 2026-08-05) — torque setpoint คงที่ ให้ servo ลด RPM ลงเองอัตโนมัติเมื่อรัศมีม้วนโต (ที่มา §4.2) **loop ปิดอยู่ในตัว servo drive เอง ไม่ผ่าน FSM** — FSM แค่ enable/disable และอ่านสถานะ (tension ok / alarm) ตาม §5 · ⚠️ **แก้ 2026-08-05 รอบสาม:** เดิมเขียนว่า "ต้องมี tension sensor/load cell ป้อนกลับ" — [ADR-008](../adr/ADR_008_takeup_servo_torque_control.md) ตัดสินแล้วว่า **ช่วง prototype ไม่ใช้ load cell แยก** ใช้ค่า torque/current ที่ drive รายงานเป็นตัววัดแทน (ที่มา §4.6) — **ช่วงการทำงานที่ต้องชดเชย: มวลม้วน 0 → 0.9 kg, เทปสะสม 0 → 4.05 m ต่อ carrier** (ดูข้อ 2.1) รัศมี r(t) โตตามสูตร mentor doc §4.3 `r(t) = √(r₀² + (thickness/π)×L(t))` โดย L(t) คำนวณฟรีจาก feed encoder ที่มีอยู่แล้ว — ค่า `r₀` (รัศมี core) และ `thickness` (ความหนาเทปต่อชั้น) ยังไม่มีข้อมูล |
| sealing (กดลง/ยกขึ้น) | _ยังไม่มีข้อมูล_ | _ยังไม่มีข้อมูล_ | _ยังไม่มีข้อมูล_ | จังหวะตามเวลา |

> เอกสารออกแบบละเอียดของ feed/takeup อยู่ที่ [`motion_design_source_mentor.md`](motion_design_source_mentor.md)
>
> **✅ ยืนยันความถูกต้องของตัวเลขใน mentor doc (2026-08-05):** user ยืนยันแล้วว่าชิ้นงานที่บรรจุคือ
> อุปกรณ์อิเล็กทรอนิก Noise Filter (20×15×10mm) — **ตัวเดียวกับที่ `motion_design_source_mentor.md` §2 อ้างอิงไว้**
> ดังนั้นตัวเลขชุด 18mm/รอบ และการตรวจ resolution ใน §3.6 (roller D=30mm → 0.047 mm/count → 18mm ≈ 383 count,
> resolution เกินพอ) **ใช้ได้ตามที่คำนวณไว้ ไม่ต้องคำนวณใหม่** เช่นเดียวกับ hardware candidate
> (MISUMI E-57ESTM02 closed-loop stepper + Omron E6A2-CWZ5C 500P/R encoder ที่ measuring roller)
>
> **✅ ปิดประเด็น "18mm ไม่ใช่ผลคูณของ 4mm" แล้ว (2026-08-05 รอบสาม)** — user ยืนยันเอกสาร motion
> ทั้งฉบับ: เทปตัวนี้เป็น carrier tape เฉพาะทาง ไม่อยู่ใต้กฎ EIA-481 ⇒ ไม่ต้องหารลงตัวกับ 4mm
> **แต่คำถามที่ยังเหลือคือ sprocket hole pitch ของเทปเฉพาะทางตัวนี้เท่ากับเท่าไร** (ดู Open Questions ข้อ 1)
> ยังกระทบ pin mechanism (ADR-005) โดยตรงตามเดิม เพราะ pin ต้องเสียบรู sprocket ให้ตรงทุกรอบตามหลักการข้อ 1

### 3.1 สถาปัตยกรรม feedback สองชั้นของแกน feed

ที่มา: `motion_design_source_mentor.md` §3.5 — **ทั้งสองชั้นต้องมีพร้อมกัน ห้ามตัดตัวใดตัวหนึ่งออก**

| ชั้น | ตำแหน่งติดตั้ง | ตรวจจับอะไร | ถ้าไม่มีจะพลาดอะไร |
|---|---|---|---|
| encoder ในตัว closed-loop stepper | เพลามอเตอร์ | มอเตอร์ stall / step-loss | มอเตอร์หมุนไม่ครบแล้วไม่มีใครรู้ |
| Omron E6A2-CWZ5C (แยกอิสระ) | measuring roller | **ตำแหน่งเทปจริงเป็น mm — ground truth** | roller ลื่น (slip) กับเทป → มอเตอร์รายงานว่าครบแต่เทปเดินไม่ครบ |

**หลักการ:** encoder ที่เพลามอเตอร์กัน stall ได้ แต่**กัน slip ระหว่าง roller กับเทปไม่ได้**
ค่าที่ใช้ตัดสินว่า "ถึง 18mm แล้ว" ต้องมาจาก encoder ที่ measuring roller เสมอ

**การตรวจ resolution (ที่มา §3.6):**

```
mm ต่อ 1 count = πD / 2000        (encoder 500 P/R, quadrature ×4)
D = 30 mm  →  0.047 mm/count  →  18 mm ≈ 383 count      (resolution เกินพอ)
RPM สูงสุดที่ encoder ตอบสนองได้ = (30,000 Hz × 60) / 500 ≈ 3,600 RPM  (เกินความต้องการจริงมาก)
```

> ⚠️ **D = 30 mm เป็นค่าตัวอย่างที่เอกสารต้นทางสมมติไว้ ยังไม่ใช่เส้นผ่านศูนย์กลาง measuring roller จริง**
> ถ้าออกแบบ roller จริงเป็นค่าอื่น ต้องคำนวณ count/18mm ใหม่ — ห้ามคัดเลข 383 ไปใช้ตรง ๆ ก่อนล็อกขนาด roller

### 3.2 การแบ่งหน้าที่ระหว่าง FSM กับ motion (ที่มา §5)

- **feed axis** — FSM สั่งแบบ discrete: `move` แล้วรอ event `position reached` (ไม่ poll raw I/O)
- **takeup axis** — torque loop วิ่งอยู่ในตัว servo drive เอง **FSM ไม่ได้อยู่ใน loop** สั่งได้แค่ enable/disable
  และอ่านสถานะ (tension ok / alarm)
- **safety layer แยกอิสระจาก application logic** — ดูข้อ 6
- **dancer arm** เป็นตัวเชื่อม motion สองโดเมนที่จังหวะไม่ตรงกัน (feed = discrete step, takeup = continuous
  winding) ไม่ให้ชนกัน — **ยังไม่มีสเปกกลไก dancer arm จริง (ระยะชัก, สปริง/ลม, เซนเซอร์ตำแหน่ง) ดู Open Questions**
- **หลักการ migration:** FSM คุยกับ motion ผ่าน event ไม่ใช่ raw I/O ⇒ เปลี่ยนฮาร์ดแวร์ได้โดยไม่ต้อง
  แก้ sequence logic (ที่มา §7)

---

## 4. I/O List

**สำคัญ:** `fsm` จะเอาคอลัมน์ `signal_name` ไปทำ guard และ `stm32` จะเอาไปทำ pin mapping
ห้ามให้ใครคิดชื่อสัญญาณขึ้นเองนอกตารางนี้

> 🔴 **สัญญาณที่ทำเครื่องหมาย `SAFETY` ในตารางนี้ห้าม `fsm`/`stm32`/`backend` แตะเด็ดขาด**
> ไม่ใช่ DI/DO ธรรมดา — เป็นสายของวงจร safety ที่ต้องเดินตรงจากอุปกรณ์ safety ไปยัง drive
> **ห้ามขับจากซอฟต์แวร์ ห้ามเอาไปทำ guard ของ state machine** เหตุผลอยู่ในข้อ 6

| signal_name | ชนิด | อุปกรณ์ | active | หมายเหตุ |
|---|---|---|---|---|
| `ESTOP_NC` | DI | ปุ่ม E-STOP (NC contact, hardwired safety loop) | L | สัญญาณฮาร์ดแวร์จริงของปุ่ม E-STOP ที่ `fsm_spec.md` §6.1 รอมา — คู่กับ protocol action `ESTOP` (software) ที่ `fsm` ใช้ผูก guard อยู่แล้ว active=L เพราะเป็น NC contact แบบ fail-safe (ปุ่มกด/สายขาด = วงจรเปิด = อ่านได้ L) รุ่นปุ่มจริงยังไม่เลือก (ADR ใหม่ค้างไว้) — **user confirm 2026-08-05: ยืนยันหลักการเท่านั้น ยังไม่มี ADR เลือกรุ่น** |
| `TENSION_FEEDBACK` | AI | Tension sensor / load cell (takeup) | N/A (analog) | ⚠️ **แขวนไว้ 2026-08-05 (รอบสาม) — ยังไม่ต้อง implement** [ADR-008](../adr/ADR_008_takeup_servo_torque_control.md) ตัดสินว่าช่วง prototype **ไม่ใช้ load cell แยก** เพราะ torque loop ปิดอยู่ในตัว servo drive และ drive รายงานค่า torque/current ออกมาได้เอง (§4.6) — เก็บชื่อสัญญาณนี้ไว้เผื่ออนาคตถ้าต้องการ tension วัดตรงที่เส้นเทป **`fsm` ยังไม่ต้องผูก guard กับสัญญาณนี้** |
| `FEED_ENC_A` | DI | Omron E6A2-CWZ5C 500P/R ที่ measuring roller | — | ช่อง A ของ encoder ground truth ตำแหน่งเทป · 🔴 **output เป็น NPN open collector 12–24 VDC** ต้องมี **pull-up + level shifting** ก่อนเข้า logic ของ STM32 Extension IO ต่อตรงไม่ได้ (`motion_design_source_mentor.md` §3.7 ข้อ 1) |
| `FEED_ENC_B` | DI | Omron E6A2-CWZ5C 500P/R ที่ measuring roller | — | ช่อง B — ใช้คู่กับ A ทำ quadrature ×4 (ได้ 2000 count/รอบ) เพื่อรู้ทิศทางด้วย ไม่ใช่แค่จำนวน · เงื่อนไข level shifting เหมือน `FEED_ENC_A` |
| `FEED_ENC_Z` | DI | Omron E6A2-CWZ5C 500P/R ที่ measuring roller | — | ช่อง Z (index, 1 พัลส์/รอบ) — ใช้ตรวจสอบ/รีเซ็ตการนับสะสม · เงื่อนไข level shifting เหมือน `FEED_ENC_A` · **ยังไม่ตัดสินว่าจะใช้ Z จริงหรือไม่** ขึ้นกับว่าใช้ pin lock เป็น reference อยู่แล้ว (ADR-001) |
| `TAKEUP_ENABLE` | DO | Delta servo drive (takeup) | _ยังไม่ระบุ_ | FSM สั่ง enable/disable แกน takeup เท่านั้น — **ไม่ได้สั่ง speed หรือ position** เพราะ torque loop อยู่ในตัว drive (§5) |
| `TAKEUP_ALARM` | DI | Delta servo drive (takeup) | _ยังไม่ระบุ_ | สถานะ alarm จาก drive ให้ FSM อ่าน (§5 "FSM แค่ enable/disable และอ่านสถานะ") — active level ต้องดูจาก datasheet drive ที่เลือกจริงก่อน **ห้ามเดา** |
| `TAKEUP_TORQUE_CMD` | AO **หรือ** Modbus register | Delta servo drive (takeup) | N/A | torque setpoint ที่ส่งให้ drive · ⚠️ **ยังตัดสินไม่ได้ว่าเป็น analog 0–10 V หรือ Modbus** (`motion_design_source_mentor.md` §4.7 ข้อ 2) — ถ้าเป็น Modbus จะ**ไม่ใช่สัญญาณ I/O จริง** และหายไปจากตารางนี้ ไปอยู่ใน `protocol.md` แทน **`stm32` ยังจอง pin ให้สัญญาณนี้ไม่ได้จนกว่าจะตัดสิน** ดู Open Questions |
| `GUARD_NC` | DI | Guard/door limit switch (NC contact) | L | ใช้บอก application layer ว่า guard เปิดอยู่ (เพื่อ log/แสดงผล/บล็อกการเริ่มรอบใหม่) · 🔴 **ไม่ใช่ตัวที่ทำหน้าที่หยุดมอเตอร์** การตัด torque เมื่อ guard เปิดต้องทำผ่าน `STO_CH1/CH2` ในวงจร safety ดูข้อ 6 · active=L เพราะเป็น NC fail-safe เหมือน `ESTOP_NC` |
| `STO_CH1` | **SAFETY** (hardwired) | Delta servo drive — Safe Torque Off ช่อง 1 | L (fail-safe) | 🔴 **ห้ามขับจากซอฟต์แวร์** เดินสายตรงจาก safety relay/E-STOP loop เข้า drive · สองช่องแยกกันเพื่อความ redundant ตามที่ ISO 13849-1 Cat 3 ต้องการ · **ยังไม่ยืนยันว่า drive รุ่นที่เลือกมี STO ในตัวหรือต้องซื้อ safety module เพิ่ม** ดู Open Questions |
| `STO_CH2` | **SAFETY** (hardwired) | Delta servo drive — Safe Torque Off ช่อง 2 | L (fail-safe) | 🔴 ช่องที่สองของ STO — เงื่อนไขเดียวกับ `STO_CH1` ทุกข้อ |

---

## 5. Sensor & Actuator List

| ตำแหน่ง | อุปกรณ์ | รุ่น | สเปกที่ใช้ตัดสินใจ | ADR |
|---|---|---|---|---|
| นับพัลส์ (prototype) | Counter | RS PRO | 20 kHz, รองรับ A+B quadrature | [ADR-001](../adr/ADR_001_encoder_counter.md) |
| ติดตามการเคลื่อนที่ (measuring roller) | Incremental Encoder | **Omron E6A2-CWZ5C 500P/R** | 500 P/R → quadrature ×4 = 2000 count/รอบ · roller D=30mm (ค่าตัวอย่าง) → 0.047 mm/count → 18mm ≈ 383 count · electrical response 30 kHz → รองรับถึง ~3,600 RPM · **NPN open collector 12–24 VDC ต้อง level shift** · allowable shaft load radial 10 N / thrust 5 N → **ต้องต่อผ่าน flexible coupling ห้าม rigid mount** · **IP50 ไม่กันน้ำมัน/ฝุ่น ต้องมี enclosure ถ้าอยู่ใกล้ไอน้ำมัน** (ที่มา `motion_design_source_mentor.md` §3.4, §3.6, §3.7) | ADR-004 (ยังไม่เขียน — เอกสารต้นทางระบุรุ่นที่เลือกแล้วแต่**ไม่ได้เทียบทางเลือกอื่น** จึงยังเขียน ADR ที่มีเนื้อหาจริงไม่ได้) |
| ขับเคลื่อนเทป (feed) | Closed-loop Stepper Motor | **MISUMI E-57ESTM02** | holding torque 1.2 / 2 N·m · closed-loop = มี encoder ในตัวที่เพลามอเตอร์ ใช้จับ stall/step-loss (ชั้นที่ 1 ของ feedback สองชั้น ดูข้อ 3.1) · ⚠️ **ยังไม่ได้ตรวจ torque-speed curve เทียบกับ load จริงของ feed roller** ดู Open Questions (ที่มา §3.4, §3.5) | ADR-006 (ยังไม่เขียน — เหตุผลเดียวกับ ADR-004) |
| ขับ stepper (feed) | Stepper Driver | **MISUMI E-EDR57A** | ไดรเวอร์คู่กับ E-57ESTM02 · **interface สั่งงาน (pulse/dir/enable) ยังไม่ยืนยันจาก datasheet** จึงยังไม่ลงชื่อสัญญาณใน I/O List ข้อ 4 — `stm32` ยังจอง pin ไม่ได้ (ที่มา §3.4) | ADR-006 (ยังไม่เขียน) |
| ม้วนเก็บ (takeup) | AC Servo Drive + Motor | **Delta ASD-B2-0721 + ECMA-C10807** | 750W · rated torque **2.39 N·m** · max ~7.16 N·m · ใช้ **torque control mode** (ไม่ใช่ speed/position) · drive รายงานค่า torque/current ออกมาได้เอง จึงใช้แทน load cell ในช่วง prototype | **[ADR-008](../adr/ADR_008_takeup_servo_torque_control.md) ✅ เขียนแล้ว 2026-08-05** |
| ล็อกตำแหน่ง | Pin Mechanism | _ยังไม่ระบุ_ | ⛔ **ออกแบบไม่ได้จนกว่าจะรู้ sprocket hole pitch จริงของเทปเฉพาะทางตัวนี้** (ดูข้อ 2.2 + Open Questions ข้อ 1) | ADR-005 (ยังไม่เขียน — บล็อกอยู่) |
| ตรวจตำแหน่ง/ชิ้นงาน | Sensor | _ยังไม่ระบุ_ | | ADR-007 (ยังไม่เขียน) |
| วัดแรงตึงเทป (takeup) | Tension sensor / Load cell | _ไม่ใช้ในช่วง prototype_ | ⚠️ **เปลี่ยนข้อสรุป 2026-08-05 (รอบสาม)** — [ADR-008](../adr/ADR_008_takeup_servo_torque_control.md) ตัดสินว่าใช้ค่า torque/current จาก servo drive เป็นตัววัดแทน **ไม่ต้องซื้อ load cell แยกในช่วง prototype** (`motion_design_source_mentor.md` §4.6) · `bom-cost` **ยังไม่ต้องตั้งรายการ load cell** | [ADR-008](../adr/ADR_008_takeup_servo_torque_control.md) |
| กันจังหวะ feed/takeup ชนกัน | Dancer arm | _ยังไม่ระบุ_ | เชื่อม motion 2 โดเมน (feed = discrete step, takeup = continuous winding) ตาม §5 — **ยังไม่มีสเปกกลไกจริง** (ระยะชัก, สปริง/ลม, เซนเซอร์ตำแหน่ง) ดู Open Questions | _ยังไม่จองเลข ADR_ |

**แผนอนาคต:** ย้ายจาก RS PRO Counter ไป **STM32F401 timer-based encoder decoding**
หลัง validate พฤติกรรมกลไกและระบบเรียบร้อยแล้ว (ลดความเสี่ยง firmware ในช่วง prototype)

---

## 6. Safety & Interlock

`fsm` จะเอาหัวข้อนี้ไปทำ guard — เงื่อนไขที่เขียนตรงนี้คือเงื่อนไขที่ห้ามละเมิด

### 6.1 🔴 ข้อสรุปสำคัญที่สุด — E-STOP ระดับซอฟต์แวร์ "ไม่พอ"

> **เพิ่ม 2026-08-05 (รอบสาม)** จาก `motion_design_source_mentor.md` §5 + §6
> **เขียนไว้ตรงนี้เพราะเพิ่งมีการ implement E-STOP latch ระดับซอฟต์แวร์เสร็จไปเมื่อ 2026-08-05**
> (`fsm_spec.md` หัวข้อ 6 + `gateway_fsm.py`) — **งานนั้นถูกต้องและยังต้องมีต่อ แต่ยังไม่ใช่ safety function**

ระบบต้องมี **safety layer แยกอิสระจาก application logic** สองชั้นที่ทำงานคนละหน้าที่:

| ชั้น | ทำอะไร | สถานะตอนนี้ |
|---|---|---|
| **ชั้นซอฟต์แวร์** — action `ESTOP` → latch `step_allowed=false` → `ALARM` | หยุด **ลำดับการทำงาน** ไม่ให้เดินต่อ + บันทึก alarm + แจ้งจอ/เว็บ | ✅ ทำแล้ว (`fsm_spec.md` หัวข้อ 6) |
| **ชั้นฮาร์ดแวร์** — **STO (Safe Torque Off)** | ตัด **แรงบิดจริงที่มอเตอร์** | ❌ **ยังไม่มี — ต้องทำ** |

**ข้อกำหนดที่ห้ามละเมิด (อ้าง `motion_design_source_mentor.md` §5):**

```
STO ต้องตัด torque ได้โดยไม่ผ่าน FSM
(hardwired หรือ safety-rated fieldbus เท่านั้น)
```

เหตุผล: ถ้าการตัดกำลังขับต้องวิ่งผ่าน Python FSM → Rust bridge → Modbus TCP → บอร์ด STM32
แล้ว**ซอฟต์แวร์ชั้นใดชั้นหนึ่งค้าง/ตาย/สายหลุด มอเตอร์จะไม่ถูกตัดเลย** — และมีหลักฐานแล้วว่า
สายไปบอร์ดหลุดได้จริงเมื่อเว้นจังหวะเกิน ~200 ms (ดู `STATUS.md` ประกาศ 2026-08-05)
⇒ **ห้ามให้ path ของ safety เดินผ่านซอฟต์แวร์เด็ดขาด**

**`fsm` / `backend` / `stm32` ต้องเข้าใจตรงกันว่า:** action `ESTOP` ที่ implement ไปแล้ว
**ไม่ได้ทำให้เครื่องปลอดภัยตามมาตรฐาน** มันทำให้ *ลำดับงาน* ปลอดภัยเท่านั้น
**ห้ามเขียนเอกสาร/สไลด์/thesis ว่าระบบมี E-STOP ที่ปลอดภัยแล้ว** จนกว่าจะมี STO จริง

### 6.2 ฟังก์ชัน safety ที่ต้องมี (ที่มา §6)

Take-up reel อยู่ใกล้ operator และมี **nip point** (จุดหนีบระหว่างม้วนกับ roller) — ต้องมี:

| ฟังก์ชัน | ทำอะไร | trigger |
|---|---|---|
| **STO** (Safe Torque Off) | ตัด torque ทันที | guard เปิด / E-STOP กด |
| **SLS** (Safely Limited Speed) | จำกัดความเร็วสูงสุดขณะ guard เปิด | โหมด jog / maintenance |
| **Safe Torque Limit** | จำกัด torque สูงสุดที่จุด nip point | ตลอดเวลาที่เดินเครื่อง |

**เป้าหมายระดับความปลอดภัย: ISO 13849-1 Category 3, PL d**
(Cat 3 = ความผิดพลาดเดี่ยวต้องไม่ทำให้ฟังก์ชัน safety หาย ⇒ **ต้องเป็นวงจรสองช่องทาง (dual channel)**
ซึ่งเป็นเหตุผลที่ I/O List มี `STO_CH1` และ `STO_CH2` แยกกัน)

**กฎเรื่องค่า torque:**

```
Normal operating torque  <  Safe Torque Limit        (ต้องมี margin เสมอ)
```

⚠️ **ค่าจริงของทั้งสองฝั่งยังไม่มี** — normal operating torque ต้องได้จาก empirical calibration
([`motion_takeup_tension.md`](motion_takeup_tension.md)) ส่วน Safe Torque Limit ต้องได้จาก risk assessment
**ห้ามตั้งค่าใดค่าหนึ่งโดยไม่มีอีกค่า**

### 6.3 มาตรฐานที่ต้องอ้างอิง (ยังไม่ได้ทำ)

| มาตรฐาน | ใช้ทำอะไร | สถานะ |
|---|---|---|
| ISO 12100 | risk assessment ของทั้งเครื่อง (โดยเฉพาะ nip point ของ takeup) | ❌ ยังไม่ทำ |
| ISO 13849-1 | กำหนด PL rating + สถาปัตยกรรมวงจร safety (เป้า Cat 3 PL d) | ❌ ยังไม่ทำ |
| ISO 13857 | ระยะปลอดภัย (safety distance) ของ guard | ❌ ยังไม่ทำ |

### 6.4 ตารางเงื่อนไข interlock

| เงื่อนไข | ต้องเกิดอะไรขึ้น (ชั้นฮาร์ดแวร์) | ต้องเกิดอะไรขึ้น (ชั้นซอฟต์แวร์) |
|---|---|---|
| E-STOP กด | 🔴 **STO ตัด torque ทั้ง feed และ takeup ทันที ผ่านวงจร hardwired ไม่ผ่าน FSM** (`STO_CH1`+`STO_CH2`) | action `ESTOP` → `step_allowed=false` → `ALARM` + บันทึก alarm (มีแล้วใน gateway ตาม `fsm_spec.md` §6.2) · สัญญาณ `ESTOP_NC` ให้ `fsm` ผูก guard ชั้นฮาร์ดแวร์เพิ่มได้ตามที่ `fsm_spec.md` §6.1 รอไว้ |
| guard/ประตูเปิด | 🔴 **STO ตัด torque** (หรือเข้าโหมด SLS ถ้าเป็น jog/maintenance ที่อนุญาต) | อ่าน `GUARD_NC` → ห้ามเริ่มรอบใหม่ + แจ้งผู้ใช้ |
| อุณหภูมิเกินช่วง | — | ห้ามซีล |
| servo drive แจ้ง alarm | drive หยุดเอง | อ่าน `TAKEUP_ALARM` → เข้า `ALARM` |
| ระหว่างทำ empirical torque calibration | 🔴 ต้องมี E-STOP/STO อยู่ในระยะเอื้อมตลอดเวลา + ตั้ง Torque Limit ไว้ต่ำกว่าค่าที่คำนวณว่าปลอดภัยเสมอ (ที่มา §4.6) | — |

---

## 7. Open Questions

> **อัปเดต 2026-08-05 (รอบสาม)** — user ยืนยันเอกสารออกแบบ motion ทั้งฉบับ
> ✅ **ปิดเพิ่ม 1 ข้อ: ที่มาของ pocket pitch 18mm** (= ชิ้นงาน 15mm + clearance 1.5mm/ข้าง และเป็น
> carrier tape เฉพาะทาง ไม่ผูกกับ EIA-481 ⇒ ไม่ต้องหารลงตัวกับ 4mm) — **ประเด็น 18÷4=4.5 ตกไปทั้งข้อ**
> แต่การปิดข้อนี้**เปิดคำถามใหม่ที่ใหญ่กว่าเดิม** (ข้อ 1 ด้านล่าง) และมีของใหม่จากฝั่ง motion/safety อีกหลายข้อ

### เรื่องเทป / กลไก

- [ ] 🔴 **sprocket hole pitch ของเทปเฉพาะทางตัวนี้เท่ากับเท่าไร — คำถามใหม่ 2026-08-05 (รอบสาม)**
      **เกิดขึ้นเพราะปิดข้อ 18mm ไปแล้ว:** เมื่อยืนยันว่าเทปตัวนี้เป็น carrier tape เฉพาะทางที่**ไม่อยู่ใต้
      EIA-481** แปลว่า**เราอ้าง "sprocket hole pitch = 4.00mm ตามมาตรฐาน" ต่อไปไม่ได้อีกแล้ว** —
      ค่าเดิม 4mm ในข้อ 2.2 ถูกถอนออกเพราะข้ออ้างที่ค้ำมันหายไปพร้อมกับ EIA-481
      **เอกสารออกแบบ motion ที่ user ยืนยันไม่ได้ระบุค่านี้ไว้เลย** (พูดถึงแต่ pocket pitch)
      **ทำไมสำคัญ:** หลักการข้อ 1 ของสเปกนี้ระบุว่า**ความแม่นยำตำแหน่งสุดท้ายมาจาก pin ที่เสียบรู sprocket**
      ⇒ ถ้าไม่รู้ระยะรู จะออกแบบ pin mechanism (ADR-005) ไม่ได้เลย และยังตอบไม่ได้ว่า feed 18mm
      ต่อรอบจะไปหยุดตรงรูพอดีทุกรอบหรือไม่
      **ต้องได้มาโดย:** วัดจากเทปจริงที่มีอยู่ หรือขอ drawing/datasheet ของเทปเฉพาะทางตัวนี้
- [ ] tape width จริง — เลือกไม่ได้จนกว่าจะได้ drawing/เทปจริงมาวัด
      ข้อจำกัดที่รู้แล้ว: ต้องมากกว่า 20mm (ดูข้อ 2.2) · หมายเหตุ: ตอนนี้รู้แล้วว่าเป็นเทปเฉพาะทาง
      **จึงไม่จำเป็นต้องเป็นค่ามาตรฐาน 24/32mm** — ต้องวัดของจริงเท่านั้น
- [ ] เส้นผ่านศูนย์กลาง **core** ของม้วน takeup และเส้นผ่านศูนย์กลางม้วนตอนเต็ม
      (= ค่า `r₀` และช่วงของ `r(t)` ในสูตร §4.3) — ต้องวัดจากแบบ CAD ของเราเอง
      **จำเป็นต่อการประเมินว่า torque setpoint ค่าเดียวพอไหม หรือต้องขยับตามขนาดม้วน**
- [ ] ความหนาเทปต่อชั้น (`thickness` ในสูตร §4.3) — ยังไม่มีค่า
- [ ] เส้นผ่านศูนย์กลาง **measuring roller** จริง — §3.6 ใช้ D=30mm เป็นค่าตัวอย่างเท่านั้น
      ล็อกค่านี้แล้วต้องคำนวณ count ต่อ 18mm ใหม่ (ห้ามใช้เลข 383 ก่อนล็อก)
- [ ] สเปกกลไก **dancer arm** — ระยะชัก, ใช้สปริงหรือลม, มีเซนเซอร์ตำแหน่งไหม (เอกสาร motion ระบุแค่หน้าที่)

### เรื่อง takeup / servo (ดู [ADR-008](../adr/ADR_008_takeup_servo_torque_control.md))

- [ ] 🔴 **"torque ประมาณ 2" ที่พี่เลี้ยงระบุ หมายถึงอะไรกันแน่** — *rated torque ของมอเตอร์ที่จะซื้อ*
      หรือ *torque ที่คำนวณว่าต้องใช้งานจริง* · **สองความหมายนี้พาไปสู่มอเตอร์คนละ class**
      (ถ้า 2 N·m คือ operating load จริง มอเตอร์ rated 2.39 N·m จะเหลือ margin น้อยเกินไป
      ต้องขยับขึ้น class) — เป็นสมมติฐานที่ ADR-008 ตั้งอยู่บนมัน **ต้องยืนยันก่อนสั่งซื้อ**
- [ ] ยืนยันว่า workshop/lab มี **ไฟ 3-phase 220V** รองรับ servo 750W หรือไม่ (บาง SKU เป็น single-phase)
- [ ] servo drive รุ่นที่เลือกมี **STO ในตัว** หรือต้องซื้อ safety module เพิ่ม (กระทบ `STO_CH1/CH2` ใน I/O List)
- [ ] **torque command interface** — analog 0–10 V หรือ Modbus · ถ้าเป็น Modbus สัญญาณ `TAKEUP_TORQUE_CMD`
      จะไม่ใช่ I/O จริงและต้องย้ายไปนิยามใน `protocol.md` แทน (**`integration` + `stm32` รอข้อนี้อยู่**)
- [ ] **Delta servo ที่สั่งซื้อไปแล้ว (ดู `STATUS.md` ประกาศ 2026-08-03 ของ `bom-cost`) เป็นรุ่นไหน
      ตรงกับ ASD-B2-0721 + ECMA-C10807 ที่ ADR-008 เลือกหรือไม่** — ถ้าไม่ตรงต้องกลับมาแก้ ADR-008
- [ ] ทำ **empirical torque calibration** ตาม [`motion_takeup_tension.md`](motion_takeup_tension.md)
      เมื่อประกอบตัวทดลองเสร็จ → ได้ค่า normal operating torque จริง

### เรื่อง feed

- [ ] คำนวณ/ตรวจ **torque-speed curve ของ closed-loop stepper เทียบกับ load จริงของ feed roller**
      (holding torque 1.2/2 N·m เป็นค่า holding ไม่ใช่ค่าที่ความเร็วใช้งาน) → ยังกรอก accel ในข้อ 3 ไม่ได้
- [ ] วงจร **pull-up + level shifting** ของ encoder NPN open collector → logic ของ STM32
      ใช้แรงดันเท่าไร ต้านทานเท่าไร — **`stm32` ต้องรู้ก่อนออกแบบ interface board**

### เรื่อง safety

- [ ] 🔴 ทำ **risk assessment ตาม ISO 12100** โดยเฉพาะ nip point ของ takeup reel → ยังไม่มีค่า
      Safe Torque Limit / SLS จริง (ดูข้อ 6.2)
- [ ] เลือกอุปกรณ์วงจร safety จริง (safety relay, ปุ่ม E-STOP รุ่นไหน, guard switch) — ยังไม่มี ADR

### เรื่องอื่น

- [ ] จะย้ายไป STM32F401 เมื่อไร ใช้เกณฑ์อะไรตัดสินว่า "validate แล้ว" (ยังไม่ตอบ)

> ห้ามเติมตัวเลขมั่วให้ตารางดูครบ — ช่องว่างที่ทำเครื่องหมายไว้ปลอดภัยกว่าตัวเลขที่เดา
