export default function BrandLogo({ size = "md", showName = true }) {
  const sizes = {
    sm: { wrap: 28, icon: 14, font: 13 },
    md: { wrap: 34, icon: 18, font: 16 },
    lg: { wrap: 42, icon: 22, font: 20 },
  };
  const s = sizes[size];

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <div style={{
        width: s.wrap, height: s.wrap,
        borderRadius: size === "lg" ? 10 : 8,
        background: "var(--green)", display: "grid", placeItems: "center",
        flexShrink: 0, boxShadow: "0 2px 8px rgba(26,107,60,0.3)", transition: "background 0.25s",
      }}>
        {/* Icono: play + ondas de video */}
        <svg viewBox="0 0 24 24" width={s.icon} height={s.icon} fill="none">
          <rect x="3" y="3" width="8" height="8" rx="1.5" fill="white" />
          <rect x="13" y="3" width="8" height="8" rx="1.5" fill="white" />
          <rect x="3" y="13" width="8" height="8" rx="1.5" fill="white" />
          <circle cx="17" cy="17" r="4" fill="white" />
        </svg>
      </div>
      {showName && (
        <div style={{
          fontSize: s.font, fontWeight: 800, letterSpacing: "-0.4px",
          color: "var(--text)", fontFamily: "var(--font)",
        }}>
          <span style={{ color: "var(--green)", transition: "color 0.25s" }}>Flow</span>Gen
        </div>
      )}
    </div>
  );
}
