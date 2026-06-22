import React from "react";

// Minimal stroked icon set (24x24, currentColor) — no external dependency.
const I = (p) => (
  <svg
    width={p.size || 20}
    height={p.size || 20}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={p.sw || 1.7}
    strokeLinecap="round"
    strokeLinejoin="round"
    {...p.rest}
  >
    {p.children}
  </svg>
);

export const ChatIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
  </I>
);
export const PluginIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M4 7h3V4a2 2 0 0 1 4 0v3h3M4 7v10a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-3h-3a2 2 0 0 1 0-4h3V7a2 2 0 0 0-2-2h-3" />
  </I>
);
export const ProviderIcon = (p) => (
  <I {...{ rest: p }}>
    <rect x="3" y="3" width="18" height="8" rx="2" />
    <rect x="3" y="13" width="18" height="8" rx="2" />
    <path d="M7 7h.01M7 17h.01" />
  </I>
);
export const McpIcon = (p) => (
  <I {...{ rest: p }}>
    <circle cx="12" cy="12" r="3" />
    <path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" />
  </I>
);
export const SessionIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M3 5h18M3 12h18M3 19h12" />
  </I>
);
export const SettingsIcon = (p) => (
  <I {...{ rest: p }}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.2.62.78 1.05 1.51 1.05H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </I>
);
export const SendIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z" />
  </I>
);
export const MicIcon = (p) => (
  <I {...{ rest: p }}>
    <rect x="9" y="2" width="6" height="12" rx="3" />
    <path d="M19 10a7 7 0 0 1-14 0M12 19v3" />
  </I>
);
export const PlusIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M12 5v14M5 12h14" />
  </I>
);
export const StopIcon = (p) => (
  <I {...{ rest: p }}>
    <rect x="6" y="6" width="12" height="12" rx="2" />
  </I>
);
export const MinIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M5 12h14" />
  </I>
);
export const MaxIcon = (p) => (
  <I {...{ rest: p }}>
    <rect x="5" y="5" width="14" height="14" rx="2" />
  </I>
);
export const CloseIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M18 6 6 18M6 6l12 12" />
  </I>
);
export const CpuIcon = (p) => (
  <I {...{ rest: p }}>
    <rect x="6" y="6" width="12" height="12" rx="2" />
    <path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2" />
  </I>
);
export const PulseIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M3 12h4l3 8 4-16 3 8h4" />
  </I>
);
export const ChevronIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M6 9l6 6 6-6" />
  </I>
);
export const FileIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6" />
  </I>
);
export const MailIcon = (p) => (
  <I {...{ rest: p }}>
    <rect x="2" y="4" width="20" height="16" rx="2" />
    <path d="m2 7 10 6 10-6" />
  </I>
);
export const MusicIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M9 18V5l12-2v13" />
    <circle cx="6" cy="18" r="3" />
    <circle cx="18" cy="16" r="3" />
  </I>
);
export const GlobeIcon = (p) => (
  <I {...{ rest: p }}>
    <circle cx="12" cy="12" r="10" />
    <path d="M2 12h20M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20z" />
  </I>
);
export const CodeIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="m16 18 6-6-6-6M8 6l-6 6 6 6" />
  </I>
);
export const TerminalIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="m4 17 6-6-6-6M12 19h8" />
  </I>
);
export const CalendarIcon = (p) => (
  <I {...{ rest: p }}>
    <rect x="3" y="4" width="18" height="18" rx="2" />
    <path d="M16 2v4M8 2v4M3 10h18" />
  </I>
);
export const BellIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0" />
  </I>
);
export const DatabaseIcon = (p) => (
  <I {...{ rest: p }}>
    <ellipse cx="12" cy="5" rx="9" ry="3" />
    <path d="M3 5v14a9 3 0 0 0 18 0V5M3 12a9 3 0 0 0 18 0" />
  </I>
);
export const CameraIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z" />
    <circle cx="12" cy="13" r="3" />
  </I>
);
export const BrainIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M12 5a3 3 0 0 0-6 0 3 3 0 0 0-1 5.8A3 3 0 0 0 7 16a3 3 0 0 0 5 1 3 3 0 0 0 5-1 3 3 0 0 0 2-5.2A3 3 0 0 0 18 5a3 3 0 0 0-6 0zM12 5v12" />
  </I>
);
export const LockIcon = (p) => (
  <I {...{ rest: p }}>
    <rect x="4" y="11" width="16" height="10" rx="2" />
    <path d="M8 11V7a4 4 0 0 1 8 0v4" />
  </I>
);
export const ImageIcon = (p) => (
  <I {...{ rest: p }}>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <circle cx="9" cy="9" r="2" />
    <path d="m21 15-5-5L5 21" />
  </I>
);
export const BoxIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M21 8 12 3 3 8v8l9 5 9-5z" />
    <path d="M3 8l9 5 9-5M12 13v8" />
  </I>
);
export const ActivityIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
  </I>
);
export const LayoutIcon = (p) => (
  <I {...{ rest: p }}>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <path d="M9 3v18M3 9h6" />
  </I>
);
export const OrbDotIcon = (p) => (
  <I {...{ rest: p }}>
    <circle cx="12" cy="12" r="5" />
    <circle cx="12" cy="12" r="9" opacity="0.5" />
  </I>
);
export const ExpandIcon = (p) => (
  <I {...{ rest: p }}>
    <path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M16 21h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
  </I>
);
