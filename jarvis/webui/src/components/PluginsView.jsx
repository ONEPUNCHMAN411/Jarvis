import React, { useMemo, useState } from "react";
import { motion } from "motion/react";
import { useStore } from "../store.jsx";
import { enablePlugin, disablePlugin, listPlugins } from "../bridge.js";
import {
  PluginIcon, FileIcon, MailIcon, MusicIcon, GlobeIcon, CodeIcon, TerminalIcon,
  CalendarIcon, BellIcon, DatabaseIcon, CameraIcon, BrainIcon, LockIcon, ImageIcon,
  BoxIcon, ActivityIcon, MicIcon,
} from "./Icons.jsx";

// Map a plugin name → meaningful icon + category (first keyword match wins).
const RULES = [
  { k: ["vault", "encrypt"], cat: "Security", Icon: LockIcon },
  { k: ["database"], cat: "Data", Icon: DatabaseIcon },
  { k: ["qr"], cat: "Data", Icon: BoxIcon },
  { k: ["file", "document", "converter", "note"], cat: "Files", Icon: FileIcon },
  { k: ["email", "mail", "slack", "discord", "contact", "remote"], cat: "Comms", Icon: MailIcon },
  { k: ["spotify", "music"], cat: "Media", Icon: MusicIcon },
  { k: ["camera", "video"], cat: "Media", Icon: CameraIcon },
  { k: ["image", "ocr", "annotation"], cat: "Media", Icon: ImageIcon },
  { k: ["tts", "voicememo", "voice_memo", "dictation"], cat: "Voice", Icon: MicIcon },
  { k: ["search", "news", "browser", "network", "api", "autofill", "web"], cat: "Web", Icon: GlobeIcon },
  { k: ["code", "execut"], cat: "Dev", Icon: TerminalIcon },
  { k: ["github", "git"], cat: "Dev", Icon: CodeIcon },
  { k: ["blender", "app_test", "apptester", "macro", "region", "workspace"], cat: "Dev", Icon: BoxIcon },
  { k: ["calendar", "schedul", "pomodoro", "habit", "todo", "context"], cat: "Productivity", Icon: CalendarIcon },
  { k: ["system", "monitor", "alert"], cat: "System", Icon: ActivityIcon },
  { k: ["memory", "translat"], cat: "AI", Icon: BrainIcon },
];
function meta(name) {
  const s = (name || "").toLowerCase();
  for (const r of RULES) if (r.k.some((k) => s.includes(k))) return r;
  return { cat: "Other", Icon: PluginIcon };
}

function Switch({ on, onClick }) {
  return (
    <div className={`switch ${on ? "on" : ""}`} onClick={onClick} role="switch" aria-checked={on}>
      <div className="knob" />
    </div>
  );
}

export default function PluginsView() {
  const { plugins } = useStore();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all"); // all | on | off
  const [cat, setCat] = useState("All");

  const withMeta = useMemo(() => plugins.map((p) => ({ ...p, ...meta(p.name) })), [plugins]);
  const categories = useMemo(
    () => ["All", ...Array.from(new Set(withMeta.map((p) => p.cat))).sort()],
    [withMeta]
  );

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    return withMeta
      .filter((p) => (status === "all" ? true : status === "on" ? p.enabled : !p.enabled))
      .filter((p) => (cat === "All" ? true : p.cat === cat))
      .filter((p) => (s ? p.name.toLowerCase().includes(s) || p.cat.toLowerCase().includes(s) : true))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [withMeta, q, status, cat]);

  const enabled = plugins.filter((p) => p.enabled).length;

  return (
    <>
      <div className="view-head">
        <h1>Plugins</h1>
        <span className="sub">{enabled} of {plugins.length} active</span>
        <div className="grow" />
        <input
          className="input"
          style={{ width: 220 }}
          placeholder="Search plugins…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Search plugins"
        />
      </div>

      <div className="filter-row">
        <div className="seg" style={{ width: 220 }}>
          {[["all", "All"], ["on", "Active"], ["off", "Off"]].map(([v, l]) => (
            <button key={v} className={status === v ? "active" : ""} onClick={() => setStatus(v)}>{l}</button>
          ))}
        </div>
        <div className="cat-chips">
          {categories.map((c) => (
            <button key={c} className={`cat-chip ${cat === c ? "active" : ""}`} onClick={() => setCat(c)}>{c}</button>
          ))}
        </div>
      </div>

      <div className="grid-wrap">
        {plugins.length === 0 ? (
          <div className="empty">Loading plugins…</div>
        ) : filtered.length === 0 ? (
          <div className="empty">
            No plugins match “{q || cat}”.<br />
            <button className="btn ghost sm" style={{ marginTop: 10 }} onClick={() => { setQ(""); setStatus("all"); setCat("All"); }}>
              Clear filters
            </button>
          </div>
        ) : (
          <div className="plugin-grid">
            {filtered.map((p, i) => (
              <motion.div
                key={p.name}
                className="plugin-card"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i * 0.012, 0.3) }}
              >
                <div className="pc-top">
                  <div className="pc-ic"><p.Icon size={18} /></div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="pc-name">{p.name.replace(/_/g, " ")}</div>
                    <div className="pc-state">{p.cat} · {p.enabled ? "Active" : "Off"}</div>
                  </div>
                  <Switch on={p.enabled} onClick={() => (p.enabled ? disablePlugin(p.name) : enablePlugin(p.name))} />
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
