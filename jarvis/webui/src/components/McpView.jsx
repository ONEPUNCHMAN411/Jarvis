import React from "react";
import { motion } from "motion/react";
import { McpIcon } from "./Icons.jsx";

// Catalog mirrors the native MCP manager's installable set. Install/config is
// handled by the runtime's MCP bridge via config; this view surfaces the
// catalog for discovery inside the command center.
const CATALOG = [
  { name: "filesystem", desc: "Read & write local files and directories" },
  { name: "brave-search", desc: "Web search via the Brave Search API" },
  { name: "github", desc: "Repos, issues, and pull requests" },
  { name: "memory", desc: "Persistent knowledge-graph memory" },
  { name: "puppeteer", desc: "Headless browser automation" },
  { name: "sequential-thinking", desc: "Structured step-by-step reasoning" },
  { name: "sqlite", desc: "Query local SQLite databases" },
  { name: "time", desc: "Time, date, and timezone tools" },
];

export default function McpView() {
  return (
    <>
      <div className="view-head">
        <h1>MCP Servers</h1>
        <span className="sub">{CATALOG.length} in catalog</span>
        <div className="grow" />
        <span className="hint">Enable in <span className="kbd">config/default.yaml</span></span>
      </div>

      <div className="grid-wrap">
        <div className="plugin-grid">
          {CATALOG.map((s, i) => (
            <motion.div
              key={s.name}
              className="plugin-card"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(i * 0.02, 0.3) }}
            >
              <div className="pc-top">
                <div className="pc-ic"><McpIcon size={18} /></div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="pc-name">{s.name}</div>
                  <div className="pc-state">MCP server</div>
                </div>
              </div>
              <div className="hint">{s.desc}</div>
            </motion.div>
          ))}
        </div>
      </div>
    </>
  );
}
