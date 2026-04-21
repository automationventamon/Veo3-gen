import { useState } from "react";
import Sidebar     from "../components/Sidebar.jsx";
import ImageUploader from "../components/ImageUploader.jsx";
import JobStatus   from "../components/JobStatus.jsx";
import { useVideoJobs } from "../hooks/useVideoJobs.js";
import { createJob }    from "../services/jobService.js";

export default function VideoGeneratorPage({ user, onLogout, isDark, onToggleTheme }) {
  const [images,      setImages]      = useState([]);
  const [submitting,  setSubmitting]  = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [activeView,  setActiveView]  = useState("generator");

  const { jobs, addJob, hasActive } = useVideoJobs();

  const handleGenerate = async () => {
    if (!images.length) return;
    setSubmitting(true);
    setSubmitError("");
    try {
      const job = await createJob(images);
      addJob(job);
      // clear images after submitting
      setImages([]);
      setActiveView("generator");
    } catch (err) {
      setSubmitError(err.message || "Error al enviar el trabajo.");
    } finally {
      setSubmitting(false);
    }
  };

  const activeJobCount = jobs.filter((j) => j.status === "pending" || j.status === "running").length;

  return (
    <div className="shell">
      <Sidebar
        user={user.username}
        jobCount={activeJobCount}
        isDark={isDark}
        onToggleTheme={onToggleTheme}
        onLogout={onLogout}
        activeView={activeView}
        onViewChange={setActiveView}
      />

      <div className="main">
        <div className="topbar">
          <div className="topbar-left">
            <div className="topbar-title">
              {activeView === "generator" ? "Generador de Videos" : "Historial"}
            </div>
            <div className="topbar-sub">
              {activeView === "generator"
                ? "Subí imágenes, escribí los prompts y enviá al bot de Google Flow"
                : "Todos tus trabajos de generación"}
            </div>
          </div>
          <div className="topbar-right">
            {hasActive && (
              <div className="topbar-pill">
                <div className="topbar-pill-dot" />
                Bot activo
              </div>
            )}
          </div>
        </div>

        <div className="body">
          {activeView === "generator" && (
            <>
              {/* Upload + prompts */}
              <div className="panel-card">
                <div className="panel-card-title">
                  Imágenes
                  {images.length > 0 && (
                    <span className="panel-card-title-count">{images.length} imagen{images.length !== 1 ? "es" : ""}</span>
                  )}
                </div>
                <ImageUploader images={images} onImagesChange={setImages} />
              </div>

              {/* Generate button */}
              {images.length > 0 && (
                <div>
                  <button
                    className="btn-generate"
                    onClick={handleGenerate}
                    disabled={submitting || !images.length}
                  >
                    {submitting
                      ? <><div className="spinner" /> Enviando al bot...</>
                      : <>🎬 Generar Videos ({images.length} imagen{images.length !== 1 ? "es" : ""})</>
                    }
                  </button>
                  {submitError && (
                    <div style={{ fontSize: 12, color: "var(--error)", marginTop: 8, textAlign: "center" }}>
                      {submitError}
                    </div>
                  )}
                  <div className="generate-hint">
                    El bot de Google Flow procesará cada imagen y generará 4 videos por imagen.
                    Podés cerrar esta ventana — los videos estarán listos cuando vuelvas.
                  </div>
                </div>
              )}

              {/* Active jobs preview */}
              {jobs.length > 0 && (
                <div className="panel-card">
                  <div className="panel-card-title">
                    Trabajos recientes
                    <span className="panel-card-title-count">{jobs.length}</span>
                  </div>
                  <JobStatus jobs={jobs.slice(0, 3)} />
                  {jobs.length > 3 && (
                    <div
                      style={{ marginTop: 12, fontSize: 12, color: "var(--green)", cursor: "pointer", fontWeight: 600 }}
                      onClick={() => setActiveView("history")}
                    >
                      Ver todos los trabajos →
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {activeView === "history" && (
            <div className="panel-card">
              <div className="panel-card-title">
                Historial de trabajos
                <span className="panel-card-title-count">{jobs.length}</span>
              </div>
              <JobStatus jobs={jobs} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
