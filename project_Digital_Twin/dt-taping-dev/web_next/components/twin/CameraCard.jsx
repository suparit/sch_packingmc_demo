'use client';

import { useEffect, useState } from 'react';
import { Card } from '@/components/ui/Telemetry.jsx';

// การ์ดกล้อง HIKROBOT บนหน้า /twin (28 ก.ย. 2569) — ย้ายของจากหน้า :5000 มาไว้ที่เดียวกับปุ่มควบคุม
//   แท็บ "ชิ้นงาน" = ภาพที่ตรวจ + PASS/FAIL + ผลตรวจ 4 ข้อ · แท็บ "Carrier" = ระยะหลุมเทียบเส้น index + ตั้ง index
// ข้อมูลมาจากแอปกล้อง 03_Vision/ocr/app_vision_ocr.py ผ่านตัวกลาง /camera/... ของเว็บ (app/camera/[...path]/route.js)
// ดูอย่างเดียว — PASS/FAIL ส่งให้ FSM โดยแอปกล้องเอง ไม่ผ่านการ์ดนี้

const POLL_MS = 1000;

const CameraIcon = (
  <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M4 7h3l2-2.5h6L17 7h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z" />
    <circle cx="12" cy="13" r="3.5" />
  </svg>
);

function useCameraStatus() {
  const [st, setSt] = useState(null); // null = ยังไม่เคยได้ · { offline: true } = แอปกล้องไม่ได้เปิด
  useEffect(() => {
    let stop = false;
    let timer;
    const tick = async () => {
      try {
        const r = await fetch('/camera/api/status', { cache: 'no-store' });
        const j = await r.json();
        if (!stop) setSt(r.ok ? j : { offline: true });
      } catch {
        if (!stop) setSt({ offline: true });
      }
      if (!stop) timer = setTimeout(tick, POLL_MS);
    };
    tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, []);
  return st;
}

function Badge({ tone, children }) {
  const tones = {
    ok: 'bg-emerald-500/85 text-white',
    ng: 'bg-rose-500/85 text-white',
    idle: 'bg-white/10 text-slate-300',
  };
  return <span className={`rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold ${tones[tone]}`}>{children}</span>;
}

export default function CameraCard() {
  const st = useCameraStatus();
  const [tab, setTab] = useState('part');
  // ตั้งเส้น index ด้วยการคลิกบนภาพ (28 ก.ย. 2569 — แบบให้โปรแกรมหาเองจับขอบช่องด้านในหลุมผิดเส้น)
  // picking = รอคลิก · pickedY = แถวที่คลิก (สัดส่วน 0..1 ของความสูงภาพ) รอกดยืนยัน · hoverY = เส้นนำตามเมาส์
  const [picking, setPicking] = useState(false);
  const [pickedY, setPickedY] = useState(null);
  const [hoverY, setHoverY] = useState(null);
  const [indexMsg, setIndexMsg] = useState('');

  const offline = !st || st.offline;
  const cam = !offline && st.camera;
  const c = (!offline && st.carrier) || {};
  const seq = !offline ? st.seq : 0;
  // แท็บชิ้นงาน: ภาพนิ่งที่ใช้ตัดสินชิ้นล่าสุด (ค้างไว้ให้คนอ่าน จนตัดสินชิ้นถัดไป) หรือภาพสด (28 ก.ย. 2569)
  const [showDecision, setShowDecision] = useState(true);
  const dec = !offline && st.decision;
  const useDec = showDecision && Boolean(dec);
  const shownFields = useDec ? dec.fields : st?.fields;
  // ผลตรวจ 4 ข้อหลัก = ช่องที่ขึ้นต้นด้วยเลข ("1 มีชิ้นงาน" …) · ที่เหลือ (BRAND / PART NR …) เป็นค่าที่อ่านได้
  const checks = (!offline && Array.isArray(shownFields) ? shownFields : []).filter((f) => /^\d/.test(f.name));
  const readings = (!offline && Array.isArray(shownFields) ? shownFields : []).filter((f) => !/^\d/.test(f.name) && f.value && f.value !== '—');

  const cancelPick = () => {
    setPicking(false);
    setPickedY(null);
    setHoverY(null);
  };
  // แถวใต้เมาส์: f = สัดส่วนความสูงภาพ (ส่งให้แอปกล้อง) + ตำแหน่ง px ในกรอบ (วาดเส้นนำทับภาพ)
  const rowAt = (e) => {
    const img = e.currentTarget;
    const r = img.getBoundingClientRect();
    const f = (e.clientY - r.top) / r.height;
    if (!(f >= 0 && f <= 1)) return null;
    return { f, top: img.offsetTop + f * img.offsetHeight, left: img.offsetLeft, width: img.offsetWidth };
  };
  const guide = (g, cls) =>
    g && <div aria-hidden className={`pointer-events-none absolute h-0 border-t-2 border-dashed ${cls}`} style={{ top: g.top, left: g.left, width: g.width }} />;

  const setIndex = async () => {
    const y = pickedY?.f;
    cancelPick();
    if (y == null) return;
    try {
      const r = await fetch(`/camera/api/set_index?y=${y.toFixed(4)}`, { method: 'POST' });
      setIndexMsg(r.ok ? 'ตั้งเส้น index ใหม่แล้ว' : 'ตั้งไม่ได้ — แอปกล้องไม่ตอบ');
    } catch {
      setIndexMsg('ตั้งไม่ได้ — แอปกล้องไม่ตอบ');
    }
    setTimeout(() => setIndexMsg(''), 4000);
  };

  const head = offline ? (
    <Badge tone="idle">OFFLINE</Badge>
  ) : !cam ? (
    <Badge tone="idle">ไม่มีกล้อง</Badge>
  ) : tab === 'part' && useDec ? (
    <Badge tone={dec.passed ? 'ok' : 'ng'}>{dec.passed ? 'PASS' : 'NG'}</Badge>
  ) : tab === 'part' ? (
    <Badge tone={st.passed ? 'ok' : 'ng'}>{st.passed ? 'PASS' : 'FAIL'}</Badge>
  ) : c.off_mm == null ? (
    <Badge tone="idle">{c.set ? 'วัดไม่ได้' : 'ยังไม่ตั้ง index'}</Badge>
  ) : (
    <Badge tone={c.ok ? 'ok' : 'ng'}>{`${c.off_mm > 0 ? '+' : ''}${Number(c.off_mm).toFixed(2)} mm`}</Badge>
  );

  // ลิงก์หน้ากล้องเต็มใช้ host เดียวกับที่เปิดเว็บ (เครื่องอื่นในวงเดียวกันก็กดได้) — ตั้งหลัง mount
  // ถ้าคิดตอน render ค่าฝั่ง server (127.0.0.1) กับฝั่งเบราว์เซอร์ (localhost) ไม่ตรงกัน = hydration error
  const [fullPage, setFullPage] = useState('http://127.0.0.1:5000');
  useEffect(() => setFullPage(`http://${window.location.hostname}:5000`), []);

  return (
    <Card title="Vision camera" icon={CameraIcon} right={head}>
      <div className="mb-2 grid grid-cols-2 gap-1 rounded-lg border border-white/10 bg-black/20 p-0.5 text-xs" role="tablist">
        {[
          ['part', 'ชิ้นงาน'],
          ['carrier', 'Carrier'],
        ].map(([k, label]) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={tab === k}
            onClick={() => {
              setTab(k);
              cancelPick();
            }}
            className={`rounded-md py-1 transition ${tab === k ? 'bg-sky-400/20 text-sky-100' : 'text-slate-400 hover:text-slate-200'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {offline ? (
        <p className="py-6 text-center text-xs text-slate-500">
          แอปกล้องไม่ได้เปิด (หน้า :5000) — เปิดด้วย START.bat
        </p>
      ) : (
        <>
          <div
            className={`relative grid aspect-[4/3] w-full place-items-center overflow-hidden rounded-lg border bg-black ${
              picking && tab === 'carrier' ? 'border-amber-300/70' : 'border-white/10'
            }`}
          >
            {cam ? (
              // eslint-disable-next-line @next/next/no-img-element -- ภาพสดจากแอปกล้อง เปลี่ยนทุกวินาที ไม่ต้อง optimize
              <img
                src={
                  tab === 'part' && useDec
                    ? `/camera/decision.jpg?d=${encodeURIComponent(`${dec.time}_${dec.pocket}`)}` // เปลี่ยนเฉพาะตอนตัดสินชิ้นใหม่
                    : `/camera/${tab === 'part' ? 'roi.jpg' : 'carrier.jpg'}?t=${seq}`
                }
                alt={tab === 'part' ? 'ภาพชิ้นงานที่กล้องตรวจ' : 'ภาพหลุม carrier เทียบเส้น index'}
                className={`max-h-full max-w-full object-contain ${picking && tab === 'carrier' ? 'cursor-crosshair' : ''}`}
                onMouseMove={picking && tab === 'carrier' ? (e) => setHoverY(rowAt(e)) : undefined}
                onMouseLeave={() => setHoverY(null)}
                onClick={
                  picking && tab === 'carrier'
                    ? (e) => {
                        const g = rowAt(e);
                        if (g) {
                          setPickedY(g);
                          setPicking(false);
                          setHoverY(null);
                        }
                      }
                    : undefined
                }
              />
            ) : (
              <span className="text-xs text-slate-500">{st.reason || 'กล้องกำลังเชื่อมต่อ…'}</span>
            )}
            {tab === 'carrier' && guide(hoverY, 'border-amber-300/80')}
            {tab === 'carrier' && guide(pickedY, 'border-amber-300')}
          </div>

          {tab === 'part' ? (
            <div className="mt-2 space-y-0.5">
              <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[10px]">
                {[
                  [true, 'ภาพที่ใช้ตัดสิน'],
                  [false, 'ภาพสด'],
                ].map(([v, label]) => (
                  <button
                    key={label}
                    type="button"
                    aria-pressed={showDecision === v}
                    onClick={() => setShowDecision(v)}
                    className={`rounded-md border px-2 py-0.5 transition ${
                      showDecision === v ? 'border-sky-300/40 bg-sky-400/20 text-sky-100' : 'border-white/10 text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {label}
                  </button>
                ))}
                <span className="text-slate-500">
                  {useDec
                    ? `ภาพนิ่งที่ส่งผลให้ FSM · ${dec.time}${dec.pocket != null ? ` · หลุม ${dec.pocket}` : ''}`
                    : showDecision
                      ? 'ยังไม่มีภาพที่ใช้ตัดสิน — แสดงภาพสด'
                      : 'ภาพสด (อัปเดตทุกวินาที)'}
                </span>
              </div>
              {checks.map((f) => (
                <div key={f.name} className={`flex items-center justify-between gap-2 text-xs ${f.ok ? 'text-emerald-300' : f.required ? 'text-rose-300' : 'text-slate-500'}`}>
                  <span className="shrink-0">
                    {f.ok ? '✓' : '✗'} {f.name}
                  </span>
                  <span className="truncate text-right text-[11px] text-slate-400" title={String(f.value)}>
                    {String(f.value)}
                  </span>
                </div>
              ))}
              {readings.length > 0 && (
                <div className="pt-1 font-mono text-[10px] text-slate-500">{readings.map((f) => `${f.name.replace('· ', '')}=${f.value}`).join(' · ')}</div>
              )}
              <div className="pt-1 text-[10px] text-slate-500">
                ส่งให้ FSM ล่าสุด: {st.last_sent || '—'} · OCR {st.ocr_ms ?? '—'} ms · สว่าง {st.brightness ?? '—'}
              </div>
            </div>
          ) : (
            <div className="mt-2 space-y-1.5">
              <div className={`text-xs ${c.off_mm == null ? 'text-slate-400' : c.ok ? 'text-emerald-300' : 'text-rose-300'}`}>
                {c.off_mm == null ? c.msg || '—' : `${c.ok ? 'ตรง index' : 'ไม่ตรง index'} (เกณฑ์ ±${c.tol_mm} mm)`}
              </div>
              {c.off_mm != null && c.msg && <div className="text-[10px] text-slate-500">{c.msg}{c.score != null ? ` · คะแนนแม่แบบ ${c.score}` : ''}</div>}
              <div className="text-[10px] text-slate-500">เส้นเขียว = index · เส้นส้ม = ตำแหน่งเดียวกันของหลุมตอนนี้ · ดูอย่างเดียว ไม่ส่งผลให้ FSM</div>
              {picking ? (
                <div className="flex flex-wrap items-center gap-2 text-[11px]">
                  <span className="text-amber-200">คลิกบนภาพตรงแถวที่จะให้เป็นเส้น index (เช่น ขอบบนของหลุม)</span>
                  <button type="button" onClick={cancelPick} className="rounded-lg border border-white/10 bg-white/[0.06] px-3 py-1 text-slate-200">
                    ยกเลิก
                  </button>
                </div>
              ) : pickedY == null ? (
                <button
                  type="button"
                  onClick={() => setPicking(true)}
                  disabled={!cam}
                  className="rounded-lg border border-white/15 bg-white/[0.06] px-3 py-1.5 text-xs text-slate-200 transition hover:bg-white/[0.12] disabled:opacity-35"
                >
                  ตั้ง index: คลิกบนภาพ
                </button>
              ) : (
                <div className="flex flex-wrap items-center gap-2 text-[11px]">
                  <span className="text-amber-200">ใช้เส้นประนี้เป็น index ใหม่? ทับเส้นเดิม (เครื่องหยุด + หลุมว่าง + หลุมตรงแล้ว)</span>
                  <button type="button" onClick={setIndex} className="rounded-lg border border-amber-300/40 bg-amber-400/20 px-3 py-1 text-amber-50 hover:bg-amber-400/30">
                    ยืนยัน
                  </button>
                  <button type="button" onClick={cancelPick} className="rounded-lg border border-white/10 bg-white/[0.06] px-3 py-1 text-slate-200">
                    ยกเลิก
                  </button>
                </div>
              )}
              {indexMsg && <div className="text-[11px] text-sky-200">{indexMsg}</div>}
            </div>
          )}
        </>
      )}

      <a href={fullPage} target="_blank" rel="noreferrer" className="mt-2 inline-block text-[10px] text-slate-500 underline-offset-2 hover:text-slate-300 hover:underline">
        เปิดหน้ากล้องเต็ม :5000 ↗
      </a>
    </Card>
  );
}
