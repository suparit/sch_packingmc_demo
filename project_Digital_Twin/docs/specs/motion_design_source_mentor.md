# Taping Machine Digital Twin Framework — Motion Design

## Feed Motor & Take-up Reel Engineering Summary

> เอกสารนี้สรุปการออกแบบระบบ Motion Control สำหรับ Taping Machine Digital Twin Framework
> โดยเน้น **เหตุผลเชิงวิศวกรรม (why)** มากกว่าแค่การเลือกอุปกรณ์ (what)

---

## 1. Reframing the Problem

คำถามเริ่มต้น: *"ควรใช้มอเตอร์ตัวไหน?"*
คำถามที่ถูกต้อง: *"ระบบต้องการพฤติกรรมแบบไหน แล้วมอเตอร์/control mode ไหนตอบโจทย์นั้น"*

| | มุมมองนักศึกษา | มุมมองวิศวกร |
|---|---|---|
| จุดเริ่มต้น | หาสเปคมอเตอร์ | วิเคราะห์ physics ของระบบก่อน |
| ผลลัพธ์ | เลือกของ | ออกแบบระบบ + เลือกของเป็นผลสรุป |

**หลักการสำคัญ**: Feed Motor และ Take-up Reel ต้องใช้ control philosophy คนละแบบ เพราะตัวแปรที่ต้องควบคุมต่างกันโดยพื้นฐาน

| | Feed Motor | Take-up Reel |
|---|---|---|
| ตัวแปรที่ควบคุม | **ตำแหน่ง (Position)** | **แรงตึง (Tension)** |
| Control mode | Position loop, encoder feedback | Torque control mode |
| พฤติกรรม | Move → Stop → Move (discrete) | Continuous, ต้องชดเชยเมื่อ diameter เปลี่ยน |

---

## 2. Product Being Packaged

ชิ้นงานที่ carrier tape ต้องบรรจุคือ **อุปกรณ์อิเล็กทรอนิก Noise Filter**:

> 🔴 **ชื่อยี่ห้อ/รุ่นของชิ้นงานถูกตัดออกจากไฟล์นี้โดยตั้งใจ (2026-08-05)** ตามกติกา กติกาเนื้อหาของ repo
> เอกสารต้นทางนอก repo ระบุรุ่นไว้ **ห้ามคัดกลับเข้ามา** — ตัวเลขสเปกด้านล่างเก็บครบตามต้นฉบับ

| พารามิเตอร์ | ค่า |
|---|---|
| น้ำหนัก | 4 g/ชิ้น |
| ขนาด (L×W×H) | 20 × 15 × 10 mm |
| จำนวนต่อ carrier | 225 ชิ้น |
| น้ำหนักรวม/carrier | 225 × 4g ≈ **0.9 kg** |
| ความยาวเทป/carrier | 225 × 18mm ≈ **4.05 m** |

---

## 3. Feed Motion Design

### 3.1 Concept

```
Feed ON → Drive roller หมุน → Measuring roller encoder นับระยะ → 18.00 mm reached → Feed OFF → Settle
```

### 3.2 ทำไมต้องเป็นระยะ 18 mm

**18 mm ไม่ใช่ตัวเลขที่ Motion Design เป็นคนกำหนด — เป็นค่าที่ถูกกำหนดจากฝั่ง Product/Tape Design**

ตามมาตรฐาน EIA-481 (มาตรฐานอุตสาหกรรมสำหรับ carrier tape บรรจุชิ้นส่วน SMT):
- Sprocket hole pitch มาตรฐานคือ 4.00 mm
- Pocket pitch ต้องเป็น**จำนวนเท่าของ sprocket hole pitch** (เช่น 4, 8, 12, 16, 20, 24, 32 mm) เพื่อให้ตำแหน่ง pocket ตรงกับจังหวะ feeder ทุกครั้ง — ชิ้นส่วนขนาดเล็กมาก (0402, 0201) อาจใช้ pitch ฐาน 2mm หรือ 1mm แทน

**18 mm ไม่ตรงกับค่ามาตรฐานทั่วไป (16 หรือ 20 mm)** — เมื่อเทียบกับสเปคชิ้นงานจริง (Section 2) พบว่า:

```
ชิ้นงานกว้าง (W) = 15 mm
Pocket Pitch      = 18 mm
ส่วนต่าง          = 3 mm  →  เผื่อ clearance ข้างละ 1.5 mm
```

