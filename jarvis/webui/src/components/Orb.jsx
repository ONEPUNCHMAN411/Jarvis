import React from "react";
import { motion } from "motion/react";

const COLORS = {
  idle: "#3B9EFF",
  listening: "#4FD2FF",
  transcribing: "#36E2C4",
  thinking: "#FFC24A",
  speaking: "#34E5A0",
  error: "#FF5470",
};

// Percentage-based so it scales with .orb-wrap (92px) or .orb-wrap.lg (220px).
const RINGS = [
  { r: 78, a: "cc", w: 2 },
  { r: 100, a: "80", w: 1.5 },
  { r: 124, a: "4d", w: 1.2 },
];

export default function Orb({ status = "idle", mic = 0, size = "" }) {
  const c = COLORS[status] || COLORS.idle;
  const spin = status === "thinking" ? 7 : status === "listening" ? 11 : 24;
  const pulse = status === "speaking" || status === "thinking";

  return (
    <div className={`orb-wrap ${size}`}>
      <motion.div
        className="orb-halo"
        style={{ background: `radial-gradient(circle, ${c}40 0%, transparent 66%)` }}
        animate={{ scale: [1, 1.07, 1], opacity: [0.5, 0.85, 0.5] }}
        transition={{ duration: pulse ? 1.8 : 4, repeat: Infinity, ease: "easeInOut" }}
      />
      {RINGS.map((ring, i) => (
        <motion.div
          key={i}
          className="orb-ring"
          style={{
            width: `${ring.r}%`,
            height: `${ring.r}%`,
            border: `${ring.w}px solid ${c}${ring.a}`,
            borderTopColor: i === 0 ? c : undefined,
          }}
          animate={{ rotate: i % 2 === 0 ? 360 : -360 }}
          transition={{ duration: spin + i * 8, repeat: Infinity, ease: "linear" }}
        />
      ))}
      <motion.div
        className="orb-core"
        style={{
          background: `radial-gradient(circle at 36% 30%, ${c} 0%, #07101e 74%)`,
          boxShadow: `0 0 46px ${c}77, inset 0 0 30px ${c}33`,
        }}
        animate={{ scale: 1 + Math.min(mic, 1) * 0.18 }}
        transition={{ type: "spring", stiffness: 300, damping: 16 }}
      >
        <span className="orb-text">JARVIS</span>
      </motion.div>

      {/* orbiting sparks */}
      {[0, 1, 2].map((i) => (
        <motion.div
          key={`s${i}`}
          className="orb-spark-orbit"
          animate={{ rotate: i % 2 === 0 ? 360 : -360 }}
          transition={{ duration: 9 + i * 4, repeat: Infinity, ease: "linear" }}
          style={{ width: `${86 + i * 16}%`, height: `${86 + i * 16}%` }}
        >
          <span className="orb-spark" style={{ background: c, boxShadow: `0 0 8px ${c}` }} />
        </motion.div>
      ))}
    </div>
  );
}
