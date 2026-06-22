import React, { createContext, useContext, useEffect, useReducer, useRef } from "react";
import { initBridge, onEvent, getStatus } from "./bridge.js";

const Ctx = createContext(null);
export const useStore = () => useContext(Ctx);

const MAX_INTEL = 60;
const now = () =>
  new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

const initial = {
  connected: false,
  ready: false,
  status: "idle",
  mic: 0,
  messages: [],
  sessionId: null,
  sessions: [],
  plugins: [],
  stats: { cpu: 0, mem: 0, disk: 0, tx: 0, rx: 0, providers: [], voice: true },
  netHist: [],
  settings: null,
  providerTests: {},
  intel: [],
  streamId: null,
  orbOnly: false,
};

function addMsg(state, msg) {
  return { ...state, messages: [...state.messages, msg] };
}
function intel(state, kind, text) {
  const row = { id: "i" + Date.now() + Math.random(), kind, text, when: now() };
  return { ...state, intel: [...state.intel.slice(-(MAX_INTEL - 1)), row] };
}

function reducer(state, e) {
  switch (e.type) {
    case "_bridge_ready":
      return { ...state, connected: true };
    case "_bridge_unavailable":
      return { ...state, connected: false };
    case "runtime_ready":
      return intel({ ...state, ready: true }, "info", "JARVIS runtime ready");
    case "orb_only":
      return { ...state, orbOnly: !!e.on };
    case "_clear_messages":
      return { ...state, messages: [], streamId: null };

    case "status":
      return { ...state, status: e.status || "idle" };
    case "mic":
      return { ...state, mic: Math.min(1, (e.level || 0) * 40) };

    case "message": {
      const role = e.sender === "YOU" ? "user" : e.sender === "JARVIS" ? "assistant" : "system";
      if (role === "assistant" && state.streamId != null) {
        const id = state.streamId;
        return {
          ...state,
          streamId: null,
          messages: state.messages.map((m) => (m.id === id ? { ...m, text: e.text, raw: e.raw } : m)),
        };
      }
      return addMsg(state, {
        id: "m" + Date.now() + Math.random(),
        role,
        text: e.text,
        raw: e.raw,
      });
    }
    case "partial_response": {
      const acc = e.accumulated || "";
      if (state.streamId == null) {
        const id = "s" + Date.now();
        return { ...state, streamId: id, messages: [...state.messages, { id, role: "assistant", text: acc }] };
      }
      return {
        ...state,
        messages: state.messages.map((m) => (m.id === state.streamId ? { ...m, text: acc } : m)),
      };
    }
    case "proactive_help":
      return addMsg(state, {
        id: "p" + Date.now(),
        role: "assistant",
        text: e.text || e.message || "",
        proactive: true,
      });

    case "chat_history": {
      const msgs = (e.messages || []).map((m, i) => ({
        id: "h" + i,
        role: m.role === "user" ? "user" : "assistant",
        text: m.content,
      }));
      return { ...state, messages: msgs, sessionId: e.session_id, streamId: null };
    }
    case "new_session":
      return intel({ ...state, messages: [], sessionId: e.session_id, streamId: null }, "info", "New session started");
    case "session_list":
      return { ...state, sessions: e.sessions || [] };

    case "plugins_list":
      return { ...state, plugins: e.plugins || [] };
    case "status_report":
      return {
        ...state,
        stats: {
          cpu: Math.round(e.cpu || 0),
          mem: Math.round(e.mem_pct || 0),
          disk: Math.round(e.disk_pct || 0),
          tx: e.net_tx || 0,
          rx: e.net_rx || 0,
          providers: e.providers || [],
          voice: e.voice_enabled !== false,
        },
        netHist: [...state.netHist.slice(-39), { tx: e.net_tx || 0, rx: e.net_rx || 0 }],
      };

    case "settings_loaded":
    case "settings_saved":
      return { ...state, settings: e.settings || state.settings };

    case "provider_test":
      return {
        ...state,
        providerTests: {
          ...state.providerTests,
          [e.provider]: { success: !!e.success, message: e.message || "", help: e.help },
        },
      };

    case "log":
      return intel(state, e.level === "warning" ? "warning" : e.level === "error" ? "error" : "info", e.message || "");
    case "tool_call":
      return intel(state, "tool", `Running ${e.name || "tool"}${e.summary ? ": " + e.summary : ""}`);
    case "tool_result":
      return intel(state, "tool", `${e.name || "tool"} done${e.summary ? ": " + e.summary : ""}`);
    case "computer_use_start":
      return intel(state, "tool", "Computer control engaged");
    case "computer_use_end":
      return intel(state, "tool", "Computer control released");

    default:
      return state;
  }
}

export function StoreProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initial);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const off = onEvent(dispatch);
    initBridge();
    // Poll system stats for the live gauges + network sparkline.
    const poll = setInterval(getStatus, 2000);
    return () => {
      off();
      clearInterval(poll);
    };
  }, []);

  return <Ctx.Provider value={{ ...state, dispatch }}>{children}</Ctx.Provider>;
}
