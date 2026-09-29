'use client';

import { Suspense, useCallback, useMemo, useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { LabelProjector, MachineModel, ModelBoundary, createDirector } from '@/components/three/MachineModel.jsx';
import { Floor, PointerTilt, StageLights } from '@/components/three/Stage.jsx';
import { ALARM_STATE } from '@/lib/twin.js';

// ค่อย ๆ ขยับ director ไปหาค่าที่ปุ่มบน HUD ตั้ง (แยกชิ้น / โฮโลแกรม) + สีวงแหวนตามสถานะเครื่อง
function TwinDirector({ view, director, sysRef, ringRef }) {
  useFrame((_, dt) => {
    const v = view.current;
    const d = director.current;
    const k = 1 - Math.exp(-dt * 3);
    d.explode += ((v.exploded ? 1 : 0) - d.explode) * k;
    d.labels += ((v.exploded ? 1 : 0) - d.labels) * k;
    d.holo += ((v.xray ? 1 : 0) - d.holo) * k;
    d.reveal += ((v.xray ? 0.12 : 1) - d.reveal) * k;
    const s = sysRef.current;
    ringRef.current = s.current_state === ALARM_STATE ? '#f87171' : s.running ? '#38bdf8' : '#64748b';
  });
  return null;
}

export default function TwinCanvas({ sysRef, view, store, onModelFail }) {
  const director = useRef(createDirector({ reveal: 1, holo: 0 }));
  const ringRef = useRef('#64748b');
  const onRig = useCallback((rig) => {
    store.rig = rig;
  }, [store]);
  const dpr = useMemo(() => [1, 1.75], []);

  return (
    <Canvas
      dpr={dpr}
      camera={{ position: [9.6, 4.2, -6.8], fov: 34, near: 0.1, far: 100 }}
      gl={{ antialias: true, alpha: true, toneMapping: THREE.ACESFilmicToneMapping, powerPreference: 'high-performance' }}
      onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}
    >
      <fog attach="fog" args={['#05070d', 11, 26]} />
      <StageLights />
      <PointerTilt strength={0.5}>
        <ModelBoundary onFail={onModelFail}>
          <Suspense fallback={null}>
            <MachineModel director={director} sysRef={sysRef} onRig={onRig} />
          </Suspense>
        </ModelBoundary>
      </PointerTilt>
      <Floor ringColorRef={ringRef} />
      <TwinDirector view={view} director={director} sysRef={sysRef} ringRef={ringRef} />
      <LabelProjector store={store} director={director} />
      <OrbitControls
        makeDefault
        enablePan={false}
        enableDamping
        dampingFactor={0.06}
        rotateSpeed={0.7}
        minDistance={4}
        maxDistance={17}
        minPolarAngle={Math.PI * 0.1}
        maxPolarAngle={Math.PI * 0.48}
        target={[0, 0.9, 0]}
        autoRotate
        autoRotateSpeed={0.3}
      />
    </Canvas>
  );
}
