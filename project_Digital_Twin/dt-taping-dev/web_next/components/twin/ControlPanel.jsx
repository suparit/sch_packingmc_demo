'use client';

import { useEffect, useState } from 'react';
import { Card, Icon } from '@/components/ui/Telemetry.jsx';
import { ALARM_STATE, DECISION_CHECKPOINTS, REASON_TH } from '@/lib/twin.js';

// ปุ่มควบคุมเครื่อง — ส่ง action ตาม protocol.md ข้อ 4 / 8 ผ่าน send() ของ useTwinLink
// LIVE = เข้า gateway จริง (ถ้า gateway ต่อ RUST_BRIDGE=1 จะขับของจริงบนบอร์ด) · DEMO = ตัวจำลองในเบราว์เซอร์

function Btn({ onClick, disabled, tone = 'default', title, className = '', children }) {
  const tones = {
    default: 'bg-white/[0.06] text-slate-100 hover:bg-white/[0.12] border-white/10',
    go: 'bg-emerald-400/15 text-emerald-200 hover:bg-emerald-400/25 border-emerald-300/30',
    stop: 'bg-amber-400/10 text-amber-200 hover:bg-amber-400/20 border-amber-300/25',
    info: 'bg-sky-400/15 text-sky-100 hover:bg-sky-400/25 border-sky-300/30',
    bad: 'bg-rose-500/15 text-rose-200 hover:bg-rose-500/25 border-rose-300/30',
  };
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`rounded-xl border px-3 py-2.5 text-sm font-medium transition active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-35 disabled:active:scale-100 ${tones[tone]} ${className}`}
    >
      {children}
    </button>
  );
}

