# web_next — เว็บ Digital Twin เวอร์ชันทดสอบ (preview)

เว็บตัวใหม่ แยกจาก `cad/index1.html` เดิม **ไม่แตะของเดิมเลย** — Next.js 16 (App Router) + React 19 + Tailwind CSS 4 +
Three.js ผ่าน `@react-three/fiber` / `@react-three/drei` · โมเดลคือ `cad/export/Machine.glb` ตัวจริง

| หน้า | ทำอะไร |
|---|---|
| `/` | หน้าแนะนำแบบเลื่อนเล่าเรื่อง — โมเดล 3D ค้างอยู่หลังเนื้อหา เลื่อนแล้ว **โฮโลแกรม → โมเดลจริง → แยกชิ้นส่วน Taping Machine → carrier tape (ภาพ 3D ประกอบ) → HMI (กรอบจอลอย 3D เลื่อนแล้วสลับ 4 หน้าจอหน้าเครื่อง) → Digital Twin** จบที่ปุ่มเข้าหน้าทดสอบ |
| `/twin` | หน้าทดสอบ — ปุ่มควบคุม (E-STOP / START / STOP / RESET / MODE / NEXT / PASS / NG / SPEED) + การ์ด telemetry + โมเดลลากหมุนได้ + ปุ่มแยกชิ้น / โฮโลแกรม |
| `/analytics` | วิเคราะห์การผลิต (ยกจาก `cad/analytics.html`) — KPI เวลาต่อรอบ · กราฟเวลาเฉลี่ยต่อสเต็ป (เกณฑ์ friction 1.35 s) · กราฟเวลารวมต่อรอบ · 10 แถวล่าสุด · Sync + รีเฟรชอัตโนมัติ 3 วิ · LIVE อ่านฐานข้อมูล gateway (`GET_HISTORY`) / DEMO อ่านประวัติตัวจำลอง |
| `/models/<ไฟล์>.glb` | route เสิร์ฟ `.glb` จาก `cad/export/` ตรง ๆ (ไม่ก๊อป 26 MB มาซ้ำ · กัน `../`) |

## รัน

**ง่ายสุด — ดับเบิลคลิก `START_WEB.bat`** (ในโฟลเดอร์นี้)

| เลือก | ได้อะไร |
|---|---|
| `1` (ค่าตั้งต้น ถ้าไม่กดอะไรใน 8 วิ) | เปิดเว็บอย่างเดียว — หน้า `/twin` ใช้ตัวจำลองในเบราว์เซอร์ (DEMO) |
| `2` | เปิดเว็บ + `python_backend/gateway_fsm.py` (gateway จำลอง **ไม่ต่อบอร์ด**) — หน้า `/twin` เป็น LIVE |

สคริปต์ติดตั้งแพ็กเกจเองครั้งแรก, ถ้าพอร์ต 5173 / 8765 มีตัวเปิดอยู่แล้วจะใช้ตัวเดิม, รอจนหน้าเว็บตอบแล้วเปิดเบราว์เซอร์ให้
เปิดตรงหน้าทดสอบ: `START_WEB.bat 1 twin` · ปิด: ดับเบิลคลิก `STOP_WEB.bat` (หรือปิดหน้าต่าง `DT-web-next` · `stop_all.bat` ที่ root ก็ปิดให้ เพราะชื่อหน้าต่างขึ้นต้น `DT-`)

**แบบพิมพ์คำสั่งเอง**

```bash
cd web_next
npm install     # ครั้งแรกครั้งเดียว
npm run dev     # เปิด http://localhost:5173  (เครื่องอื่นในวงเดียวกัน: http://<IP เครื่องนี้>:5173)
```

เปิด gateway ไว้ด้วย (`python_backend/gateway_fsm.py`) หน้า `/twin` จะขึ้น **LIVE · gateway** และปุ่มจะส่งเข้า gateway จริง
ไม่มี gateway → **DEMO · ตัวจำลอง** (ป้ายเหลือง) ปุ่มสั่งตัวจำลองในเบราว์เซอร์ `lib/demoMachine.js` แทน

| พารามิเตอร์ URL (หน้า `/twin`) | ผล |
|---|---|
| `?ws=ws://192.168.x.x:8765` | ต่อ gateway เครื่องอื่น (ค่าตั้งต้น = host เดียวกับหน้าเว็บ พอร์ต 8765) |
| `?demo=0` | ปิดตัวจำลอง — ไม่มี gateway = OFFLINE ปุ่มกดไม่ได้ |

## ⚠️ ปุ่มบน `/twin` สั่งเครื่องได้จริง

