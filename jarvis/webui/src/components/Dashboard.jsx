import React, { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useStore } from "../store.jsx";
import { sendText, triggerVoice, cancel, newSession, listSessions, applySettings } from "../bridge.js";
import Orb3D, { STATUS_COLORS } from "./Orb3D.jsx";
import { MicIcon, SendIcon, StopIcon, PlusIcon } from "./Icons.jsx";

const STATUS_LABEL = {
  idle: "Ready", listening: "Listening", transcribing: "Transcribing",
  thinking: "Thinking", speaking: "Responding", error: "Error",
};
const STATUS_SUB = {
  idle: "Standing by for typed or spoken instructions",
  listening: "Go ahead, I'm listening", transcribing: "Turning speech into text",
  thinking: "Working on it", speaking: "Here's what I found", error: "Something went wrong",
};
const QUICK = [
  ["Translate", "translate this: "],
  ["Image generator", "generate an image of "],
  ["OCR", "read the text on my screen"],
  ["Pomodoro", "start a 25 minute pomodoro"],
];

function RingGauge({ value, label, color }) {
  const R = 28, C = 2 * Math.PI * R, pct = Math.max(0, Math.min(100, value));
  return (
    <div className="gauge">
      <div className="ring" style={{ width: 72, height: 72 }}>
        <svg width="72" height="72" viewBox="0 0 72 72">
          <circle cx="36" cy="36" r={R} fill="none" stroke="rgba(120,170,255,0.12)" strokeWidth="5" />
          <motion.circle
            cx="36" cy="36" r={R} fill="none" stroke={color} strokeWidth="5" strokeLinecap="round"
            transform="rotate(-90 36 36)" strokeDasharray={C}
            animate={{ strokeDashoffset: C - (C * pct) / 100 }} transition={{ type: "spring", stiffness: 120, damping: 20 }}
          />
        </svg>
        <div className="val" style={{ fontSize: 14 }}>{Math.round(pct)}%</div>
      </div>
      <div className="lbl">{label}</div>
    </div>
  );
}

