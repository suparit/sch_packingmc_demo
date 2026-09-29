'use client';

import { useEffect, useRef, useState } from 'react';
import { FRICTION_S } from '@/lib/analytics.js';

// กราฟ SVG ของหน้า Analytics — ทำตาม dataviz skill:
// แท่งหนา ≤ 24px ปลายมน 4px ฝั่งข้อมูล ฐานเหลี่ยม · กริดเส้นเดียว 1px จาง · ป้ายตัวเลขเฉพาะจุดสำคัญ
// ข้อความใช้สีตัวอักษรเสมอ (ไม่ใช้สีแท่ง) · สีสถานะ (friction / alarm) มากับไอคอน + คำเสมอ · ชี้ได้ทุกแท่ง (tooltip)
const C = {
  series: '#38bdf8',
  warning: '#fab219',
  critical: '#d03b3b',
  grid: 'rgb(255 255 255 / 0.08)',
  axis: '#64748b',
  text: '#cbd5e1',
  muted: '#94a3b8',
};

function useWidth() {
  const ref = useRef(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.floor(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

// ขั้นแกนตัวเลขแบบเลขกลม (0.2 / 0.5 / 1 / 2 / 5 …)
function niceTicks(max, target = 5) {
  if (!(max > 0)) return [0, 1];
  const raw = max / target;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const out = [];
  for (let v = 0; v <= max + step * 0.001; v += step) out.push(Number(v.toFixed(6)));
  if (out[out.length - 1] < max) out.push(Number((out[out.length - 1] + step).toFixed(6)));
  return out;
}

// แท่งแนวนอน: ฐานเหลี่ยมที่ x0 ปลายมน 4px ที่ x1
function hBar(x0, x1, y, h) {
  const w = Math.max(0, x1 - x0);
  const r = Math.min(4, w, h / 2);
  return `M${x0},${y}H${x1 - r}Q${x1},${y} ${x1},${y + r}V${y + h - r}Q${x1},${y + h} ${x1 - r},${y + h}H${x0}Z`;
}
// แท่งแนวตั้ง: ฐานเหลี่ยมที่ y0 (ล่าง) ปลายมน 4px ที่ y1 (บน)
function vBar(x, w, y0, y1) {
  const h = Math.max(0, y0 - y1);
  const r = Math.min(4, h, w / 2);
  return `M${x},${y0}V${y1 + r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 + r}V${y0}Z`;
}

const fmt = (v) => `${Number(v).toFixed(2)} s`;

function Tooltip({ tip }) {
  if (!tip) return null;
  return (
    <div
      role="status"
      className="pointer-events-none absolute z-10 min-w-40 -translate-x-1/2 -translate-y-full rounded-xl border border-white/10 bg-ink-900/95 px-3 py-2 text-xs shadow-xl backdrop-blur"
      style={{ left: tip.x, top: tip.y - 8 }}
    >
      <div className="mb-1 font-mono text-[11px] text-white">{tip.title}</div>
      {tip.lines.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-4 text-slate-400">
          <span>{k}</span>
          <span className="font-mono tabular-nums text-slate-100">{v}</span>
        </div>
      ))}
    </div>
  );
}

export function StatusMark({ kind }) {
  // ไอคอน + คำ คู่กับสีเสมอ (ไม่ให้สีบอกความหมายตัวเดียว)
  if (kind === 'tripped')
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-[#d03b3b]/15 px-1.5 py-0.5 text-[10px] font-semibold text-rose-200">
        <span aria-hidden>⛔</span>TRIPPED
      </span>
    );
  if (kind === 'friction')
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-[#fab219]/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-200">
        <span aria-hidden>⚠</span>FRICTION
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-emerald-400/10 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300">
      <span aria-hidden>✓</span>NORMAL
    </span>
  );
}

// ───────────────────────── เวลาเฉลี่ยต่อสเต็ป (แท่งแนวนอน) ─────────────────────────
export function StepChart({ steps }) {
  const [ref, w] = useWidth();
  const [tip, setTip] = useState(null);
  const row = 26;
  const bar = 14;
  const labelW = w < 480 ? 128 : 172;
  const top = 26;
  const right = 64;
  const h = top + steps.length * row + 26;
  const max = Math.max(FRICTION_S, ...steps.map((s) => s.avg)) * 1.08;
  const ticks = niceTicks(max);
  const xMax = ticks[ticks.length - 1];
  const plotW = Math.max(40, w - labelW - right);
  const x = (v) => labelW + (v / xMax) * plotW;
  const peak = steps.reduce((a, s) => (s.avg > (a?.avg ?? -1) ? s : a), null);

  return (
    <div ref={ref} className="relative" onMouseLeave={() => setTip(null)}>
      {w > 0 && (
        <svg width={w} height={h} role="img" aria-label="เวลาเฉลี่ยของแต่ละสเต็ป (วินาที)">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={top - 6} y2={h - 22} stroke={C.grid} />
              <text x={x(t)} y={h - 6} textAnchor="middle" fontSize="10" fill={C.axis} fontFamily="var(--font-mono)">
                {t}
              </text>
            </g>
          ))}
          {/* เกณฑ์ FRICTION */}
          <line x1={x(FRICTION_S)} x2={x(FRICTION_S)} y1={top - 10} y2={h - 22} stroke={C.warning} strokeOpacity="0.7" />
          <text x={x(FRICTION_S)} y={top - 14} textAnchor="middle" fontSize="10" fill={C.muted}>
            ⚠ เกณฑ์ friction {FRICTION_S} s
          </text>
          {steps.map((s, i) => {
            const y = top + i * row + (row - bar) / 2;
            const kind = s.state === 'ALARM' ? 'tripped' : s.avg > FRICTION_S ? 'friction' : 'normal';
            const fill = kind === 'tripped' ? C.critical : kind === 'friction' ? C.warning : C.series;
            const label = kind !== 'normal' || s === peak;
            return (
              <g key={s.state}>
                <text x={labelW - 10} y={y + bar / 2 + 4} textAnchor="end" fontSize="11" fill={C.text} fontFamily="var(--font-mono)">
                  {s.state.length > (labelW < 150 ? 16 : 22) ? `${s.state.slice(0, labelW < 150 ? 15 : 21)}…` : s.state}
                </text>
                <path d={hBar(labelW, x(s.avg), y, bar)} fill={fill} opacity={tip && tip.key !== s.state ? 0.45 : 1} />
                {label && (
                  <text x={x(s.avg) + 6} y={y + bar / 2 + 4} fontSize="11" fill={C.text} fontFamily="var(--font-mono)">
                    {kind === 'friction' ? '⚠ ' : kind === 'tripped' ? '⛔ ' : ''}
                    {s.avg.toFixed(2)}s
                  </text>
                )}
                {/* พื้นที่ชี้ = ทั้งแถว ใหญ่กว่าแท่ง */}
                <rect
                  x={0}
                  y={top + i * row}
                  width={w}
                  height={row}
                  fill="transparent"
                  onMouseEnter={() =>
                    setTip({
                      key: s.state,
                      x: Math.min(w - 90, Math.max(90, x(s.avg))),
                      y: y,
                      title: s.state,
                      lines: [
                        ['เฉลี่ย', fmt(s.avg)],
                        ['นานสุด', fmt(s.max)],
                        ['จำนวนครั้ง', s.count],
                      ],
                    })
                  }
                />
              </g>
            );
          })}
        </svg>
      )}
      <Tooltip tip={tip} />
    </div>
  );
}

