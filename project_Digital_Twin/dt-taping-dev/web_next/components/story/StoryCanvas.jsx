'use client';

import { Suspense, useCallback, useMemo, useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { LabelProjector, MachineModel, ModelBoundary, createDirector } from '@/components/three/MachineModel.jsx';
import { Floor, PointerTilt, StageLights } from '@/components/three/Stage.jsx';
import { KEYFRAMES } from './keyframes.js';

const lerp = THREE.MathUtils.lerp;
const tmp = new THREE.Vector3();
const SEAL_CYCLE_S = 2.8; // หนึ่งรอบ กดลง + ยกขึ้น (ภาพประกอบ ไม่ใช่เวลาจริงของเครื่อง)
const SEAL_PRESS_STORY = 2.2; // กดลึกกว่าค่าจริงนิดหน่อยให้เห็นชัดตอนซูม (หน่วย CAD)

// อ่านตำแหน่งเลื่อน (scroll.current.p = 0..N-1 ต่อเนื่อง) → ขับกล้อง + director ทุกเฟรม
function ScrollDirector({ scroll, director, sysRef, store, ringRef }) {
  const smooth = useRef({ p: 0, cam: new THREE.Vector3(8.2, 3.4, -6.0), look: new THREE.Vector3(0, 0.75, 0) });

  useFrame((state, dt) => {
    const sm = smooth.current;
    const target = scroll.current.p;
    sm.p += (target - sm.p) * (1 - Math.exp(-dt * 5)); // เลื่อนนุ่ม ไม่กระตุกตามล้อเมาส์

    const n = KEYFRAMES.length - 1;
    const p = Math.min(n, Math.max(0, sm.p));
    const i = Math.min(n - 1, Math.floor(p));
    const raw = p - i;
    const t = THREE.MathUtils.smoothstep(raw, 0.2, 0.8); // ค้างที่แต่ละ section ช่วงกลาง ๆ
    const a = KEYFRAMES[i];
    const b = KEYFRAMES[i + 1];

    const d = director.current;
    d.explode = lerp(a.explode, b.explode, t);
    d.reveal = lerp(a.reveal, b.reveal, t);
    d.holo = lerp(a.holo, b.holo, t);
    d.labels = lerp(a.labels, b.labels, t);
    d.ghost = lerp(a.ghost ?? 0.55, b.ghost ?? 0.55, t);
    d.focus = t < 0.5 ? a.focus : b.focus;
    ringRef.current = t < 0.5 ? a.ring : b.ring;

    // จุดมอง + ตำแหน่งกล้องของ keyframe (รองรับแบบตามชิ้นส่วน)
    const resolve = (k, out) => {
      if (k.lookPart && store.rig) {
        const part = store.rig.parts.find((x) => x.node.name === k.lookPart);
        if (part) {
          part.anchor.getWorldPosition(tmp);
          out.look.copy(tmp);
          out.cam.copy(tmp).add(new THREE.Vector3(...k.camOffset));
          return out;
        }
      }
      out.look.set(...(k.look ?? [0, 0.8, 0]));
      out.cam.set(...(k.cam ?? [5, 2.5, 6]));
      return out;
    };
    const ka = resolve(a, { cam: new THREE.Vector3(), look: new THREE.Vector3() });
    const kb = resolve(b, { cam: new THREE.Vector3(), look: new THREE.Vector3() });
    const camT = ka.cam.lerp(kb.cam, t);
    const lookT = ka.look.lerp(kb.look, t);

    // จอแคบ: ถอยกล้องออกให้โมเดลเต็มจอ
    const aspect = state.size.width / state.size.height;
    if (aspect < 1) camT.sub(lookT).multiplyScalar(1 + (1 - aspect) * 0.9).add(lookT);

    // จอกว้าง: เลื่อนทั้งกล้องและจุดมองไปทางซ้ายของภาพ → โมเดลไปอยู่ขวา พ้นข้อความ
    if (aspect > 1.2) {
      const shift = lerp(a.shift ?? 0, b.shift ?? 0, t);
      const dist = camT.distanceTo(lookT);
      const right = tmp.subVectors(lookT, camT).cross(THREE.Object3D.DEFAULT_UP).normalize();
      const amount = -shift * dist * 0.22 * Math.min(1, (aspect - 1.2) * 2);
      camT.addScaledVector(right, amount);
      lookT.addScaledVector(right, amount);
    }

    const k = 1 - Math.exp(-dt * 4);
    sm.cam.lerp(camT, k);
    sm.look.lerp(lookT, k);
    state.camera.position.copy(sm.cam);
    state.camera.lookAt(sm.look);

    // section ที่ตั้ง seal: true — วนจังหวะซีล — กดลง (SEAL_PROCESS) ครึ่งรอบ / ยกขึ้น + เทปเดิน (FEED_CARRIER) อีกครึ่ง
    const near = Math.round(sm.p);
    const inSeal = Boolean(KEYFRAMES[near]?.seal) && Math.abs(sm.p - near) < 0.5;
    const sys = sysRef.current;
    sys.running = true;
    if (inSeal) {
      const phase = (state.clock.elapsedTime % SEAL_CYCLE_S) / SEAL_CYCLE_S;
      const down = phase < 0.5;
      sys.current_state = down ? 'SEAL_PROCESS' : 'FEED_CARRIER';
      d.arrow = down ? -1 : 1;
      d.sealPress = SEAL_PRESS_STORY;
      scroll.current.seal = down ? 'down' : 'up';
    } else {
      sys.current_state = d.explode > 0.05 ? 'READY' : 'FEED_CARRIER';
      d.arrow = 0;
      d.sealPress = 1;
      scroll.current.seal = null;
    }
  });
  return null;
}

export default function StoryCanvas({ scroll, store, onModelFail }) {
  const director = useRef(createDirector(KEYFRAMES[0]));
  const sysRef = useRef({ running: true, current_state: 'FEED_CARRIER', speed_mul: 0.6 });
  const ringRef = useRef('#38bdf8');
  const onRig = useCallback((rig) => {
    store.rig = rig;
  }, [store]);
  const dpr = useMemo(() => [1, 1.75], []);

  return (
    <Canvas
      dpr={dpr}
      camera={{ position: [8.2, 3.4, -6.0], fov: 35, near: 0.1, far: 100 }}
      gl={{ antialias: true, alpha: true, toneMapping: THREE.ACESFilmicToneMapping, powerPreference: 'high-performance' }}
      onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}
    >
      <fog attach="fog" args={['#05070d', 10, 26]} />
      <StageLights />
      <PointerTilt strength={0.8}>
        <ModelBoundary onFail={onModelFail}>
          <Suspense fallback={null}>
            <MachineModel director={director} sysRef={sysRef} onRig={onRig} />
          </Suspense>
        </ModelBoundary>
      </PointerTilt>
      <Floor ringColorRef={ringRef} />
      <ScrollDirector scroll={scroll} director={director} sysRef={sysRef} store={store} ringRef={ringRef} />
      <LabelProjector store={store} director={director} />
    </Canvas>
  );
}
