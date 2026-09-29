'use client';

import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Environment, Grid, Lightformer, useProgress } from '@react-three/drei';
import * as THREE from 'three';

// แสงรอบด้านแบบนุ่ม + แสงสะท้อนสร้างในเครื่อง (ไม่โหลด HDR จากเน็ต — เครื่องหน้างานอาจออฟไลน์)
export function StageLights() {
  return (
    <>
      <ambientLight intensity={0.35} />
      <hemisphereLight args={['#bfdbfe', '#0b1020', 0.45]} />
      <directionalLight position={[4, 8, 5]} intensity={1.4} />
      <pointLight position={[-5, 2.5, -3]} intensity={25} color="#818cf8" />
      <pointLight position={[5, 1.5, 4]} intensity={18} color="#38bdf8" />
      <Environment resolution={256}>
        <Lightformer intensity={2} position={[0, 5, -6]} scale={[10, 3, 1]} color="#dbeafe" />
        <Lightformer intensity={1.2} position={[-6, 2, 0]} rotation-y={Math.PI / 2} scale={[8, 2, 1]} color="#818cf8" />
        <Lightformer intensity={1.2} position={[6, 2, 0]} rotation-y={-Math.PI / 2} scale={[8, 2, 1]} color="#38bdf8" />
        <Lightformer form="ring" intensity={3} position={[0, 6, 2]} scale={2} color="#ffffff" />
      </Environment>
    </>
  );
}

// พื้น: เงานุ่มปลอม (texture วงกลมไล่สี — ถูกกว่า ContactShadows ที่ต้องวาดโมเดล 700k เหลี่ยมซ้ำ) + กริด
export function Floor({ ringColorRef }) {
  const shadowTex = useMemo(() => {
    const c = document.createElement('canvas');
    c.width = c.height = 256;
    const g = c.getContext('2d');
    const grd = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    grd.addColorStop(0, 'rgba(0,0,0,0.75)');
    grd.addColorStop(0.55, 'rgba(0,0,0,0.35)');
    grd.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grd;
    g.fillRect(0, 0, 256, 256);
    return new THREE.CanvasTexture(c);
  }, []);

  const ring = useRef();
  const mat = useRef();
  const color = useMemo(() => new THREE.Color(), []);
  useFrame((_, dt) => {
    if (ring.current) ring.current.rotation.z += dt * 0.12;
    if (mat.current && ringColorRef?.current) {
      color.set(ringColorRef.current);
      mat.current.color.lerp(color, 1 - Math.exp(-dt * 4));
    }
  });

  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.002, 0]} scale={[7.5, 3.6, 1]}>
        <planeGeometry />
        <meshBasicMaterial map={shadowTex} transparent depthWrite={false} toneMapped={false} />
      </mesh>
      <mesh ref={ring} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.004, 0]}>
        <ringGeometry args={[3.4, 3.44, 160, 1, 0, Math.PI * 1.65]} />
        <meshBasicMaterial ref={mat} color="#38bdf8" transparent opacity={0.6} toneMapped={false} />
      </mesh>
      <Grid
        args={[40, 40]}
        cellSize={0.3}
        cellThickness={0.5}
        cellColor="#1e293b"
        sectionSize={1.8}
        sectionThickness={1}
        sectionColor="#1d4ed8"
        fadeDistance={18}
        fadeStrength={1.6}
        infiniteGrid
      />
    </group>
  );
}

// เอียงทั้งกลุ่มตามตำแหน่งเมาส์แบบหน่วง (ใช้ได้ทั้งตอนเลื่อนหน้าและตอนลากหมุน)
export function PointerTilt({ strength = 1, children }) {
  const g = useRef();
  useFrame((state, dt) => {
    if (!g.current) return;
    const k = 1 - Math.exp(-dt * 2.5);
    g.current.rotation.y += (state.pointer.x * 0.3 * strength - g.current.rotation.y) * k;
    g.current.rotation.x += (-state.pointer.y * 0.08 * strength - g.current.rotation.x) * k;
  });
  return <group ref={g}>{children}</group>;
}

// ป้ายความคืบหน้าการโหลด .glb (26 MB) — เป็น DOM นอก Canvas
export function LoadingOverlay({ failed, className = 'left-1/2' }) {
  const { progress, active } = useProgress();
  if (failed) {
    return (
      <div className={`glass pointer-events-none absolute ${className} top-1/2 z-20 -translate-x-1/2 -translate-y-1/2 rounded-2xl px-4 py-3 text-center text-xs text-amber-200`}>
        โหลดโมเดล Machine.glb ไม่ได้
        <div className="mt-1 text-slate-400">เช็คว่ามีไฟล์ใน cad/export/ และรันผ่าน npm run dev</div>
      </div>
    );
  }
  if (!active) return null;
  return (
    <div className={`pointer-events-none absolute ${className} top-1/2 z-20 w-56 -translate-x-1/2 -translate-y-1/2 text-center`}>
      <div className="mb-2 font-mono text-[11px] tracking-wider text-sky-200">กำลังโหลดโมเดล CAD {progress.toFixed(0)}%</div>
      <div className="h-1 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-gradient-to-r from-sky-400 to-indigo-400 transition-[width] duration-200" style={{ width: `${progress}%` }} />
      </div>
    </div>
  );
}
