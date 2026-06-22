import React, { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import Orb from "./Orb.jsx";

export const STATUS_COLORS = {
  idle: "#3B9EFF",
  listening: "#4FD2FF",
  transcribing: "#36E2C4",
  thinking: "#FFC24A",
  speaking: "#34E5A0",
  error: "#FF5470",
};

const ADD = THREE.AdditiveBlending;

function webglOK() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (c.getContext("webgl") || c.getContext("experimental-webgl")));
  } catch (e) {
    return false;
  }
}
function rnd(seed, n) {
  const x = Math.sin(seed * 99.13 + n * 7.7) * 43758.5453;
  return x - Math.floor(x);
}

// Procedural marbled-blue planet texture (fbm value noise) — generated once.
function makePlanetTexture() {
  const w = 512, h = 256;
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const ctx = c.getContext("2d");
  const img = ctx.createImageData(w, h);
  const d = img.data;
  const hash = (x, y) => { const n = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return n - Math.floor(n); };
  const lerp = (a, b, t) => a + (b - a) * t;
  const sm = (t) => t * t * (3 - 2 * t);
  const vn = (x, y) => {
    const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
    const u = sm(xf), v = sm(yf);
    return lerp(lerp(hash(xi, yi), hash(xi + 1, yi), u), lerp(hash(xi, yi + 1), hash(xi + 1, yi + 1), u), v);
  };
  const fbm = (x, y) => { let s = 0, a = 0.5, f = 1; for (let i = 0; i < 5; i++) { s += a * vn(x * f, y * f); f *= 2; a *= 0.5; } return s; };
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const n = fbm(x / 40, y / 40);
      const t = Math.min(1, Math.max(0, (n - 0.28) / 0.5));
      const i = (y * w + x) * 4;
      d[i] = lerp(8, 96, t);
      d[i + 1] = lerp(24, 158, t);
      d[i + 2] = lerp(52, 235, t);
      d[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

function Planet({ colorRef, micRef }) {
  const grp = useRef();
  const surf = useRef();
  const tex = useMemo(makePlanetTexture, []);
  const atmoMat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        uniforms: { uColor: { value: new THREE.Color("#3B9EFF") }, uIntensity: { value: 1.0 } },
        vertexShader:
          "varying vec3 vN; varying vec3 vP;\n" +
          "void main(){ vN = normalize(normalMatrix*normal); vec4 mv = modelViewMatrix*vec4(position,1.0); vP = mv.xyz; gl_Position = projectionMatrix*mv; }",
        fragmentShader:
          "uniform vec3 uColor; uniform float uIntensity; varying vec3 vN; varying vec3 vP;\n" +
          "void main(){ vec3 v = normalize(-vP); float f = pow(1.0 - max(dot(vN, v), 0.0), 2.6); gl_FragColor = vec4(uColor, f * uIntensity); }",
        transparent: true, side: THREE.BackSide, blending: ADD, depthWrite: false,
      }),
    []
  );
  useFrame((s, dt) => {
    const m = micRef.current || 0;
    if (grp.current) {
      grp.current.rotation.y += dt * 0.045;
      grp.current.scale.setScalar(1.12 * (1 + m * 0.06));
    }
    if (surf.current) surf.current.emissiveIntensity = 0.32 + m * 0.3;
    atmoMat.uniforms.uColor.value.lerp(colorRef.current, 0.06);
    atmoMat.uniforms.uIntensity.value = 1.0 + m * 0.7;
  });
  return (
    <group ref={grp} rotation={[0.05, 0, 0.28]}>
      <mesh>
        <sphereGeometry args={[1, 64, 64]} />
        <meshStandardMaterial ref={surf} map={tex} emissive="#1b4d8a" emissiveMap={tex} emissiveIntensity={0.32} roughness={0.78} metalness={0.12} />
      </mesh>
      <mesh material={atmoMat} scale={1.16}>
        <sphereGeometry args={[1, 48, 48]} />
      </mesh>
    </group>
  );
}

