import React, { useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useStore } from "./store.jsx";
import {
  minimizeWindow, toggleMaximize, closeWindow, enterOrbOnly, exitOrbOnly, dragWindow,
} from "./bridge.js";
import {
  PluginIcon, ProviderIcon, McpIcon, SessionIcon, SettingsIcon,
  MinIcon, MaxIcon, CloseIcon, OrbDotIcon,
} from "./components/Icons.jsx";
import Orb3D from "./components/Orb3D.jsx";
import Dashboard from "./components/Dashboard.jsx";
import PluginsView from "./components/PluginsView.jsx";
import ProvidersView from "./components/ProvidersView.jsx";
import SettingsView from "./components/SettingsView.jsx";
import SessionsView from "./components/SessionsView.jsx";
import McpView from "./components/McpView.jsx";

const NAV = [
  { id: "plugins", label: "Plugins", Icon: PluginIcon, View: PluginsView },
  { id: "providers", label: "Providers", Icon: ProviderIcon, View: ProvidersView },
  { id: "mcp", label: "MCP", Icon: McpIcon, View: McpView },
  { id: "sessions", label: "Sessions", Icon: SessionIcon, View: SessionsView },
  { id: "settings", label: "Settings", Icon: SettingsIcon, View: SettingsView },
];

function OrbOnly() {
  const { status, mic } = useStore();
  const last = useRef(null);
  const down = (e) => { last.current = { x: e.screenX, y: e.screenY }; e.currentTarget.setPointerCapture(e.pointerId); };
  const move = (e) => {
    if (!last.current) return;
    const dx = e.screenX - last.current.x, dy = e.screenY - last.current.y;
    if (dx || dy) { dragWindow(dx, dy); last.current = { x: e.screenX, y: e.screenY }; }
  };
  const up = (e) => { last.current = null; try { e.currentTarget.releasePointerCapture(e.pointerId); } catch (err) {} };
  return (
    <div
      className="orb-only"
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onDoubleClick={exitOrbOnly}
      onContextMenu={(e) => { e.preventDefault(); exitOrbOnly(); }}
      title="Drag to move · double-click or right-click to restore"
    >
      <Orb3D status={status} mic={mic} compact mark />
    </div>
  );
}

export default function App() {
  const { ready, orbOnly } = useStore();
  const [overlay, setOverlay] = useState(null);

  if (orbOnly) return <OrbOnly />;

  const Active = overlay && NAV.find((n) => n.id === overlay);

  return (
    <div className="app">
      <div className="titlebar">
        <div className="brand"><span className="spark" />JARVIS</div>
        <span className="build-chip">{ready ? "ONLINE" : "BOOTING"}</span>
        <div className="grow" />
        <div className="topnav">
          {NAV.map(({ id, label, Icon }) => (
            <button key={id} className={`topnav-btn ${overlay === id ? "active" : ""}`} onClick={() => setOverlay(overlay === id ? null : id)} title={label}>
              <Icon size={17} />
            </button>
          ))}
        </div>
        <div className="win-sep" />
        <div className="win-btns">
          <button className="win-btn" onClick={enterOrbOnly} title="Orb only"><OrbDotIcon size={15} /></button>
          <button className="win-btn" onClick={minimizeWindow} title="Minimize"><MinIcon size={15} /></button>
          <button className="win-btn" onClick={toggleMaximize} title="Maximize"><MaxIcon size={13} /></button>
          <button className="win-btn danger" onClick={closeWindow} title="Close"><CloseIcon size={15} /></button>
        </div>
      </div>

      <Dashboard />

      <AnimatePresence>
        {Active && (
          <motion.div className="overlay-scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setOverlay(null)}>
            <motion.div
              className="overlay-panel"
              initial={{ opacity: 0, y: 16, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 16, scale: 0.98 }}
              transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
              onClick={(e) => e.stopPropagation()}
            >
              <button className="overlay-close" onClick={() => setOverlay(null)} title="Close"><CloseIcon size={16} /></button>
              <Active.View setView={setOverlay} />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
