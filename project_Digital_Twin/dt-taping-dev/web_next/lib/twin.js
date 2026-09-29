// ข้อมูลกลางของเครื่อง — อ้างจาก docs/specs/state_table.csv, fsm_spec.md, protocol.md, machine_spec.md
// ห้ามเดาชื่อ state หรือคีย์เอง ถ้าสัญญาเปลี่ยนต้องแก้ที่นี่ที่เดียว

// ลำดับตามคอลัมน์ next_state_ok (0 → 15 แล้ววนกลับ) · ms = timeout_ms ใช้เป็นจังหวะของตัวจำลอง
export const STATES = [
  { id: 'LOAD_CARRIER', th: 'โหลด carrier tape', ms: 500 },
  { id: 'INDEX_CARRIER', th: 'เดินเทปไปตำแหน่ง index', ms: 800 },
  { id: 'POWER_ON', th: 'เปิดระบบ', ms: 500 },
  { id: 'SET_PARAMS', th: 'ตั้งค่าพารามิเตอร์', ms: 500 },
  { id: 'SENSOR_CHECK_CARRIER', th: 'ตรวจตำแหน่งเทปด้วยเซนเซอร์', ms: 400 },
  { id: 'READY', th: 'พร้อมทำงาน', ms: 500 },
  { id: 'LOAD_PART', th: 'วางชิ้นงานลงพ็อกเก็ต', ms: 800 },
  { id: 'VISION', th: 'กล้องตรวจชิ้นงาน', ms: 400 },
  { id: 'CHECK_TEMP', th: 'ตรวจอุณหภูมิพร้อมซีล', ms: 400 },
  { id: 'FEED_CARRIER', th: 'เดินเทปไปพ็อกเก็ตถัดไป', ms: 1300 },
  { id: 'COUNT_PROCESS', th: 'ประมวลผลการนับ', ms: 500 },
  { id: 'COUNT_CHECK', th: 'เช็คว่าครบจำนวนหรือยัง', ms: 500 },
  { id: 'COUNT_ACCUMULATE', th: 'สะสมยอด', ms: 400 },
  { id: 'SEAL_PROCESS', th: 'ซีล cover tape (ความร้อน + แรงกด)', ms: 1000 },
  { id: 'VISION_QC', th: 'ตรวจคุณภาพรอยซีล', ms: 400 },
  { id: 'TAKEUP_REEL', th: 'ม้วนเก็บเข้ารีล', ms: 1000 },
];
export const ALARM_STATE = 'ALARM';

// fsm_spec.md ข้อ 6.3.1 — 5 จุดที่รับ DECISION ได้ (VISION หยุดรอทุกโหมด · ที่เหลือหยุดเฉพาะ semi)
export const DECISION_CHECKPOINTS = ['SENSOR_CHECK_CARRIER', 'VISION', 'CHECK_TEMP', 'COUNT_CHECK', 'VISION_QC'];

export const stateIndex = (name) => STATES.findIndex((s) => s.id === name);
export const stateLabel = (name) =>
  name === ALARM_STATE ? 'หยุดเครื่อง แสดง error' : STATES[stateIndex(name)]?.th ?? '—';

// เพดานอุณหภูมิที่ FSM ใช้ตัด (ข้อความ "HEATER OVERHEATED (OVER 200°C)" ใน protocol.md ข้อ 2.2)
export const TEMP_LIMIT = 200;

// ความหมายของบิต — board_protocol.md ข้อ 9 + protocol.md ข้อ 4.1 / 4.3 / 9.6
export const OP0_BITS = ['FEED', 'SEAL', 'TAKEUP', 'ALARM', '—', '—', '—', '—'];
export const OP1_BITS = ['Seal A', 'Seal B', 'Cyl C', '—', 'PUL', '—', '—', '—'];

// ตัวเลขของตัวเครื่องที่โชว์บนหน้าแนะนำ — machine_spec.md ข้อ 2 / fsm_spec.md
// ⛔ ห้ามใส่สเปกชิ้นงาน / เทป / รีลของลูกค้า (ขนาดชิ้น, pitch, จำนวนต่อรีล) ลงหน้าเว็บ — CLAUDE.md ข้อ 7.4
export const SPEC = {
  maxPcsPerMin: 30,
  stepsPerCycle: 16,
  checkpoints: 5,
  modules: 7,
};