export default function ControlPanel({ s, link, send, events, cameraAuto, onCameraAuto }) {
  const alarm = s.current_state === ALARM_STATE;
  // โหมด step + NEXT มีเฉพาะ gateway ของเพื่อน — gateway 01_DigitalTwin (มีคีย์ hw_sync) ไม่มีโหมดนี้ และตัวจำลองก็ซ่อน
  // (27 ก.ย. 2569 เจ้าของงานให้เอาออก: ปุ่ม Step โหมด สับสนกับปุ่ม STEP 1 หลุม) · protocol.md 8.5
  const stepSupported = link.status === 'live' && 'step_wait' in s && !('hw_sync' in s);
  const [speed, setSpeed] = useState(1);
  const [nextLock, setNextLock] = useState(false);

  // ปลดล็อก NEXT เมื่อ state เปลี่ยน หรือได้ NEXT_ACK (protocol.md 8.5)
  useEffect(() => setNextLock(false), [s.current_state]);
  const lastAck = events[events.length - 1];
  useEffect(() => {
    if (lastAck?.type === 'NEXT_ACK') setNextLock(false);
  }, [lastAck]);
  useEffect(() => {
    setSpeed(Number(s.speed_mul) || 1);
  }, [s.speed_mul]);

  const canNext =
    stepSupported && s.mode === 'step' && s.running && s.step_wait && !alarm && s.current_state !== 'VISION' && !nextLock;
  const canDecide = s.step_allowed && DECISION_CHECKPOINTS.includes(s.current_state);
  const offline = link.status !== 'live' && link.status !== 'demo';
  const cylOn = s.cyl_c === 'ON';                 // สถานะจริงจาก gateway (ไม่ใช่สถานะปุ่มในเว็บ)
  const feedBusy = s.feed_state === 'running';
  const syncSupported = link.status === 'live' && 'hw_sync' in s;   // gateway ของเพื่อน/ตัวจำลองไม่มีคีย์นี้
  const synced = syncSupported && s.hw_sync === true;

  return (
    <Card
      title="Controls"
      icon={Icon.sliders}
      right={
        <span className={`rounded-md px-2 py-0.5 font-mono text-[10px] ${link.status === 'live' ? 'bg-emerald-400/15 text-emerald-300' : 'bg-amber-400/15 text-amber-300'}`}>
          {link.status === 'live' ? '→ gateway' : '→ ตัวจำลอง'}
        </span>
      }
    >
      {link.status === 'live' && s.feed_src === 'REAL' && !syncSupported && (
        <div className="mb-3 rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          ต่อบอร์ดจริงอยู่ (feed_src = REAL) — ปุ่มจะขับมอเตอร์และโซลินอยด์จริง ให้แน่ใจว่าไม่มีคนอยู่ในพื้นที่เครื่อง
        </div>
      )}

      {/* สั่งเครื่องจริงอยู่ — ปุ่ม Sync ย้ายไปอยู่ข้างป้ายสถานะมุมขวาบน (27 ก.ย. 2569) */}
      {synced && (
        <div className="mb-3 rounded-xl border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          ● สั่งเครื่องจริงอยู่ — ปุ่มขับมอเตอร์ · โซลินอยด์ · Cylinder C จริง ให้แน่ใจว่าไม่มีคนอยู่ในพื้นที่เครื่อง
        </div>
      )}

      {/* E-STOP: กดได้เสมอ ไม่มีเงื่อนไข */}
      <button
        type="button"
        onClick={() => send('ESTOP')}
        disabled={offline}
        className="group relative mb-3 flex w-full items-center justify-center gap-3 overflow-hidden rounded-2xl border border-rose-400/50 bg-gradient-to-b from-rose-500 to-rose-700 py-3.5 text-base font-bold tracking-wide text-white shadow-[0_0_30px_-8px_#f43f5e] transition active:scale-[0.98] disabled:opacity-40"
      >
        <span className="grid h-6 w-6 place-items-center rounded-full border-2 border-white/80 text-[10px]">■</span>
        E-STOP
      </button>

      <div className="grid grid-cols-3 gap-2">
        <Btn tone="go" onClick={() => send('START')} disabled={offline || s.running || alarm} title={alarm ? 'อยู่ใน ALARM — กด RESET ก่อน' : ''}>
          ▶ START
        </Btn>
        <Btn tone="stop" onClick={() => send('STOP')} disabled={offline || !s.running}>
          ❚❚ STOP
        </Btn>
        <Btn
          onClick={() => send('RESET')}
          disabled={offline || (s.running && !alarm)}
          title={alarm ? 'ปลด ALARM กลับสเต็ปเดิม (ยอดคงเดิม)' : 'เริ่ม batch ใหม่ — ยอดกลับเป็น 0'}
        >
          ↺ RESET
        </Btn>
      </div>
      <p className="mt-1.5 text-[10px] text-slate-500">
        {alarm ? 'RESET = ปลด ALARM กลับสเต็ปเดิม ยอดไม่หาย · ไม่เดินเองจนกว่าจะกด START' : 'RESET ตอนหยุด = เริ่ม batch ใหม่ ยอดกลับเป็น 0'}
      </p>

      {/* INIT / STEP — ปุ่มเดียวกับจอ HMI (27 ก.ย. 2569) · gateway ใช้กติกาเดียวกับจอ
          INIT = Cylinder C กด carrier แนบ roller (op1 bit 2) ต้องกดก่อน START ตอนต่อบอร์ดจริง
          28 ก.ย. 2569: C กด/ปล่อยด้วย INIT อย่างเดียว — ALARM ไม่ปล่อยเองแล้ว (เทปไม่ไหล) · E-STOP ยังปล่อย
          STEP = feed 1 หลุมตอนเครื่องหยุด ใช้เลื่อน carrier เข้าตำแหน่ง index (ส่ง SINGLE_CYCLE แบบเดียวกับจอ) */}
      <div className="mt-2 grid grid-cols-2 gap-2">
        <Btn
          tone={cylOn ? 'info' : 'default'}
          onClick={() => send('CYL_C', { value: cylOn ? 'OFF' : 'ON' })}
          disabled={offline}
          title={cylOn ? 'Cylinder C กดอยู่ — กดอีกครั้งเพื่อปล่อย' : 'Cylinder C กด carrier แนบ roller'}
        >
          {cylOn ? '● INIT · C กดอยู่' : '○ INIT'}
        </Btn>
        <Btn
          tone="info"
          onClick={() => send('SINGLE_CYCLE')}
          disabled={offline || s.running || alarm || !cylOn || feedBusy}
          title={!cylOn ? 'กด INIT ก่อน' : s.running ? 'ใช้ได้ตอนเครื่องหยุด' : feedBusy ? 'มอเตอร์กำลัง feed อยู่' : 'feed 1 หลุม'}
        >
          {feedBusy && !s.running ? '… กำลัง feed' : '⏭ STEP 1 หลุม'}
        </Btn>
      </div>
      <p className="mt-1.5 text-[10px] text-slate-500">
        {cylOn ? 'STEP จนหลุมตรงตำแหน่ง index แล้วกด START' : 'ต่อบอร์ดจริง: กด INIT ก่อน START (หลัง E-STOP ต้องกดใหม่)'}
      </p>

      {/* โหมด */}
      <div className="mt-4">
        <div className="mb-1.5 text-[10px] uppercase tracking-[0.14em] text-slate-500">Mode</div>
        <div className={`grid gap-1 rounded-xl border border-white/10 bg-black/20 p-1 ${stepSupported ? 'grid-cols-3' : 'grid-cols-2'}`}>
          {(stepSupported ? ['auto', 'semi', 'step'] : ['auto', 'semi']).map((m) => {
            const switchingStep = (m === 'step') !== (s.mode === 'step');
            return (
              <button
                key={m}
                type="button"
                onClick={() => send('MODE', { mode: m })}
                disabled={offline || (s.running && switchingStep)}
                title={s.running && switchingStep ? 'ต้อง STOP ก่อนสลับเข้า/ออกโหมด step' : ''}
                className={`rounded-lg py-1.5 text-xs font-medium capitalize transition disabled:cursor-not-allowed disabled:opacity-35 ${
                  s.mode === m ? 'bg-sky-400/20 text-sky-100 shadow-[inset_0_0_0_1px_rgb(56_189_248/0.4)]' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {m}
              </button>
            );
          })}
        </div>
      </div>

      {/* NEXT (โหมด step) + DECISION */}
      <div className={`mt-4 grid gap-2 ${stepSupported ? 'grid-cols-3' : 'grid-cols-2'}`}>
        {stepSupported && (
        <Btn
          tone="info"
          onClick={() => {
            setNextLock(true);
            send('NEXT', { expect_state: s.current_state });
          }}
          disabled={offline || !canNext}
          title="โหมด step — ปล่อยสเต็ปที่ทำงานเสร็จแล้ว"
        >
          NEXT ⏭
        </Btn>
        )}
        <Btn tone="go" onClick={() => send('DECISION', { value: true })} disabled={offline || !canDecide}>
          ✓ PASS
        </Btn>
        <Btn tone="bad" onClick={() => send('DECISION', { value: false })} disabled={offline || !canDecide} title="NG → เข้า ALARM">
          ✕ NG
        </Btn>
      </div>
      <p className="mt-1.5 min-h-[1.2em] text-[10px] text-slate-500">
        {canDecide
          ? `FSM รอคำตัดสินที่ ${s.current_state}`
          : s.mode === 'step' && s.step_wait
            ? 'สเต็ปนี้ทำงานเสร็จแล้ว — กด NEXT เพื่อไปต่อ'
            : 'PASS / NG กดได้เมื่อ FSM หยุดรอที่จุดตรวจ'}
      </p>

      {/* ความเร็ว */}
      <div className="mt-4">
        <div className="mb-1.5 flex items-center justify-between text-[10px] uppercase tracking-[0.14em] text-slate-500">
          <span>Speed</span>
          <span className="font-mono text-xs normal-case tracking-normal text-slate-300">×{speed.toFixed(1)}</span>
        </div>
        <input
          type="range"
          min="0.5"
          max="3"
          step="0.5"
          value={speed}
          disabled={offline}
          onChange={(e) => {
            const v = Number(e.target.value);
            setSpeed(v);
            send('SPEED', { value: v });
          }}
          className="w-full accent-sky-400"
          aria-label="ตัวคูณความเร็ว"
        />
      </div>

      {link.status === 'demo' && (
        <label className="mt-4 flex cursor-pointer items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-slate-300">
          <span>
            กล้องจำลองกด PASS ให้เองที่ VISION
            <span className="block text-[10px] text-slate-500">ปิดเพื่อลองตัดสินเอง</span>
          </span>
          <input type="checkbox" checked={cameraAuto} onChange={(e) => onCameraAuto(e.target.checked)} className="h-4 w-4 accent-sky-400" />
        </label>
      )}

      <AckFeed events={events} />
    </Card>
  );
}

// ผลตอบกลับของคำสั่ง (ACK) — ปฏิเสธต้องบอกเหตุผล ห้ามเงียบ (protocol.md 8.5)
function AckFeed({ events }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const recent = events.filter((e) => now - e.at < 6000).slice(-3);
  if (!recent.length) return null;
  return (
    <div className="mt-4 space-y-1.5" aria-live="polite">
      {recent.map((e) => {
        const ok = e.kind === 'ack' ? e.accepted : e.ok;
        const label = e.type ? e.type.replace('_ACK', '') : '';
        const text = e.text ?? (ok ? `รับคำสั่ง${e.mode ? ` · ${e.mode}` : ''}${e.state ? ` · ${e.state}` : ''}` : REASON_TH[e.reason] ?? e.reason ?? 'ถูกปฏิเสธ');
        return (
          <div
            key={e.id}
            className={`flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[11px] ${ok ? 'bg-emerald-400/10 text-emerald-200' : 'bg-rose-500/10 text-rose-200'}`}
          >
            <span className="font-mono text-[10px] opacity-70">{label}</span>
            <span>{text}</span>
          </div>
        );
      })}
    </div>
  );
}
