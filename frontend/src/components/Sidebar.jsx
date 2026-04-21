import BrandLogo from "./BrandLogo.jsx";

export default function Sidebar({ user, jobCount, isDark, onToggleTheme, onLogout, activeView, onViewChange }) {
  return (
    <nav className="nav">
      <div className="nav-brand">
        <BrandLogo size="md" showName={true} />
      </div>

      <div className="nav-section">
        <div className="nav-section-label">Menu</div>

        <div
          className={`nav-item${activeView === "generator" ? " active" : ""}`}
          onClick={() => onViewChange("generator")}
        >
          <div className="nav-item-icon">🎬</div>
          <span className="nav-item-label">Generar Videos</span>
          {activeView === "generator" && jobCount > 0 && (
            <span className="nav-item-badge">{jobCount}</span>
          )}
        </div>

        <div
          className={`nav-item${activeView === "history" ? " active" : ""}`}
          onClick={() => onViewChange("history")}
        >
          <div className="nav-item-icon">📋</div>
          <span className="nav-item-label">Historial</span>
        </div>

        <div className="nav-item" style={{ opacity: 0.4, cursor: "default" }}>
          <div className="nav-item-icon">⚙️</div>
          <span className="nav-item-label">Settings</span>
        </div>
      </div>

      <div className="nav-spacer" />

      <div className="nav-theme-wrap">
        <div className="theme-toggle-wrap" onClick={onToggleTheme}>
          <button className="theme-toggle" aria-label="Toggle theme">
            <div className="theme-toggle-knob">{isDark ? "🌙" : "☀️"}</div>
          </button>
          <span className="theme-toggle-label">{isDark ? "Dark mode" : "Light mode"}</span>
        </div>
      </div>

      <div className="nav-bottom">
        <div className="nav-user" onClick={onLogout} title="Click to log out">
          <div className="nav-avatar">{user[0].toUpperCase()}</div>
          <div className="nav-user-info">
            <div className="nav-user-name">{user}</div>
            <div className="nav-user-role">Click to log out</div>
          </div>
          <button className="nav-logout-btn" onClick={(e) => { e.stopPropagation(); onLogout(); }}>↗</button>
        </div>
      </div>
    </nav>
  );
}
