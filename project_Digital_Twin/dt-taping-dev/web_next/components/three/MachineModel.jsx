'use client';

import { Component, useLayoutEffect, useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import * as THREE from 'three';
import { ALARM_STATE, PARTS } from '@/lib/twin.js';

export const MODEL_URL = '/models/Machine.glb';
const FIT = 6; // ย่อโมเดลให้เส้นทแยงกล่องยาวเท่านี้ (หน่วยฉาก)
const GHOST = 0.1; // ความทึบของชิ้นที่ไม่ได้โฟกัส
const SEAL_PRESS = 1.0; // ระยะกดของหัวซีลค่าตั้งต้น (หน่วย CAD) — หน้าแรกช่วง Sealing ตั้งให้ลึกขึ้นเพื่อให้เห็นชัด
const SPIN_NODES = ['Roll_1', 'Roll_2'];

// ─────────────────────────────────────────────────────────────
// "director" = ออบเจกต์ธรรมดาที่หน้าเว็บเขียนค่าใส่ แล้วโมเดลอ่านทุกเฟรม (ไม่ผ่าน React state)
//   explode 0..1  แยกชิ้น · reveal 0..1 โมเดลจริง · holo 0..1 โฮโลแกรม
//   labels 0..1   ป้ายชื่อชิ้นส่วน · focus ชื่อ node (หรือ array ของชื่อ) ที่โฟกัส ชิ้นอื่นจางลง · null = ไม่โฟกัส
//   sealPress     ระยะกดหัวซีล (หน่วย CAD) · arrow −1 ลง / +1 ขึ้น / 0 ซ่อน — ลูกศรข้างหัวซีล
// ─────────────────────────────────────────────────────────────
export function createDirector(init = {}) {
  return { explode: 0, reveal: 1, holo: 0, labels: 0, focus: null, sealPress: SEAL_PRESS, arrow: 0, ...init };
}

const focusList = (f) => (f == null ? [] : Array.isArray(f) ? f : [f]);

// เปลือกโฮโลแกรม: fresnel ขอบเรือง + เส้นสแกนวิ่งตามแกน y (additive ไม่เขียน depth)
function makeHoloMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uOpacity: { value: 0 },
      uColor: { value: new THREE.Color('#0b3b66') },
      uRim: { value: new THREE.Color('#67e8f9') },
    },
    vertexShader: /* glsl */ `
      varying vec3 vN;
      varying vec3 vV;
      varying float vY;
      void main() {
        vec4 wp = modelMatrix * vec4(position, 1.0);
        vY = wp.y;
        vec4 mv = viewMatrix * wp;
        vV = -mv.xyz;
        vN = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      uniform float uTime;
      uniform float uOpacity;
      uniform vec3 uColor;
      uniform vec3 uRim;
      varying vec3 vN;
      varying vec3 vV;
      varying float vY;
      void main() {
        float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 2.0);
        float scan = smoothstep(0.93, 1.0, sin(vY * 16.0 - uTime * 2.4));
        vec3 c = mix(uColor, uRim, f) + uRim * scan * 0.6;
        float a = (0.04 + f * 0.8 + scan * 0.35) * uOpacity;
        gl_FragColor = vec4(c, a);
      }`,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide,
  });
}

// ห่อชิ้นส่วนด้วย pivot ที่กลางกล่องของมัน — ลูกกลิ้งใน CAD มี origin อยู่ที่ศูนย์ของทั้งเครื่อง
function wrapInPivot(obj) {
  const parent = obj.parent;
  const center = new THREE.Box3().setFromObject(obj).getCenter(new THREE.Vector3());
  const pivot = new THREE.Group();
  pivot.name = `${obj.name}__pivot`;
  pivot.position.copy(parent.worldToLocal(center));
  pivot.quaternion.copy(obj.quaternion);
  parent.add(pivot);
  pivot.updateMatrixWorld(true);
  pivot.attach(obj);
  return pivot;
}

// แกนหมุนของจาน = แกนที่บางที่สุดของ geometry (ในพิกัดของชิ้นเอง)
function thinAxis(obj) {
  const box = new THREE.Box3();
  obj.traverse((o) => {
    if (o.isMesh) {
      o.geometry.computeBoundingBox();
      box.union(o.geometry.boundingBox);
    }
  });
  const s = box.getSize(new THREE.Vector3());
  if (s.x <= s.y && s.x <= s.z) return new THREE.Vector3(1, 0, 0);
  if (s.y <= s.x && s.y <= s.z) return new THREE.Vector3(0, 1, 0);
  return new THREE.Vector3(0, 0, 1);
}

