/**
 * 3D-Szene (SPEC 10.3 Mitte). Koordinaten: SPEC (x Wasser, y links, z oben) → three (x, z, −y).
 * Brett mit Biegelinie des Kragbalkens (Auflager Fulkrum, Lager Anker), skaliert auf z_b.
 * Level 1: illustrative Figur (KSP-Höhe und Beinlänge simuliert, Gelenke/Arme abgeleitet).
 * Level 2: simulierte Segmentkette (12 Körperpunkte); im Flug Haltung ab TO eingefroren,
 * Rotation mit ω = H/I.
 */
import { Html, Line, OrbitControls } from '@react-three/drei';
import { Canvas, useThree } from '@react-three/fiber';
import { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib';
import { frameAt, type View } from '../lib/view';
import { useStore } from '../store';

const RED = '#E10600';
const BOARD_W = 0.495;
const BOARD_T = 0.06;

export type CamPreset = 'side' | 'front' | 'board';

function sampleAt(r: View, t: number) {
  const i = frameAt(r, t);
  return { i, z_c: r.com_z[i], x_c: r.com_x[i], z_b: r.z_b[i], x_b: r.x_b[i], F: r.F[i], Fx: r.Fx[i], l: r.l ? r.l[i] : 0 };
}

/** Normierte Biegelinie: Überhang (s ab Fulkrum, 0..a) und Spannfeld (u ab Anker, 0..L). */
function overhangShape(s: number, a: number, L: number) {
  return (s * (2 * a * L + 3 * a * s - s * s)) / (2 * a * a * (L + a));
}
function spanShape(u: number, a: number, L: number) {
  return -(u * (L * L - u * u)) / (2 * a * L * (L + a));
}

function Board({ r, t }: { r: View; t: number }) {
  const { overhang: a, span: L } = r.geom;
  const len = a + L;
  const geo = useMemo(() => new THREE.BoxGeometry(len, BOARD_T, BOARD_W, 120, 1, 1), [len]);
  const base = useMemo(() => Float32Array.from(geo.attributes.position.array), [geo]);
  const { z_b, x_b } = sampleAt(r, t);
  useLayoutEffect(() => {
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const x0 = base[i * 3] + len / 2 - L; // relativ zum Fulkrum: −L..a
      const y0 = base[i * 3 + 1];
      let w = 0;
      let dx = 0;
      if (x0 >= 0) { w = z_b * overhangShape(x0, a, L); dx = x_b * (x0 / a) ** 2; } else { w = z_b * spanShape(x0 + L, a, L); }
      pos.setX(i, x0 - a + dx);
      pos.setY(i, y0 - BOARD_T / 2 + w);
    }
    pos.needsUpdate = true;
    geo.computeVertexNormals();
  }, [geo, base, z_b, x_b, a, L, len]);
  return (
    <group>
      <mesh geometry={geo} castShadow>
        <meshStandardMaterial color="#d9d9de" roughness={0.6} metalness={0.05} />
      </mesh>
      {/* Fulkrum-Rolle und Unterbau */}
      <mesh position={[-a, -BOARD_T - 0.06, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.06, 0.06, BOARD_W + 0.2, 24]} />
        <meshStandardMaterial color={RED} roughness={0.4} />
      </mesh>
      <mesh position={[-a, -1.6, 0]}>
        <boxGeometry args={[0.25, 2.9, 0.9]} />
        <meshStandardMaterial color="#2A2A30" />
      </mesh>
      <mesh position={[-a - L, -1.6, 0]}>
        <boxGeometry args={[0.25, 2.9, 0.9]} />
        <meshStandardMaterial color="#2A2A30" />
      </mesh>
      <mesh position={[-a - L / 2, -3.05, 0]}>
        <boxGeometry args={[L + 1.2, 0.1, 2]} />
        <meshStandardMaterial color="#16161A" />
      </mesh>
    </group>
  );
}

