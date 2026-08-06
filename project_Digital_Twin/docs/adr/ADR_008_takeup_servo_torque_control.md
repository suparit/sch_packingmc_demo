# ADR-008: การควบคุมแรงตึงเทปของแกน Take-up (Servo Torque Control)

## Status

**Accepted** — เลือก class มอเตอร์แล้ว แต่ **ยังไม่ปิดการเลือกรุ่นย่อยจนกว่าจะเคลียร์ Open Items ข้างล่าง**

## Date

2026-08-05

## ที่มาของข้อมูล

เอกสารออกแบบ motion ที่ **user ยืนยันความถูกต้องแล้ว 2026-08-05**
(สรุปไว้ใน [`../specs/motion_design_source_mentor.md`](../specs/motion_design_source_mentor.md) §4)
ตัวเลข rated torque อ้างจากตาราง ECMA-C series ในเอกสารฉบับนั้น

> 🔴 **หมายเหตุความลับ:** ห้ามระบุยี่ห้อ/รุ่นของชิ้นงานที่ลูกค้าให้มาบรรจุ และห้ามระบุรหัสเครื่องอ้างอิง
> ของลูกค้าลงใน repo นี้ (ดูหัวข้อ "กติกาเนื้อหา" ใน README) — ในเอกสารนี้เรียกว่า "ชิ้นงาน" และ "เครื่องเดิม" เท่านั้น
> ยี่ห้ออุปกรณ์ที่เราซื้อเอง (Delta / MISUMI / Omron / DKM) ระบุได้ตามปกติ

---

## 1. Context — ปัญหาที่ต้องแก้

แกน take-up ม้วนเทปที่บรรจุชิ้นงานแล้วเก็บเป็นรีล ตัวแปรที่ต้องคุมคือ **แรงตึงเทป (tension)**
ไม่ใช่ตำแหน่งหรือความเร็ว

### 1.1 ทำไมคุม speed/position ไม่ได้

```
เส้นผ่านศูนย์กลางม้วนโตขึ้นเรื่อย ๆ ระหว่างรอบ
        ↓
RPM คงที่ → linear speed เพิ่มขึ้น (v = ωr)
        ↓
tension เพิ่มแบบไม่เป็นเชิงเส้น
        ↓
เทปยับ / ฉีกขาด / ดึงชิ้นงานหลุดจาก pocket
```

ช่วงที่ต้องชดเชยจริงในเครื่องนี้: มวลม้วน **0 → 0.9 kg** และเทปสะสม **0 → 4.05 m** ต่อ carrier
(225 ชิ้น × 4 g, 225 × 18 mm — ดู `machine_spec.md` ข้อ 2.1)

### 1.2 หลักการ torque control

```
Torque ที่ต้องการ = F_tension × r(t)
```

คุมที่ torque แทน RPM ⇒ เมื่อ `r` โตขึ้น drive จะ**ลด RPM ลงเองอัตโนมัติ**เพื่อรักษา torque setpoint
⇒ tension คงที่ **โดยไม่ต้องรู้ค่า `r(t)` แบบ real-time**

ถ้าต้องการ compensation ละเอียดขึ้นในภายหลัง ประมาณรัศมีได้จาก
`r(t) = √( r₀² + (thickness/π) × L(t) )` โดย `L(t)` **คำนวณได้ฟรีจาก feed encoder ที่มีอยู่แล้ว**
(ยังไม่มีค่า `r₀` และ `thickness` — ดู Open Items)

### 1.3 วิเคราะห์เครื่องเดิม — ปัญหาจริงไม่ใช่ torque

มอเตอร์เดิม: **DKM 6IDGF-6G + gearhead 6GD20M** (6 W, 220 VAC, ~1250 rpm no-load, เกียร์ 20:1, ปรับด้วย knob มือ)

```
ω        = 1250 rpm × 2π/60          = 130.9 rad/s
T_motor  = P / ω = 6 W / 130.9       ≈ 0.046 N·m      (ที่เพลามอเตอร์ ก่อนเกียร์)
T_output = 0.046 × 20 × 0.7 (eff.)   ≈ 0.64 N·m       ที่ ~62.5 rpm
```