// เตรียมโมเดลครั้งเดียวต่อฉาก: clone, ย่อให้พอดี, แยกวัสดุ, สร้างเปลือกโฮโลแกรม, จุดยึดป้าย
function buildRig(scene) {
  const root = scene.clone(true);
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const s = FIT / size.length();
  const offset = new THREE.Vector3(-center.x * s, -box.min.y * s, -center.z * s);

  const parts = [];
  for (const info of PARTS) {
    const node = root.getObjectByName(info.node);
    if (!node) continue;
    const spin = SPIN_NODES.includes(info.node);
    const axis = spin ? thinAxis(node) : null;
    const partCenter = new THREE.Box3().setFromObject(node).getCenter(new THREE.Vector3());
    const mover = spin ? wrapInPivot(node) : node;

    const holo = makeHoloMaterial();
    const reals = [];
    const holoMeshes = [];
    node.traverse((o) => {
      if (!o.isMesh) return;
      const mats = (Array.isArray(o.material) ? o.material : [o.material]).map((m) => {
        const c = m.clone();
        c.transparent = true;
        c.envMapIntensity = 1.15;
        if (!c.emissive) c.emissive = new THREE.Color(0, 0, 0);
        reals.push(c);
        return c;
      });
      o.material = Array.isArray(o.material) ? mats : mats[0];
      o.userData.real = true;
      const h = new THREE.Mesh(o.geometry, holo);
      h.renderOrder = 2;
      h.raycast = () => {};
      holoMeshes.push(h);
    });
    // เพิ่มหลัง traverse — ห้ามแก้โครงต้นไม้ระหว่างเดิน
    let i = 0;
    node.traverse((o) => {
      if (o.isMesh && o.userData.real && i < holoMeshes.length) o.add(holoMeshes[i++]);
    });

    const anchor = new THREE.Object3D();
    mover.updateMatrixWorld(true);
    anchor.position.copy(mover.worldToLocal(partCenter.clone()));
    mover.add(anchor);

    parts.push({
      ...info,
      node,
      mover,
      anchor,
      reals,
      holo,
      holoMeshes,
      axis,
      angle: 0,
      basePos: mover.position.clone(),
      baseQuat: mover.quaternion.clone(),
      explodeVec: new THREE.Vector3(...info.explode).divideScalar(s),
      state: { reveal: -1, holo: -1, glow: -1 },
    });
  }
  return { root, s, offset, parts };
}

const tmpQ = new THREE.Quaternion();
const cyan = new THREE.Color('#38bdf8');

export function MachineModel({ director, sysRef, onRig }) {
  const { scene } = useGLTF(MODEL_URL);
  const rig = useMemo(() => buildRig(scene), [scene]);

  useLayoutEffect(() => {
    onRig?.(rig);
    return () => onRig?.(null);
  }, [rig, onRig]);

  useFrame((state, dt) => {
    const d = director.current ?? director;
    const sys = sysRef?.current;
    const time = state.clock.elapsedTime;
    const run = sys && sys.running && sys.current_state !== ALARM_STATE;
    const speed = Math.max(0.25, Number(sys?.speed_mul) || 1);

    rig.parts.forEach((p, i) => {
      // แยกชิ้น — ชิ้นหลัง ๆ ออกตัวช้ากว่านิด (stagger) ให้ดูเป็นลำดับ
      const e = THREE.MathUtils.smoothstep(d.explode, i * 0.06, 0.6 + i * 0.06);
      p.mover.position.copy(p.basePos).addScaledVector(p.explodeVec, e);

      // ลูกกลิ้ง: หมุนตาม state ของเครื่อง
      if (p.axis) {
        const turning =
          run && ((p.node.name === 'Roll_1' && sys.current_state === 'FEED_CARRIER') || (p.node.name === 'Roll_2' && sys.current_state === 'TAKEUP_REEL'));
        if (turning) p.angle -= dt * 2.2 * speed;
        p.mover.quaternion.copy(p.baseQuat).multiply(tmpQ.setFromAxisAngle(p.axis, p.angle));
      }
      // หัวซีล: กดลงตอน SEAL_PROCESS
      if (p.node.name === 'Sealing') {
        const target = p.basePos.y - (sys?.current_state === 'SEAL_PROCESS' ? d.sealPress ?? SEAL_PRESS : 0);
        p.pressY = (p.pressY ?? p.basePos.y) + (target - (p.pressY ?? p.basePos.y)) * (1 - Math.exp(-dt * 8));
        p.mover.position.y += p.pressY - p.basePos.y;
      }

      // วัสดุ — อัปเดตเฉพาะตอนค่าเปลี่ยนจริง
      const fl = focusList(d.focus);
      const focused = fl.includes(p.node.name);
      const dim = fl.length > 0 && !focused;
      const reveal = d.reveal * (dim ? GHOST : 1);
      const holo = Math.max(d.holo, dim ? d.ghost ?? 0.55 : 0); // ghost = ความเรืองของชิ้นที่ไม่ได้โฟกัส
      // เรืองเฉพาะชิ้นแรกในรายการโฟกัส (ชิ้นหลัก) ชิ้นที่เหลือแค่ไม่จาง
      const glow = focused && fl[0] === p.node.name ? 0.35 + 0.15 * Math.sin(time * 3) : 0;
      if (Math.abs(reveal - p.state.reveal) > 0.004) {
        p.state.reveal = reveal;
        for (const m of p.reals) {
          m.opacity = reveal;
          m.depthWrite = reveal > 0.6;
          m.visible = reveal > 0.01;
        }
      }
      if (Math.abs(glow - p.state.glow) > 0.004) {
        p.state.glow = glow;
        for (const m of p.reals) m.emissive.copy(cyan).multiplyScalar(glow);
      }
      if (Math.abs(holo - p.state.holo) > 0.004) {
        p.state.holo = holo;
        p.holo.uniforms.uOpacity.value = holo;
        for (const h of p.holoMeshes) h.visible = holo > 0.01;
      }
      p.holo.uniforms.uTime.value = time;
    });
  });

  return (
    <group scale={rig.s} position={rig.offset}>
      <primitive object={rig.root} />
    </group>
  );
}