**สรุป**: 18 mm = ขนาดจริงของชิ้นงาน (ด้าน 15mm ที่วางตามแนวเทป) + ระยะเผื่อผนัง pocket ข้างละ 1.5mm — แปลว่า tape นี้เป็น carrier tape เฉพาะทางสำหรับชิ้นงานนี้ ไม่ได้ผูกกับกฎ EIA-481 sprocket-multiple โดยตรง

**หลักการสำหรับ Motion Design**: ไม่ว่าที่มาของ 18 mm จะเป็นแบบไหน มันคือ**ค่าคงที่จากภายนอกที่ระบบต้อง achieve ให้แม่นยำและ repeatable ทุกรอบ** — นี่คือเหตุผลที่แท้จริงว่าทำไมต้องใช้ Position Control + Encoder Feedback แทนการนับ pulse หรือคุมเวลา เพราะเป้าหมายคือการ "ตี target ที่ fix มาแล้วให้แม่น" ไม่ใช่การเลือกค่า target เอง

### 3.3 เหตุผลที่ต้องเป็น Position + Encoder (ไม่ใช่ Time-based หรือ Speed-only)

- **Time-based**: ผิดสะสมทันทีถ้ามี slip, โหลดเปลี่ยน, แรงเสียดทานเปลี่ยนตามสภาพแวดล้อม
- **Speed-only**: ไม่รู้ตำแหน่งจริง ต้อง "เดา" เวลาหยุด
- **Position + Encoder feedback**: ปิด loop จริงที่ตำแหน่งเทป ไม่สนใจ slip หรือโหลดเปลี่ยน เพราะอ้างอิงจากการเคลื่อนที่จริง

**หลักการ**: อย่า trust actuator (มอเตอร์) ว่าเท่ากับผลลัพธ์ของ process (ตำแหน่งเทปจริง) — ต้องวัดที่ process โดยตรง

### 3.4 Hardware ที่เลือกใช้

