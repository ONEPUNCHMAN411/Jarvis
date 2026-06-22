import React, { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useStore } from "../store.jsx";
import { CpuIcon, PulseIcon } from "./Icons.jsx";

function RingGauge({ value, label, color }) {
  const R = 30;
  const C = 2 * Math.PI * R;
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="gauge">
      <div className="ring">
        <svg width="76" height="76" viewBox="0 0 76 76">
          <circle cx="38" cy="38" r={R} fill="none" stroke="rgba(120,170,255,0.12)" strokeWidth="6" />
          <motion.circle
            cx="38" cy="38" r={R} fill="none" stroke={color} strokeWidth="6" strokeLinecap="round"
            transform="rotate(-90 38 38)"
            strokeDasharray={C}
            initial={false}
            animate={{ strokeDashoffset: C - (C * pct) / 100 }}
            transition={{ type: "spring", stiffness: 120, damping: 20 }}
            style={{ filter: `drop-shadow(0 0 5px ${color}88)` }}
          />
        </svg>
        <div className="val">{Math.round(pct)}%</div>
      </div>
      <div className="lbl">{label}</div>
    </div>
  );
}

function Clock() {
  const [t, setT] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setT(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="card clock">
      <div className="time">{t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</div>
      <div className="date">
        {t.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })}
      </div>
    </div>
  );
}

export default function HudColumn() {
  const { stats, intel } = useStore();
  const cpuColor = stats.cpu > 85 ? "var(--danger)" : stats.cpu > 60 ? "var(--warn)" : "var(--accent)";
  const memColor = stats.mem > 85 ? "var(--danger)" : stats.mem > 60 ? "var(--warn)" : "var(--accent-2)";

  return (
    <aside className="hud">
      <Clock />

      <div className="card">
        <div className="card-h"><CpuIcon size={15} /> System</div>
        <div className="gauges">
          <RingGauge value={stats.cpu} label="CPU" color={cpuColor} />
          <RingGauge value={stats.mem} label="Memory" color={memColor} />
        </div>
      </div>

      <div className="card" style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        <div className="card-h"><PulseIcon size={15} /> Activity<span className="grow" /></div>
        <div className="intel">
          {intel.length === 0 && <div className="hint">No activity yet.</div>}
          <AnimatePresence initial={false}>
            {intel.slice().reverse().map((r) => (
              <motion.div
                key={r.id}
                className={`intel-row ${r.kind}`}
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                layout
              >
                <span className="tick" />
                <span>{r.text}</span>
                <span className="when">{r.when}</span>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </div>
    </aside>
  );
}