// Faint orbital ellipse rings around the planet.
function OrbitRings({ colorRef }) {
  const mat = useRef();
  useFrame(() => mat.current && mat.current.color.lerp(colorRef.current, 0.05));
  const rings = [
    { r: 1.9, tilt: [1.32, 0.1, 0] },
    { r: 2.4, tilt: [1.15, 0.5, 0.2] },
    { r: 2.9, tilt: [1.42, -0.3, 0.1] },
  ];
  return (
    <>
      {rings.map((rg, i) => (
        <mesh key={i} rotation={rg.tilt}>
          <torusGeometry args={[rg.r, 0.004, 6, 128]} />
          <meshBasicMaterial ref={i === 0 ? mat : undefined} color="#3B9EFF" transparent opacity={0.14} blending={ADD} depthWrite={false} />
        </mesh>
      ))}
    </>
  );
}

const LANES = [
  { radius: 1.9, incl: 1.32, tilt: 0.1, speed: 0.3 },
  { radius: 2.4, incl: 1.15, tilt: 0.5, speed: -0.22 },
  { radius: 2.9, incl: 1.42, tilt: 0.1, speed: 0.16 },
];
function Moon({ lane, phase, size, colorRef }) {
  const ref = useRef();
  const mat = useRef();
  useFrame((s) => {
    const t = s.clock.elapsedTime * lane.speed + phase;
    if (ref.current) ref.current.position.set(Math.cos(t) * lane.radius, 0, Math.sin(t) * lane.radius);
    if (mat.current) mat.current.color.lerp(colorRef.current, 0.06);
  });
  return (
    <mesh ref={ref}>
      <sphereGeometry args={[size, 16, 16]} />
      <meshBasicMaterial ref={mat} color="#5BC8FF" transparent opacity={0.95} blending={ADD} />
    </mesh>
  );
}
function Satellites({ count, colorRef }) {
  const lanes = useMemo(() => {
    const byLane = LANES.map(() => []);
    for (let i = 0; i < count; i++) byLane[i % LANES.length].push({ phase: rnd(i, 4) * Math.PI * 2, size: 0.04 + rnd(i, 5) * 0.05 });
    return byLane;
  }, [count]);
  return (
    <>
      {LANES.map((lane, li) => (
        <group key={li} rotation={[lane.incl, 0, lane.tilt]}>
          {lanes[li].map((m, mi) => <Moon key={mi} lane={lane} phase={m.phase} size={m.size} colorRef={colorRef} />)}
        </group>
      ))}
    </>
  );
}

function Starfield() {
  const geo = useMemo(() => {
    const N = 360, pos = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      const r = 10 + rnd(i, 1) * 6, th = rnd(i, 2) * Math.PI * 2, ph = Math.acos(2 * rnd(i, 3) - 1);
      pos[i * 3] = r * Math.sin(ph) * Math.cos(th);
      pos[i * 3 + 1] = r * Math.cos(ph);
      pos[i * 3 + 2] = r * Math.sin(ph) * Math.sin(th);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    return g;
  }, []);
  return <points geometry={geo}><pointsMaterial color="#9fb6d8" size={0.05} sizeAttenuation transparent opacity={0.6} /></points>;
}

function Scene({ status, mic, count, compact }) {
  const colorRef = useRef(new THREE.Color(STATUS_COLORS[status] || STATUS_COLORS.idle));
  const micRef = useRef(0);
  colorRef.current.set(STATUS_COLORS[status] || STATUS_COLORS.idle);
  micRef.current = mic;
  return (
    <>
      <ambientLight intensity={0.3} />
      <directionalLight position={[4, 2.5, 5]} intensity={1.7} color="#eaf3ff" />
      <pointLight position={[-4, -1, -3]} intensity={0.4} ref={(l) => l && l.color.copy(colorRef.current)} />
      <Planet colorRef={colorRef} micRef={micRef} />
      {!compact && <OrbitRings colorRef={colorRef} />}
      {!compact && <Satellites count={count} colorRef={colorRef} />}
      {!compact && <Starfield />}
    </>
  );
}

export default function Orb3D({ status = "idle", mic = 0, count = 6, compact = false, mark = false, className = "" }) {
  const ok = useMemo(webglOK, []);
  if (!ok) {
    return (
      <div className={`orb3d fallback ${className}`}>
        <Orb status={status} mic={mic} size="lg" />
      </div>
    );
  }
  return (
    <div className={`orb3d ${className}`}>
      <Canvas dpr={[1, 2]} camera={{ position: [0, 0, compact ? 3.4 : 5.2], fov: 46 }} gl={{ antialias: true, alpha: true }}>
        <Scene status={status} mic={mic} count={count} compact={compact} />
      </Canvas>
      {mark && <div className="orb-mark">J A R V I S</div>}
    </div>
  );
}