// ตัวเลขช่วง Sealing บนหน้าแรก
// อุณหภูมิซีลจริง 189–191 °C — user ยืนยัน 2026-09-25 (machine_spec.md ข้อ 2.2 ยังว่าง ต้องให้ machine-design ลงต่อ)
// limitC = เพดานที่ FSM ตัดเข้า ALARM ("HEATER OVERHEATED (OVER 200°C)" — protocol.md ข้อ 2.2)
// ⛔ เวลาซีลไม่แสดงบนหน้าเว็บ (user สั่ง) — จังหวะกดลง/ยกขึ้นในฉาก 3D เป็นภาพจำลองเท่านั้น
export const SEAL = {
  tempMinC: 189,
  tempMaxC: 191,
  limitC: 200,
};

// ชิ้นส่วนใน cad/export/Machine.glb (7 node) — ตีความหน้าที่จากชื่อใน CAD + ตำแหน่งตามแนวเทป
// ลำดับตามทางเดินของเทป: Roll_1 → Cerrier → Sealing → Feed_Cerrier/Cylender_Feed → Roll_2
// explode = ทิศที่ชิ้นส่วนลอยออกตอนแยกชิ้น (หน่วยฉากหลังย่อโมเดลแล้ว)
// แกนของโมเดล: เทปวิ่งตามแกน z (Roll_1 ฝั่ง −z → Roll_2 ฝั่ง +z) · ด้านหน้าเครื่องหัน +x · ตู้สีขาวอยู่ปลาย +z
export const PARTS = [
  {
    node: 'Farm',
    name: 'โครงเครื่อง',
    en: 'Frame',
    desc: 'โครงอะลูมิเนียมโปรไฟล์ ยึดทุกโมดูลให้อยู่ในแนวเดียวกับเทป',
    explode: [0, 0, 0],
  },
  {
    node: 'Roll_1',
    name: 'รีลฝั่งป้อน',
    en: 'Supply reel',
    desc: 'ม้วน carrier tape เปล่าที่ป้อนเข้าเครื่อง',
    explode: [0.1, 1.0, -0.45],
  },
  {
    node: 'Cerrier',
    name: 'Carrier tape',
    en: 'Carrier tape',
    desc: 'เทปที่มีหลุมเรียงกัน ใส่ชิ้นงานอิเล็กทรอนิกส์ SMC หลุมละชิ้น',
    explode: [1.3, 1.3, 0],
  },
  {
    node: 'Sealing',
    name: 'หัวซีล',
    en: 'Sealing head',
    desc: 'ความร้อน + แรงกด ปิด cover tape ลงบนพ็อกเก็ต',
    explode: [0.7, 1.7, -0.2],
  },
  {
    node: 'Cylender_Feed',
    name: 'กระบอกลมชุด feed',
    en: 'Feed cylinder',
    desc: 'กระบอกลมของชุดดึงเทป (สั่งผ่านโซลินอยด์บน op1)',
    explode: [0.3, 1.1, 0.6],
  },
  {
    node: 'Feed_Cerrier',
    name: 'ชุดดึงเทป',
    en: 'Tape feeder',
    desc: 'ขับด้วย closed-loop stepper เดินเทปไปทีละหนึ่งหลุม',
    explode: [1.1, 0.2, 0.6],
  },
  {
    node: 'Roll_2',
    name: 'รีลเก็บ',
    en: 'Take-up reel',
    desc: 'ม้วนเทปที่ซีลแล้ว คุมแรงตึงด้วย servo โหมด torque',
    explode: [0.1, 1.0, 0.45],
  },
];

// ค่าเริ่มต้นหน้าตาเดียวกับ system_data ของ gateway (ฝั่งเว็บต้องแกะ .system ก่อน)
export const EMPTY_SYSTEM = {
  current_state: 'READY',
  running: false,
  step_allowed: false,
  cycles: 0,
  pieces_count: 0,
  target_pieces: 0,
  pitch: 24,
  current_temp: 0,
  mode: 'auto',
  speed_mul: 1,
  ip0: 0,
  ip1: 0,
  op0: 0,
  op1: 0,
  camera1_count: 0,
  encoder_count: 0,
  predictive_warning: '',
};

// ข้อความของ reason ใน ACK — protocol.md ข้อ 8.2 / 8.3
export const REASON_TH = {
  alarm: 'อยู่ใน ALARM — กด RESET',
  not_step_mode: 'ไม่ได้อยู่โหมด Step',
  not_running: 'กด START ก่อน',
  use_decision: 'สเต็ปนี้ใช้ PASS / NG',
  state_mismatch: 'สเต็ปเปลี่ยนไปแล้ว ลองใหม่',
  not_waiting: 'รอให้สเต็ปทำงานเสร็จ',
  invalid_mode: 'โหมดไม่ถูกต้อง',
  step_switch_while_running: 'ต้อง STOP ก่อนสลับเข้า/ออกโหมด Step',
  not_allowed: 'ตอนนี้เครื่องไม่ได้รอคำตัดสิน',
};
