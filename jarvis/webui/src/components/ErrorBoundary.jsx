import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  componentDidCatch(error, info) {
    // surface to the QWebEngine console for debugging
    console.error("View crashed:", error, info);
  }
  componentDidUpdate(prev) {
    if (prev.viewKey !== this.props.viewKey && this.state.error) {
      this.setState({ error: null });
    }
  }
  render() {
    if (this.state.error) {
      return (
        <div className="empty" style={{ color: "var(--danger)" }}>
          This panel hit an error:<br />
          <code style={{ fontSize: 12, color: "var(--text-dim)" }}>{String(this.state.error.message || this.state.error)}</code>
        </div>
      );
    }
    return this.props.children;
  }
}
