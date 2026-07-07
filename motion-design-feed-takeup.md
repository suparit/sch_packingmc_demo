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

## 2. Feed Motion Design

### 2.1 Concept

```
Feed ON → Drive roller หมุน → Measuring roller encoder นับระยะ → 18.00 mm reached → Feed OFF → Settle
```

### 2.2 ทำไมต้องเป็นระยะ 18 mm

**18 mm ไม่ใช่ตัวเลขที่ Motion Design เป็นคนกำหนด — เป็นค่าที่ถูกกำหนดจากฝั่ง Product/Tape Design**

ตามมาตรฐาน EIA-481 (มาตรฐานอุตสาหกรรมสำหรับ carrier tape บรรจุชิ้นส่วน SMT):
- Sprocket hole pitch มาตรฐานคือ 4.00 mm
- Pocket pitch ต้องเป็น**จำนวนเท่าของ sprocket hole pitch** (เช่น 4, 8, 12, 16, 20, 24, 32 mm) เพื่อให้ตำแหน่ง pocket ตรงกับจังหวะ feeder ทุกครั้ง — ชิ้นส่วนขนาดเล็กมาก (0402, 0201) อาจใช้ pitch ฐาน 2mm หรือ 1mm แทน

**ข้อสังเกต**: 18 mm ไม่ตรงกับค่ามาตรฐานทั่วไปที่มักเจอ (16 หรือ 20 mm) ซึ่งบอกได้ 2 แนวทาง (ต้องยืนยันกับ drawing ของเทปจริง):
1. Carrier tape ของเครื่อง BK05 อาจไม่ใช่ tape มาตรฐานสำหรับป้อนเข้า SMT feeder ทั่วไป (เช่น ใช้กับชิ้นส่วนที่ไม่ใช่ SMD) จึงไม่ถูกผูกกับกฎ 4mm-multiple
2. หรือ 18 mm ถูกกำหนดจากขนาดจริงของชิ้นส่วน + ระยะห่างขั้นต่ำระหว่าง pocket ที่ product engineer เป็นคนกำหนด

**หลักการสำหรับ Motion Design**: ไม่ว่าที่มาของ 18 mm จะเป็นข้อไหน มันคือ**ค่าคงที่จากภายนอกที่ระบบต้อง achieve ให้แม่นยำและ repeatable ทุกรอบ** — นี่คือเหตุผลที่แท้จริงว่าทำไมต้องใช้ Position Control + Encoder Feedback แทนการนับ pulse หรือคุมเวลา เพราะเป้าหมายคือการ "ตี target ที่ fix มาแล้วให้แม่น" ไม่ใช่การเลือกค่า target เอง

### 2.3 เหตุผลที่ต้องเป็น Position + Encoder (ไม่ใช่ Time-based หรือ Speed-only)

- **Time-based**: ผิดสะสมทันทีถ้ามี slip, โหลดเปลี่ยน, แรงเสียดทานเปลี่ยนตามสภาพแวดล้อม
- **Speed-only**: ไม่รู้ตำแหน่งจริง ต้อง "เดา" เวลาหยุด
- **Position + Encoder feedback**: ปิด loop จริงที่ตำแหน่งเทป ไม่สนใจ slip หรือโหลดเปลี่ยน เพราะอ้างอิงจากการเคลื่อนที่จริง

**หลักการ**: อย่า trust actuator (มอเตอร์) ว่าเท่ากับผลลัพธ์ของ process (ตำแหน่งเทปจริง) — ต้องวัดที่ process โดยตรง

### 2.4 Hardware ที่เลือกใช้

