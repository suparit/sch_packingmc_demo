'use client';

import { useEffect, useRef } from 'react';

// หน้าจอ HMI หน้าเครื่อง (TouchGFX) — ภาพจาก user 2026-09-26 เก็บที่ public/hmi/
// คำอธิบายอ้างจากโค้ดจอจริงใน NOXCORE/Appli/TouchGFX/gui/src (ปุ่มไหนส่งคำสั่งจริง) + protocol.md ข้อ 4
// ⚠️ หน้าซ่อมบำรุง: ตอนนี้ผูกคำสั่งจริงแค่ Welding UP/DOWN (MANUAL_SEAL) — ปุ่มอื่นยังเป็นหน้าตา ห้ามเขียนว่าใช้งานได้
export const HMI_SCREENS = [
  {
    key: 'main',
    code: 'MAIN',
    tab: 'หน้าหลัก',
    title: 'หน้าหลัก',
    src: '/hmi/main.webp',
    points: [
      'ดู state ของเครื่อง, cycle time และ pitch แบบ real-time',
      'อุณหภูมิ heater ซ้าย–ขวา และยอดผลิตเทียบเป้าหมาย',
      'START · STOP · RESET · STEP เดินครบ 1 รอบแล้วหยุด · INIT สั่งกระบอก C',
      'แก้ pitch / เป้าหมายได้จากหน้านี้ และตัดสิน PASS / NG เมื่อเครื่องรอ',
    ],
  },
  {
    key: 'report',
    code: 'REPORT',
    tab: 'รายงาน',
    title: 'รายงานการผลิต',
    src: '/hmi/report.webp',
    points: [
      'สรุปยอดผลิต OK / NG และ % yield',
      'ประวัติการทำงานและ alarm ย้อนหลังจากฐานข้อมูล',
      'รีเฟรชอัตโนมัติ · ล้างประวัติเพื่อเริ่ม lot ใหม่ · บันทึกออกเป็นไฟล์ CSV',
    ],
  },
  {
    key: 'settings',
    code: 'SETTINGS',
    tab: 'ตั้งค่า',
    title: 'ตั้งค่าเครื่อง',
    src: '/hmi/settings.webp',
    points: [
      'ปรับความเร็ว อัตราเร่ง และอัตราหน่วงของมอเตอร์',
      'ตั้งอุณหภูมิ จำนวนชิ้นเป้าหมาย และระยะ pitch',
      'ตำแหน่งกล้อง ตำแหน่งโหลด และตำแหน่งรีล',
      'กด SAVE PARAMS ส่งค่าทั้งหมดเข้า Python',
    ],
  },
  {
    key: 'maintenance',
    code: 'MAINTENANCE',
    tab: 'ซ่อมบำรุง',
    title: 'ซ่อมบำรุง',
    src: '/hmi/maintenance.webp',
    points: [
      'สั่งหัวซีลขึ้น / ลงด้วยมือเพื่อทดสอบกลไก (ใช้ได้เมื่อเครื่องหยุด)',
      'รวมปุ่มทดสอบฮาร์ดแวร์และหน้าตรวจเซนเซอร์ I/O ไว้ที่เดียว',
      'ระหว่างอยู่หน้านี้ START ถูกล็อกทุกช่องทาง กันเครื่องเดินขณะมีคนทำงาน',
    ],
  },
];