function Limb({ a, b, r, color = '#F4F4F5' }: { a: THREE.Vector3; b: THREE.Vector3; r: number; color?: string }) {
  const ref = useRef<THREE.Mesh>(null);
  useLayoutEffect(() => {
    const m = ref.current;
    if (!m) return;
    const d = new THREE.Vector3().subVectors(b, a);
    const len = d.length();
    m.position.copy(a).addScaledVector(d, 0.5);
    m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.clone().normalize());
    m.scale.set(1, Math.max(len, 1e-3), 1);
  }, [a, b]);
  return (
    <mesh ref={ref} castShadow>
      <cylinderGeometry args={[r, r, 1, 12]} />
      <meshStandardMaterial color={color} roughness={0.5} />
    </mesh>
  );
}

/** Zwei-Glied-IK in der Sagittalebene, Knie nach vorn (+x). */
function knee(ankle: THREE.Vector3, hip: THREE.Vector3, l1: number, l2: number): THREE.Vector3 {
  const d = new THREE.Vector3().subVectors(hip, ankle);
  const D = Math.min(d.length(), l1 + l2 - 1e-4);
  const cosA = (l2 * l2 + D * D - l1 * l1) / (2 * l2 * D);
  const ang = Math.acos(Math.max(-1, Math.min(1, cosA)));
  const base = Math.atan2(d.y, d.x);
  const th = base - ang; // Knie vor der Linie
  return new THREE.Vector3(ankle.x + l2 * Math.cos(th), ankle.y + l2 * Math.sin(th), 0);
}

const SKELETON: [number, number, number, string?][] = [
  // [Punkt a, Punkt b, Radius/H, Farbe]
  [0, 1, 0.016], [1, 2, 0.02], [1, 3, 0.02], [2, 3, 0.02], [3, 4, 0.026], [4, 5, 0.036],
  [5, 7, 0.07], [6, 9, 0.022, '#A1A1AA'], [9, 10, 0.019, '#A1A1AA'], [10, 11, 0.015, '#A1A1AA'],
];

function Diver2({ r, t }: { r: View; t: number }) {
  const { H } = r.geom;
  const s = sampleAt(r, t);
  const P = r.points!;
  const pt = (k: number, side = 0) => new THREE.Vector3(P[s.i * 24 + 2 * k], P[s.i * 24 + 2 * k + 1], side);
  const head = pt(7).lerp(pt(8), 0.55);
  const BW = r.geom.M * 9.81;
  const contact = t >= 0 && t <= r.events.TO;
  const F = new THREE.Vector2(s.Fx, s.F);
  const fLen = (F.length() / BW) * 0.25;
  const ang = Math.atan2(F.x, F.y);
  const foot = pt(1);
  return (
    <group>
      {[-1, 1].map((side) => (
        <group key={side}>
          {SKELETON.map(([a, b, rad, col], k) => {
            const lateral = k === 6 ? 0 : side * (k >= 7 ? 0.1 : 0.055) * H;
            return <Limb key={k} a={pt(a, lateral)} b={pt(b, lateral)} r={rad * H} color={col} />;
          })}
        </group>
      ))}
      <mesh position={head}><sphereGeometry args={[0.065 * H, 20, 16]} /><meshStandardMaterial color="#F4F4F5" /></mesh>
      <mesh position={[s.x_c, s.z_c, 0]}><sphereGeometry args={[0.035, 16, 12]} /><meshBasicMaterial color={RED} /></mesh>
      {contact && fLen > 0.005 && (
        <group position={[foot.x, foot.y, 0.3]} rotation={[0, 0, -ang]}>
          <mesh position={[0, fLen / 2, 0]}><cylinderGeometry args={[0.018, 0.018, fLen, 10]} /><meshBasicMaterial color={RED} /></mesh>
          <mesh position={[0, fLen + 0.04, 0]}><coneGeometry args={[0.045, 0.09, 14]} /><meshBasicMaterial color={RED} /></mesh>
          <Html position={[0.12, fLen + 0.05, 0]} className="label3d red">{`${(F.length() / BW).toFixed(2)} BW`}</Html>
        </group>
      )}
    </group>
  );
}