| ส่วนประกอบ | รุ่น | หน้าที่ |
|---|---|---|
| Stepper Driver | MISUMI [E-EDR57A](https://th.misumi-ec.com/en/vona2/detail/110310618659/?HissuCode=E-EDR57A) | ขับ closed-loop stepper motor |
| Stepper Motor | MISUMI [E-57ESTM02](https://th.misumi-ec.com/en/vona2/detail/110310618659/?HissuCode=E-57ESTM02) | Closed-loop stepper, holding torque 1.2/2 N·m |
| Measuring Roller Encoder | Omron [E6A2-CWZ5C 500P/R](https://th.misumi-ec.com/en/vona2/detail/221005138844/?HissuCode=E6A2-CWZ5C%20500P%2FR%200.5M) | วัดตำแหน่งจริงของเทป (ground truth) |

### 2.5 สถาปัตยกรรม Feedback สองชั้น

| Encoder | ตำแหน่งติดตั้ง | ตรวจจับ |
|---|---|---|
| Encoder ในตัว Closed-loop stepper | เพลามอเตอร์ | มอเตอร์ stall/step-loss หรือไม่ |
| Omron E6A2 (แยกอิสระ) | Measuring Roller | ตำแหน่งเทปจริง (mm) — ground truth |

Encoder ที่เพลามอเตอร์ป้องกัน **stepper stall** แต่ไม่ป้องกัน **slip ระหว่าง roller กับเทป** — จึงต้องมี encoder แยกที่ Measuring Roller เป็นตัวตัดสินตำแหน่งจริงเสมอ

### 2.6 การตรวจสอบ Resolution และ Speed

```
mm ต่อ 1 count = เส้นรอบวง roller (πD) / 2000   (quadrature ×4, 500 P/R)

ตัวอย่าง D = 30 mm → 0.047 mm/count → 18 mm ≈ 383 count (resolution เกินพอ)

RPM สูงสุดที่ encoder ตอบสนองได้ (electrical response 30 kHz):
RPM_max ≈ (30,000 × 60) / 500 ≈ 3,600 RPM   (เกินความต้องการจริงมาก)
```

### 2.7 ข้อควรระวังในการติดตั้ง

1. Output เป็น NPN open collector 12–24 VDC → ต้องมี pull-up + level shifting ให้ตรงกับ logic level ของ STM32 Extension IO
2. Allowable shaft load: Radial 10 N / Thrust 5 N → ต้องต่อผ่าน **flexible coupling** ไม่ใช่ rigid mount
3. IP50 เท่านั้น (ไม่กันน้ำ/น้ำมัน) → ต้องมี enclosure เพิ่มถ้าใกล้จุดที่มีไอน้ำมัน/ฝุ่น

---

## 3. Take-up Reel Design

### 3.1 ทำไมห้ามใช้ Position หรือ Speed Control

```
Diameter ม้วนเทปเพิ่มขึ้น
        ↓
RPM คงที่ → Linear speed เพิ่มขึ้น (v = ωr)
        ↓
Tension เพิ่มขึ้นแบบไม่เป็นเชิงเส้น
        ↓
เทปยับ / ฉีกขาด / ดึง component หลุดจาก pocket
```

### 3.2 หลักการ Torque Control

```
Torque ที่ต้องการ = F_tension × r(t)
```

เมื่อคุมที่ Torque (ไม่ใช่ RPM) — ถ้า r โตขึ้น servo drive จะลด RPM ลงเองโดยอัตโนมัติเพื่อรักษา Torque setpoint คงที่ ⇒ Tension คงที่เสมอ **โดยไม่ต้องรู้ค่า r(t) แบบ real-time**

### 3.3 การ estimate diameter (ถ้าต้องการ compensation ละเอียดขึ้น)

```
r(t) = √( r₀² + (thickness / π) × L(t) )
```

- `r₀` = รัศมี core เริ่มต้น
- `thickness` = ความหนาเทปต่อชั้น
- `L(t)` = ความยาวเทปสะสมที่พันแล้ว (คำนวณได้ฟรีจาก Feed encoder ที่มีอยู่แล้ว)

### 3.4 Hardware ที่เลือกใช้ (ตามที่พี่เลี้ยงแนะนำ)

Delta AC Servo System — [ASD-A2 & ASD-B2 Online Basic Training](https://www.youtube.com/watch?v=EvdSDoPgeOE)

- True closed-loop AC servo (DSP-based current control ผ่าน IGBT ขับ PMSM motor)
- รองรับการสลับโหมด Position / Speed / **Torque Control Mode** พร้อม torque limit, speed limit ในตัว
- Servo drive จับคู่กับ ECMA series motor ได้หลายขนาดกำลัง (100 W – 3000 W)

**A2 vs B2**: ทั้งคู่เป็น DSP-based PMSM servo คล้ายกัน — A2 เป็นรุ่น high-end (communication protocol เพิ่ม เช่น CANopen/DMCNET, tuning ละเอียดกว่า) ส่วน B2 เป็นรุ่น general purpose/economical เหมาะกับ use case single-axis อย่าง Take-up Reel ที่ไม่ต้อง sync กับแกนอื่นแบบ real-time network

### 3.5 สิ่งที่ต้องเช็คก่อนเลือกรุ่นจริง

1. **STO (Safe Torque Off)** — built-in หรือต้องเพิ่ม safety module (ดู Safety Analysis)
2. **Torque command interface** — analog (0–10 V) หรือผ่าน communication (Modbus) ให้ตรงกับสถาปัตยกรรม Extension IO ที่ใช้ Modbus TCP อยู่แล้ว
3. **Power rating (100 W – 3000 W)** — คำนวณจาก `Torque = F_tension × r_max` แล้วแปลงเป็น `Power = Torque × ω_max`

> **รอข้อมูล**: แรงตึงเทปเป้าหมาย (N) และเส้นผ่านศูนย์กลาง core/max ของม้วนเทป เพื่อคำนวณ sizing แบบเต็มรูปแบบ

---

## 4. Motion Architecture

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

## 5. Safety Analysis Framework

Take-up Reel อยู่ใกล้ operator — ต้องมี:

- **STO (Safe Torque Off)** — ตัด torque ทันทีเมื่อ guard เปิด/E-stop กด (ISO 13849-1, Cat 3 PLd)
- **SLS (Safely Limited Speed)** — จำกัดความเร็วสูงสุดขณะ guard เปิดสำหรับ jog/maintenance
- **Safe Torque Limit** — จำกัด torque สูงสุดที่จุด nip point

ต้องทำ risk assessment ตาม ISO 12100 และอ้างอิง ISO 13857 (safety distance) + ISO 13849-1 (PL rating) เพื่อกำหนดค่า Safety Speed/Torque จริง — **Normal operating torque ต้องต่ำกว่า Safety Torque limit เสมอ พร้อม margin**

---

## 6. Motion Philosophy: Prototype → Production

| ด้าน | Prototype | Production |
|---|---|---|
| Feed | Closed-loop stepper + measuring roller encoder | (คงเดิม หรืออัพเป็น servo position mode ถ้าต้องการความเร็ว/แม่นยำสูงขึ้น) |
| Take-up | AC gear motor + slip clutch (concept เดิม) | **Delta ASDA-A2/B2 Torque Control Mode** (ตัดสินใจแล้ว) |
| เหตุผล | Validate sequence, cost ต่ำ | เมื่อ sequence นิ่งแล้ว ลงทุนใน precision hardware ที่จุดเสี่ยงเสียหายมากที่สุด |

**หลักการ migration**: FSM คุยกับ motion ผ่าน event ("position reached", "tension status") ไม่ใช่ raw I/O — เปลี่ยน hardware โดยไม่ต้อง redesign sequence logic

---

## 7. Open Action Items

- [ ] ยืนยันแรงตึงเทปเป้าหมาย (N) จาก spec ผู้ผลิต carrier tape หรือมาตรฐานโรงงาน
- [ ] วัดเส้นผ่านศูนย์กลาง core และเส้นผ่านศูนย์กลางสูงสุดของม้วนเทปเต็ม
- [ ] คำนวณ Torque/Power sizing เพื่อเลือกรุ่น ECMA motor คู่กับ ASDA-B2/A2
- [ ] ยืนยัน STO/safety module ของรุ่น servo ที่เลือก
- [ ] ยืนยัน torque command interface (analog vs Modbus) ให้ตรงกับสถาปัตยกรรม Extension IO เดิม
- [ ] ทำ risk assessment ตาม ISO 12100 สำหรับจุด nip point ของ Take-up Reel
- [ ] คำนวณ holding torque / torque-speed curve ของ closed-loop stepper เทียบกับ load จริงของ Feed roller