// ───────────────────────── เวลารวมต่อรอบ (แท่งแนวตั้ง) ─────────────────────────
export function CycleChart({ cycles, mean }) {
  const [ref, w] = useWidth();
  const [tip, setTip] = useState(null);
  const h = 250;
  const top = 30;
  const bottom = 34;
  const left = 40;
  const right = 12;
  const max = Math.max(1, ...cycles.map((c) => c.total)) * 1.12;
  const ticks = niceTicks(max, 4);
  const yMax = ticks[ticks.length - 1];
  const plotH = h - top - bottom;
  const y = (v) => top + plotH - (v / yMax) * plotH;
  const band = cycles.length ? Math.max(1, (w - left - right) / cycles.length) : 1;
  const barW = Math.min(24, band * 0.6);
  const done = cycles.filter((c) => c.complete);
  const peak = done.reduce((a, c) => (c.total > (a?.total ?? -1) ? c : a), null);

  return (
    <div ref={ref} className="relative" onMouseLeave={() => setTip(null)}>
      {w > 0 && (
        <svg width={w} height={h} role="img" aria-label="เวลารวมของแต่ละรอบการผลิต (วินาที)">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={left} x2={w - right} y1={y(t)} y2={y(t)} stroke={C.grid} />
              <text x={left - 8} y={y(t) + 3} textAnchor="end" fontSize="10" fill={C.axis} fontFamily="var(--font-mono)">
                {t}
              </text>
            </g>
          ))}
          {mean != null && (
            <g>
              <line x1={left} x2={w - right} y1={y(mean)} y2={y(mean)} stroke={C.muted} strokeOpacity="0.8" />
              <text x={w - right} y={y(mean) - 6} textAnchor="end" fontSize="10" fill={C.muted}>
                เฉลี่ย {mean.toFixed(2)} s
              </text>
            </g>
          )}
          {cycles.map((c, i) => {
            const cx = left + band * i + band / 2;
            const bx = cx - barW / 2;
            return (
              <g key={c.key}>
                <path
                  d={vBar(bx, barW, y(0), y(c.total))}
                  fill={C.series}
                  fillOpacity={c.complete ? 1 : 0.3}
                  stroke={c.complete ? 'none' : C.series}
                  strokeDasharray={c.complete ? undefined : '3 3'}
                  opacity={tip && tip.key !== c.key ? 0.45 : 1}
                />
                {/* ป้ายค่าเฉพาะรอบที่นานสุด — ซ่อนถ้าชิดป้ายเส้นเฉลี่ยจนทับกัน (ค่าอยู่ใน tooltip/ตาราง) */}
                {((c === peak && (mean == null || Math.abs(y(c.total) - y(mean)) > 16)) || !c.complete) && (
                  <text x={cx} y={y(c.total) - 8} textAnchor="middle" fontSize="10" fill={c.complete ? C.text : C.muted} fontFamily="var(--font-mono)">
                    {c.complete ? `${c.total.toFixed(1)}s` : c.note}
                  </text>
                )}
                <text x={cx} y={h - 12} textAnchor="middle" fontSize="10" fill={C.axis} fontFamily="var(--font-mono)">
                  #{c.id}
                </text>
                <rect
                  x={cx - band / 2}
                  y={top}
                  width={band}
                  height={plotH}
                  fill="transparent"
                  onMouseEnter={() =>
                    setTip({
                      key: c.key,
                      x: Math.min(w - 90, Math.max(90, cx)),
                      y: y(c.total),
                      title: `รอบ #${c.id}${c.complete ? '' : ` · ${c.note}`}`,
                      lines: [
                        ['เวลารวม', fmt(c.total)],
                        ['จำนวนสเต็ปที่บันทึก', c.steps],
                      ],
                    })
                  }
                />
              </g>
            );
          })}
        </svg>
      )}
      <Tooltip tip={tip} />
    </div>
  );
}
