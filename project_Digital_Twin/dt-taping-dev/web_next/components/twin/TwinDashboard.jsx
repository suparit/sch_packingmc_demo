'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useEffect, useId, useRef, useState } from 'react';
import { PartLabels, createLabelStore } from '@/components/three/MachineModel.jsx';
import { LoadingOverlay } from '@/components/three/Stage.jsx';
import { Bits, Card, Icon, Ring, Sparkline, Stat } from '@/components/ui/Telemetry.jsx';
import { DEFAULT_WS_URL, useTwinLink } from '@/lib/useTwinLink.js';
import { ALARM_STATE, DECISION_CHECKPOINTS, OP0_BITS, OP1_BITS, SEAL, STATES, TEMP_LIMIT, stateIndex, stateLabel } from '@/lib/twin.js';

// ระดับอุณหภูมิ — ตีความเหมือนสเต็ป CHECK_TEMP ใน gateway_fsm.py ทุกช่วง:
// 189–191 ผ่าน · > 200 เข้า ALARM · ค่าอื่น (ต่ำกว่าช่วง / 192–200) = FSM รออยู่ที่ CHECK_TEMP ยังไม่ซีล
const tempLevel = (t) =>
  t <= 0 ? 'idle' : t > TEMP_LIMIT ? 'over' : t > SEAL.tempMaxC ? 'high' : t < SEAL.tempMinC ? 'low' : 'ok';
import ControlPanel from './ControlPanel.jsx';
import CameraCard from './CameraCard.jsx';

const TwinCanvas = dynamic(() => import('./TwinCanvas.jsx'), { ssr: false });

