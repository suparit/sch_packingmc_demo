import { ALARM_STATE, DECISION_CHECKPOINTS, EMPTY_SYSTEM, STATES } from './twin.js';

// ตัวจำลองเครื่องในเบราว์เซอร์ — ใช้ตอนไม่มี gateway (โหมด DEMO)
// ทำตามกติกาเดียวกับ python_backend/gateway_fsm.py ให้มากที่สุด เพื่อให้ "ลองกดปุ่ม" แล้วได้ผลเหมือนจริง:
//   · VISION หยุดรอ DECISION ทุกโหมด · checkpoint อื่นหยุดเฉพาะ semi (fsm_spec.md 6.3.1)
//   · DECISION รับเฉพาะเมื่ออยู่ checkpoint และ step_allowed (สองชั้น — ข้อ 6.3.2)
//   · ESTOP → ALARM จำสเต็ปเดิม · RESET กิ่ง 1 ปลด ALARM / กิ่ง 2 เริ่ม batch ใหม่ (ข้อ 6.4)
//   · โหมด step: งานเสร็จแล้วรอ NEXT (protocol.md ข้อ 8)
// ⚠️ ไม่ใช่ตัวแทนของ gateway สำหรับทดสอบ safety — เป็นของโชว์/ฝึกกดเท่านั้น

const FEED_PULSES = 115; // พัลส์ต่อ pitch ของ feed (protocol.md 8.4 — 115/114)
const CAMERA_DELAY_MS = 700;
const DEMO_TARGET = 200; // ยอดเป้าหมายของตัวจำลอง — ตัวเลขสมมติ ไม่ใช่สเปกรีลของลูกค้า
const LOG_MAX = 100; // เท่ากับ LIMIT 100 ของ GET_HISTORY ใน gateway_fsm.py

// เวลาแบบเดียวกับคอลัมน์ timestamp ของ machine_logs (YYYY-MM-DD HH:MM:SS)
const stamp = () => {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
};

