'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { PartLabels, createLabelStore } from '@/components/three/MachineModel.jsx';
import { LoadingOverlay } from '@/components/three/Stage.jsx';
import { PARTS } from '@/lib/twin.js';
import HmiDevice, { HMI_SCREENS } from './HmiShowcase.jsx';
import { KEYFRAMES } from './keyframes.js';

// Canvas ใช้ WebGL — โหลดฝั่งเบราว์เซอร์เท่านั้น
const StoryCanvas = dynamic(() => import('./StoryCanvas.jsx'), { ssr: false });
const CarrierTape3D = dynamic(() => import('./CarrierTape3D.jsx'), {
  ssr: false,
  loading: () => <div className="mt-6 aspect-[16/10] w-full rounded-2xl border border-white/10 bg-[#07080b]" />,
});

const NAV = [
  { id: 'hero', label: 'เริ่ม' },
  { id: 'machine', label: 'เครื่อง' },
  { id: 'parts', label: 'ชิ้นส่วน' },
  { id: 'carrier', label: 'Carrier tape' },
  { id: 'hmi', label: 'HMI' },
  { id: 'twin', label: 'Digital Twin' },
  { id: 'start', label: 'ทดสอบ' },
];

export default function StoryPage() {
  const scroll = useRef({ p: 0, step: -1 });
  const [store] = useState(createLabelStore);
  const sections = useRef([]);
  const [active, setActive] = useState(0);
  const [modelFailed, setModelFailed] = useState(false);

  // ตำแหน่งเลื่อน → p ต่อเนื่อง 0..N-1 (กลาง section i = i) · ใช้จุดกึ่งกลางจอเป็นตัววัด
  useEffect(() => {
    const n = KEYFRAMES.length - 1;
    let raf = 0;
    const measure = () => {
      raf = 0;
      const c = window.scrollY + window.innerHeight / 2;
      let p = 0;
      sections.current.forEach((el, i) => {
        if (!el) return;
        const top = el.offsetTop;
        const h = el.offsetHeight;
        if (c >= top && c < top + h) p = i + (c - top) / h - 0.5;
        else if (c >= top + h) p = i + 0.5;
      });
      p = Math.min(n, Math.max(0, p));
      scroll.current.p = p;
      setActive((a) => (a === Math.round(p) ? a : Math.round(p)));
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      cancelAnimationFrame(raf);
    };
  }, []);

  const sec = (i) => (el) => {
    sections.current[i] = el;
  };

  return (
    <main className="relative bg-ink-950">
      {/* ฉาก 3D ค้างอยู่หลังเนื้อหาตลอดการเลื่อน */}
      <div className="fixed inset-0 z-0">
        <Backdrop />
        <StoryCanvas scroll={scroll} store={store} onModelFail={() => setModelFailed(true)} />
        <PartLabels store={store} />
        <LoadingOverlay failed={modelFailed} className="left-1/2 lg:left-[64%]" />
        {/* ไล่เงาฝั่งซ้ายให้ตัวหนังสืออ่านง่ายบนจอใหญ่ */}
        <div className="pointer-events-none absolute inset-y-0 left-0 hidden w-[46%] bg-gradient-to-r from-ink-950/80 via-ink-950/40 to-transparent lg:block" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-ink-950/90 to-transparent lg:hidden" />
      </div>

      <TopNav active={active} />
      <SideDots active={active} />

      <div className="relative z-10">
        <Hero ref={sec(0)} />
        <Machine ref={sec(1)} />
        <Parts ref={sec(2)} />
        <Carrier ref={sec(3)} />
        <Hmi ref={sec(4)} />
        <TwinIntro ref={sec(5)} />
        <StartCta ref={sec(6)} />
      </div>
    </main>
  );
}

// ───────────────────────── โครงร่วม ─────────────────────────

function Backdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0">
      <div className="absolute left-[55%] top-[45%] h-[70vmin] w-[90vmin] -translate-x-1/2 -translate-y-1/2 rounded-full bg-sky-500/15 blur-[130px]" />
      <div className="absolute right-[5%] top-[5%] h-[40vmin] w-[40vmin] rounded-full bg-indigo-500/15 blur-[120px]" />
      <div
        className="absolute inset-0 opacity-30"
        style={{
          backgroundImage:
            'linear-gradient(rgb(255 255 255 / 0.03) 1px, transparent 1px), linear-gradient(90deg, rgb(255 255 255 / 0.03) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
          maskImage: 'radial-gradient(ellipse at 60% 50%, black 25%, transparent 75%)',
        }}
      />
    </div>
  );
}

