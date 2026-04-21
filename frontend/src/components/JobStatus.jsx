import { downloadJobUrl } from "../services/jobService.js";

const STATUS_ICON = { pending: "🕐", running: "⚙️", done: "✅", error: "❌" };
const STATUS_LABEL = { pending: "En cola", running: "Generando...", done: "Listo", error: "Error" };

function formatDate(iso) {
  return new Date(iso).toLocaleString("es", { dateStyle: "short", timeStyle: "short" });
}

export default function JobStatus({ jobs }) {
  if (!jobs.length) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">🎬</div>
        <div className="empty-state-title">Sin trabajos aún</div>
        <div className="empty-state-sub">Subí imágenes y hacé clic en Generar Videos para empezar.</div>
      </div>
    );
  }

  const active = jobs.find((j) => j.status === "running" || j.status === "pending");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

      {/* Progreso del trabajo activo */}
      {active && (
        <div className="status-panel">
          <div className="status-panel-header">
            <div className="status-panel-title">
              {active.status === "running" ? "⚙️ Generando videos..." : "🕐 En cola..."}
            </div>
            <div className={`status-badge ${active.status}`}>
              {STATUS_LABEL[active.status]}
            </div>
          </div>

          <div>
            <div className="big-progress-track">
              <div
                className="big-progress-fill"
                style={{ width: `${active.totalImages ? Math.round((active.doneImages / active.totalImages) * 100) : 0}%` }}
              />
            </div>
            <div className="big-progress-meta">
              <span className="progress-text">
                {active.status === "pending" ? "Esperando disponibilidad del bot..." : "Procesando imágenes una a una"}
              </span>
              <span className="progress-count">
                {active.doneImages}/{active.totalImages}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Lista de todos los trabajos */}
      <div className="job-list">
        {jobs.map((job) => (
          <div key={job.id} className={`job-card${job.status === "running" ? " active" : ""}`}>
            <div className="job-card-icon">{STATUS_ICON[job.status]}</div>
            <div className="job-card-info">
              <div className="job-card-title">
                {job.totalImages} imagen{job.totalImages !== 1 ? "s" : ""}
              </div>
              <div className="job-card-sub">{formatDate(job.createdAt)}</div>
              {(job.status === "running" || job.status === "pending") && (
                <div className="job-card-progress">
                  {job.doneImages}/{job.totalImages} completadas
                </div>
              )}
              {job.status === "error" && job.errorMsg && (
                <div className="job-card-progress" style={{ color: "var(--error)" }}>{job.errorMsg}</div>
              )}
            </div>
            <div className={`status-badge ${job.status}`}>{STATUS_LABEL[job.status]}</div>
            {job.status === "done" && (
              <a
                href={downloadJobUrl(job.id)}
                download
                style={{ marginLeft: 8 }}
              >
                <button className="btn-zip" style={{ padding: "7px 14px", fontSize: 12 }}>
                  ⬇️ ZIP
                </button>
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
