// มุมกล้อง + สถานะโมเดลของแต่ละ section บนหน้าแรก (index ตรงกับลำดับ section ใน StoryPage)
// cam / look = ตำแหน่งกล้องและจุดมอง (หน่วยฉาก หลังย่อโมเดลให้ทแยง 6 หน่วย)
// lookPart = ให้จุดมองตามชิ้นส่วนนั้น (ใช้ตอนโฟกัส) · camOffset = ระยะกล้องจากชิ้นนั้น
// ghost = ความเรืองของชิ้นที่ไม่ได้โฟกัส (ค่าตั้งต้น 0.55) · seal = เล่นจังหวะซีลวนไป (กดลง ↓ / ยกขึ้น ↑ + เทปเดิน) — ตอนนี้ไม่มี section ไหนใช้
// shift = ดันโมเดลไปทางขวาของจอ (จอกว้างเท่านั้น) เพราะข้อความอยู่ฝั่งซ้าย · 0 = กลางจอ
export const KEYFRAMES = [
  // 0 hero — โฮโลแกรมล้วน มุมเฉียงจากหน้าเครื่องฝั่งรีลป้อน (ตู้อยู่ด้านหลัง ไม่บัง)
  { cam: [8.2, 3.4, -6.0], look: [0, 0.8, 0], explode: 0, reveal: 0, holo: 1, labels: 0, focus: null, ring: '#38bdf8', shift: 1 },
  // 1 รู้จักเครื่อง — มองตรงจากหน้าเครื่อง เห็นทางเดินเทปเต็มความยาว
  { cam: [10.2, 2.5, 0.2], look: [0, 0.9, 0.1], explode: 0, reveal: 1, holo: 0.08, labels: 0, focus: null, ring: '#38bdf8', shift: 1 },
  // 2 แยกชิ้นส่วน — ยกมุมสูงขึ้นให้เห็นชิ้นที่ลอยออกมา
  { cam: [11.6, 5.6, -0.4], look: [0.5, 1.2, 0], explode: 1, reveal: 1, holo: 0.1, labels: 1, focus: null, ring: '#818cf8', shift: 0.75 },
  // 3 carrier tape — โฟกัสเทป ชิ้นอื่นกลายเป็นโฮโลแกรมจาง
  { lookPart: 'Cerrier', camOffset: [2.4, 1.3, -2.6], explode: 0.4, reveal: 1, holo: 0, labels: 1, focus: 'Cerrier', ring: '#f59e0b', shift: 1 },
  // 4 HMI — ฉากหลังเป็นโฮโลแกรมจาง ๆ ไกล ๆ ให้กรอบจอ HMI (DOM) เด่น
  { cam: [9.5, 4.8, 5.6], look: [0, 0.4, 0], explode: 0, reveal: 0.15, holo: 0.45, labels: 0, focus: null, ring: '#38bdf8', shift: 0 },
  // 5 ทดสอบกับ Digital Twin — ครึ่งจริงครึ่งโฮโลแกรม มุมสูงจากอีกฝั่ง
  { cam: [7.2, 5.2, 5.8], look: [0, 0.8, 0], explode: 0.15, reveal: 0.5, holo: 0.85, labels: 0, focus: null, ring: '#34d399', shift: 1 },
  // 6 เรียกให้เข้าไปทดสอบ — กลางจอ
  { cam: [8.4, 3.4, -4.8], look: [0, -0.35, 0], explode: 0, reveal: 1, holo: 0.3, labels: 0, focus: null, ring: '#38bdf8', shift: 0 },
];
