import React, { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useStore } from "../store.jsx";
import { sendText, triggerVoice, cancel, newSession, applySettings } from "../bridge.js";
import Orb3D, { STATUS_COLORS } from "./Orb3D.jsx";
import { SendIcon, MicIcon, PlusIcon, StopIcon, ChatIcon, ChevronIcon } from "./Icons.jsx";

const QUICK = [
  ["Screenshot", "take a screenshot"],
  ["System info", "show system info"],
  ["What can you do?", "what can you do?"],
  ["Read the news", "read me the news"],
];

const STATUS_LABEL = {
  idle: "Listening for you",
  listening: "Listening…",
  transcribing: "Transcribing…",
  thinking: "Thinking…",
  speaking: "Responding…",
  error: "Something went wrong",
};
const STATUS_SUB = {
  idle: "Say “Hey JARVIS”, press the mic, or type below",
  listening: "Go ahead, I'm listening",
  transcribing: "Turning your speech into text",
  thinking: "Working on it",
  speaking: "Here's what I found",
  error: "Try again, or check Providers",
};

function Typing() {
  return (
    <span className="typing">
      {[0, 1, 2].map((i) => (
        <motion.i key={i} animate={{ opacity: [0.3, 1, 0.3], y: [0, -3, 0] }} transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15 }} />
      ))}
    </span>
  );
}

function Bubble({ m, streaming }) {
  return (
    <motion.div
      className={`bubble ${m.role}`}
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 380, damping: 30 }}
      layout
    >
      {m.role !== "system" && <div className="who">{m.role === "user" ? "You" : "JARVIS"}</div>}
      {m.text ? m.text : streaming ? <Typing /> : ""}
    </motion.div>
  );
}

export default function ChatView() {
  const { messages, sessions, status, mic, streamId, settings } = useStore();
  const [input, setInput] = useState("");
  const [open, setOpen] = useState(false); // transcript expanded
  const autoListen = !!settings && settings.background_mode && settings.background_mode !== "off";
  const toggleAuto = () =>
    settings && applySettings({ ...settings, background_mode: autoListen ? "off" : "wake_phrase" });
  const listRef = useRef(null);
  const taRef = useRef(null);
  const busy = status === "thinking" || status === "transcribing";
  const micLive = status === "listening";
  const color = STATUS_COLORS[status] || STATUS_COLORS.idle;

  // Orb fills with satellite orbs as conversations accumulate (starts with a few).
  const orbCount = useMemo(
    () => Math.min(4 + (sessions?.length || 0) + Math.floor(messages.length / 2), 42),
    [sessions, messages.length]
  );

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages, open]);

  const grow = (el) => {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  };
  const submit = (e) => {
    if (e) e.preventDefault();
    const t = input.trim();
    if (!t) return;
    sendText(t);
    setInput("");
    setOpen(true);
    if (taRef.current) taRef.current.style.height = "auto";
  };
  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const peek = messages.slice(-3);

  return (
    <div className={`voice-stage ${open ? "open" : ""}`}>
      {/* ---- ORB: the attraction ---- */}
      <div className="stage-top">
        <Orb3D status={status} mic={mic} count={orbCount} />
        <AnimatePresence mode="wait">
          <motion.div
            key={status}
            className="voice-status"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.3 }}
          >
            <div className="vs-title" style={{ color }}>
              <span className="vs-dot" style={{ background: color, boxShadow: `0 0 16px ${color}` }} />
              {STATUS_LABEL[status] || status}
            </div>
            <div className="vs-sub">{STATUS_SUB[status] || ""}</div>
          </motion.div>
        </AnimatePresence>

        <div className="voice-actions">
          <motion.button
            className={`talk-btn ${micLive ? "live" : ""}`}
            onClick={() => triggerVoice()}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.94 }}
            style={micLive ? { borderColor: color, boxShadow: `0 0 36px ${color}66` } : undefined}
          >
            <MicIcon size={26} />
          </motion.button>
          {busy && (
            <motion.button className="icon-btn lg" onClick={() => cancel()} whileTap={{ scale: 0.94 }} title="Stop">
              <StopIcon size={20} />
            </motion.button>
          )}
          <motion.button
            className={`auto-pill ${autoListen ? "on" : ""}`}
            onClick={toggleAuto}
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.96 }}
            title="Auto-listen for the wake word"
          >
            <span className="ap-dot" />
            {autoListen ? "Auto-listen on" : "Auto-listen off"}
          </motion.button>
        </div>

        {!open && (
          <div className="quick-row">
            {QUICK.map(([label, cmd], i) => (
              <motion.button
                key={label}
                className="chip"
                onClick={() => { sendText(cmd); setOpen(true); }}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05 * i }}
                whileHover={{ scale: 1.05, y: -2 }}
                whileTap={{ scale: 0.95 }}
              >
                {label}
              </motion.button>
            ))}
          </div>
        )}
      </div>

      {/* ---- transcript (secondary) ---- */}
      <div className="transcript">
        <div className="tr-head">
          <button className="tr-toggle" onClick={() => setOpen((o) => !o)}>
            <ChatIcon size={15} /> Conversation
            <span className="tr-count">{messages.length}</span>
            <motion.span className="chev" animate={{ rotate: open ? 180 : 0 }}><ChevronIcon size={14} /></motion.span>
          </button>
          <div className="grow" />
          <motion.button className="btn ghost sm" onClick={() => { newSession(); setOpen(false); }} whileTap={{ scale: 0.95 }}>
            <PlusIcon size={14} /> New
          </motion.button>
        </div>

        <div className={`messages ${open ? "full" : "peek"}`} ref={listRef}>
          {messages.length === 0 ? (
            <div className="empty">Your conversation will appear here.</div>
          ) : (
            <AnimatePresence initial={false}>
              {(open ? messages : peek).map((m) => (
                <Bubble key={m.id} m={m} streaming={m.id === streamId} />
              ))}
            </AnimatePresence>
          )}
        </div>

        <form className="composer thin" onSubmit={submit}>
          <textarea
            ref={taRef}
            rows={1}
            value={input}
            onChange={(e) => { setInput(e.target.value); grow(e.target); }}
            onKeyDown={onKey}
            onFocus={() => setOpen(true)}
            placeholder="…or type a command"
          />
          {busy ? (
            <motion.button type="button" className="icon-btn" onClick={() => cancel()} whileTap={{ scale: 0.92 }} title="Stop">
              <StopIcon size={17} />
            </motion.button>
          ) : (
            <motion.button type="submit" className="icon-btn send" whileHover={{ scale: 1.06 }} whileTap={{ scale: 0.92 }} title="Send">
              <SendIcon size={18} />
            </motion.button>
          )}
        </form>
      </div>
    </div>
  );
}