**ข้อสรุปที่สำคัญที่สุดของ ADR นี้:** 6 W ดูน้อยมาก แต่หลังทดเกียร์แล้วได้ torque ~0.6–0.9 N·m
ซึ่ง**ใกล้เคียงกับที่ต้องใช้จริง** (ไม่ได้ต่างกัน 100 เท่าอย่างที่ดูจากตัวเลข wattage เปล่า ๆ เพราะ
`Torque × Speed = Power` — มอเตอร์แลกความเร็วที่ไม่ได้ใช้ประโยชน์ไปเป็น torque ผ่านเกียร์)

⇒ **ปัญหาของเครื่องเดิมไม่ใช่ torque ไม่พอ แต่คือไม่มี control loop ทางอิเล็กทรอนิกส์:**

| ปัญหา | ผลกระทบ |
|---|---|
| AC induction motor เป็น constant-speed device โดยธรรมชาติ | ไม่มี torque control loop ทางไฟฟ้าเลย |
| knob = ปรับ voltage ผ่าน variac/triac ไม่ใช่ vector control | ลด V เพื่อลด speed แต่ **torque ลดตาม (T ∝ V²)** |
| **operator คือ control loop จริงของระบบ** | ตอนม้วนโต (ต้องการ torque **มากขึ้น**) operator มักลด V เพื่อลด speed → **torque กลับลดสวนทางกับที่ต้องการ** |
| ผลลัพธ์ขึ้นกับทักษะ/ความใส่ใจของคน | ไม่ consistent ระหว่างกะ/ระหว่างคน |
| ไม่มี record ไม่ repeatable | **tacit knowledge ของ operator แปลงเป็น digital model ไม่ได้ → ขัดกับเป้าหมาย Digital Twin โดยตรง** |
| ต้องมีคนยืนเฝ้าตลอด | ขัดกับเป้าหมาย automation |

**สรุปเชิงวิศวกรรม:** เครื่องเดิม*มี* tension control อยู่แล้ว แต่ implement ด้วย**คน**แทนวงจร
การย้ายไป torque control mode ของ servo คือการ **digitize สิ่งที่ operator ทำอยู่แล้วด้วยมือ**
ให้แม่นยำและ repeatable — นี่คือเหตุผลหลักที่ต้องเปลี่ยน ไม่ใช่เพราะ torque ไม่พอ

---

## 2. Options Considered

### 2.1 Control mode

| ทางเลือก | ผล | ตัดสิน |
|---|---|---|
| คงเดิม: AC motor + manual knob | ต้นทุน 0 แต่ไม่ repeatable, ไม่มี data, ต้องมีคนเฝ้า | ❌ ขัดเป้าหมาย Digital Twin |
| Speed control (VFD/servo speed mode) | tension เพิ่มขึ้นเมื่อ r โต ตามข้อ 1.1 | ❌ ผิดหลักฟิสิกส์ของงานม้วน |
| Position control | ไม่มีความหมายสำหรับแกนที่ปลายทางเป็นม้วนขนาดเปลี่ยนได้ | ❌ |
| **Torque control mode (servo)** | tension คงที่เองเมื่อ r โต · drive รายงาน torque/current ออกมาได้ | ✅ **เลือก** |

### 2.2 Drive series — Delta ASD-A2 vs ASD-B2

