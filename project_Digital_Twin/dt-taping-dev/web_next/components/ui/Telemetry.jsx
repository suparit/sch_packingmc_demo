'use client';

import { useId } from 'react';

// ชิ้นส่วน UI ของ HUD — ไม่มี logic ของเครื่องในไฟล์นี้

export function Card({ title, icon, right, className = '', children }) {
  return (
    <section className={`glass pointer-events-auto rounded-2xl p-4 ${className}`}>
      <header className="mb-3 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
          {icon && <span className="text-sky-300/80">{icon}</span>}
          {title}
        </h3>
        {right}
      </header>
      {children}
    </section>
  );
}

export function Sparkline({ data, min, max, limit, color = '#38bdf8', height = 44 }) {
  const id = useId().replace(/:/g, '');
  const w = 200;
  const h = height;
  if (data.length < 2) return <div style={{ height }} />;
  const lo = min ?? Math.min(...data);
  const hi = max ?? Math.max(...data);
  const span = hi - lo || 1;
  const x = (i) => (i / (data.length - 1)) * w;
  const y = (v) => h - 2 - ((Math.min(hi, Math.max(lo, v)) - lo) / span) * (h - 4);
  const line = data.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="block w-full" style={{ height }}>
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.35" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {limit != null && limit <= hi && (
        <line x1="0" x2={w} y1={y(limit)} y2={y(limit)} stroke="#f87171" strokeWidth="1" strokeDasharray="4 4" vectorEffect="non-scaling-stroke" opacity="0.7" />
      )}
      <path d={`${line}L${w},${h}L0,${h}Z`} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  );
}

export function Ring({ value, max, size = 72, stroke = 7, color = '#34d399', children }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const p = max > 0 ? Math.min(1, value / max) : 0;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(255 255 255 / 0.08)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - p)}
          style={{ transition: 'stroke-dashoffset 400ms ease' }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center">{children}</div>
    </div>
  );
}

export function Bits({ label, value, names }) {
  const v = Number(value) || 0;
  return (
    <div className="flex items-center gap-3">
      <span className="w-9 font-mono text-[11px] text-slate-400">{label}</span>
      <div className="flex gap-1">
        {names.map((n, i) => {
          const on = (v >> i) & 1;
          return (
            <span
              key={i}
              title={`bit ${i} · ${n}`}
              className={`h-3.5 w-3.5 rounded-[4px] border transition-colors duration-150 ${
                on ? 'border-emerald-300/60 bg-emerald-400 shadow-[0_0_10px_#34d399]' : 'border-white/10 bg-white/[0.04]'
              }`}
            />
          );
        })}
      </div>
      <span className="ml-auto font-mono text-[11px] tabular-nums text-slate-500">0x{v.toString(16).toUpperCase().padStart(2, '0')}</span>
    </div>
  );
}

export function Stat({ label, value, unit }) {
  return (
    <div className="min-w-0">
      <div className="truncate text-[10px] uppercase tracking-[0.14em] text-slate-500">{label}</div>
      <div className="font-mono text-sm tabular-nums text-slate-100">
        {value}
        {unit && <span className="ml-1 text-[11px] text-slate-500">{unit}</span>}
      </div>
    </div>
  );
}

export const Icon = {
  temp: (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z" />
    </svg>
  ),
  box: (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
      <path d="M21 8 12 3 3 8v8l9 5 9-5V8z" />
      <path d="m3 8 9 5 9-5M12 13v8" />
    </svg>
  ),
  motor: (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" />
    </svg>
  ),
  chip: (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="6" y="6" width="12" height="12" rx="2" />
      <path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" />
    </svg>
  ),
  flow: (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M3 12h4l3-8 4 16 3-8h4" />
    </svg>
  ),
  sliders: (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6" />
    </svg>
  ),
  sensor: (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M5 12a7 7 0 0 1 14 0M8.5 12a3.5 3.5 0 0 1 7 0" />
      <circle cx="12" cy="12" r="1" />
      <path d="M12 13v8" />
    </svg>
  ),
};
