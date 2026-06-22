import React, { useEffect, useState } from "react";
import { useStore } from "../store.jsx";
import { applySettings, previewVoice, setUiMode, enterOrbOnly } from "../bridge.js";

function Segment({ value, options, onChange }) {
  return (
    <div className="seg">
      {options.map((o) => (
        <button key={o.v} className={value === o.v ? "active" : ""} onClick={() => onChange(o.v)}>
          {o.l}
        </button>
      ))}
    </div>
  );
}

export default function SettingsView() {
  const { settings } = useStore();
  const [draft, setDraft] = useState(null);

  useEffect(() => {
    if (settings) setDraft(JSON.parse(JSON.stringify(settings)));
  }, [settings]);

  if (!draft) return <div className="empty">Loading settings…</div>;

  const set = (patch) => {
    const next = { ...draft, ...patch };
    setDraft(next);
    applySettings(next);
  };

  return (
    <>
      <div className="view-head">
        <h1>Settings</h1>
        <span className="sub">behaviour · voice · context</span>
      </div>

      <div className="stack">
        <div className="settings-grid">
          <div className="card">
            <div className="card-h">Automation policy</div>
            <Segment
              value={draft.automation_policy || "ask"}
              onChange={(v) => set({ automation_policy: v })}
              options={[{ v: "ask", l: "Ask first" }, { v: "full_auto", l: "Full auto" }]}
            />
            <p className="hint" style={{ marginTop: 10 }}>
              Whether JARVIS asks before taking control of your machine.
            </p>
          </div>

          <div className="card">
            <div className="card-h">Background mode</div>
            <Segment
              value={draft.background_mode || "wake_phrase"}
              onChange={(v) => set({ background_mode: v })}
              options={[
                { v: "wake_phrase", l: "Wake phrase" },
                { v: "always_listening", l: "Always" },
                { v: "off", l: "Off" },
              ]}
            />
            <p className="hint" style={{ marginTop: 10 }}>Hotkey <span className="kbd">Ctrl+Shift+J</span> always works.</p>
          </div>

          <div className="card">
            <div className="card-h">Voice</div>
            <div className="row">
              <div
                className={`switch ${draft.voice_enabled ? "on" : ""}`}
                onClick={() => set({ voice_enabled: !draft.voice_enabled })}
                role="switch"
                aria-checked={!!draft.voice_enabled}
              >
                <div className="knob" />
              </div>
              <span className="hint" style={{ margin: 0 }}>{draft.voice_enabled ? "Enabled" : "Disabled"}</span>
              <div style={{ flex: 1 }} />
              <button className="btn ghost" onClick={() => previewVoice(draft.voice_profile || "jarvis")}>
                Preview
              </button>
            </div>
          </div>

          <div className="card">
            <div className="card-h">Interface</div>
            <Segment
              value={draft.ui_mode === "legacy" ? "legacy" : "react"}
              onChange={(v) => setUiMode(v)}
              options={[{ v: "react", l: "Modern (React)" }, { v: "legacy", l: "Legacy" }]}
            />
            <div className="row" style={{ marginTop: 10 }}>
              <button className="btn ghost" onClick={() => enterOrbOnly()}>Orb-only mode</button>
              <span className="hint" style={{ margin: 0 }}>Switching UI restarts JARVIS.</span>
            </div>
          </div>

          <div className="card">
            <div className="card-h">Screen awareness</div>
            <div className="row">
              <div
                className={`switch ${draft.screen_awareness ? "on" : ""}`}
                onClick={() => set({ screen_awareness: !draft.screen_awareness })}
                role="switch"
                aria-checked={!!draft.screen_awareness}
              >
                <div className="knob" />
              </div>
              <span className="hint" style={{ margin: 0 }}>
                {draft.screen_awareness ? "JARVIS can see your screen" : "Screen vision off"}
              </span>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-h">Pinned context</div>
          <textarea
            className="input"
            style={{ minHeight: 90, resize: "vertical", userSelect: "text" }}
            placeholder="Always keep this in mind (name, preferences, projects)…"
            value={draft.pinned_context || ""}
            onChange={(e) => setDraft({ ...draft, pinned_context: e.target.value })}
            onBlur={() => applySettings(draft)}
          />
          <p className="hint" style={{ marginTop: 8 }}>Prepended to every system prompt.</p>
        </div>
      </div>
    </>
  );
}