function Diver({ r, t }: { r: View; t: number }) {
  if (r.points) return <Diver2 r={r} t={t} />;
  return <Diver1 r={r} t={t} />;
}

function Diver1({ r, t }: { r: View; t: number }) {
  const { H, l_max, d } = r.geom;
  const s = sampleAt(r, t);
  const contact = t >= 0 && t <= r.events.TO;
  const l = contact ? s.l : l_max;
  const com = new THREE.Vector3(s.x_c, s.z_c, 0);
  const toe = contact ? new THREE.Vector3(-d + s.x_b, s.z_b, 0) : new THREE.Vector3(s.x_c, s.z_c - l, 0);
  // Proportionen (Winter/de Leva, gerundet): Hüfte 0,08·H unter KSP, Unterschenkel+Fuß, Oberschenkel 0,245·H
  const hip = new THREE.Vector3(com.x, com.y - 0.08 * H, 0);
  const ext = Math.min(1, Math.max(0, (l - 0.48 * H) / (l_max - 0.48 * H))); // 0 gebeugt … 1 gestreckt
  const ankle = new THREE.Vector3(toe.x - 0.03 * H * (1 - 0.6 * ext), toe.y + 0.045 * H + 0.04 * H * ext, 0);
  const kn = knee(ankle, hip, 0.245 * H, 0.246 * H);
  const lean = (1 - ext) * 0.35;
  const shoulder = new THREE.Vector3(hip.x + Math.sin(lean) * 0.29 * H, hip.y + Math.cos(lean) * 0.29 * H, 0);
  const head = new THREE.Vector3(shoulder.x + Math.sin(lean) * 0.09 * H, shoulder.y + Math.cos(lean) * 0.09 * H, 0);
  // Armhaltung illustrativ: hinten-unten bei TD → über Kopf bei TO
  const tTo = r.events.TO;
  const prog = t < 0 ? 0.6 : t <= tTo ? Math.min(1, t / tTo) : 1;
  // Winkel zur hängenden Lage: 0 = Arme unten, negativ = hinten, π = über Kopf
  const armAng = THREE.MathUtils.degToRad(-60 + 240 * (1 - Math.pow(1 - prog, 2)));
  const arm = (side: number) => {
    const sh = shoulder.clone().add(new THREE.Vector3(0, 0, side * 0.1 * H));
    const hand = sh.clone().add(new THREE.Vector3(Math.sin(armAng) * 0.36 * H, -Math.cos(armAng) * 0.36 * H, 0));
    return [sh, hand] as const;
  };
  const legs = [-1, 1].map((side) => {
    const off = new THREE.Vector3(0, 0, side * 0.055 * H);
    return { toe: toe.clone().add(off), ankle: ankle.clone().add(off), knee: kn.clone().add(off), hip: hip.clone().add(off) };
  });
  const BW = r.geom.M * 9.81;
  const fLen = (s.F / BW) * 0.25;
  return (
    <group>
      {legs.map((g, i) => (
        <group key={i}>
          <Limb a={g.toe} b={g.ankle} r={0.018 * H} />
          <Limb a={g.ankle} b={g.knee} r={0.024 * H} />
          <Limb a={g.knee} b={g.hip} r={0.034 * H} />
        </group>
      ))}
      <Limb a={hip} b={shoulder} r={0.07 * H} />
      {[-1, 1].map((side) => { const [a, b] = arm(side); return <Limb key={side} a={a} b={b} r={0.02 * H} color="#A1A1AA" />; })}
      <mesh position={head}><sphereGeometry args={[0.065 * H, 20, 16]} /><meshStandardMaterial color="#F4F4F5" /></mesh>
      {/* KSP */}
      <mesh position={com}><sphereGeometry args={[0.035, 16, 12]} /><meshBasicMaterial color={RED} /></mesh>
      {/* Brettreaktionskraft am Kraftangriffspunkt */}
      {fLen > 0.005 && (
        <group position={[toe.x, toe.y, 0.3]}>
          <mesh position={[0, fLen / 2, 0]}><cylinderGeometry args={[0.018, 0.018, fLen, 10]} /><meshBasicMaterial color={RED} /></mesh>
          <mesh position={[0, fLen + 0.04, 0]}><coneGeometry args={[0.045, 0.09, 14]} /><meshBasicMaterial color={RED} /></mesh>
          <Html position={[0.12, fLen + 0.05, 0]} className="label3d red">{`${(s.F / BW).toFixed(2)} BW`}</Html>
        </group>
      )}
    </group>
  );
}

