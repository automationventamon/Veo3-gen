import { useState } from "react";
import BrandLogo from "./BrandLogo.jsx";

export default function LoginScreen({ onLogin, isDark, onToggleTheme }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);

  const handleSubmit = async () => {
    if (!username.trim() || !password.trim()) {
      setError("Please fill in both fields.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res  = await fetch("/api/login", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ username: username.trim().toLowerCase(), password }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.error || "Login failed."); return; }

      sessionStorage.setItem("flowgen_token", data.token);
      sessionStorage.setItem("flowgen_user",  data.username);
      onLogin({ username: data.username, token: data.token });
    } catch {
      setError("Cannot connect to the server. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-bg">
      <div className="login-dots" />
      <div className="login-card">
        <button className="login-theme-btn" onClick={onToggleTheme}>
          {isDark ? "☀️" : "🌙"} <span>{isDark ? "Light" : "Dark"}</span>
        </button>

        <div className="login-brand">
          <BrandLogo size="lg" showName={true} />
        </div>

        <div className="login-headline">Welcome back</div>
        <div className="login-sub">Sign in to start generating videos with Google Flow.</div>

        <div className="field">
          <label>Username</label>
          <input
            value={username}
            onChange={(e) => { setUsername(e.target.value); setError(""); }}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            placeholder="Enter your username"
            autoFocus autoComplete="username" disabled={loading}
          />
        </div>

        <div className="field">
          <label>Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => { setPassword(e.target.value); setError(""); }}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            placeholder="Enter your password"
            autoComplete="current-password" disabled={loading}
          />
        </div>

        <button className="btn-login" onClick={handleSubmit} disabled={loading}>
          {loading ? "Signing in..." : "Sign In"}
        </button>

        {error && <div className="login-err">{error}</div>}
      </div>
    </div>
  );
}
