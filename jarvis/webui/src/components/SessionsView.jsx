import React, { useEffect } from "react";
import { motion } from "motion/react";
import { useStore } from "../store.jsx";
import { listSessions, loadSession, newSession } from "../bridge.js";
import { PlusIcon, SessionIcon } from "./Icons.jsx";

function when(ts) {
  if (!ts) return "";
  const d = typeof ts === "number" ? new Date(ts * (ts < 1e12 ? 1000 : 1)) : new Date(ts);
  if (isNaN(d)) return String(ts);
  return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function SessionsView() {
  const { sessions, sessionId } = useStore();

  useEffect(() => {
    listSessions();
  }, []);

  return (
    <>
      <div className="view-head">
        <h1>Sessions</h1>
        <span className="sub">{sessions.length} saved</span>
        <div className="grow" />
        <button className="btn primary" onClick={() => newSession()}>
          <PlusIcon size={15} /> &nbsp;New session
        </button>
      </div>

      <div className="stack">
        {sessions.length === 0 && <div className="empty">No saved sessions yet.</div>}
        {sessions.map((s, i) => {
          const id = s.session_id || s.id || s.sessionId;
          const title = s.title || s.summary || s.first_message || `Session ${i + 1}`;
          const count = s.message_count ?? s.messages ?? s.count;
          return (
            <motion.div
              key={id || i}
              className="session-row"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(i * 0.02, 0.3) }}
              onClick={() => id && loadSession(id)}
              style={{ cursor: "pointer", outline: id === sessionId ? "1px solid var(--border-strong)" : "none" }}
            >
              <div className="pc-ic"><SessionIcon size={17} /></div>
              <div className="grow">
                <div className="s-title">{title}</div>
                <div className="s-meta">
                  {when(s.updated_at || s.created_at || s.timestamp)}
                  {count != null ? ` · ${count} messages` : ""}
                  {id === sessionId ? " · current" : ""}
                </div>
              </div>
              <button className="btn ghost" onClick={(e) => { e.stopPropagation(); id && loadSession(id); }}>
                Open
              </button>
            </motion.div>
          );
        })}
      </div>
    </>
  );
}