// ─────────────────────────────────────────────────────────────
// ป้ายชื่อชิ้นส่วน — วาดเป็น DOM นอก Canvas แล้วให้ LabelProjector (ใน Canvas) ขยับทุกเฟรม
// (ไม่ใช้ drei <Html> เพราะถอดออกกลางเฟรมแล้ว React 19 error)
// ─────────────────────────────────────────────────────────────
export function createLabelStore() {
  return { rig: null, els: {} };
}

const v3 = new THREE.Vector3();
export function LabelProjector({ store, director }) {
  const { camera, size } = useThree();
  useFrame(() => {
    const d = director.current ?? director;
    const rig = store.rig;
    if (!rig) return;
    for (const p of rig.parts) {
      const name = p.node.name; // p.node เป็น Object3D แล้ว (buildRig แทนที่ชื่อด้วยออบเจกต์)
      const el = store.els[name];
      if (!el) continue;
      p.anchor.getWorldPosition(v3);
      v3.project(camera);
      const behind = v3.z > 1;
      const x = (v3.x * 0.5 + 0.5) * size.width;
      const y = (-v3.y * 0.5 + 0.5) * size.height;
      const fl = focusList(d.focus);
      const show = fl.length ? (fl.includes(name) ? 1 : 0) : 1;
      const op = behind ? 0 : d.labels * show;
      el.style.opacity = op.toFixed(3);
      el.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0) translate(-50%, -100%)`;
    }

    // ลูกศรบอกทิศหัวซีล (↓ กดลง / ↑ ยกขึ้น) — ยึดกับจุดกลางของ Sealing แล้วเลื่อนไปทางขวา
    const arrow = store.arrowEl;
    const seal = rig.parts.find((p) => p.node.name === 'Sealing');
    if (arrow && seal) {
      seal.anchor.getWorldPosition(v3);
      v3.project(camera);
      const x = (v3.x * 0.5 + 0.5) * size.width;
      const y = (-v3.y * 0.5 + 0.5) * size.height;
      arrow.style.opacity = d.arrow && v3.z <= 1 ? '1' : '0';
      arrow.style.transform = `translate3d(${x.toFixed(1)}px, ${(y - 110).toFixed(1)}px, 0) translate(-50%, -50%)`;
      arrow.dataset.dir = d.arrow < 0 ? 'down' : 'up';
    }
  });
  return null;
}

export function PartLabels({ store }) {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      {PARTS.map((p, i) => (
        <div
          key={p.node}
          ref={(el) => {
            if (el) store.els[p.node] = el;
            else delete store.els[p.node];
          }}
          className="absolute left-0 top-0 opacity-0 will-change-transform"
        >
          <div className="glass mb-2 flex items-center gap-2 whitespace-nowrap rounded-full py-1 pl-1 pr-3 text-[11px]">
            <span className="grid h-5 w-5 place-items-center rounded-full bg-sky-400/20 font-mono text-[10px] text-sky-200">{i + 1}</span>
            <span className="font-medium text-white">{p.name}</span>
            <span className="text-slate-400">{p.en}</span>
          </div>
          <div className="mx-auto h-5 w-px bg-gradient-to-b from-sky-300/70 to-transparent" />
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
export class ModelBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(err) {
    console.warn('[twin] โหลด Machine.glb ไม่ได้:', err?.message ?? err);
    this.props.onFail?.();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}