- โหมด LIVE ปุ่มส่ง action ตาม `docs/specs/protocol.md` ข้อ 4 / 8 เข้า gateway ตัวเดียวกับจอ HMI
- ถ้า gateway รันด้วย `RUST_BRIDGE=1` และ `feed_src == "REAL"` หน้าเว็บขึ้นแถบแดงเตือนว่าปุ่มขับมอเตอร์ / โซลินอยด์จริง
- กติกาปุ่มตามสัญญา: NEXT ใช้ได้เฉพาะโหมด step + `step_wait` (ข้อ 8.5) · สลับเข้า/ออก step ต้อง STOP ก่อน (ข้อ 8.3) ·
  PASS/NG กดได้เฉพาะ checkpoint + `step_allowed` (fsm_spec 6.3) · ACK ที่ถูกปฏิเสธแสดงเหตุผลเป็นภาษาไทย
- E-STOP กดได้ตลอด (ยกเว้นยังไม่ได้เชื่อมต่อ)

## ไฟล์

| ไฟล์ | หน้าที่ |
|---|---|
| `lib/twin.js` | ชื่อ state / checkpoint / ความหมายบิต / ตัวเลขเครื่อง / 7 ชิ้นส่วนใน GLB + ทิศแยกชิ้น — **แก้ที่นี่ที่เดียวถ้าสัญญาเปลี่ยน** |
| `lib/useTwinLink.js` | WebSocket + reconnect + สลับ LIVE/DEMO + `send()` + ACK + ประวัติกราฟ |
| `lib/demoMachine.js` | ตัวจำลอง FSM ในเบราว์เซอร์ (ทำตามกติกา gateway: VISION รอทุกโหมด, semi รอ 5 checkpoint, step รอ NEXT, ESTOP/RESET 2 กิ่ง) · อุณหภูมิอยู่ในช่วง 189–191 · เป้า 200 ชิ้นเป็นตัวเลขสมมติ |
| `components/three/MachineModel.jsx` | โหลด GLB, ย่อให้พอดี, เปลือกโฮโลแกรม (shader fresnel), แยกชิ้น, โฟกัส, หมุนลูกกลิ้ง / กดหัวซีลตาม state, ป้ายชื่อชิ้นส่วน |
| `components/three/Stage.jsx` | แสง (ไม่โหลด HDR จากเน็ต), พื้น + วงแหวนสถานะ, เอียงตามเมาส์, ป้ายโหลด |
| `components/story/*` | หน้าแรก: `keyframes.js` = มุมกล้อง/สถานะโมเดลต่อ section · `StoryCanvas.jsx` = ขับกล้องตามการเลื่อน + จังหวะซีล · `StoryPage.jsx` = เนื้อหา · `CarrierTape3D.jsx` = ฉาก carrier tape แยก (วาดเฉพาะตอนอยู่บนจอ) |
| `components/twin/*` | หน้าทดสอบ: `TwinDashboard.jsx` (HUD + การ์ด) · `ControlPanel.jsx` (ปุ่ม + ACK) · `TwinCanvas.jsx` (ฉาก + OrbitControls) |

แกนของโมเดลหลังโหลด: เทปวิ่งตามแกน **z** (`Roll_1` ฝั่ง −z → `Roll_2` ฝั่ง +z) · หน้าเครื่องหัน **+x** · ตู้สีขาวอยู่ปลาย +z
(node ใน GLB หมุน 90° รอบแกน y มาจาก CAD) — ใช้ตอนตั้งมุมกล้องใน `keyframes.js`

## ⛔ ข้อมูลลูกค้า

ชิ้นงาน / carrier tape / รีล เป็น product ของลูกค้า — **ห้ามใส่สเปก** (ขนาดชิ้น, pitch, จำนวนต่อรีล, ชื่อชิ้นงาน, รูปถ่าย) ลงหน้าเว็บ (CLAUDE.md ข้อ 7.4)
- ภาพ carrier tape ใน section 03 สร้างในโค้ด (`components/story/CarrierTape3D.jsx`) เป็นรูปทรงทั่วไป ติดป้าย "ไม่ใช่แบบของชิ้นงานจริง"
- ตัวเลขที่โชว์ได้อยู่ใน `lib/twin.js` → `SPEC` (ของตัวเครื่อง) และ `SEAL` (อุณหภูมิซีล 189–191 °C · เพดาน 200 °C) · **ไม่แสดงเวลาซีล** (user สั่ง)

## ยังไม่ได้ทำ / ข้อจำกัด

- โมเดล ~725k เหลี่ยม + เปลือกโฮโลแกรม → เครื่องที่ไม่มีการ์ดจอจะหน่วง ยังไม่มีโหมดโมเดลเบา
- หน้าที่ของ `Cylender_Feed` / `Roll_1` / `Roll_2` ตีความจากชื่อใน CAD + ตำแหน่ง ยังไม่ได้ยืนยันกับ `machine_spec.md`
- พอร์ต 5173 ยังไม่ได้ลงใน `docs/specs/port_map.md` (เป็นของ agent `integration`)