function Sparkline({ data, color, label }) {
  const pts = useMemo(() => {
    if (!data.length) return "";
    const max = Math.max(0.05, ...data);
    const w = 100, h = 30;
    return data.map((v, i) => `${(i / Math.max(1, data.length - 1)) * w},${h - (v / max) * h}`).join(" ");
  }, [data]);
  const last = data.length ? data[data.length - 1] : 0;
  return (
    <div className="spark">
      <div className="spark-head"><span>{label}</span><span className="spark-val">{last.toFixed(1)} MB/s</span></div>
      <svg viewBox="0 0 100 30" preserveAspectRatio="none" className="spark-svg">
        <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}

function MiniCalendar() {
  const [d] = useState(() => new Date());
  const y = d.getFullYear(), m = d.getMonth(), today = d.getDate();
  const first = new Date(y, m, 1).getDay();
  const days = new Date(y, m + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < first; i++) cells.push(null);
  for (let i = 1; i <= days; i++) cells.push(i);
  const month = d.toLocaleString([], { month: "long" });
  return (
    <div className="cal">
      <div className="cal-head">{month} <span>{y}</span></div>
      <div className="cal-grid">
        {["S", "M", "T", "W", "T", "F", "S"].map((w, i) => <div key={"h" + i} className="cal-dow">{w}</div>)}
        {cells.map((c, i) => (
          <div key={i} className={`cal-day ${c === today ? "today" : ""} ${c && (i % 7 === 0 || i % 7 === 6) ? "wknd" : ""}`}>{c || ""}</div>
        ))}
      </div>
    </div>
  );
}

function Bubble({ m, streaming }) {
  return (
    <motion.div className={`bubble ${m.role}`} initial={{ opacity: 0, y: 10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ type: "spring", stiffness: 380, damping: 30 }} layout>
      {m.role !== "system" && <div className="who">{m.role === "user" ? "You" : "JARVIS"}</div>}
      {m.text || (streaming ? "…" : "")}
    </motion.div>
  );
}

export default function Dashboard() {
  const { messages, status, mic, stats, intel, settings, sessions, streamId, dispatch } = useStore();
  const [input, setInput] = useState("");
  const [font, setFont] = useState(14);
  const listRef = useRef(null);
  const taRef = useRef(null);
  const busy = status === "thinking" || status === "transcribing";
  const micLive = status === "listening";
  const color = STATUS_COLORS[status] || STATUS_COLORS.idle;

  const logRows = intel.filter((r) => r.kind !== "tool");
  const feedRows = intel.filter((r) => r.kind === "tool");
  const txHist = useStore().netHist.map((n) => n.tx);
  const rxHist = useStore().netHist.map((n) => n.rx);

  useEffect(() => { listSessions(); }, []);
  useEffect(() => { if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight; }, [messages]);

  const submit = (e) => {
    if (e) e.preventDefault();
    const t = input.trim();
    if (!t) return;
    sendText(t); setInput("");
    if (taRef.current) taRef.current.style.height = "auto";
  };
  const grow = (el) => { if (el) { el.style.height = "auto"; el.style.height = Math.min(el.scrollHeight, 120) + "px"; } };
  const onKey = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } };

  const providers = settings?.providers || {};
  const provOptions = ["auto", ...Object.keys(providers)];
  const ctxPct = Math.min(100, Math.round(messages.reduce((a, m) => a + (m.text || "").length, 0) / 320));

  const exportChat = () => {
    const md = messages.map((m) => `**${m.role === "user" ? "You" : m.role === "assistant" ? "JARVIS" : "System"}:** ${m.text}`).join("\n\n");
    const blob = new Blob([md], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "jarvis_chat.md";
    a.click();
  };

  return (
    <div className="dash">
      {/* ---- LEFT: system + network + log ---- */}
      <aside className="dash-col left">
        <div className="card">
          <div className="card-h">System</div>
          <div className="gauges">
            <RingGauge value={stats.cpu} label="CPU" color="#3B9EFF" />
            <RingGauge value={stats.mem} label="RAM" color="#4FD2FF" />
            <RingGauge value={stats.disk} label="Disk" color="#FFC24A" />
          </div>
        </div>
        <div className="card">
          <div className="card-h">Network</div>
          <Sparkline data={txHist} color="#4FD2FF" label="TX" />
          <Sparkline data={rxHist} color="#34E5A0" label="RX" />
        </div>
        <div className="card grow-card">
          <div className="card-h">Log</div>
          <div className="intel">
            {logRows.length === 0 && <div className="hint">No activity yet.</div>}
            <AnimatePresence initial={false}>
              {logRows.slice().reverse().map((r) => (
                <motion.div key={r.id} className={`intel-row ${r.kind}`} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} layout>
                  <span className="tick" /><span>{r.text}</span><span className="when">{r.when}</span>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      </aside>

      {/* ---- CENTER: orb + status + talk + conversation ---- */}
      <main className="dash-center">
        <div className="stage">
          <Orb3D status={status} mic={mic} count={6} mark className="hero-orb" />
          <AnimatePresence mode="wait">
            <motion.div key={status} className="stage-status" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.3 }}>
              <div className="ss-title" style={{ color }}>{STATUS_LABEL[status] || status}</div>
              <motion.button className={`talk-btn wide ${micLive ? "live" : ""}`} onClick={() => triggerVoice()} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>Talk</motion.button>
              <div className="ss-sub">{STATUS_SUB[status] || ""}</div>
            </motion.div>
          </AnimatePresence>
        </div>

        <div className="convo">
          <div className="convo-bar">
            <span className="cb-label">Conversation</span>
            <select className="select sm" value={settings?.primary_provider || "auto"} onChange={(e) => settings && applySettings({ ...settings, primary_provider: e.target.value })}>
              {provOptions.map((p) => <option key={p} value={p}>{p === "auto" ? "Auto" : p}</option>)}
            </select>
            <span className="cb-ctx">~{ctxPct}% ctx</span>
            <div className="grow" />
            <button className="cb-btn" onClick={() => setFont((f) => Math.max(11, f - 1))}>A−</button>
            <button className="cb-btn" onClick={() => setFont((f) => Math.min(22, f + 1))}>A+</button>
            <button className="cb-btn" onClick={exportChat}>Export</button>
            <button className="cb-btn" onClick={() => sendText("show my bookmarks")}>Bookmarks</button>
            <button className="cb-btn" onClick={() => sendText("list my macros")}>Macros</button>
            <button className="cb-btn" onClick={() => sendText("list my scheduled tasks")}>Schedules</button>
            <button className="cb-btn" onClick={() => { newSession(); }}>New chat</button>
            <button className="cb-btn" onClick={() => dispatch({ type: "_clear_messages" })}>Clear</button>
          </div>
          <div className="messages" ref={listRef} style={{ fontSize: font }}>
            {messages.length === 0 ? (
              <div className="empty">Ask JARVIS anything, or press Talk.</div>
            ) : (
              <AnimatePresence initial={false}>
                {messages.map((m) => <Bubble key={m.id} m={m} streaming={m.id === streamId} />)}
              </AnimatePresence>
            )}
          </div>
          <form className="composer" onSubmit={submit}>
            <textarea ref={taRef} rows={1} value={input} onChange={(e) => { setInput(e.target.value); grow(e.target); }} onKeyDown={onKey} placeholder="Tell JARVIS what to do…" />
            <motion.button type="button" className={`icon-btn mic ${micLive ? "live" : ""}`} onClick={() => triggerVoice()} whileTap={{ scale: 0.92 }}><MicIcon size={19} /></motion.button>
            {busy ? (
              <motion.button type="button" className="icon-btn" onClick={() => cancel()} whileTap={{ scale: 0.92 }}><StopIcon size={17} /></motion.button>
            ) : (
              <motion.button type="submit" className="icon-btn send" whileHover={{ scale: 1.06 }} whileTap={{ scale: 0.92 }}><SendIcon size={18} /></motion.button>
            )}
          </form>
        </div>
      </main>

      {/* ---- RIGHT: quick tools + calendar + intel ---- */}
      <aside className="dash-col right">
        <div className="card">
          <div className="card-h">Quick tools</div>
          <div className="qt">
            {QUICK.map(([label, cmd]) => (
              <button key={label} className="qt-btn" onClick={() => sendText(cmd.trim())}>{label}</button>
            ))}
          </div>
        </div>
        <div className="card"><div className="card-h">Calendar</div><MiniCalendar /></div>
        <div className="card grow-card">
          <div className="card-h">Intel feed</div>
          <div className="intel">
            {feedRows.length === 0 && <div className="hint">No activity yet.</div>}
            <AnimatePresence initial={false}>
              {feedRows.slice().reverse().map((r) => (
                <motion.div key={r.id} className="intel-row tool" initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} layout>
                  <span className="tick" /><span>{r.text}</span><span className="when">{r.when}</span>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      </aside>
    </div>
  );
}
