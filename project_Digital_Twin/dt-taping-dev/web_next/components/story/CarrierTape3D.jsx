'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Environment, Lightformer } from '@react-three/drei';
import * as THREE from 'three';

// ภาพประกอบ carrier tape แบบ 3D — สร้างรูปทรงในโค้ดทั้งหมด ไม่ได้มาจากแบบของชิ้นงานจริง
// (ชิ้นงาน + เทปของลูกค้าห้ามลง repo — CLAUDE.md ข้อ 7.4) · สัดส่วนเป็นแบบทั่วไปของเทปขึ้นรูปหลุมสี่เหลี่ยม

const P = 1; // ระยะระหว่างหลุม (หน่วยฉาก)
const N = 10; // จำนวนหลุมที่วาด — วนเลื่อนต่อกันไม่รู้จบ
const W = 1.55; // ความกว้างเทป
const T = 0.035; // ความหนาแผ่นเทป
const OPEN = 0.74; // ขนาดปากหลุม
const BOTTOM = 0.6; // ขนาดก้นหลุม (ผนังเอียงเข้า)
const DEPTH = 0.5; // ความลึกหลุม
const HOLE_R = 0.034; // รูสเตอร์
const HOLE_EDGE = 0.66; // ระยะแถวรูจากแกนกลางเทป

const plastic = { color: '#131417', roughness: 0.78, metalness: 0.0, envMapIntensity: 0.3 };

function roundedRectPath(path, cx, cy, s, r) {
  const h = s / 2;
  path.moveTo(cx - h + r, cy - h);
  path.lineTo(cx + h - r, cy - h);
  path.quadraticCurveTo(cx + h, cy - h, cx + h, cy - h + r);
  path.lineTo(cx + h, cy + h - r);
  path.quadraticCurveTo(cx + h, cy + h, cx + h - r, cy + h);
  path.lineTo(cx - h + r, cy + h);
  path.quadraticCurveTo(cx - h, cy + h, cx - h, cy + h - r);
  path.lineTo(cx - h, cy - h + r);
  path.quadraticCurveTo(cx - h, cy - h, cx - h + r, cy - h);
  return path;
}

// แผ่นเทปด้านบน: สี่เหลี่ยมยาว เจาะปากหลุม + รูสเตอร์สองขอบ (ขอบมน bevel ให้รับแสงเป็นเส้นแบบในรูปถ่าย)
function useFlangeGeometry() {
  return useMemo(() => {
    const len = N * P;
    const shape = new THREE.Shape();
    shape.moveTo(-len / 2, -W / 2);
    shape.lineTo(len / 2, -W / 2);
    shape.lineTo(len / 2, W / 2);
    shape.lineTo(-len / 2, W / 2);
    shape.lineTo(-len / 2, -W / 2);
    for (let i = 0; i < N; i++) {
      const cx = -len / 2 + P / 2 + i * P;
      shape.holes.push(roundedRectPath(new THREE.Path(), cx, 0, OPEN, 0.05));
      for (let k = 0; k < 4; k++) {
        const hx = -len / 2 + i * P + (k + 0.5) * (P / 4);
        for (const y of [-HOLE_EDGE, HOLE_EDGE]) {
          const hole = new THREE.Path();
          hole.absarc(hx, y, HOLE_R, 0, Math.PI * 2, true);
          shape.holes.push(hole);
        }
      }
    }
    const g = new THREE.ExtrudeGeometry(shape, {
      depth: T,
      bevelEnabled: true,
      bevelThickness: 0.008,
      bevelSize: 0.008,
      bevelSegments: 2,
      curveSegments: 10,
    });
    g.rotateX(-Math.PI / 2); // นอนราบ ด้านบนหันขึ้น
    return g;
  }, []);
}

