import React, { useEffect, useState } from "react";
import { useStore } from "../store.jsx";
import { applySettings, testProvider } from "../bridge.js";

// Display order + which fields each provider exposes.
const PROVIDERS = [
  { key: "llamacpp", label: "llama.cpp (local)", fields: ["model_path"] },
  { key: "ollama", label: "Ollama (local)", fields: ["base_url", "model"] },
  { key: "claude", label: "Claude", fields: ["api_key", "model"] },
  { key: "groq", label: "Groq", fields: ["api_key", "model"] },
  { key: "mistral", label: "Mistral", fields: ["api_key", "model"] },
  { key: "gemini", label: "Gemini", fields: ["api_key", "model"] },
  { key: "openai", label: "OpenAI", fields: ["api_key", "base_url", "model"] },
  { key: "openrouter", label: "OpenRouter", fields: ["api_key", "model"] },
];
const FIELD_LABEL = { api_key: "API key", base_url: "Base URL", model: "Model", model_path: "Model path" };

export default function ProvidersView() {
  const { settings, providerTests } = useStore();
  const [draft, setDraft] = useState(null);

  useEffect(() => {
    if (settings) setDraft(JSON.parse(JSON.stringify(settings)));
  }, [settings]);

  if (!draft) return <div className="empty">Loading settings…</div>;
  const providers = draft.providers || {};

  const setField = (pk, field, val) => {
    setDraft((d) => ({
      ...d,
      providers: { ...d.providers, [pk]: { ...(d.providers[pk] || {}), [field]: val } },
    }));
  };
  const save = (next) => {
    const merged = next || draft;
    setDraft(merged);
    applySettings(merged);
  };
  const toggle = (pk) => {
    const cur = providers[pk] || {};
    save({ ...draft, providers: { ...providers, [pk]: { ...cur, enabled: !cur.enabled } } });
  };

  return (
    <>
      <div className="view-head">
        <h1>AI Providers</h1>
        <span className="sub">primary · {draft.primary_provider || "auto"}</span>
        <div className="grow" />
        <select
          className="select"
          style={{ width: 200 }}
          value={draft.primary_provider || "auto"}
          onChange={(e) => save({ ...draft, primary_provider: e.target.value })}
        >
          <option value="auto">Auto (fallback)</option>
          {PROVIDERS.map((p) => (
            <option key={p.key} value={p.key}>{p.label}</option>
          ))}
        </select>
      </div>

      <div className="stack">
        {PROVIDERS.map((p) => {
          const cfg = providers[p.key] || {};
          const test = providerTests[p.key];
          return (
            <div className="prov-card" key={p.key}>
              <div className="ph">
                <span className={`pstatus ${test ? (test.success ? "ok" : "bad") : ""}`} />
                <span className="pname">{p.label}</span>
                <div className="grow" style={{ flex: 1 }} />
                <button className="btn ghost" onClick={() => testProvider(p.key)}>Test</button>
                <div
                  className={`switch ${cfg.enabled ? "on" : ""}`}
                  onClick={() => toggle(p.key)}
                  role="switch"
                  aria-checked={!!cfg.enabled}
                >
                  <div className="knob" />
                </div>
              </div>
              {cfg.enabled && (
                <div className="pb">
                  {p.fields.map((f) => (
                    <div className="field" key={f}>
                      <label>{FIELD_LABEL[f]}</label>
                      <input
                        className="input"
                        type={f === "api_key" ? "password" : "text"}
                        value={cfg[f] || ""}
                        placeholder={FIELD_LABEL[f]}
                        onChange={(e) => setField(p.key, f, e.target.value)}
                        onBlur={() => save()}
                      />
                    </div>
                  ))}
                  {test && (
                    <div className={`test-msg ${test.success ? "ok" : "bad"}`}>
                      {test.message}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}