| ส่วนประกอบ | รุ่น | หน้าที่ |
|---|---|---|
| Stepper Driver | MISUMI [E-EDR57A](https://th.misumi-ec.com/en/vona2/detail/110310618659/?HissuCode=E-EDR57A) | ขับ closed-loop stepper motor |
| Stepper Motor | MISUMI [E-57ESTM02](https://th.misumi-ec.com/en/vona2/detail/110310618659/?HissuCode=E-57ESTM02) | Closed-loop stepper, holding torque 1.2/2 N·m |
| Measuring Roller Encoder | Omron [E6A2-CWZ5C 500P/R](https://th.misumi-ec.com/en/vona2/detail/221005138844/?HissuCode=E6A2-CWZ5C%20500P%2FR%200.5M) | วัดตำแหน่งจริงของเทป (ground truth) |

### 3.5 สถาปัตยกรรม Feedback สองชั้น

| Encoder | ตำแหน่งติดตั้ง | ตรวจจับ |
|---|---|---|
| Encoder ในตัว Closed-loop stepper | เพลามอเตอร์ | มอเตอร์ stall/step-loss หรือไม่ |
| Omron E6A2 (แยกอิสระ) | Measuring Roller | ตำแหน่งเทปจริง (mm) — ground truth |

Encoder ที่เพลามอเตอร์ป้องกัน **stepper stall** แต่ไม่ป้องกัน **slip ระหว่าง roller กับเทป** — จึงต้องมี encoder แยกที่ Measuring Roller เป็นตัวตัดสินตำแหน่งจริงเสมอ

### 3.6 การตรวจสอบ Resolution และ Speed

```
mm ต่อ 1 count = เส้นรอบวง roller (πD) / 2000   (quadrature ×4, 500 P/R)

ตัวอย่าง D = 30 mm → 0.047 mm/count → 18 mm ≈ 383 count (resolution เกินพอ)

RPM สูงสุดที่ encoder ตอบสนองได้ (electrical response 30 kHz):
RPM_max ≈ (30,000 × 60) / 500 ≈ 3,600 RPM   (เกินความต้องการจริงมาก)
```

### 3.7 ข้อควรระวังในการติดตั้ง

1. Output เป็น NPN open collector 12–24 VDC → ต้องมี pull-up + level shifting ให้ตรงกับ logic level ของ STM32 Extension IO
2. Allowable shaft load: Radial 10 N / Thrust 5 N → ต้องต่อผ่าน **flexible coupling** ไม่ใช่ rigid mount
3. IP50 เท่านั้น (ไม่กันน้ำ/น้ำมัน) → ต้องมี enclosure เพิ่มถ้าใกล้จุดที่มีไอน้ำมัน/ฝุ่น

---

## 4. Take-up Reel Design

### 4.1 ทำไมห้ามใช้ Position หรือ Speed Control

```
Diameter ม้วนเทปเพิ่มขึ้น
        ↓
RPM คงที่ → Linear speed เพิ่มขึ้น (v = ωr)
        ↓
Tension เพิ่มขึ้นแบบไม่เป็นเชิงเส้น
        ↓
เทปยับ / ฉีกขาด / ดึง component หลุดจาก pocket
```

### 4.2 หลักการ Torque Control

```
Torque ที่ต้องการ = F_tension × r(t)
```

เมื่อคุมที่ Torque (ไม่ใช่ RPM) — ถ้า r โตขึ้น servo drive จะลด RPM ลงเองโดยอัตโนมัติเพื่อรักษา Torque setpoint คงที่ ⇒ Tension คงที่เสมอ **โดยไม่ต้องรู้ค่า r(t) แบบ real-time**

### 4.3 การ estimate diameter (ถ้าต้องการ compensation ละเอียดขึ้น)

```
r(t) = √( r₀² + (thickness / π) × L(t) )
```

- `r₀` = รัศมี core เริ่มต้น
- `thickness` = ความหนาเทปต่อชั้น
- `L(t)` = ความยาวเทปสะสมที่พันแล้ว (คำนวณได้ฟรีจาก Feed encoder ที่มีอยู่แล้ว)

### 4.4 Legacy Motor Analysis (เครื่องเดิม)

มอเตอร์เดิมของเครื่องอ้างอิงจากเครื่องเดิม : **DKM 6IDGF-6G + Gearhead 6GD20M**

| พารามิเตอร์ | ค่า |
|---|---|
| Power | 6 W |
| Voltage / Freq | 220 VAC / 50 Hz |
| Speed (no-load) | ~1250 rpm |
| Gear ratio | 20:1 |
| ปรับความเร็ว | Manual knob |

**Torque ที่เพลามอเตอร์ (ก่อนเกียร์):**
```
ω = 1250 rpm × 2π/60 = 130.9 rad/s
T_motor = P / ω = 6W / 130.9 ≈ 0.046 N·m
```

**Torque หลังผ่านเกียร์ 20:1 (สมมติ efficiency ~70%):**
```
T_output = 0.046 × 20 × 0.7 ≈ 0.64 N·m   ที่ ~62.5 rpm
```

**ข้อสรุป**: Power 6W ดูน้อยมาก แต่หลังผ่านเกียร์ทดรอบแล้ว torque ที่ได้ (~0.6-0.9 N·m) **ใกล้เคียงกับ target ที่ต้องการจริง** (ไม่ใช่ต่างกัน 100 เท่าอย่างที่ดูจาก wattage เปล่าๆ) เพราะ `Torque × Speed = Power` คงที่ — มอเตอร์แลกความเร็วสูงที่ไม่มีประโยชน์ ไปเป็น torque ผ่านเกียร์

**ปัญหาจริงของเครื่องเดิมไม่ใช่เรื่อง torque แต่คือ:**

1. **AC Induction Motor เป็น constant-speed device โดยธรรมชาติ** — ไม่มี torque control loop ทางไฟฟ้า
2. **Manual knob = ปรับ Voltage ผ่าน Variac/Triac dimmer** ไม่ใช่ vector control จริง — ลด V เพื่อลด speed แต่ Torque ก็ลดตาม (T ∝ V²)
3. **Operator คือ control loop จริงของระบบ** — คนมองม้วนเทปโตขึ้นแล้วหมุน knob ชดเชยเอง ไม่ใช่วงจรอิเล็กทรอนิกส์

**ปัญหาของวิธี manual knob:**

| ปัญหา | ผลกระทบ |
|---|---|
| ขึ้นกับทักษะ/ความใส่ใจของ operator | ผลลัพธ์ไม่ consistent ระหว่างกะ/คน |
| Voltage ลด → Torque ลดตาม (T∝V²) | ตอนม้วนโต (ต้องการ torque **มากขึ้น**) operator มักลด V เพื่อลด speed → torque กลับ**ลดสวนทาง**กับที่ต้องการ |
| ไม่มี record/ไม่ repeatable | ขัดกับเป้าหมาย Digital Twin — tacit knowledge ของ operator แปลงเป็น digital model ไม่ได้ |
| ต้องมีคนอยู่หน้าเครื่องตลอด | ขัดกับเป้าหมาย automation |

**สรุปเชิงวิศวกรรม**: เครื่องเดิมไม่ได้ไม่มี tension control — มันมี แต่ implement ด้วยคนแทนวงจร การเปลี่ยนไปใช้ Torque Control Mode ของ servo คือการ **digitize สิ่งที่ operator ทำอยู่แล้วด้วยมือ** ให้เป็นระบบอัตโนมัติที่แม่นยำและ repeatable — ตรงกับ concept ของ Digital Twin Framework

### 4.5 Hardware เป้าหมายใหม่: Motor + Controller (ไม่ใช้ Manual Knob)

Delta AC Servo System — [ASD-A2 & ASD-B2 Online Basic Training](https://www.youtube.com/watch?v=EvdSDoPgeOE)

- True closed-loop AC servo (DSP-based current control ผ่าน IGBT ขับ PMSM motor)
- รองรับการสลับโหมด Position / Speed / **Torque Control Mode** พร้อม torque limit, speed limit ในตัว
- Servo drive จับคู่กับ ECMA series motor ได้หลายขนาดกำลัง (100 W – 3000 W)

**A2 vs B2**: ทั้งคู่เป็น DSP-based PMSM servo คล้ายกัน — A2 เป็นรุ่น high-end (communication protocol เพิ่ม เช่น CANopen/DMCNET, tuning ละเอียดกว่า) ส่วน B2 เป็นรุ่น general purpose/economical เหมาะกับ use case single-axis อย่าง Take-up Reel ที่ไม่ต้อง sync กับแกนอื่นแบบ real-time network

**ตาราง Rated Torque ของ ECMA-C Series (low inertia, 3000rpm):**

| Motor Power | Rated Torque (N·m) | Max Torque (N·m) | Drive รุ่น |
|---|---|---|---|
| 100W | 0.32 | 0.96 | ASD-A2/B2-0121 |
| 200W | 0.64 | 1.92 | ASD-A2/B2-0221 |
| 400W | 1.27 | 3.82 | ASD-A2/B2-0421 |
| **750W** | **2.39** | ~7.16 | **ASD-A2/B2-0721** |
| 1000W | 3.18 | ~9.55 | ASD-A2/B2-1021 |
| 1500W | 4.77 | ~14.3 | ASD-A2/B2-1521 |

**คำแนะนำ**: เริ่มที่ **750W (ASD-B2-0721 + ECMA-C10807, Rated Torque 2.39 N·m)**

เหตุผล:
1. ตรงกับตัวเลข "torque ประมาณ 2" ที่พี่เลี้ยงระบุไว้พอดี
2. มี dynamic range กว้าง (0 → 7.16 N·m momentary) เพียงพอสำหรับการทดลองหาค่า F_tension จริงโดยไม่กลัวโหลดเกินขีดความสามารถ
3. ไม่โอเวอร์ไซส์เกินจำเป็นเทียบกับ class ที่สูงกว่า (1.5-2kW แพงกว่ามากและใหญ่เกินความจำเป็นสำหรับงานเทปบางเบา)

> **หมายเหตุ**: 750W ขึ้นไปมักต้องเช็คว่าใช้ไฟ single-phase หรือ three-phase 220V — ต้องยืนยันว่า workshop/lab มีไฟ 3-phase รองรับหรือไม่ ก่อนสั่งซื้อ

### 4.6 Empirical Torque Calibration Procedure

เพราะ F_tension ยังไม่สามารถวัดได้แน่ชัด (ยังอยู่ระหว่างสร้างตัวทดลอง) — ใช้ servo drive เป็นเครื่องมือวัดในตัว แทนการต้องมี load cell แยก:

```
1. ตั้งค่า Torque Limit (parameter P1-02 หรือเทียบเท่า) ไว้ต่ำๆ ก่อน เพื่อความปลอดภัยตอนทดลอง
2. สั่ง Torque command เริ่มจากค่าน้อย (เช่น 5-10% ของ rated)
3. ค่อยๆ เพิ่มทีละนิด พร้อมสังเกตพฤติกรรมเทปด้วยตา:
   - เทปหย่อน/ตก = torque ยังน้อยไป → เพิ่ม
   - เทปตึงจน pocket บิด/component เคลื่อน = torque มากไป → ลด
4. เมื่อเจอจุดที่ "ตึงพอดี" — อ่านค่า Torque/Current ที่แสดงบนหน้าจอ drive
   (หรือผ่าน ASDA-Soft, หรือ Modbus register จาก Rust layer โดยตรง)
5. ทำซ้ำที่ diameter ต่างๆ กัน (core, กลาง, เต็มม้วน) เพื่อดูว่า
   torque setpoint คงที่ค่าเดียวพอไหม หรือช่วงต้น/ปลายต้องขยับ
```

**ข้อดี**: ค่าที่ได้คือ empirical calibration curve จากระบบจริงทั้งหมด (แรงเสียดทาน, mounting, tape จริง) แม่นยำกว่าการวัดแยกชิ้นด้วยตาชั่ง — และบันทึกไว้เป็น ground-truth parameter ป้อนกลับเข้า Digital Twin simulation model ได้ทันที

**ข้อควรระวังระหว่างทดลอง**:
- ตั้ง Torque Limit ไว้ต่ำกว่าค่าที่คำนวณว่าปลอดภัยเสมอ — อย่าปล่อยให้ drive วิ่งที่ max torque โดยไม่ได้ตั้งใจ
- มี E-stop/STO เข้าถึงง่ายตลอดการทดลอง
- บันทึกค่า Torque ที่ใช้ได้จริงทุกครั้งที่ทดลอง

### 4.7 สิ่งที่ต้องเช็คก่อนเลือกรุ่นจริง

1. **STO (Safe Torque Off)** — built-in หรือต้องเพิ่ม safety module (ดู Section 6)
2. **Torque command interface** — analog (0–10 V) หรือผ่าน communication (Modbus) ให้ตรงกับสถาปัตยกรรม Extension IO ที่ใช้ Modbus TCP อยู่แล้ว
3. **ยืนยันกับพี่เลี้ยง**: "Torque ประมาณ 2" หมายถึง rated torque ของมอเตอร์ที่จะสั่งซื้อ หรือค่า torque ที่คำนวณว่าต้องใช้งานจริง (นำไปสู่ class มอเตอร์ต่างกัน)

---

## 5. Motion Architecture

```
                     Python System FSM
                    (sequencer, decision logic)
                     /                      \
        move cmd + encoder fbk       enable / tension status
                   /                          \
        Feed axis                        Take-up axis
   (position control,                (torque control,
    encoder loop)                     dancer feedback)
                   \                          /
                    \                        /
                       Safety layer
                  (STO, SLS, safe torque limit)
```

- FSM สั่ง Feed axis แบบ discrete (move → wait confirm)
- Take-up axis วิ่ง torque loop อัตโนมัติในตัว servo drive เอง — FSM แค่ enable/disable และอ่านสถานะ (tension ok / alarm)
- **Safety layer แยกอิสระจาก application logic** — STO ต้องตัด torque ได้โดยไม่ผ่าน FSM (hardwired หรือ safety-rated fieldbus)
- **Dancer arm** เป็นตัวเชื่อมระหว่าง motion domain สองแบบ (Feed แบบ discrete step กับ Take-up แบบ continuous winding) ไม่ให้ชนกัน

---

## 6. Safety Analysis Framework

Take-up Reel อยู่ใกล้ operator — ต้องมี:

- **STO (Safe Torque Off)** — ตัด torque ทันทีเมื่อ guard เปิด/E-stop กด (ISO 13849-1, Cat 3 PLd)
- **SLS (Safely Limited Speed)** — จำกัดความเร็วสูงสุดขณะ guard เปิดสำหรับ jog/maintenance
- **Safe Torque Limit** — จำกัด torque สูงสุดที่จุด nip point

ต้องทำ risk assessment ตาม ISO 12100 และอ้างอิง ISO 13857 (safety distance) + ISO 13849-1 (PL rating) เพื่อกำหนดค่า Safety Speed/Torque จริง — **Normal operating torque ต้องต่ำกว่า Safety Torque limit เสมอ พร้อม margin**

---

## 7. Motion Philosophy: Prototype → Production

| ด้าน | Prototype | Production |
|---|---|---|
| Feed | Closed-loop stepper + measuring roller encoder | (คงเดิม หรืออัพเป็น servo position mode ถ้าต้องการความเร็ว/แม่นยำสูงขึ้น) |
| Take-up | Manual AC motor + knob (legacy) | **Delta ASDA-A2/B2 Torque Control Mode 750W** (ตัดสินใจแล้ว) |
| เหตุผล | Validate sequence, cost ต่ำ | Digitize สิ่งที่ operator ทำด้วยมือ ให้ repeatable/automated |

**หลักการ migration**: FSM คุยกับ motion ผ่าน event ("position reached", "tension status") ไม่ใช่ raw I/O — เปลี่ยน hardware โดยไม่ต้อง redesign sequence logic

---