function TopNav({ active }) {
  return (
    <nav className="fixed inset-x-0 top-0 z-30 flex items-center justify-between gap-3 px-4 pt-4 sm:px-6">
      <a href="#hero" className="glass flex items-center gap-2.5 rounded-full py-1.5 pl-1.5 pr-4">
        <span className="grid h-7 w-7 place-items-center rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 text-[11px] font-bold text-ink-950">DT</span>
        <span className="text-sm font-semibold tracking-tight">Digital Twin</span>
      </a>
      <div className="glass hidden items-center gap-1 rounded-full p-1 md:flex">
        {NAV.slice(1, 6).map((n, i) => (
          <a
            key={n.id}
            href={`#${n.id}`}
            className={`rounded-full px-3 py-1 text-xs transition-colors ${
              active === i + 1 ? 'bg-white/10 text-white' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {n.label}
          </a>
        ))}
      </div>
      <Link
        href="/twin"
        className="rounded-full bg-sky-400 px-4 py-2 text-xs font-semibold text-ink-950 shadow-[0_0_24px_-4px_#38bdf8] transition hover:bg-sky-300"
      >
        เปิด Digital Twin →
      </Link>
    </nav>
  );
}

function SideDots({ active }) {
  return (
    <div className="fixed right-5 top-1/2 z-30 hidden -translate-y-1/2 flex-col gap-3 lg:flex">
      {NAV.map((n, i) => (
        <a key={n.id} href={`#${n.id}`} aria-label={n.label} className="group flex items-center justify-end gap-2">
          <span className="text-[10px] text-slate-400 opacity-0 transition-opacity group-hover:opacity-100">{n.label}</span>
          <span className={`block rounded-full transition-all ${active === i ? 'h-5 w-1.5 bg-sky-400' : 'h-1.5 w-1.5 bg-white/25'}`} />
        </a>
      ))}
    </div>
  );
}

// ครอบ section: สูงอย่างน้อยเต็มจอ ตัวหนังสือชิดซ้ายบนจอใหญ่ / ชิดล่างบนมือถือ (ให้เห็นโมเดลด้านบน)
function Section({ id, ref, className = '', children }) {
  return (
    <section
      id={id}
      ref={ref}
      className={`relative flex min-h-[130vh] items-end px-4 sm:px-6 lg:items-center lg:px-16 ${className}`}
    >
      {children}
    </section>
  );
}

function Eyebrow({ n, children }) {
  return (
    <p className="mb-3 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.2em] text-sky-300/90">
      {n && <span className="rounded bg-sky-400/15 px-1.5 py-0.5 text-sky-200">{n}</span>}
      {children}
    </p>
  );
}

function Panel({ className = '', children }) {
  return <div className={`glass w-full max-w-xl rounded-3xl p-6 sm:p-8 ${className}`}>{children}</div>;
}

// ───────────────────────── 0 · Hero ─────────────────────────

function Hero({ ref }) {
  return (
    <section id="hero" ref={ref} className="relative flex min-h-[110vh] items-end px-4 pb-24 pt-28 sm:px-6 lg:items-center lg:px-16 lg:pb-0">
      <div className="max-w-2xl">
        <Eyebrow>SMD Reel Taping Machine · Digital Twin</Eyebrow>
        <h1 className="text-4xl font-semibold leading-[1.1] tracking-tight text-white sm:text-5xl lg:text-6xl">
          Taping Machine
          <span className="block bg-gradient-to-r from-sky-300 via-indigo-300 to-fuchsia-300 bg-clip-text pb-1 text-transparent">
            Industrial Digital Twin
          </span>
        </h1>
        <p className="mt-5 max-w-[46ch] text-base leading-relaxed text-slate-300">
          เลื่อนลงเพื่อสำรวจโครงสร้างและการทำงานของเครื่อง Taping Machine ผ่านระบบ Digital Twin ที่จำลองลำดับการทำงานของเครื่องจักร
          พร้อมแสดงผลการทำงานของเครื่อง
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <a href="#machine" className="glass rounded-full px-5 py-2.5 text-sm font-medium text-white transition hover:bg-white/10">
            เริ่มสำรวจ ↓
          </a>
          <Link href="/twin" className="rounded-full px-5 py-2.5 text-sm text-sky-200 transition hover:text-white">
            ข้ามไปหน้าทดสอบ →
          </Link>
        </div>
      </div>
      <div className="pointer-events-none absolute bottom-8 left-1/2 flex -translate-x-1/2 flex-col items-center gap-2 text-[11px] text-slate-400">
        <span>เลื่อนลง</span>
        <span className="flex h-8 w-5 justify-center rounded-full border border-white/25 pt-1.5">
          <span className="scroll-cue block h-1.5 w-1 rounded-full bg-sky-300" />
        </span>
      </div>
    </section>
  );
}

// ───────────────────────── 1 · รู้จักเครื่อง ─────────────────────────

function Machine({ ref }) {
  return (
    <Section id="machine" ref={ref}>
      <Panel className="mb-10 lg:mb-0">
        <Eyebrow n="01">รู้จักเครื่อง</Eyebrow>
        <h2 className="text-3xl font-semibold tracking-tight text-white">เครื่องนี้ทำอะไร</h2>
        <p className="mt-4 leading-relaxed text-slate-300">
          รับ <b className="text-white">carrier tape</b> เปล่าเข้ามา วางชิ้นงาน SMD ลงพ็อกเก็ตทีละชิ้น ให้กล้องตรวจ แล้วปิดด้วย{' '}
          <b className="text-white">cover tape</b> ด้วยความร้อนและแรงกด ก่อนม้วนเก็บเป็นรีลตามจำนวนที่ตั้งไว้
        </p>
        <ProcessFlow />
      </Panel>
    </Section>
  );
}

// ขั้นตอนการทำงานแบบเข้าใจง่าย 5 ขั้น — ไฮไลต์วนทีละขั้นให้เห็นเป็นกระบวนการ (ไม่มีตัวเลข/สเปกชิ้นงาน)
const FLOW = [
  { t: 'ป้อนเทป', d: 'carrier tape เปล่าเดินเข้าเครื่องทีละหลุม', icon: 'M4 12h11m0 0-4-4m4 4-4 4M19 5v14' },
  { t: 'วางชิ้นงาน', d: 'ใส่ชิ้นงานอิเล็กทรอนิกส์ลงหลุม หลุมละชิ้น', icon: 'M12 3v10m0 0-4-4m4 4 4-4M5 17h14v3H5z' },
  { t: 'กล้องตรวจ', d: 'ตรวจว่ามีชิ้นงานและวางถูกต้อง', icon: 'M3 12s3.5-6 9-6 9 6 9 6-3.5 6-9 6-9-6-9-6zm9 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6z' },
  { t: 'ซีลปิด', d: 'ความร้อน + แรงกด ปิด cover tape ทับหลุม', icon: 'M12 3c2 3 5 5 5 9a5 5 0 0 1-10 0c0-2 1-3.5 2-4.5 0 2 1 3 2 3 0-3 1-5.5 1-7.5z' },
  { t: 'ม้วนเก็บ', d: 'ม้วนเทปที่ซีลแล้วเป็นรีล พร้อมส่งต่อ', icon: 'M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18zm0-6a3 3 0 1 0 0-6 3 3 0 0 0 0 6z' },
];

function ProcessFlow() {
  const [on, setOn] = useState(0);
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const t = setInterval(() => setOn((i) => (i + 1) % FLOW.length), 1600);
    return () => clearInterval(t);
  }, []);
  return (
    <ol className="relative mt-6 space-y-1" aria-label="ขั้นตอนการทำงานของเครื่อง">
      {/* เส้นเชื่อมแนวตั้งหลังไอคอน */}
      <span aria-hidden className="absolute bottom-6 left-[21px] top-6 w-px bg-gradient-to-b from-sky-400/50 via-sky-400/25 to-sky-400/50" />
      {FLOW.map((f, i) => {
        const active = i === on;
        return (
          <li
            key={f.t}
            className={`relative flex items-center gap-4 rounded-2xl px-2 py-2.5 transition-colors duration-500 ${active ? 'bg-sky-400/10' : ''}`}
          >
            <span
              className={`relative z-10 grid h-[26px] w-[26px] shrink-0 place-items-center rounded-full border transition-all duration-500 ${
                active
                  ? 'border-sky-300 bg-sky-400 text-ink-950 shadow-[0_0_18px_#38bdf8]'
                  : 'border-sky-400/40 bg-ink-950 text-sky-300'
              }`}
            >
              <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d={f.icon} />
              </svg>
            </span>
            <div className="min-w-0">
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-[11px] text-slate-500">{String(i + 1).padStart(2, '0')}</span>
                <span className={`font-medium transition-colors duration-500 ${active ? 'text-white' : 'text-slate-200'}`}>{f.t}</span>
              </div>
              <div className="text-sm text-slate-400">{f.d}</div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

// ───────────────────────── 2 · แยกชิ้นส่วน ─────────────────────────

function Parts({ ref }) {
  return (
    <Section id="parts" ref={ref}>
      <Panel className="mb-10 lg:mb-0">
        <Eyebrow n="02">แยกชิ้นส่วน</Eyebrow>
        <h2 className="text-3xl font-semibold tracking-tight text-white">ส่วนประกอบ Taping Machine</h2>
        <p className="mt-3 text-sm text-slate-400">เรียงตามทางเดินของเทป — จากรีลป้อน ผ่านหัวซีลและชุดดึง ไปจบที่รีลเก็บ · ขยับเมาส์เพื่อเอียงมุมมอง</p>
        <ol className="mt-5 grid gap-2 sm:grid-cols-2">
          {PARTS.map((p, i) => (
            <li key={p.node} className="flex gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-3">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-sky-400/15 font-mono text-[11px] text-sky-200">{i + 1}</span>
              <div className="min-w-0">
                <div className="text-sm font-medium text-white">
                  {p.name} <span className="text-xs font-normal text-slate-500">{p.en}</span>
                </div>
                <div className="mt-0.5 text-xs leading-relaxed text-slate-400">{p.desc}</div>
              </div>
            </li>
          ))}
        </ol>
      </Panel>
    </Section>
  );
}

// ───────────────────────── 3 · Carrier tape ─────────────────────────

function Carrier({ ref }) {
  return (
    <Section id="carrier" ref={ref}>
      <Panel className="mb-10 lg:mb-0">
        <Eyebrow n="03">Carrier tape</Eyebrow>
        <h2 className="text-3xl font-semibold tracking-tight text-white">ที่บรรจุชิ้นงาน SMC</h2>
        <p className="mt-4 leading-relaxed text-slate-300">
          carrier tape คือเทปที่ขึ้นรูปเป็นหลุมเรียงต่อกัน ใช้บรรจุชิ้นงานอุปกรณ์อิเล็กทรอนิกส์แบบ SMC (surface-mount component) หลุมละหนึ่งชิ้น
          แล้วปิดทับด้วย cover tape ก่อนม้วนเก็บเป็นรีล เพื่อส่งต่อให้เครื่องประกอบแผงวงจรหยิบไปใช้ทีละชิ้น
        </p>
        <CarrierTape3D />
        <div className="mt-5 flex flex-wrap gap-2 text-xs">
          {['หนึ่งหลุม หนึ่งชิ้น', 'ปิดด้วย cover tape', 'ม้วนเก็บเป็นรีล'].map((x) => (
            <span key={x} className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-slate-300">
              {x}
            </span>
          ))}
        </div>
      </Panel>
    </Section>
  );
}

// ───────────────────────── 4 · HMI ─────────────────────────
// section สูง 4 หน้าจอ — กล่องด้านในค้างกลางจอ (sticky) แล้วสลับหน้า HMI ตามระยะที่เลื่อนผ่าน section

function Hmi({ ref }) {
  const box = useRef(null);
  const [idx, setIdx] = useState(0);
  const n = HMI_SCREENS.length;

  useEffect(() => {
    let raf = 0;
    const measure = () => {
      raf = 0;
      const el = box.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const span = Math.max(1, r.height - window.innerHeight);
      const f = Math.min(0.999, Math.max(0, -r.top / span));
      const i = Math.floor(f * n);
      setIdx((prev) => (prev === i ? prev : i));
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      cancelAnimationFrame(raf);
    };
  }, [n]);

  // กดแท็บ = เลื่อนหน้าไปช่วงของหน้าจอนั้น (ไม่กระโดดข้าม ให้ฉาก 3D ตามทัน)
  const jump = (i) => {
    const el = box.current;
    if (!el) return;
    const span = el.offsetHeight - window.innerHeight;
    window.scrollTo({ top: el.offsetTop + span * ((i + 0.5) / n), behavior: 'smooth' });
  };

  const cur = HMI_SCREENS[idx];
  return (
    <section
      id="hmi"
      ref={(el) => {
        box.current = el;
        ref?.(el);
      }}
      className="relative min-h-[420vh] px-4 sm:px-6 lg:px-16"
    >
      <div className="sticky top-0 flex min-h-screen items-center pb-4 pt-24 lg:py-20">
        <div className="grid w-full items-center gap-6 lg:grid-cols-[minmax(0,440px)_minmax(0,1fr)] lg:gap-16">
          <Panel className="order-2 lg:order-1">
            <Eyebrow n="04">HMI</Eyebrow>
            <h2 className="text-3xl font-semibold tracking-tight text-white">จอควบคุมหน้าเครื่อง</h2>
            <p className="mt-4 leading-relaxed text-slate-300">
              จอสัมผัสหน้าเครื่อง (TouchGFX บนบอร์ด STM32) ส่งคำสั่งเข้า <b className="text-white">python</b> ตัวเดียวกับเว็บนี้
              กดปุ่มบนจอแล้วเห็นผลบน Digital Twin ทันที
            </p>

            <div className="mt-5 grid grid-cols-4 gap-1 rounded-xl border border-white/10 bg-black/20 p-1" role="tablist" aria-label="หน้าจอ HMI">
              {HMI_SCREENS.map((s, i) => (
                <button
                  key={s.key}
                  type="button"
                  role="tab"
                  aria-selected={i === idx}
                  onClick={() => jump(i)}
                  className={`truncate rounded-lg px-1 py-1.5 text-xs transition ${
                    i === idx ? 'bg-sky-400/20 text-sky-100 shadow-[inset_0_0_0_1px_rgb(56_189_248/0.4)]' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {s.tab}
                </button>
              ))}
            </div>

            <div key={cur.key} className="hmi-fade mt-5">
              <div className="text-lg font-semibold text-white">{cur.title}</div>
              <ul className="mt-3 space-y-2">
                {cur.points.map((t) => (
                  <li key={t} className="flex gap-2.5 text-sm leading-relaxed text-slate-300">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-sky-400 shadow-[0_0_8px_#38bdf8]" />
                    {t}
                  </li>
                ))}
              </ul>
            </div>
            <p className="mt-5 hidden text-xs text-slate-500 sm:block">หน้าตั้งค่าและซ่อมบำรุงต้องใส่รหัสก่อนเข้าทุกครั้ง</p>
          </Panel>

          <div className="order-1 lg:order-2">
            <HmiDevice index={idx} />
            <div className="mt-6 hidden justify-center gap-2 lg:flex" aria-hidden>
              {HMI_SCREENS.map((s, i) => (
                <span key={s.key} className={`h-1 rounded-full transition-all duration-300 ${i === idx ? 'w-8 bg-sky-400' : 'w-3 bg-white/20'}`} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

// ───────────────────────── 5 · Digital Twin ─────────────────────────

function TwinIntro({ ref }) {
  return (
    <Section id="twin" ref={ref}>
      <Panel className="mb-10 max-w-2xl lg:mb-0">
        <Eyebrow n="05">Digital Twin</Eyebrow>
        <h2 className="text-3xl font-semibold tracking-tight text-white">ระบบโดยรวมของ Digital Twin</h2>
        <p className="mt-4 leading-relaxed text-slate-300">
          ทุกจอคุยกับ <b className="text-white">python</b> ตัวเดียวที่ถือ state machine ของเครื่อง — เว็บนี้ จอหน้าเครื่อง และกล้องเห็นสถานะเดียวกันพร้อมกัน
          เมื่อพร้อมค่อยต่อ bridge ลงบอร์ดจริง คำสั่งชุดเดิมจะไปขับโซลินอยด์และมอเตอร์
        </p>
        <ArchDiagram />
      </Panel>
    </Section>
  );
}

// ผังการเชื่อมต่อ (ย่อจาก docs/specs/protocol.md ข้อ 1 + port_map.md)
function ArchDiagram() {
  const Node = ({ x, y, w = 128, title, sub, tone = '#38bdf8' }) => (
    <g>
      <rect x={x} y={y} width={w} height={46} rx={10} fill="rgb(255 255 255 / 0.04)" stroke={tone} strokeOpacity="0.55" />
      <text x={x + w / 2} y={y + 20} textAnchor="middle" fontSize="12" fontWeight="600" fill="#f1f5f9">{title}</text>
      <text x={x + w / 2} y={y + 36} textAnchor="middle" fontSize="10" fill="#94a3b8">{sub}</text>
    </g>
  );
  const Wire = ({ d, label, lx, ly, tone = '#38bdf8' }) => (
    <g>
      <path d={d} fill="none" stroke={tone} strokeOpacity="0.8" strokeWidth="1.5" className="flow-dash" />
      <text x={lx} y={ly} textAnchor="middle" fontSize="9.5" fill={tone} fontFamily="var(--font-mono)">{label}</text>
    </g>
  );
  return (
    <svg viewBox="0 0 560 250" className="mt-6 w-full" role="img" aria-label="ผังการเชื่อมต่อ: จอ HMI และเว็บ และกล้อง ต่อเข้า Python gateway, gateway ต่อ Rust bridge ลงบอร์ด STM32">
      <Node x={10} y={10} title="จอ HMI" sub="TouchGFX" tone="#818cf8" />
      <Node x={216} y={10} title="Python gateway" sub="FSM 16 สเต็ป + ALARM" tone="#34d399" />
      <Node x={422} y={10} title="เว็บ 3D Twin" sub="หน้านี้" />
      <Node x={422} y={100} title="กล้อง" sub="ตรวจชิ้นงาน → PASS/NG" tone="#f59e0b" />
      <Node x={216} y={100} title="Rust bridge" sub="Modbus client" tone="#f472b6" />
      <Node x={216} y={190} title="บอร์ด I/O" sub="STM32 · โซลินอยด์ · มอเตอร์" tone="#f472b6" />
      <Wire d="M138 33 H216" label="TCP 8766" lx={177} ly={27} tone="#818cf8" />
      <Wire d="M344 33 H422" label="WS 8765" lx={383} ly={27} />
      <Wire d="M344 40 C390 40 380 123 422 123" label="WS 8765" lx={392} ly={92} tone="#f59e0b" />
      <Wire d="M280 56 V100" label="TCP 8767" lx={310} ly={82} tone="#f472b6" />
      <Wire d="M280 146 V190" label="Modbus 502" lx={318} ly={172} tone="#f472b6" />
    </svg>
  );
}

// ───────────────────────── 6 · เข้าไปทดสอบ ─────────────────────────

function StartCta({ ref }) {
  return (
    <section id="start" ref={ref} className="relative flex min-h-[120vh] items-end justify-center px-4 pb-24 sm:px-6 lg:pb-32">
      <Link
        href="/twin"
        className="group flex items-center gap-3 rounded-full bg-sky-400 px-9 py-4 text-base font-semibold text-ink-950 shadow-[0_0_50px_-6px_#38bdf8] transition hover:bg-sky-300 hover:shadow-[0_0_70px_-4px_#38bdf8] sm:text-lg"
      >
        Get Started Digital Twin
        <span className="transition-transform group-hover:translate-x-1">→</span>
      </Link>
      <p className="absolute bottom-4 left-0 right-0 text-center text-[11px] text-slate-600">
        โมเดลจาก cad/export/Machine.glb · ข้อมูลเครื่องจาก docs/specs/machine_spec.md
      </p>
    </section>
  );
}