export default function TwinDashboard() {
  const { system: s, link, history, events, send, setCameraAuto, connectTo, disconnect } = useTwinLink();
  const sysRef = useRef(s);
  sysRef.current = s;
  const view = useRef({ exploded: false, xray: false });
  const [viewState, setViewState] = useState(view.current);
  const [store] = useState(createLabelStore);
  const [modelFailed, setModelFailed] = useState(false);
  const [cameraAuto, setCamAuto] = useState(true);

  const toggleView = (key) => {
    view.current = { ...view.current, [key]: !view.current[key] };
    setViewState(view.current);
  };

  return (
    <main className="relative min-h-dvh overflow-x-hidden bg-ink-950 lg:h-dvh lg:min-h-[720px] lg:overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute left-1/2 top-[40%] h-[70vmin] w-[90vmin] -translate-x-1/2 -translate-y-1/2 rounded-full bg-sky-500/15 blur-[120px]" />
        <div className="absolute right-[12%] top-[8%] h-[40vmin] w-[40vmin] rounded-full bg-indigo-500/15 blur-[120px]" />
      </div>

      {/* ฉาก 3D — มือถือ: 56vh ด้านบน · จอใหญ่: เต็มจอหลัง HUD */}
      <div className="relative h-[56vh] min-h-[340px] lg:absolute lg:inset-0 lg:h-auto">
        <TwinCanvas sysRef={sysRef} view={view} store={store} onModelFail={() => setModelFailed(true)} />
        <PartLabels store={store} />
        <LoadingOverlay failed={modelFailed} />
        <ViewToolbar view={viewState} onToggle={toggleView} className="absolute bottom-3 left-1/2 z-20 -translate-x-1/2 lg:hidden" />
      </div>

      {/* HUD */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 px-4 pt-4 sm:px-6 lg:inset-0 lg:flex lg:flex-col lg:p-5">
        <nav className="flex items-center justify-between gap-3">
          <Link href="/" className="glass pointer-events-auto flex items-center gap-2.5 rounded-full py-1.5 pl-1.5 pr-4">
            <span className="grid h-7 w-7 place-items-center rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 text-[11px] font-bold text-ink-950">DT</span>
            <span className="text-sm font-semibold tracking-tight">Digital Twin</span>
            <span className="hidden text-xs text-slate-500 sm:inline">← หน้าแนะนำ</span>
          </Link>
          <div className="flex items-center gap-2">
            <Link href="/analytics" className="glass pointer-events-auto rounded-full px-3 py-1.5 text-xs text-slate-200 transition hover:text-white">
              📊 Analytics
            </Link>
            <LinkPill link={link} s={s} send={send} connectTo={connectTo} disconnect={disconnect} />
          </div>
        </nav>

        <div className="hidden min-h-0 flex-1 gap-5 pt-5 lg:grid lg:grid-cols-[minmax(310px,350px)_1fr_minmax(300px,340px)]">
          <div className="flex min-h-0 flex-col gap-4 overflow-y-auto pb-2 [scrollbar-width:none]">
            <StateCard s={s} />
            <WarningBanner s={s} />
            <ControlPanel s={s} link={link} send={send} events={events} cameraAuto={cameraAuto} onCameraAuto={(v) => { setCamAuto(v); setCameraAuto(v); }} />
          </div>
          <div className="flex items-end justify-center pb-2">
            <ViewToolbar view={viewState} onToggle={toggleView} />
          </div>
          <div className="flex min-h-0 flex-col gap-4 overflow-y-auto pb-2 [scrollbar-width:none]">
            <CameraCard />
            <TempCard s={s} history={history} />
            <ProductionCard s={s} history={history} send={send} link={link} />
            <SensorCard s={s} link={link} />
            <FeedCard s={s} />
            <IoCard s={s} />
          </div>
        </div>
      </div>

      {/* มือถือ / แท็บเล็ต: การ์ดไหลต่อใต้ฉาก */}
      <div className="relative z-10 space-y-4 px-4 pb-10 pt-4 sm:px-6 lg:hidden">
        <WarningBanner s={s} />
        <div className="grid gap-4 sm:grid-cols-2">
          <StateCard s={s} />
          <ControlPanel s={s} link={link} send={send} events={events} cameraAuto={cameraAuto} onCameraAuto={(v) => { setCamAuto(v); setCameraAuto(v); }} />
          <CameraCard />
          <TempCard s={s} history={history} />
          <ProductionCard s={s} history={history} send={send} link={link} />
          <SensorCard s={s} link={link} />
          <FeedCard s={s} />
          <IoCard s={s} />
        </div>
      </div>
    </main>
  );
}

function ViewToolbar({ view, onToggle, className = '' }) {
  const item = (key, label) => (
    <button
      type="button"
      onClick={() => onToggle(key)}
      aria-pressed={view[key]}
      className={`rounded-full px-3 py-1.5 text-xs transition ${view[key] ? 'bg-sky-400/20 text-sky-100' : 'text-slate-300 hover:text-white'}`}
    >
      {label}
    </button>
  );
  return (
    <div className={`glass pointer-events-auto flex items-center gap-1 rounded-full p-1 ${className}`}>
      {item('exploded', 'แยกชิ้นส่วน')}
      {item('xray', 'โฮโลแกรม')}
      <span className="hidden px-2 text-[11px] text-slate-500 sm:inline">ลากเพื่อหมุน · เลื่อนเพื่อซูม</span>
    </div>
  );
}

// ไอคอนโซ่ — ปุ่ม Sync บอร์ด
const ChainIcon = ({ broken }) => (
  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1" />
    <path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1" />
    {broken && <path d="M4 4l16 16" />}
  </svg>
);

// ป้ายสถานะรวม + ปุ่ม Sync บอร์ด (27 ก.ย. 2569)
// เดิมแยก "LIVE" (เว็บ↔gateway) กับกล่อง Sync (gateway↔บอร์ด) ผู้ใช้สับสนว่าเป็นอันเดียวกัน → รวมเป็นป้ายเดียว:
//   DEMO · ในเบราว์เซอร์ (เหลือง) / จำลอง · ไม่สั่งบอร์ด (เขียว) / เครื่องจริง · Sync แล้ว (แดง)
// ปุ่มโซ่ข้างป้าย: Sync ต้องยืนยัน (กล่องใต้ป้าย) · เลิก Sync กดครั้งเดียว · gateway ที่ไม่มีคีย์ hw_sync = ป้าย LIVE แบบเดิม ไม่มีปุ่ม
// กดตัวป้าย (จุด + ข้อความ) = เปิดกล่อง "เชื่อมกับ gateway" (28 ก.ย. 2569)
function LinkPill({ link, s, send, connectTo, disconnect }) {
  const [confirm, setConfirm] = useState(false);
  const [panel, setPanel] = useState(false);
  const syncSupported = link.status === 'live' && 'hw_sync' in s;
  const synced = syncSupported && s.hw_sync === true;
  useEffect(() => setConfirm(false), [s.running, synced, link.status]);

  // สี (เจ้าของงานเลือก 27 ก.ย. 2569): DEMO เทา → จำลอง เหลือง → เครื่องจริง เขียว
  const map = {
    live: syncSupported
      ? synced
        ? { dot: 'bg-emerald-400', text: 'เครื่องจริง · Sync แล้ว', ring: 'ring-1 ring-emerald-400/60 bg-emerald-500/15', ink: 'text-emerald-100' }
        : { dot: 'bg-amber-400', text: 'จำลอง · ไม่สั่งบอร์ด', ring: '', ink: 'text-slate-200' }
      : { dot: 'bg-emerald-400', text: 'LIVE · gateway', ring: '', ink: 'text-slate-200' },
    demo: { dot: 'bg-slate-400', text: 'DEMO · ในเบราว์เซอร์', ring: '', ink: 'text-slate-200' },
    offline: { dot: 'bg-rose-400', text: 'OFFLINE', ring: '', ink: 'text-slate-200' },
    connecting: { dot: 'bg-sky-400', text: 'กำลังเชื่อมต่อ…', ring: '', ink: 'text-slate-200' },
  }[link.status];

  const feedBusy = s.feed_state === 'running';
  const blocked = s.running ? 'STOP เครื่องก่อนสลับ' : feedBusy ? 'รอ feed หยุดก่อน' : !synced && !s.hw_available ? 'บอร์ด I/O ไม่ตอบ' : '';
  const tip = synced
    ? 'ปุ่มบนเว็บสั่งเครื่องจริงอยู่'
    : syncSupported
      ? 'gateway จำลองเครื่อง บอร์ดได้เอาต์พุต 0'
      : link.status === 'demo'
        ? 'ไม่มี gateway — ตัวจำลองในเบราว์เซอร์'
        : link.url;

  return (
    <div className="pointer-events-auto relative">
      <div title={tip} className={`glass flex items-center gap-2 rounded-full py-1.5 pl-3 text-xs ${syncSupported ? 'pr-1.5' : 'pr-3'} ${map.ring}`}>
        <button
          type="button"
          onClick={() => { setConfirm(false); setPanel((v) => !v); }}
          aria-expanded={panel}
          className="flex items-center gap-2 rounded-full hover:opacity-80"
        >
          <span className={`pulse-dot h-2 w-2 rounded-full ${map.dot}`} />
          <span className={`font-medium ${map.ink}`}>{map.text}</span>
        </button>
        {syncSupported && (
          <button
            type="button"
            onClick={() => { setPanel(false); synced ? send('SYNC', { value: false }) : setConfirm((v) => !v); }}
            disabled={Boolean(blocked)}
            aria-label={synced ? 'เลิก Sync บอร์ด' : 'Sync บอร์ด'}
            title={blocked || (synced ? 'เลิก Sync — กลับเป็นจำลอง บอร์ดได้ 0 ปล่อย C' : 'Sync บอร์ด — สั่งเครื่องจริง')}
            className={`grid h-6 w-6 place-items-center rounded-full border transition disabled:cursor-not-allowed disabled:opacity-35 ${
              synced ? 'border-emerald-300/50 bg-emerald-500/25 text-emerald-100 hover:bg-emerald-500/40' : 'border-white/15 bg-white/[0.06] text-slate-200 hover:bg-white/[0.14]'
            }`}
          >
            <ChainIcon broken={synced} />
          </button>
        )}
      </div>
      {confirm && (
        <div className="glass absolute right-0 top-full z-30 mt-2 w-64 rounded-xl border border-amber-300/30 p-3 text-xs shadow-xl">
          <div className="font-semibold text-amber-200">Sync บอร์ด — เครื่องจะขยับจริง</div>
          <div className="mt-1 text-[11px] text-slate-300">มอเตอร์ · โซลินอยด์ · Cylinder C · กล้อง ทำงานจริง ให้แน่ใจว่าไม่มีคนอยู่ในพื้นที่เครื่อง</div>
          <div className="mt-2.5 flex justify-end gap-2">
            <button type="button" onClick={() => setConfirm(false)} className="rounded-lg border border-white/10 bg-white/[0.06] px-3 py-1.5 text-slate-200 hover:bg-white/[0.12]">
              ยกเลิก
            </button>
            <button
              type="button"
              onClick={() => { setConfirm(false); send('SYNC', { value: true }); }}
              className="rounded-lg border border-rose-300/40 bg-rose-500/30 px-3 py-1.5 font-semibold text-rose-50 hover:bg-rose-500/45"
            >
              ยืนยัน Sync
            </button>
          </div>
        </div>
      )}
      {panel && <ConnectPanel link={link} s={s} connectTo={connectTo} disconnect={disconnect} onClose={() => setPanel(false)} />}
    </div>
  );
}

// กล่อง "เชื่อมกับ gateway" — แบบเดียวกับเว็บของเพื่อน แต่ขั้นตอนชี้ไป START.bat ของเรา
// (ไม่มีไฟล์ dt-gateway.zip ให้ดาวน์โหลด — gateway เราต้องรันจากโฟลเดอร์ Wab ที่มีกล้อง/บอร์ด)
// ปุ่มเดียวสลับ: กด 1 ครั้ง = เชื่อม · กดอีกครั้ง = เลิกเชื่อม (กลับตัวจำลอง) · แก้ที่อยู่แล้วปุ่มกลับเป็น "เชื่อม" (ย้ายปลายทาง)
// เลิกเชื่อมตอนเครื่องเดินไม่ได้ — เว็บจะเสียปุ่ม E-STOP ขณะ gateway ยังเดินเครื่องต่อ
function ConnectPanel({ link, s, connectTo, disconnect, onClose }) {
  const [draft, setDraft] = useState(link.url || DEFAULT_WS_URL);
  const inputId = useId();
  const url = draft.trim();
  const valid = url === '' || /^wss?:\/\/\S+$/.test(url);
  const willDisconnect = link.enabled && url === link.url;
  const blocked = willDisconnect && link.status === 'live' && s.running ? 'STOP เครื่องก่อนเลิกเชื่อม' : '';
  const status = !link.enabled
    ? { text: 'ยังไม่ได้เชื่อม — ใช้ตัวจำลองในเบราว์เซอร์', ink: 'text-slate-400' }
    : {
        live: { text: `เชื่อมแล้ว — ${link.url}`, ink: 'text-emerald-300' },
        demo: { text: `รอ gateway ที่ ${link.url} — ใช้ตัวจำลองไปก่อน`, ink: 'text-amber-200' },
        connecting: { text: `กำลังเชื่อมต่อ ${link.url}…`, ink: 'text-sky-300' },
        offline: { text: `เชื่อมไม่ได้ — ${link.url}`, ink: 'text-rose-300' },
      }[link.status];

  return (
    <div className="absolute right-0 top-full z-30 mt-2 w-[min(22rem,calc(100vw-2rem))] rounded-2xl border border-white/10 bg-ink-900 p-4 text-sm shadow-2xl shadow-black/60">
      <div className="flex items-start justify-between gap-3">
        <div className="text-base font-semibold text-slate-100">เชื่อมกับ gateway</div>
        <button type="button" onClick={onClose} aria-label="ปิด" className="-mr-1 -mt-1 rounded-full px-2 text-slate-400 hover:text-white">
          ✕
        </button>
      </div>
      <p className="mt-1 text-xs text-slate-400">
        ไม่เชื่อมก็ใช้ได้ — ทุกปุ่มจะสั่งตัวจำลองในเบราว์เซอร์ · ถ้ามี gateway รันอยู่ กดเชื่อมเพื่อให้ปุ่มสั่งงานจริง
      </p>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (blocked) return;
          if (willDisconnect) disconnect();
          else if (valid) connectTo(url);
        }}
      >
        <label htmlFor={inputId} className="sr-only">
          ที่อยู่ gateway
        </label>
        <input
          id={inputId}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          spellCheck={false}
          placeholder={DEFAULT_WS_URL}
          className={`min-w-0 flex-1 rounded-xl border bg-black/30 px-3 py-2 font-mono text-sm text-slate-100 outline-none ${
            valid ? 'border-white/10 focus:border-sky-400/60' : 'border-rose-400/60'
          }`}
        />
        <button
          type="submit"
          disabled={willDisconnect ? Boolean(blocked) : !valid}
          title={blocked}
          className={`shrink-0 rounded-xl px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-40 ${
            willDisconnect
              ? 'border border-white/15 bg-white/[0.06] text-slate-100 hover:bg-white/[0.14]'
              : 'bg-sky-400 text-ink-950 hover:bg-sky-300'
          }`}
        >
          {willDisconnect ? 'เลิกเชื่อม' : 'เชื่อม'}
        </button>
      </form>
      <div className={`mt-2 text-xs ${!valid || blocked ? 'text-rose-300' : status.ink}`}>
        {!valid ? 'ต้องขึ้นต้นด้วย ws:// หรือ wss://' : blocked || status.text}
      </div>

      <div className="mt-4 border-t border-white/10 pt-3">
        <div className="text-xs font-semibold text-slate-200">ยังไม่มี gateway?</div>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-xs text-slate-300">
          <li>
            ดับเบิลคลิก <code className="font-mono text-slate-100">START.bat</code> ในโฟลเดอร์ <code className="font-mono text-slate-100">Wab</code>
          </li>
          <li>รอหน้าต่าง gateway ขึ้น (เปิดมาเป็นโหมดจำลองเสมอ ยังไม่สั่งบอร์ด)</li>
          <li>
            กลับมากด <b>เชื่อม</b> ที่ <code className="font-mono text-slate-100">{DEFAULT_WS_URL}</code>
          </li>
        </ol>
        <p className="mt-3 text-[11px] text-slate-500">
          เว็บต่อ gateway ให้เองอยู่แล้วเมื่อเปิดจาก START.bat · ที่อยู่ที่พิมพ์/การเลิกเชื่อม ใช้จนกว่าจะ reload หน้า (reload = กลับไปต่อ gateway ของ START.bat) · สั่งเครื่องจริงต้องกดปุ่มโซ่ (Sync) อีกขั้น
        </p>
      </div>
    </div>
  );
}

