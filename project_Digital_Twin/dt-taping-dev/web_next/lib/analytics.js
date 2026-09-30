// คำนวณสถิติหน้า Analytics จากแถว HISTORY_RESPONSE (gateway_fsm.py — SELECT ... FROM machine_logs LIMIT 100)
// รูปแถว: { state, duration (วินาที), cycle, mode, time } เรียงเก่า → ใหม่
// สูตรเดียวกับ cad/analytics.html (เฉลี่ยต่อสเต็ป · รวมต่อรอบ · 10 แถวล่าสุด · FRICTION > 1.35 s · ALARM = TRIPPED)
// ต่างจากของเดิม: แบ่ง "รอบ" ตามลำดับแถว ไม่ใช่รวมตามเลข cycle ตรง ๆ เพราะ
//   · gateway_fsm.py บันทึกแถว TAKEUP_REEL ก่อน cycles += 1 → แถวนี้ปิดรอบของมันเอง
//   · RESET เริ่ม batch ใหม่ cycles กลับเป็น 0 → เลข cycle ซ้ำข้าม batch (ของเดิมรวมเป็นแท่งเดียวผิด ๆ)
//   · หน้าต่าง 100 แถวตัดรอบแรกกลางทาง · รอบสุดท้ายอาจยังเดินอยู่
// รอบที่ "ครบ" = เริ่มที่ LOAD_CARRIER และจบที่ TAKEUP_REEL เท่านั้น — รอบไม่ครบแสดงจางและไม่นับใน KPI
// (ของเดิมเอารอบที่เพิ่งเริ่มมาเป็น "เร็วที่สุด" ทำให้ OPTIMAL ผิด)

import { ALARM_STATE, STATES } from './twin.js';

export const FRICTION_S = 1.35;

export function rowStatus(row) {
  if (row.state === ALARM_STATE) return 'tripped';
  if (Number(row.duration) > FRICTION_S) return 'friction';
  return 'normal';
}

export function computeAnalytics(rows, machineRunning = false) {
  const byState = new Map();
  for (const r of rows) {
    const d = Number(r.duration) || 0;
    if (r.state) {
      const s = byState.get(r.state) ?? { total: 0, count: 0, max: 0 };
      s.total += d;
      s.count += 1;
      s.max = Math.max(s.max, d);
      byState.set(r.state, s);
    }
  }

  // เรียงสเต็ปตามลำดับ FSM (state_table.csv) — ALARM ไว้ท้าย · state ที่ไม่รู้จักต่อท้ายสุด
  const order = [...STATES.map((s) => s.id), ALARM_STATE];
  const steps = [...byState.entries()]
    .map(([state, s]) => ({ state, avg: s.total / s.count, count: s.count, total: s.total, max: s.max }))
    .sort((a, b) => {
      const ia = order.indexOf(a.state);
      const ib = order.indexOf(b.state);
      return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib);
    });

  // แบ่งรอบตามลำดับ: ขึ้นรอบใหม่หลังแถว TAKEUP_REEL หรือเมื่อเลข cycle เปลี่ยน
  const segs = [];
  let cur = null;
  for (const r of rows) {
    const id = r.cycle ?? null;
    if (!cur || cur.closed || cur.id !== id) {
      cur = { id, rows: [], closed: false };
      segs.push(cur);
    }
    cur.rows.push(r);
    if (r.state === 'TAKEUP_REEL') cur.closed = true;
  }
  const cycles = segs.map((g, i) => {
    const complete = g.rows[0].state === 'LOAD_CARRIER' && g.rows[g.rows.length - 1].state === 'TAKEUP_REEL';
    const last = i === segs.length - 1;
    return {
      key: i,
      id: g.id,
      total: g.rows.reduce((a, r) => a + (Number(r.duration) || 0), 0),
      steps: g.rows.length,
      complete,
      // รอบไม่ครบ: ตัวสุดท้ายขณะเครื่องเดิน = กำลังเดิน · ที่เหลือ = ถูกตัดขอบหน้าต่าง / RESET / หยุดกลางรอบ
      note: complete ? '' : last && machineRunning ? 'กำลังเดิน' : 'ไม่ครบรอบ',
    };
  });

  const done = cycles.filter((c) => c.complete);
  const kpi = done.length
    ? {
        mean: done.reduce((a, c) => a + c.total, 0) / done.length,
        best: Math.min(...done.map((c) => c.total)),
        worst: Math.max(...done.map((c) => c.total)),
        n: done.length,
      }
    : null;

  const counts = { friction: 0, tripped: 0 };
  for (const r of rows) {
    const st = rowStatus(r);
    if (st !== 'normal') counts[st] += 1;
  }

  return { steps, cycles, kpi, counts, latest: rows.slice(-10).reverse() };
}