function Trajectory({ r }: { r: View }) {
  const pts = useMemo(() => {
    const out: [number, number, number][] = [];
    for (let i = 0; i < r.t.length; i += 5) out.push([r.com_x[i], r.com_z[i], 0]);
    return out;
  }, [r]);
  const xb = (r.level === 2 ? r.metrics.x_body_board_plane : r.metrics.x_board_plane) as number;
  return (
    <group>
      <Line points={pts} color="#71717A" lineWidth={1.5} dashed dashSize={0.06} gapSize={0.04} />
      {Number.isFinite(xb) && (
        <group>
          <Line points={[[0, 0.002, 0.3], [xb, 0.002, 0.3]]} color="#F4F4F5" lineWidth={1.5} />
          <Html position={[xb / 2, 0.12, 0.3]} center className="label3d">{`Freigang ${r.level === 2 ? 'Körper' : 'KSP'} ${xb.toFixed(2)} m`}</Html>
        </group>
      )}
    </group>
  );
}

function Water() {
  return (
    <group position={[0, -3, 0]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[40, 40]} />
        <meshStandardMaterial color="#0f1a24" roughness={0.25} metalness={0.2} transparent opacity={0.92} />
      </mesh>
      <gridHelper args={[40, 80, '#1f3242', '#15232f']} position={[0, 0.002, 0]} />
      <Html position={[2.2, 0.05, 1.2]} className="label3d dim">Wasser z = −3,00 m</Html>
    </group>
  );
}

function CameraRig({ preset, controls }: { preset: CamPreset; controls: React.RefObject<OrbitControlsImpl> }) {
  const { camera } = useThree();
  useEffect(() => {
    const presets: Record<CamPreset, [THREE.Vector3, THREE.Vector3]> = {
      side: [new THREE.Vector3(-0.4, 0.0, 10.5), new THREE.Vector3(-0.4, -0.2, 0)],
      front: [new THREE.Vector3(7.5, 0.6, 0.01), new THREE.Vector3(0, 0, 0)],
      board: [new THREE.Vector3(-5.8, 1.9, 0.6), new THREE.Vector3(0.8, 0.2, 0)],
    };
    const [pos, target] = presets[preset];
    camera.position.copy(pos);
    controls.current?.target.copy(target);
    controls.current?.update();
  }, [preset, camera, controls]);
  return null;
}

export function Scene({ preset }: { preset: CamPreset }) {
  const result = useStore((s) => s.view);
  const time = useStore((s) => s.time);
  const controls = useRef<OrbitControlsImpl>(null);
  return (
    <Canvas shadows camera={{ fov: 38, near: 0.05, far: 200, position: [-0.4, 0.0, 10.5] }} gl={{ preserveDrawingBuffer: true, antialias: true }} dpr={[1, 2]}>
      <color attach="background" args={['#0B0B0D']} />
      <fog attach="fog" args={['#0B0B0D', 14, 40]} />
      <ambientLight intensity={0.45} />
      <directionalLight position={[3, 6, 5]} intensity={1.2} castShadow />
      <directionalLight position={[-4, 2, -3]} intensity={0.3} />
      <OrbitControls ref={controls} makeDefault enableDamping />
      <CameraRig preset={preset} controls={controls} />
      {result && (
        <>
          <Board r={result} t={time} />
          <Diver r={result} t={time} />
          <Trajectory r={result} />
        </>
      )}
      <Water />
    </Canvas>
  );
}