export function createDemoMachine() {
  const s = {
    ...EMPTY_SYSTEM,
    current_state: 'LOAD_CARRIER',
    target_pieces: DEMO_TARGET,
    current_temp: 190,
    step_wait: false,
    feed_src: 'SIM',
    feed_state: 'idle',
    feed_sent: 0,
    feed_total: 0,
    feed_index: 0,
    feed_half_ms: 5,
    feed_pulses: 0,
    cyl_c: 'OFF', // ปุ่ม INIT (Cylinder C) — เหมือนคีย์ cyl_c ของ gateway
  };
  let stateStart = performance.now();
  let manualFeedStart = null; // ปุ่ม STEP: feed 1 หลุมตอนเครื่องหยุด (ms ตอนเริ่ม)
  const MANUAL_FEED_MS = 700;
  let lastBeforeAlarm = null;
  let stepRelease = false;
  const opts = { cameraAuto: true };
  const log = []; // ประวัติการออกจากแต่ละ state — รูปเดียวกับแถว HISTORY_RESPONSE
  const alarmLog = []; // ประวัติ ALARM — รูปเดียวกับคีย์ alarms ของ gateway (ใหม่สุดก่อน)

  // บันทึก state ที่กำลังจะออก (เรียกก่อนเปลี่ยน state / ก่อนนับรอบ เหมือน log_state_transition_to_sql)
  const record = (now) => {
    log.push({ state: s.current_state, duration: Math.round((now - stateStart) / 10) / 100, cycle: s.cycles, mode: s.mode, time: stamp() });
    if (log.length > LOG_MAX) log.shift();
  };

  const idx = () => STATES.findIndex((x) => x.id === s.current_state);
  const enter = (name, now) => {
    s.current_state = name;
    s.step_allowed = false;
    s.step_wait = false;
    stepRelease = false;
    stateStart = now;
  };

  const enterAlarm = (reason, now) => {
    record(now);
    alarmLog.unshift({ time: stamp(), message: reason, state: s.current_state, cycle: s.cycles, pocket: s.cycles + 1, real: false, mode: s.mode });
    if (alarmLog.length > LOG_MAX) alarmLog.pop();
    if (s.current_state !== ALARM_STATE) lastBeforeAlarm = s.current_state;
    if (s.feed_state === 'running') s.feed_state = 'aborted';
    manualFeedStart = null;
    // 28 ก.ย. 2569: เหมือน gateway — ALARM ไม่ปล่อย Cylinder C เองแล้ว (ปล่อยด้วย INIT หรือ E-STOP เท่านั้น)
    if (reason.includes('EMERGENCY STOP')) s.cyl_c = 'OFF';
    s.running = false;
    s.predictive_warning = reason;
    enter(ALARM_STATE, now);
  };

  // บล็อก "ออกจากสเต็ป" — ผลข้างเคียงของแต่ละ state ตอนจบ แล้วไป next_state_ok
  const exitStep = (now) => {
    record(now);
    const cur = s.current_state;
    if (cur === 'FEED_CARRIER') {
      s.feed_state = 'done';
      s.feed_sent = s.feed_total;
      s.feed_index += 1;
      s.feed_pulses += s.feed_total;
    }
    if (cur === 'VISION') s.camera1_count += 1;
    if (cur === 'COUNT_ACCUMULATE') s.pieces_count += 1;
    if (cur === 'TAKEUP_REEL') {
      s.cycles += 1;
      if (s.pieces_count >= s.target_pieces) {
        s.running = false;
        s.predictive_warning = '🎉 SUCCESS: PRODUCTION BATCH COMPLETED!';
      }
    }
    enter(STATES[(idx() + 1) % STATES.length].id, now);
  };

  function tick(now) {
    const t = now / 1000;
    // อุณหภูมิแกว่งในช่วงซีลจริง 189–191 °C เหมือนช่วงปกติของ gateway_fsm.py (ตัวจำลองนี้ไม่ทำ fault อุณหภูมิ)
    s.current_temp = 190 + Math.round(Math.sin(t / 3));

    const cur = s.current_state;
    const alarm = cur === ALARM_STATE;
    s.op0 = alarm ? 0x08 : s.running ? (cur === 'FEED_CARRIER' ? 1 : 0) | (cur === 'SEAL_PROCESS' ? 2 : 0) | (cur === 'TAKEUP_REEL' ? 4 : 0) : 0;
    s.op1 = s.cyl_c === 'ON' ? 0x04 : 0;
    s.ip0 = cur === 'SENSOR_CHECK_CARRIER' || cur === 'LOAD_PART' ? 0x01 : 0;

    // ปุ่ม STEP — feed 1 หลุมตอนเครื่องหยุด (ไฟ FEED ติดระหว่างหมุน · ไม่นับเป็นหลุมของ batch)
    if (manualFeedStart !== null) {
      const p = Math.min(1, (now - manualFeedStart) / MANUAL_FEED_MS);
      s.feed_sent = Math.round(p * s.feed_total);
      s.op0 |= 0x01;
      if (p >= 1) {
        s.feed_state = 'done';
        s.feed_index += 1;
        s.feed_pulses += s.feed_total;
        manualFeedStart = null;
      }
    }

    if (!s.running || alarm) return { ...s };

    const dur = STATES[idx()].ms / Math.max(0.25, Number(s.speed_mul) || 1);
    const elapsed = now - stateStart;

    if (cur === 'FEED_CARRIER' && !s.step_wait) {
      if (s.feed_state !== 'running') {
        s.feed_state = 'running';
        s.feed_total = FEED_PULSES;
        s.feed_sent = 0;
      }
      s.feed_sent = Math.min(FEED_PULSES, Math.round((elapsed / dur) * FEED_PULSES));
      s.encoder_count += 2;
    }
    if (elapsed < dur) return { ...s };

    // งานของสเต็ปเสร็จแล้ว — ตัดสินว่าไปต่อหรือรอ
    if (s.mode === 'step' && cur !== 'VISION') {
      if (stepRelease) exitStep(now);
      else s.step_wait = true;
    } else if (DECISION_CHECKPOINTS.includes(cur) && (s.mode === 'semi' || cur === 'VISION')) {
      if (!s.step_allowed) s.step_allowed = true;
      // กล้องจำลอง: ยิง PASS เองที่ VISION (เหมือน app_vision.py) — ปิดได้จากหน้า twin
      if (cur === 'VISION' && opts.cameraAuto && elapsed >= dur + CAMERA_DELAY_MS) decision(true, now);
    } else {
      exitStep(now);
    }
    return { ...s };
  }

  function decision(value, now = performance.now()) {
    // สองชั้นแยกกันตาม fsm_spec.md 6.3.2 — state guard แล้วค่อย flag guard
    if (!DECISION_CHECKPOINTS.includes(s.current_state)) return { type: 'DECISION_ACK', accepted: false, reason: 'not_allowed' };
    if (!s.step_allowed) return { type: 'DECISION_ACK', accepted: false, reason: 'not_allowed' };
    s.step_allowed = false;
    if (value) exitStep(now);
    else enterAlarm('⚠️ ERROR: OPERATOR REJECTION (SEMI-AUTO NG)', now);
    return { type: 'DECISION_ACK', accepted: true };
  }

  function command(action, data = {}) {
    const now = performance.now();
    switch (action) {
      case 'START':
        if (s.pieces_count >= s.target_pieces) {
          s.predictive_warning = '⚠️ CANNOT START: BATCH DONE - PRESS RESET FIRST';
          return null;
        }
        s.running = true;
        s.predictive_warning = '';
        stateStart = now;
        return null;
      case 'STOP':
        s.running = false;
        stateStart = now;
        return null;
      case 'ESTOP':
        enterAlarm('🚨 EMERGENCY STOP ENGAGED', now);
        return null;
      case 'RESET':
        if (s.current_state === ALARM_STATE) {
          // กิ่ง 1 — ปลด ALARM กลับสเต็ปเดิม ยอดคงเดิม ไม่ auto-start
          record(now);
          const back = lastBeforeAlarm ?? 'LOAD_CARRIER';
          lastBeforeAlarm = null;
          s.running = false;
          s.predictive_warning = '';
          enter(back, now);
        } else if (!s.running) {
          // กิ่ง 2 — เริ่ม batch ใหม่
          Object.assign(s, {
            pieces_count: 0, cycles: 0, camera1_count: 0, encoder_count: 0,
            predictive_warning: '', feed_index: 0, feed_pulses: 0, feed_state: 'idle', feed_sent: 0, feed_total: 0,
          });
          enter('LOAD_CARRIER', now);
        }
        return null;
      case 'MODE': {
        const m = data.mode;
        if (!['auto', 'semi', 'step'].includes(m)) return { type: 'MODE_ACK', accepted: false, mode: s.mode, reason: 'invalid_mode' };
        if (s.running && (m === 'step') !== (s.mode === 'step'))
          return { type: 'MODE_ACK', accepted: false, mode: s.mode, reason: 'step_switch_while_running' };
        s.mode = m;
        if (m !== 'step') s.step_wait = false;
        return { type: 'MODE_ACK', accepted: true, mode: s.mode };
      }
      case 'NEXT': {
        const no = (reason) => ({ type: 'NEXT_ACK', accepted: false, state: s.current_state, reason });
        if (s.current_state === ALARM_STATE) return no('alarm');
        if (s.mode !== 'step') return no('not_step_mode');
        if (!s.running) return no('not_running');
        if (s.current_state === 'VISION') return no('use_decision');
        if (data.expect_state && data.expect_state !== s.current_state) return no('state_mismatch');
        if (!s.step_wait) return no('not_waiting');
        stepRelease = true;
        s.step_wait = false;
        return { type: 'NEXT_ACK', accepted: true, state: s.current_state };
      }
      case 'SPEED':
        s.speed_mul = Math.min(3, Math.max(0.5, Number(data.value) || 1));
        return null;
      case 'SET_PARAMS': {
        // ช่องตั้งเป้า batch — รับเฉพาะตอนหยุด (เหมือน gateway)
        const n = Number(data.target_pieces);
        if (s.running) s.predictive_warning = 'TARGET LOCKED: STOP MACHINE FIRST';
        else if (Number.isInteger(n) && n >= 1) s.target_pieces = Math.min(10000, n);
        return null;
      }
      case 'CYL_C': {
        // ปุ่ม INIT — ON ไม่รับตอน ALARM (กติกาเดียวกับ gateway) · OFF รับเสมอ
        const want = String(data.value || '').toUpperCase();
        if (want === 'ON' && s.current_state === ALARM_STATE) s.predictive_warning = 'INIT REJECTED: PRESS RESET FIRST';
        else if (want === 'ON' || want === 'OFF') s.cyl_c = want;
        return null;
      }
      case 'SINGLE_CYCLE': {
        // ปุ่ม STEP — feed 1 หลุมตอนเครื่องหยุด (ข้อความปฏิเสธเหมือน gateway)
        let reason = '';
        if (s.running) reason = 'STEP REJECTED: MACHINE RUNNING';
        else if (s.current_state === ALARM_STATE) reason = 'STEP REJECTED: PRESS RESET FIRST';
        else if (s.cyl_c !== 'ON') reason = 'STEP REJECTED: PRESS INIT FIRST';
        else if (manualFeedStart !== null) reason = 'STEP REJECTED: FEED BUSY';
        if (reason) {
          s.predictive_warning = reason;
          return null;
        }
        s.predictive_warning = '';
        s.feed_state = 'running';
        s.feed_total = FEED_PULSES;
        s.feed_sent = 0;
        manualFeedStart = now;
        return null;
      }
      case 'DECISION':
        return decision(Boolean(data.value), now);
      case 'GET_HISTORY':
        return { type: 'HISTORY_RESPONSE', data: log.slice(), alarms: alarmLog.slice() };
      default:
        return null;
    }
  }

  return { tick, command, opts };
}

// ตัวจำลองตัวเดียวทั้งแอป — เปลี่ยนหน้า /twin ↔ /analytics แล้วเครื่องจำลองกับประวัติยังอยู่ (หายเมื่อรีเฟรชหน้า)
let shared = null;
export function getDemoMachine() {
  if (!shared) shared = createDemoMachine();
  return shared;
}
