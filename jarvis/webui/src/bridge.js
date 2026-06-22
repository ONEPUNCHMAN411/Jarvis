// Thin wrapper around Qt's QWebChannel so React can talk to the Python runtime.
// In a plain browser (Vite dev with no Qt) every call is a no-op so the UI still
// renders for styling work. All object/array arguments are sent as JSON strings
// to match the Python @pyqtSlot(str) signatures.

let _jarvis = null;
const _listeners = new Set();

export function onEvent(cb) {
  _listeners.add(cb);
  return () => _listeners.delete(cb);
}

function _emit(data) {
  _listeners.forEach((cb) => {
    try {
      cb(data);
    } catch (e) {
      /* ignore listener errors */
    }
  });
}

function _call(name, ...args) {
  if (_jarvis && typeof _jarvis[name] === "function") {
    try {
      _jarvis[name](...args);
    } catch (e) {
      /* bridge not ready */
    }
  }
}

export function isConnected() {
  return _jarvis !== null;
}

// -- conversation -----------------------------------------------------------
export const sendText = (text) => _call("sendText", String(text));
export const triggerVoice = () => _call("triggerVoice");
export const cancel = () => _call("cancel");

// -- sessions / history -----------------------------------------------------
export const loadChatHistory = () => _call("loadChatHistory");
export const newSession = () => _call("newSession");
export const listSessions = () => _call("listSessions");
export const loadSession = (id) => _call("loadSession", String(id));

// -- settings / providers ---------------------------------------------------
export const applySettings = (obj) => _call("applySettings", JSON.stringify(obj || {}));
export const testProvider = (name) => _call("testProvider", String(name));
export const previewVoice = (id, custom) =>
  _call("previewVoice", String(id), custom ? JSON.stringify(custom) : "");
export const setBackgroundState = (on) => _call("setBackgroundState", !!on);

// -- plugins / status -------------------------------------------------------
export const listPlugins = () => _call("listPlugins");
export const enablePlugin = (name) => _call("enablePlugin", String(name));
export const disablePlugin = (name) => _call("disablePlugin", String(name));
export const getStatus = () => _call("getStatus");

// -- window controls --------------------------------------------------------
export const minimizeWindow = () => _call("minimizeWindow");
export const toggleMaximize = () => _call("toggleMaximize");
export const closeWindow = () => _call("closeWindow");
export const enterOrbOnly = () => _call("enterOrbOnly");
export const exitOrbOnly = () => _call("exitOrbOnly");
export const dragWindow = (dx, dy) => _call("dragWindow", Math.round(dx), Math.round(dy));
export const setUiMode = (mode) => _call("setUiMode", String(mode));

export function initBridge() {
  const QWebChannel = window.QWebChannel;
  const transport = window.qt && window.qt.webChannelTransport;
  if (typeof QWebChannel === "undefined" || !transport) {
    _emit({ type: "_bridge_unavailable" });
    return; // not inside QWebEngine — styling/dev mode
  }
  // eslint-disable-next-line no-new
  new QWebChannel(transport, (channel) => {
    _jarvis = channel.objects.jarvis;
    if (_jarvis && _jarvis.event && _jarvis.event.connect) {
      _jarvis.event.connect((payload) => {
        let data;
        try {
          data = JSON.parse(payload);
        } catch (e) {
          data = { type: "raw", payload };
        }
        _emit(data);
      });
    }
    _emit({ type: "_bridge_ready" });
    // Tell Python we're mounted so it replays initial state (status, plugins,
    // history, sessions, settings).
    _call("ready");
  });
}