function StateCard({ s }) {
  const alarm = s.current_state === ALARM_STATE;
  const idx = stateIndex(s.current_state);
  return (
    <Card
      title="FSM State"
      icon={Icon.flow}
      right={<span className="rounded-md bg-white/5 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-slate-300">mode · {s.mode}</span>}
    >
      <div className={`font-mono text-xl font-semibold tracking-tight ${alarm ? 'text-rose-300' : 'text-white'}`}>{s.current_state}</div>
      <div className="mt-0.5 text-sm text-slate-400">{stateLabel(s.current_state)}</div>
      <div className="mt-3 flex gap-[3px]" aria-label={`สเต็ป ${idx + 1} จาก ${STATES.length}`}>
        {STATES.map((st, i) => (
          <span
            key={st.id}
            title={st.id}
            className={`relative h-1.5 flex-1 rounded-full transition-colors duration-200 ${
              alarm ? 'bg-rose-500/40' : i === idx ? 'bg-sky-400 shadow-[0_0_8px_#38bdf8]' : i < idx ? 'bg-sky-400/35' : 'bg-white/[0.07]'
            }`}
          >
            {DECISION_CHECKPOINTS.includes(st.id) && <span className="absolute -top-1.5 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-amber-300/80" />}
          </span>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
        <span className={`rounded-full px-2 py-0.5 ${s.running ? 'bg-emerald-400/15 text-emerald-300' : 'bg-white/5 text-slate-400'}`}>
          {s.running ? '● RUNNING' : '○ STOPPED'}
        </span>
        {s.step_allowed && <span className="rounded-full bg-amber-400/15 px-2 py-0.5 text-amber-300">รอ operator PASS / NG</span>}
        {s.step_wait && <span className="rounded-full bg-indigo-400/15 px-2 py-0.5 text-indigo-300">รอ NEXT</span>}
      </div>
    </Card>
  );
}

function WarningBanner({ s }) {
  const alarm = s.current_state === ALARM_STATE;
  if (!s.predictive_warning && !alarm) return null;
  return (
    <div role="status" className={`glass pointer-events-auto flex items-start gap-3 rounded-2xl px-4 py-3 text-sm ring-1 ${alarm ? 'ring-rose-400/40' : 'ring-amber-400/30'}`}>
      <span className={`pulse-dot mt-1.5 h-2 w-2 shrink-0 rounded-full ${alarm ? 'bg-rose-400' : 'bg-amber-400'}`} />
      <span className={alarm ? 'text-rose-200' : 'text-amber-100'}>{s.predictive_warning || 'ALARM — กด RESET'}</span>
    </div>
  );
}

function TempCard({ s, history }) {
  const t = Number(s.current_temp) || 0;
  const lv = tempLevel(t);
  const color = lv === 'over' ? '#f87171' : lv === 'high' || lv === 'low' ? '#fbbf24' : '#38bdf8';
  return (
    <Card title="Heater" icon={Icon.temp} right={<span className="font-mono text-[10px] text-slate-500">limit {TEMP_LIMIT}°C</span>}>
      <div className="flex items-end gap-1">
        <span className="font-mono text-4xl font-semibold tabular-nums" style={{ color }}>{t}</span>
        <span className="mb-1 text-sm text-slate-400">°C</span>
      </div>
      <div className="mt-2">
        <Sparkline data={history.temp} min={120} max={210} limit={TEMP_LIMIT} color={color} />
      </div>
      <div className="mt-1 text-[10px] text-slate-500">ช่วงซีล {SEAL.tempMinC}–{SEAL.tempMaxC} °C · 45 วินาทีล่าสุด · gateway ยังส่งค่าจำลอง ไม่ใช่เซนเซอร์จริง</div>
    </Card>
  );
}

// แถบหลุมใน batch (27 ก.ย. 2569) — gateway 01_DigitalTwin: หลุมว่างหน้า · ชิ้นงาน · หลุมว่างท้าย
// จุดกลม = หลุมว่าง (เขียว = ผ่านแล้ว / ฟ้า = หลุมปัจจุบัน) · แถบกลาง = ชิ้นงานที่ทำแล้ว / เป้า
function PocketTrack({ s }) {
  const lead = Number(s.leader_pockets) || 0;
  const trail = Number(s.trailer_pockets) || 0;
  const target = Number(s.target_pieces) || 0;
  const total = Number(s.batch_pockets) || lead + target + trail;
  const pocket = Number(s.pocket) || 1;
  const done = pocket > total;
  const phase = done
    ? 'จบ batch แล้ว — กด RESET เพื่อเริ่ม batch ใหม่'
    : pocket <= lead
      ? `หลุมว่างหน้า ${pocket}/${lead} — ไม่วางชิ้นงาน (feed + ซีลตามปกติ)`
      : pocket > lead + target
        ? `หลุมว่างท้าย ${pocket - lead - target}/${trail} — ไม่วางชิ้นงาน`
        : `ชิ้นงานที่ ${pocket - lead} จาก ${target} — วางชิ้นงานก่อนถึง VISION`;
  const pip = (n, key) => (
    <span
      key={key}
      className={`h-2 w-2 shrink-0 rounded-full ${pocket === n && !done ? 'bg-sky-400 shadow-[0_0_6px_#38bdf8]' : pocket > n ? 'bg-emerald-400/80' : 'bg-white/15'}`}
    />
  );
  const pcs = Number(s.pieces_count) || 0;
  return (
    <div className="mt-3 border-t border-white/10 pt-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[10px] uppercase tracking-[0.14em] text-slate-500">pocket</span>
        <span className="font-mono text-sm tabular-nums text-slate-100">
          {Math.min(pocket, total)} <span className="text-[11px] text-slate-500">/ {total}</span>
        </span>
      </div>
      <div className="mt-1.5 flex items-center gap-1" aria-label={phase}>
        {Array.from({ length: lead }, (_, i) => pip(i + 1, `l${i}`))}
        <div className="relative mx-0.5 h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.07]">
          <div className="h-full rounded-full bg-emerald-400/70 transition-[width] duration-300" style={{ width: `${target ? Math.min(100, (pcs / target) * 100) : 0}%` }} />
        </div>
        {Array.from({ length: trail }, (_, i) => pip(lead + target + i + 1, `t${i}`))}
      </div>
      <div className={`mt-1 text-[11px] ${done ? 'text-emerald-300' : 'text-slate-400'}`}>{phase}</div>
    </div>
  );
}

// ตั้งเป้าชิ้นงานต่อ batch — gateway รับเฉพาะตอนเครื่องหยุด (SET_PARAMS · ตอนเดินขึ้น TARGET LOCKED)
function TargetEditor({ s, send, disabled }) {
  const target = Number(s.target_pieces) || 0;
  const [draft, setDraft] = useState(String(target));
  const inputId = useId(); // การ์ดถูกวาด 2 ชุด (จอใหญ่ / มือถือ) id ต้องไม่ซ้ำ
  useEffect(() => setDraft(String(target)), [target]);
  const n = Number(draft);
  const valid = Number.isInteger(n) && n >= 1 && n <= 10000;
  // พิมพ์แล้วยังไม่กด "ตั้ง" — เคยทำให้เข้าใจผิดว่าตั้งแล้ว (27 ก.ย.: พิมพ์ 2 แต่เป้ายัง 200 เครื่องเลยไม่หยุด)
  const pending = draft.trim() !== '' && n !== target;
  const apply = () => valid && n !== target && send('SET_PARAMS', { target_pieces: n });
  return (
    <form
      className="mt-3 flex flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        apply();
      }}
    >
      <label htmlFor={inputId} className="text-[10px] uppercase tracking-[0.14em] text-slate-500">
        เป้า batch
      </label>
      <input
        id={inputId}
        type="number"
        min={1}
        max={10000}
        inputMode="numeric"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        disabled={disabled || s.running}
        className={`w-20 rounded-lg border bg-black/30 px-2 py-1 font-mono text-sm tabular-nums text-slate-100 outline-none disabled:opacity-40 ${
          pending ? 'border-amber-300/70 ring-1 ring-amber-300/40' : 'border-white/10 focus:border-sky-400/60'
        }`}
      />
      <span className="text-[11px] text-slate-500">ชิ้น</span>
      <button
        type="submit"
        disabled={disabled || s.running || !valid || n === target}
        title={s.running ? 'STOP เครื่องก่อนเปลี่ยนเป้า' : ''}
        className="rounded-lg border border-sky-300/30 bg-sky-400/15 px-3 py-1 text-xs text-sky-100 transition hover:bg-sky-400/25 disabled:cursor-not-allowed disabled:opacity-35"
      >
        ตั้ง
      </button>
      <span className={`w-full text-[10px] ${pending ? 'text-amber-200' : 'text-slate-500'}`}>
        {pending
          ? s.running
            ? `ยังไม่ได้ตั้ง — เป้าตอนนี้ ${target} · STOP ก่อนแล้วกด "ตั้ง"`
            : `ยังไม่ได้ตั้ง — เป้าตอนนี้ ${target} · กด "ตั้ง" หรือ Enter`
          : s.running
            ? 'STOP ก่อนเปลี่ยนเป้า'
            : 'หลุมทั้ง batch = หลุมว่างหน้า + เป้า + หลุมว่างท้าย · ลองเป้าเล็ก ๆ เช่น 3 เพื่อดูครบวงจร'}
      </span>
    </form>
  );
}

function ProductionCard({ s, history, send, link }) {
  const pcs = Number(s.pieces_count) || 0;
  const target = Number(s.target_pieces) || 0;
  const h = history.pieces;
  // ชิ้น/นาทีจากหน้าต่าง 45 วิ — ข้ามจังหวะรีเซ็ต (ติดลบ) และจังหวะกระโดด (เพิ่งต่อ / สลับแหล่งข้อมูล)
  let gained = 0;
  for (let i = 1; i < h.length; i++) {
    const d = h[i] - h[i - 1];
    if (d > 0 && d <= 10) gained += d;
  }
  const rate = h.length > 4 ? (gained / ((h.length - 1) * 0.5)) * 60 : 0;
  return (
    <Card title="Production" icon={Icon.box}>
      <div className="flex items-center gap-4">
        <Ring value={pcs} max={target}>
          <span className="font-mono text-xs tabular-nums text-slate-300">{target ? `${Math.round((pcs / target) * 100)}%` : '—'}</span>
        </Ring>
        <div className="grid flex-1 grid-cols-2 gap-x-3 gap-y-2">
          <Stat label="pieces" value={pcs.toLocaleString()} />
          <Stat label="target" value={target ? target.toLocaleString() : '—'} />
          <Stat label="cycles" value={(Number(s.cycles) || 0).toLocaleString()} />
          <Stat label="rate" value={rate.toFixed(0)} unit="pcs/min" />
        </div>
      </div>
      {'batch_pockets' in s && <PocketTrack s={s} />}
      {send && <TargetEditor s={s} send={send} disabled={link?.status !== 'live' && link?.status !== 'demo'} />}
    </Card>
  );
}

// สถานะเซนเซอร์ / อุปกรณ์รอบเครื่อง — สรุปจากคีย์ที่ gateway ส่งมา (ไม่มีคีย์ใหม่)
function SensorCard({ s, link }) {
  const t = Number(s.current_temp) || 0;
  const alarm = s.current_state === ALARM_STATE;
  const rows = [
    {
      name: 'Heater',
      detail: tempLevel(t) === 'high' || tempLevel(t) === 'low' ? `${t} °C · รอที่ CHECK_TEMP` : `${t} °C`,
      level: { over: 'bad', high: 'warn', low: 'warn', ok: 'ok', idle: 'idle' }[tempLevel(t)],
      text: { over: 'OVER', high: 'HIGH', low: 'LOW', ok: 'OK', idle: '—' }[tempLevel(t)],
    },
    {
      name: 'Vision camera',
      detail: `${(Number(s.camera1_count) || 0).toLocaleString()} ครั้ง`,
      level: s.current_state === 'VISION' && s.step_allowed ? 'warn' : s.current_state === 'VISION' ? 'active' : 'ok',
      text: s.current_state === 'VISION' ? (s.step_allowed ? 'WAIT' : 'SCAN') : 'READY',
    },
    {
      name: 'Feed encoder',
      detail: (Number(s.encoder_count) || 0).toLocaleString(),
      level: s.current_state === 'FEED_CARRIER' && s.running ? 'active' : 'ok',
      text: s.current_state === 'FEED_CARRIER' && s.running ? 'MOVING' : 'IDLE',
    },
    {
      name: 'Board input ip0',
      detail: `0x${(Number(s.ip0) || 0).toString(16).toUpperCase().padStart(2, '0')}`,
      level: Number(s.ip0) ? 'active' : 'idle',
      text: Number(s.ip0) ? 'ON' : 'OFF',
    },
    {
      name: 'Safety chain',
      detail: alarm ? s.predictive_warning || 'ALARM' : 'ไม่มี alarm',
      level: alarm ? 'bad' : 'ok',
      text: alarm ? 'TRIP' : 'OK',
    },
    {
      name: 'Gateway link',
      detail: link.status === 'live' ? link.url.replace(/^wss?:\/\//, '') : 'ตัวจำลองในเบราว์เซอร์',
      level: link.status === 'live' ? 'ok' : link.status === 'demo' ? 'warn' : 'bad',
      text: link.status === 'live' ? 'LIVE' : link.status === 'demo' ? 'DEMO' : 'DOWN',
    },
  ];
  const dot = { ok: 'bg-emerald-400', warn: 'bg-amber-400', bad: 'bg-rose-400', active: 'bg-sky-400', idle: 'bg-slate-600' };
  const txt = { ok: 'text-emerald-300', warn: 'text-amber-300', bad: 'text-rose-300', active: 'text-sky-300', idle: 'text-slate-500' };
  return (
    <Card title="Sensors" icon={Icon.sensor}>
      <ul className="space-y-2">
        {rows.map((r) => (
          <li key={r.name} className="flex items-center gap-2.5 text-xs">
            <span className={`h-2 w-2 shrink-0 rounded-full ${dot[r.level]} ${r.level === 'active' || r.level === 'bad' ? 'pulse-dot' : ''}`} />
            <span className="text-slate-200">{r.name}</span>
            <span className="min-w-0 flex-1 truncate text-right text-slate-500">{r.detail}</span>
            <span className={`w-14 text-right font-mono text-[10px] ${txt[r.level]}`}>{r.text}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function FeedCard({ s }) {
  // feature detection ตาม protocol.md ข้อ 8.5 — gateway รุ่นเก่าไม่มีคีย์ feed_*
  if (!('feed_state' in s)) {
    return (
      <Card title="Feed motor" icon={Icon.motor}>
        <div className="text-xs text-slate-500">gateway ตัวนี้ยังไม่ส่งคีย์ feed_* (ต้องเป็นรุ่นที่ทำ protocol ข้อ 8 แล้ว)</div>
      </Card>
    );
  }
  const total = Number(s.feed_total) || 0;
  const sent = Number(s.feed_sent) || 0;
  const pct = total ? Math.min(100, (sent / total) * 100) : 0;
  const stateColor =
    { running: 'text-sky-300', done: 'text-emerald-300', aborted: 'text-amber-300', error: 'text-rose-300' }[s.feed_state] ?? 'text-slate-400';
  return (
    <Card
      title="Feed motor"
      icon={Icon.motor}
      right={
        s.feed_src && (
          <span className={`rounded-md px-2 py-0.5 font-mono text-[10px] ${s.feed_src === 'SIM' ? 'bg-amber-400/15 text-amber-300' : 'bg-emerald-400/15 text-emerald-300'}`}>
            {s.feed_src === 'SIM' ? 'SIM · ไม่ได้หมุนจริง' : 'REAL'}
          </span>
        )
      }
    >
      <div className="flex items-baseline justify-between">
        {/* protocol.md 8.4: "done" = ส่งพัลส์ครบ ไม่ใช่เทปเดินครบ (open loop) */}
        <span className={`font-mono text-sm ${stateColor}`}>{s.feed_state === 'done' ? 'done · ส่งพัลส์ครบ' : s.feed_state}</span>
        <span className="font-mono text-xs tabular-nums text-slate-400">
          {sent}/{total} pulses
        </span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
        <div className="h-full rounded-full bg-gradient-to-r from-sky-400 to-indigo-400 transition-[width] duration-150" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <Stat label="pitch #" value={s.feed_index ?? 0} />
        <Stat label="Σ pulses" value={(Number(s.feed_pulses) || 0).toLocaleString()} />
        <Stat label="½ period" value={s.feed_half_ms ?? '—'} unit="ms" />
      </div>
    </Card>
  );
}

function IoCard({ s }) {
  return (
    <Card title="I/O" icon={Icon.chip} right={<span className="font-mono text-[10px] text-slate-500">bit 0 → 7</span>}>
      <div className="space-y-2">
        <Bits label="op0" value={s.op0} names={OP0_BITS} />
        <Bits label="op1" value={s.op1} names={OP1_BITS} />
        <Bits label="ip0" value={s.ip0} names={Array(8).fill('input')} />
      </div>
    </Card>
  );
}