// ผนังหลุม: กรวยเหลี่ยม 4 ด้าน (ปากกว้าง ก้นแคบ) เปิดด้านบน — ก้นหลุมวาดแยก · flat shading ให้เห็นเหลี่ยมคม
function usePocketGeometry() {
  return useMemo(() => {
    const rTop = OPEN / Math.SQRT2;
    const rBot = BOTTOM / Math.SQRT2;
    const g = new THREE.CylinderGeometry(rTop, rBot, DEPTH, 4, 1, true);
    g.rotateY(Math.PI / 4);
    g.translate(0, -DEPTH / 2, 0);
    return g;
  }, []);
}

// ชิ้นงาน SMD ทั่วไป: ตัวถังดำ + ขาเงินสองข้าง (ไม่ใช่ชิ้นงานของลูกค้า)
function Chip() {
  const legs = [-0.18, -0.06, 0.06, 0.18];
  return (
    <group position={[0, -DEPTH + 0.26, 0]}>
      <mesh castShadow>
        <boxGeometry args={[0.46, 0.4, 0.46]} />
        <meshPhysicalMaterial color="#26282e" roughness={0.4} clearcoat={0.5} />
      </mesh>
      <mesh position={[0.12, 0.201, 0.12]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[0.025, 20]} />
        <meshStandardMaterial color="#3f3f46" />
      </mesh>
      {legs.map((z) =>
        [-1, 1].map((side) => (
          <mesh key={`${z}${side}`} position={[side * 0.255, -0.17, z]}>
            <boxGeometry args={[0.07, 0.03, 0.05]} />
            <meshStandardMaterial color="#d4d4d8" metalness={1} roughness={0.25} />
          </mesh>
        )),
      )}
    </group>
  );
}

// ผิวด้านมีเม็ดละเอียด (พลาสติกนำไฟฟ้า) — noise เทาเข้มบน canvas ใช้เป็น map + roughnessMap
function useSpeckle() {
  return useMemo(() => {
    const c = document.createElement('canvas');
    c.width = c.height = 128;
    const g = c.getContext('2d');
    const img = g.createImageData(128, 128);
    for (let i = 0; i < img.data.length; i += 4) {
      const v = 150 + Math.random() * 105;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
      img.data[i + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    const t = new THREE.CanvasTexture(c);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(12, 12);
    return t;
  }, []);
}

function Tape({ paused }) {
  const flange = useFlangeGeometry();
  const speckle = useSpeckle();
  const pocket = usePocketGeometry();
  const strip = useRef();
  const offset = useRef(0);
  // หลุมที่ว่าง (ยังไม่วางชิ้นงาน) — ให้ภาพเล่าว่า "หนึ่งหลุม หนึ่งชิ้น"
  const empty = useMemo(() => new Set([6, 7, 8, 9]), []);

  useFrame((_, dt) => {
    if (paused.current) return;
    offset.current = (offset.current + dt * 0.18) % P;
    if (strip.current) strip.current.position.x = offset.current;
  });

  return (
    <group ref={strip}>
      <mesh geometry={flange} castShadow receiveShadow>
        <meshPhysicalMaterial {...plastic} map={speckle} roughnessMap={speckle} />
      </mesh>
      {Array.from({ length: N }, (_, i) => {
        const x = -(N * P) / 2 + P / 2 + i * P;
        return (
          <group key={i} position={[x, 0, 0]}>
            <mesh geometry={pocket} castShadow receiveShadow>
              <meshPhysicalMaterial {...plastic} side={THREE.DoubleSide} flatShading />
            </mesh>
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -DEPTH, 0]} receiveShadow>
              <planeGeometry args={[BOTTOM, BOTTOM]} />
              <meshPhysicalMaterial {...plastic} />
            </mesh>
            {!empty.has(i) && <Chip />}
          </group>
        );
      })}
    </group>
  );
}