ทั้งคู่เป็น DSP-based PMSM servo (current control ผ่าน IGBT) รองรับ position/speed/**torque mode**
พร้อม torque limit + speed limit ในตัวเหมือนกัน

- **A2** — high-end, มี communication เพิ่ม (CANopen/DMCNET), tuning ละเอียดกว่า
- **B2** — general purpose/economical

take-up เป็น **single axis ที่ไม่ต้อง sync กับแกนอื่นแบบ real-time network** ⇒ **เลือก B2**

### 2.3 Motor class — ตาราง ECMA-C series (low inertia, 3000 rpm)

| Power | Rated Torque (N·m) | Max Torque (N·m) | Drive |
|---|---|---|---|
| 100W | 0.32 | 0.96 | ASD-A2/B2-0121 |
| 200W | 0.64 | 1.92 | ASD-A2/B2-0221 |
| 400W | 1.27 | 3.82 | ASD-A2/B2-0421 |
| **750W** | **2.39** | **~7.16** | **ASD-A2/B2-0721** |
| 1000W | 3.18 | ~9.55 | ASD-A2/B2-1021 |
| 1500W | 4.77 | ~14.3 | ASD-A2/B2-1521 |

---

## 3. Decision

**เลือก Delta `ASD-B2-0721` + `ECMA-C10807` (750 W, rated torque 2.39 N·m, max ~7.16 N·m)
ทำงานใน torque control mode**

**และตัดสินเพิ่มว่า: ช่วง prototype ไม่ใช้ load cell / tension sensor แยก**
ใช้ค่า torque/current ที่ servo drive รายงานออกมาเองเป็นเครื่องมือวัดแทน
(อ่านจากหน้าจอ drive, ASDA-Soft, หรือ Modbus register ผ่าน Rust layer)

### เหตุผลที่เลือก 750W

1. **rated torque 2.39 N·m ตรงกับตัวเลข "torque ประมาณ 2" ที่พี่เลี้ยงระบุไว้พอดี**
   ⚠️ ข้อนี้เป็นสมมติฐานที่ยังต้องยืนยัน — ดู Open Items ข้อ 1
2. **dynamic range กว้าง (0 → 7.16 N·m ชั่วขณะ)** — สำคัญมากเพราะ `F_tension` จริงยังไม่รู้
   ต้องหาด้วยการทดลอง การมี headroom กว้างทำให้ทดลองได้โดยไม่ชนเพดานความสามารถของมอเตอร์
3. **ไม่โอเวอร์ไซส์เกินจำเป็น** — 1.5–2 kW แพงกว่ามากและใหญ่เกินความจำเป็นสำหรับงานเทปบางเบา
   (โหลดจริงสูงสุดคือม้วนหนัก ~0.9 kg)

### เหตุผลที่ไม่ใช้ load cell แยกในช่วง prototype

- torque loop **ปิดอยู่ในตัว drive อยู่แล้ว** — ไม่ต้องการ feedback จากภายนอกเพื่อให้ loop ทำงาน
- drive วัด current/torque ของตัวเองได้ ⇒ ได้ค่าที่ใช้ calibrate มาฟรี
- ค่าที่ได้จากการทดลองกับระบบจริงรวมทุกอย่าง (แรงเสียดทาน, mounting, เทปจริง)
  **แม่นกว่าการวัดแยกชิ้น** และป้อนกลับเข้า simulation model ของ Digital Twin ได้ทันที
- ลดของที่ต้องซื้อ + ลดจุดที่ต้องเดินสาย/สอบเทียบในช่วง prototype

---

## 4. Consequences

### เชิงบวก

- tension คงที่ได้เองโดยไม่ต้องรู้ `r(t)` real-time และไม่ต้องมีคนหมุน knob
- ได้ **empirical torque calibration curve** เป็น ground-truth parameter ป้อนเข้า Digital Twin model
- FSM ไม่ต้องอยู่ใน tension loop เลย — สั่งแค่ enable/disable แล้วอ่านสถานะ
  (สัญญาณ `TAKEUP_ENABLE` / `TAKEUP_ALARM` ใน `machine_spec.md` ข้อ 4)
  ⇒ เปลี่ยนฮาร์ดแวร์ในอนาคตได้โดยไม่ต้องแก้ sequence logic

### เชิงลบ / ความเสี่ยงที่รับไว้

- **ไม่มีการวัด tension ที่เส้นเทปโดยตรง** — วัดที่เพลามอเตอร์แทน ⇒ ค่าที่อ่านได้รวมแรงเสียดทาน
  ของระบบส่งกำลังเข้าไปด้วย แยกออกจากกันไม่ได้ (ยอมรับได้ในช่วง prototype
  เพราะเรา calibrate จากพฤติกรรมเทปจริงด้วยตา ไม่ได้ต้องการค่าสัมบูรณ์)
- ถ้าอนาคตต้องการ tension จริงเป็นนิวตัน ต้องกลับมาเพิ่ม load cell
  (ชื่อสัญญาณ `TENSION_FEEDBACK` ถูกกันไว้ใน I/O List แล้ว แต่**แขวนไว้ ยังไม่ implement**)
- **750W ขึ้นไปอาจต้องใช้ไฟ 3-phase 220V** — ถ้า workshop ไม่มี ต้องเปลี่ยน SKU หรือเดินไฟเพิ่ม
- ต้องมี **STO** ตาม `machine_spec.md` ข้อ 6 — เพิ่มต้นทุนวงจร safety ที่เดิมไม่ได้คิดไว้

### สิ่งที่ ADR นี้ไป**เปลี่ยน**ของเดิม

| ของเดิม | เปลี่ยนเป็น |
|---|---|
| `machine_spec.md` ข้อ 5 แถว "วัดแรงตึงเทป" = ต้องเลือก load cell | ไม่ใช้ในช่วง prototype — `bom-cost` **ยังไม่ต้องตั้งรายการ load cell** |
| `machine_spec.md` ข้อ 4 `TENSION_FEEDBACK` (AI) = ต้องต่อ | แขวนไว้ — **`fsm` ยังไม่ต้องผูก guard กับสัญญาณนี้** |

---

## 5. Open Items — ต้องเคลียร์ก่อนสั่งซื้อ/ก่อนถือว่า ADR นี้ปิดสมบูรณ์

1. 🔴 **ยืนยันความหมายของ "torque ประมาณ 2"** — *rated torque ของมอเตอร์ที่จะซื้อ* หรือ
   *torque ที่ต้องใช้งานจริง* · ถ้าเป็นอย่างหลัง มอเตอร์ rated 2.39 N·m จะเหลือ margin น้อยเกินไป
   **และต้องขยับขึ้น class** — เหตุผลข้อ 1 ของการเลือก 750W ตั้งอยู่บนสมมติฐานนี้ทั้งข้อ
2. ยืนยันว่ามี **ไฟ 3-phase 220V** ใน workshop/lab หรือไม่
3. ยืนยันว่ารุ่นที่เลือก **มี STO ในตัว** หรือต้องซื้อ safety module เพิ่ม (ดู `machine_spec.md` ข้อ 6)
4. ยืนยัน **torque command interface** — analog 0–10 V หรือ Modbus
   (สถาปัตยกรรม Extension IO เดิมใช้ Modbus TCP อยู่แล้ว — ถ้าเลือก Modbus ต้องให้ `integration`
   นิยามลง `protocol.md` แทนที่จะเป็นสัญญาณ I/O)
5. 🔴 **ตรวจว่า Delta servo ที่สั่งซื้อไปแล้ว** (`STATUS.md` ประกาศ 2026-08-03 ของ `bom-cost`
   ระบุว่ามี Delta servo drive+motor ในใบสั่งซื้อแล้ว) **เป็นรุ่นเดียวกับที่ ADR นี้เลือกหรือไม่**
   — ถ้าไม่ตรง ต้องกลับมาแก้ ADR นี้ให้ตรงกับของจริง หรือสั่งใหม่
6. วัด `r₀` (รัศมี core) และรัศมีม้วนตอนเต็ม เพื่อประเมินว่า torque setpoint ค่าเดียวพอไหม
7. ทำ empirical torque calibration ตาม
   [`../specs/motion_takeup_tension.md`](../specs/motion_takeup_tension.md)

---

## 6. อ้างอิง

- [`../specs/motion_design_source_mentor.md`](../specs/motion_design_source_mentor.md) §4 — ที่มาของตัวเลขทั้งหมด
- [`../specs/motion_takeup_tension.md`](../specs/motion_takeup_tension.md) — ขั้นตอน calibration
- [`../specs/machine_spec.md`](../specs/machine_spec.md) ข้อ 3 (motion profile), ข้อ 4 (I/O), ข้อ 6 (safety)
