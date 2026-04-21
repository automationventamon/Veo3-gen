import { useState } from "react";
import { useTheme }          from "./hooks/useTheme.js";
import LoginScreen           from "./components/LoginScreen.jsx";
import VideoGeneratorPage    from "./pages/VideoGeneratorPage.jsx";

export default function App() {
  const { theme, toggleTheme, isDark } = useTheme();

  const [user, setUser] = useState(() => {
    const token    = sessionStorage.getItem("flowgen_token");
    const username = sessionStorage.getItem("flowgen_user");
    if (token && username) return { username, token };
    return null;
  });

  const handleLogin = (payload) => setUser(payload);

  const handleLogout = async () => {
    const token = user?.token;
    if (token) {
      try {
        await fetch("/api/logout", {
          method:  "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        });
      } catch {}
    }
    sessionStorage.removeItem("flowgen_token");
    sessionStorage.removeItem("flowgen_user");
    setUser(null);
  };

  if (!user) {
    return <LoginScreen onLogin={handleLogin} isDark={isDark} onToggleTheme={toggleTheme} />;
  }

  return (
    <VideoGeneratorPage
      user={user}
      onLogout={handleLogout}
      isDark={isDark}
      onToggleTheme={toggleTheme}
    />
  );
}