// พื้นลายร่องละเอียด (เหมือนแผ่นยางใต้เทปในภาพสินค้า) — texture วาดเองจาก canvas
function RibbedFloor() {
  const tex = useMemo(() => {
    const c = document.createElement('canvas');
    c.width = 16;
    c.height = 256;
    const g = c.getContext('2d');
    for (let y = 0; y < 256; y += 4) {
      g.fillStyle = y % 8 === 0 ? '#2a2c31' : '#0b0c0f';
      g.fillRect(0, y, 16, 4);
    }
    const t = new THREE.CanvasTexture(c);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(1, 60);
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }, []);
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0.5]} position={[0, -DEPTH - 0.02, 0]} receiveShadow>
      <planeGeometry args={[20, 20]} />
      <meshStandardMaterial map={tex} roughness={0.6} metalness={0.3} envMapIntensity={0.8} />
    </mesh>
  );
}

// กล้องมุมต่ำเฉียงแบบภาพถ่ายสินค้า + ขยับตามเมาส์เล็กน้อย
function Rig() {
  const target = useMemo(() => new THREE.Vector3(0.1, -0.22, 0.2), []);
  useFrame((state, dt) => {
    const k = 1 - Math.exp(-dt * 2);
    const px = 2.2 + state.pointer.x * 0.4;
    const py = 0.42 + state.pointer.y * 0.18;
    state.camera.position.x += (px - state.camera.position.x) * k;
    state.camera.position.y += (py - state.camera.position.y) * k;
    state.camera.lookAt(target);
  });
  return null;
}

export default function CarrierTape3D() {
  const box = useRef(null);
  const paused = useRef(false);
  const [visible, setVisible] = useState(false);

  // วาดเฉพาะตอนการ์ดอยู่บนจอ — ประหยัด GPU เพราะหน้านี้มีฉากใหญ่อีกตัวอยู่ด้านหลัง
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { rootMargin: '200px' });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    paused.current = mq.matches;
  }, []);

  return (
    <div ref={box} className="relative mt-6 aspect-[16/10] w-full overflow-hidden rounded-2xl border border-white/10 bg-[#07080b]">
      <Canvas
        shadows
        dpr={[1, 2]}
        frameloop={visible ? 'always' : 'never'}
        camera={{ position: [2.2, 0.42, 2.3], fov: 30 }}
        gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping }}
      >
        <color attach="background" args={['#07080b']} />
        <fog attach="fog" args={['#07080b', 3.2, 7]} />
        <ambientLight intensity={0.12} />
        {/* ไฟหลักย้อนแสงจากด้านหลัง-บน → ขอบหลุม / ขอบรู / ขอบเทปเป็นเส้นสว่าง · ไฟเติมด้านหน้าให้เห็นผนังหลุมใต้เทป */}
        <directionalLight position={[-3, 1.4, -2.2]} intensity={1.6} castShadow shadow-mapSize={[1024, 1024]} />
        <directionalLight position={[2.5, 0.3, 2.8]} intensity={0.45} color="#e2e8f0" />
        {/* ไฟต่ำด้านหน้าใต้ระดับเทป → ส่องผนังหลุมที่ห้อยอยู่ใต้เทปให้เห็นเป็นกล่องเหลี่ยม */}
        <pointLight position={[1.2, -0.35, 2.2]} intensity={3.5} distance={6} color="#cbd5e1" />
        <Environment resolution={128}>
          <Lightformer intensity={1.2} position={[-4, 0.8, -3]} scale={[8, 0.8, 1]} color="#ffffff" />
          <Lightformer intensity={0.4} position={[3, 0.2, 3]} scale={[4, 0.4, 1]} color="#bfdbfe" />
        </Environment>
        <group rotation={[0, -0.35, 0]} position={[0, 0, 0]}>
          <Tape paused={paused} />
          {/* พื้นร่องละเอียดสีเข้มใต้เทป */}
          <RibbedFloor />
        </group>
        <Rig />
      </Canvas>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between bg-gradient-to-t from-black/70 to-transparent px-3 pb-2 pt-8 text-[10px] text-slate-400">
        <span>ภาพประกอบ 3D — ไม่ใช่แบบของชิ้นงานจริง</span>
        <span className="font-mono">carrier tape</span>
      </div>
    </div>
  );
}
