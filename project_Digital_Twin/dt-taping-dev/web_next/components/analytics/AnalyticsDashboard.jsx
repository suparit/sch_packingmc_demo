'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { CycleChart, StatusMark, StepChart } from './Charts.jsx';
import { FRICTION_S, computeAnalytics, rowStatus } from '@/lib/analytics.js';
import { useTwinLink } from '@/lib/useTwinLink.js';

// หน้าวิเคราะห์การผลิต — ยกฟังก์ชันจาก cad/analytics.html มา (GET_HISTORY → HISTORY_RESPONSE)
// LIVE = ประวัติจากฐานข้อมูล SQLite ของ gateway · DEMO = ประวัติของตัวจำลองในเบราว์เซอร์ (ใช้ร่วมกับหน้า /twin)
const AUTO_MS = 3000;

function Panel({ title, sub, right, children, className = '' }) {
  return (
    <section className={`glass rounded-2xl p-5 ${className}`}>
      <header className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">{title}</h2>
          {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
        </div>
        {right}
      </header>
      {children}
    </section>
  );
}

function Tile({ label, value, hint, hero = false }) {
  return (
    <div className="glass rounded-2xl p-5">
      <div className="text-xs text-slate-400">{label}</div>
      <div className={`mt-1 font-semibold tabular-nums text-white ${hero ? 'text-5xl' : 'text-3xl'}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

function DataTable({ head, rows }) {
  return (
    <details className="mt-3 text-xs text-slate-400">
      <summary className="cursor-pointer select-none hover:text-slate-200">ดูเป็นตาราง</summary>
      <div className="mt-2 max-h-64 overflow-auto rounded-lg border border-white/10">
        <table className="w-full text-left">
          <thead className="bg-white/5 text-slate-300">
            <tr>{head.map((h) => <th key={h} className="px-3 py-1.5 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r[0]} className="border-t border-white/5">
                {r.map((c, i) => <td key={i} className="px-3 py-1.5 font-mono tabular-nums text-slate-200">{c}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

// ประวัติ ALARM พร้อมสาเหตุ (27 ก.ย. 2569) — จากตาราง alarm_logs ใน SQLite ของ gateway 01_DigitalTwin (ถาวร ไม่หายตอนปิดระบบ)
// เดิมเห็นแค่จำนวน ⛔ จาก machine_logs · ข้อความสาเหตุอยู่แค่จอ HMI หน้า Report และหายเมื่อปิด gateway
const causeOf = (m) => String(m || '').replace(/^⚠️\s*|^🚨\s*/u, '').replace(/\s*\(.*?\)\s*/g, ' ').replace(/\s+\d+\/\d+$/, '').trim();

function AlarmPanel({ alarms, status }) {
  const list = alarms ?? [];
  const causes = Object.entries(
    list.reduce((acc, a) => {
      const k = causeOf(a.message);
      acc[k] = (acc[k] || 0) + 1;
      return acc;
    }, {}),
  ).sort((x, y) => y[1] - x[1]);
  return (
    <Panel
      className="relative z-10 mt-4"
      title="ประวัติ ALARM"
      sub={alarms === null ? 'gateway นี้ไม่ส่งประวัติ ALARM — ดูที่จอ HMI หน้า Report' : `บันทึกถาวรในฐานข้อมูล gateway · ${list.length} รายการล่าสุด · ใหม่อยู่บน`}
    >
      {causes.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {causes.slice(0, 6).map(([cause, n]) => (
            <span key={cause} className="rounded-full border border-rose-400/25 bg-rose-500/10 px-2.5 py-1 text-[11px] text-rose-100">
              {cause} <span className="font-mono text-rose-300">×{n}</span>
            </span>
          ))}
        </div>
      )}
      <div className="max-h-80 overflow-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="sticky top-0 bg-ink-950/90 text-[11px] uppercase tracking-wider text-slate-500">
            <tr>
              <th className="py-2 pr-4 font-medium">เวลา</th>
              <th className="py-2 pr-4 font-medium">สาเหตุ</th>
              <th className="py-2 pr-4 font-medium">สเต็ปที่เกิด</th>
              <th className="py-2 pr-4 text-right font-medium">หลุม</th>
              <th className="py-2 font-medium">เครื่อง</th>
            </tr>
          </thead>
          <tbody>
            {list.map((a, i) => (
              <tr key={`${a.time}-${i}`} className="border-t border-white/5">
                <td className="py-2 pr-4 font-mono text-xs text-slate-500">{a.time}</td>
                <td className="py-2 pr-4 text-xs text-rose-100">{a.message}</td>
                <td className="py-2 pr-4 font-mono text-xs text-slate-300">{a.state}</td>
                <td className="py-2 pr-4 text-right font-mono text-xs tabular-nums text-slate-400">{a.pocket}</td>
                <td className="py-2 text-xs">
                  {a.real ? <span className="text-emerald-300">จริง (Sync)</span> : <span className="text-slate-500">จำลอง</span>}
                </td>
              </tr>
            ))}
            {!list.length && (
              <tr>
                <td colSpan={5} className="py-8 text-center text-sm text-slate-500">
                  {alarms === null ? (status === 'demo' ? 'ตัวจำลองยังไม่มี ALARM' : '—') : 'ยังไม่เคยเกิด ALARM'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

export default function AnalyticsDashboard() {
  const { system: s, link, send, records, alarms } = useTwinLink();
  const [auto, setAuto] = useState(true);
  const [syncedAt, setSyncedAt] = useState(null);
  const ready = link.status === 'live' || link.status === 'demo';

  const sync = useCallback(() => {
    if (send('GET_HISTORY')) setSyncedAt(new Date());
  }, [send]);

  // ดึงครั้งแรกทันทีที่ต่อได้ + รีเฟรชอัตโนมัติทุก 3 วิ (ปิดได้)
  useEffect(() => {
    if (!ready) return;
    sync();
    if (!auto) return;
    const t = setInterval(sync, AUTO_MS);
    return () => clearInterval(t);
  }, [ready, auto, sync]);

  const a = useMemo(() => computeAnalytics(records ?? [], s.running), [records, s.running]);
  const empty = records !== null && records.length === 0;

  return (
    <main className="relative min-h-dvh bg-ink-950 px-4 pb-16 pt-4 sm:px-6 lg:px-10">
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute left-1/3 top-0 h-[50vmin] w-[80vmin] rounded-full bg-sky-500/10 blur-[120px]" />
      </div>

      <nav className="relative z-10 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Link href="/" className="glass flex items-center gap-2.5 rounded-full py-1.5 pl-1.5 pr-4">
            <span className="grid h-7 w-7 place-items-center rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 text-[11px] font-bold text-ink-950">DT</span>
            <span className="text-sm font-semibold tracking-tight">Digital Twin</span>
          </Link>
          <Link href="/twin" className="glass rounded-full px-3 py-1.5 text-xs text-slate-300 transition hover:text-white">
            ← หน้าทดสอบ
          </Link>
        </div>
        <div className="flex items-center gap-2">
          <label className="glass flex cursor-pointer items-center gap-2 rounded-full px-3 py-1.5 text-xs text-slate-300">
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} className="h-3.5 w-3.5 accent-sky-400" />
            รีเฟรชอัตโนมัติ
          </label>
          <button
            type="button"
            onClick={sync}
            disabled={!ready}
            className="rounded-full bg-sky-400 px-4 py-1.5 text-xs font-semibold text-ink-950 transition hover:bg-sky-300 disabled:opacity-40"
          >
            ⟳ Sync ข้อมูล
          </button>
          <span className="glass flex items-center gap-2 rounded-full px-3 py-1.5 text-xs">
            <span className={`pulse-dot h-2 w-2 rounded-full ${link.status === 'live' ? 'bg-emerald-400' : link.status === 'demo' ? 'bg-amber-400' : 'bg-rose-400'}`} />
            {link.status === 'live' ? 'LIVE · ฐานข้อมูล gateway' : link.status === 'demo' ? 'DEMO · ตัวจำลอง' : 'กำลังเชื่อมต่อ…'}
          </span>
        </div>
      </nav>

      <header className="relative z-10 mt-8">
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-sky-300/90">Production analytics</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white sm:text-4xl">วิเคราะห์ประสิทธิภาพการผลิต</h1>
        <p className="mt-2 max-w-[70ch] text-sm text-slate-400">
          คำนวณจากประวัติการเปลี่ยนสเต็ป {records ? `${records.length} แถวล่าสุด` : ''} — เวลาเฉลี่ยของแต่ละสเต็ป เวลารวมต่อรอบ และรายการล่าสุด
          {syncedAt && <span className="text-slate-500"> · อัปเดต {syncedAt.toLocaleTimeString('th-TH')}</span>}
        </p>
      </header>

      {empty && (
        <div className="glass relative z-10 mt-6 rounded-2xl p-6 text-sm text-slate-300">
          ยังไม่มีประวัติการทำงาน
          {link.status === 'demo' ? (
            <>
              {' '}— ตัวจำลองยังไม่ได้เดิน{' '}
              <button type="button" onClick={() => send('START')} className="ml-2 rounded-full bg-emerald-400/20 px-3 py-1 text-xs text-emerald-200 hover:bg-emerald-400/30">
                ▶ เริ่มเดินเครื่องจำลอง
              </button>
              <span className="ml-2 text-xs text-slate-500">หรือไปกด START ที่หน้าทดสอบ</span>
            </>
          ) : (
            ' ในฐานข้อมูลของ gateway'
          )}
        </div>
      )}

      <div className="relative z-10 mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile hero label="เวลาเฉลี่ยต่อรอบ" value={a.kpi ? `${a.kpi.mean.toFixed(2)} s` : '—'} hint={a.kpi ? `จาก ${a.kpi.n} รอบที่จบแล้ว` : 'ยังไม่มีรอบที่จบ'} />
        <Tile label="รอบที่เร็วที่สุด" value={a.kpi ? `${a.kpi.best.toFixed(2)} s` : '—'} hint="เฉพาะรอบที่เดินครบ" />
        <Tile label="รอบที่ช้าที่สุด" value={a.kpi ? `${a.kpi.worst.toFixed(2)} s` : '—'} hint="เฉพาะรอบที่เดินครบ" />
        <Tile
          label="สเต็ปผิดปกติในช่วงนี้"
          value={
            <span className="flex items-baseline gap-3 text-3xl">
              <span title="FRICTION">⚠ {a.counts.friction}</span>
              <span title="ALARM" className="text-slate-400">⛔ {a.counts.tripped}</span>
            </span>
          }
          hint={`friction = นานเกิน ${FRICTION_S} s · ⛔ = ALARM`}
        />
      </div>

      <div className="relative z-10 mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <Panel title="เวลาเฉลี่ยของแต่ละสเต็ป" sub="วินาที · เรียงตามลำดับการทำงาน · ชี้ที่แท่งเพื่อดูรายละเอียด">
          {a.steps.length ? <StepChart steps={a.steps} /> : <p className="py-10 text-center text-sm text-slate-500">ยังไม่มีข้อมูล</p>}
          <DataTable head={['สเต็ป', 'เฉลี่ย (s)', 'นานสุด (s)', 'ครั้ง']} rows={a.steps.map((x) => [x.state, x.avg.toFixed(2), x.max.toFixed(2), x.count])} />
        </Panel>
        <Panel title="เวลารวมต่อรอบการผลิต" sub="วินาที · รอบที่ไม่ครบ (กำลังเดิน / ถูกตัด / RESET กลางรอบ) แสดงแบบจาง และไม่นับใน KPI">
          {a.cycles.length ? <CycleChart cycles={a.cycles} mean={a.kpi?.mean ?? null} /> : <p className="py-10 text-center text-sm text-slate-500">ยังไม่มีข้อมูล</p>}
          <DataTable head={['รอบ', 'เวลารวม (s)', 'สเต็ป', 'สถานะ']} rows={a.cycles.map((c) => [`${c.key + 1}. #${c.id}`, c.total.toFixed(2), c.steps, c.complete ? 'ครบรอบ' : c.note])} />
        </Panel>
      </div>

      <Panel className="relative z-10 mt-4" title="รายการเปลี่ยนสเต็ปล่าสุด" sub="10 แถวล่าสุด · ใหม่อยู่บน">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="py-2 pr-4 font-medium">เวลา</th>
                <th className="py-2 pr-4 font-medium">สเต็ป</th>
                <th className="py-2 pr-4 text-right font-medium">ใช้เวลา</th>
                <th className="py-2 pr-4 font-medium">โหมด</th>
                <th className="py-2 pr-4 font-medium">รอบ</th>
                <th className="py-2 font-medium">สถานะ</th>
              </tr>
            </thead>
            <tbody>
              {a.latest.map((r, i) => (
                <tr key={`${r.time}-${i}`} className="border-t border-white/5">
                  <td className="py-2 pr-4 font-mono text-xs text-slate-500">{r.time ? String(r.time).split('.')[0] : '—'}</td>
                  <td className="py-2 pr-4 font-mono text-xs text-slate-100">{r.state}</td>
                  <td className="py-2 pr-4 text-right font-mono text-xs tabular-nums text-slate-200">{Number(r.duration).toFixed(2)} s</td>
                  <td className="py-2 pr-4 text-xs uppercase text-slate-400">{r.mode || 'auto'}</td>
                  <td className="py-2 pr-4 font-mono text-xs text-slate-400">#{r.cycle}</td>
                  <td className="py-2"><StatusMark kind={rowStatus(r)} /></td>
                </tr>
              ))}
              {!a.latest.length && (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-sm text-slate-500">ยังไม่มีข้อมูล</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      <AlarmPanel alarms={alarms} status={link.status} />
    </main>
  );
}