// กรอบจอลอยแบบ 3D: เอียงตามเมาส์ · สลับหน้าด้วยการเลื่อนข้าง + เส้นสแกน · มุมเล็ง HUD · เส้น scanline
export default function HmiDevice({ index }) {
  const tilt = useRef(null);

  // เอียงตามตำแหน่งเมาส์ทั้งหน้าต่าง แบบหน่วง (ไม่ผูก React state — เขียน style ตรงทุกเฟรม)
  useEffect(() => {
    const el = tilt.current;
    if (!el || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    let tx = 0;
    let ty = 0;
    let cx = 0;
    let cy = 0;
    let raf;
    const onMove = (e) => {
      tx = (e.clientX / window.innerWidth) * 2 - 1;
      ty = (e.clientY / window.innerHeight) * 2 - 1;
    };
    const loop = () => {
      cx += (tx - cx) * 0.06;
      cy += (ty - cy) * 0.06;
      el.style.transform = `rotateY(${(-14 + cx * 8).toFixed(2)}deg) rotateX(${(5 - cy * 5).toFixed(2)}deg)`;
      raf = requestAnimationFrame(loop);
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    raf = requestAnimationFrame(loop);
    return () => {
      window.removeEventListener('pointermove', onMove);
      cancelAnimationFrame(raf);
    };
  }, []);

  const cur = HMI_SCREENS[index];
  return (
    <div className="relative w-full [perspective:1600px]">
      {/* แสงเรืองด้านหลังจอ */}
      <div aria-hidden className="absolute inset-[8%] rounded-[40px] bg-sky-500/25 blur-[70px]" />
      <div ref={tilt} className="relative [transform-style:preserve-3d] [transform:rotateY(-14deg)_rotateX(5deg)]">
        {/* ตัวเครื่องจอ */}
        <div className="relative rounded-[22px] border border-sky-300/30 bg-gradient-to-b from-slate-800 to-slate-950 p-3 shadow-[0_40px_80px_-30px_rgba(0,0,0,0.9),0_0_0_1px_rgba(56,189,248,0.08),0_0_60px_-10px_rgba(56,189,248,0.45)] sm:p-4">
          <div className="relative aspect-[5/3] overflow-hidden rounded-xl bg-black">
            {HMI_SCREENS.map((s, i) => (
              <img
                key={s.key}
                src={s.src}
                alt={`หน้าจอ HMI — ${s.title}`}
                draggable={false}
                className="absolute inset-0 h-full w-full object-cover transition-all duration-700 ease-out"
                style={{
                  opacity: i === index ? 1 : 0,
                  transform: `translateX(${i === index ? 0 : i < index ? -8 : 8}%) scale(${i === index ? 1 : 0.96})`,
                  filter: i === index ? 'none' : 'blur(4px)',
                }}
              />
            ))}
            {/* เส้นสแกนวิ่งลงทุกครั้งที่เปลี่ยนหน้า (key เปลี่ยน = เล่นใหม่) */}
            <div key={`scan-${index}`} aria-hidden className="hmi-scan pointer-events-none absolute inset-x-0 top-0 h-1/3" />
            {/* scanline บาง ๆ + แสงสะท้อนกระจก */}
            <div
              aria-hidden
              className="pointer-events-none absolute inset-0 opacity-[0.12] mix-blend-overlay"
              style={{ backgroundImage: 'repeating-linear-gradient(0deg, #fff 0 1px, transparent 1px 3px)' }}
            />
            <div aria-hidden className="pointer-events-none absolute inset-0 bg-gradient-to-br from-white/15 via-transparent to-transparent" />
          </div>
          {/* ไฟสถานะใต้จอ */}
          <div className="mt-2.5 flex items-center justify-between px-1 font-mono text-[10px] tracking-wider text-slate-500">
            <span className="flex items-center gap-1.5">
              <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-emerald-400" /> HMI · TouchGFX
            </span>
            <span>STM32H7</span>
          </div>
        </div>

        {/* มุมเล็งแบบ HUD ลอยหน้าจอ */}
        {['left-0 top-0 border-l-2 border-t-2', 'right-0 top-0 border-r-2 border-t-2', 'bottom-0 left-0 border-b-2 border-l-2', 'bottom-0 right-0 border-b-2 border-r-2'].map(
          (c) => (
            <span key={c} aria-hidden className={`absolute -m-3 h-6 w-6 border-sky-300/70 [transform:translateZ(30px)] ${c}`} />
          ),
        )}

        {/* ป้ายหน้าปัจจุบัน ลอยเหนือจอ */}
        <div className="glass absolute -top-5 left-6 flex items-center gap-2 rounded-full px-3 py-1 font-mono text-[11px] text-sky-100 [transform:translateZ(60px)]">
          <span className="text-sky-300">{String(index + 1).padStart(2, '0')}</span>
          <span className="text-slate-500">/ {String(HMI_SCREENS.length).padStart(2, '0')}</span>
          <span className="tracking-wider">{cur.code}</span>
        </div>
      </div>
    </div>
  );
}
