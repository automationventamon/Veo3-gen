"""
FlowGen VM Worker — Flask API
==============================
Recibe trabajos del backend Node.js, ejecuta el bot de Google Flow
y sirve los videos generados como ZIP para descargar.

Endpoints:
  POST /api/job                → recibe imágenes + prompts, inicia bot en background
  GET  /api/job/<id>           → devuelve estado del trabajo
  GET  /api/job/<id>/download  → devuelve ZIP con videos (cuando done)
"""

import os
import json
import shutil
import threading
import zipfile
import io
from pathlib import Path
from datetime import datetime
from uuid import uuid4

from flask import Flask, request, jsonify, send_file, abort

import flow_bot

app = Flask(__name__)

JOBS_DIR  = Path("./jobs")         # carpeta donde se guardan imágenes y videos
JOBS_DIR.mkdir(exist_ok=True)

# Estado en memoria: { job_id: { status, total, done, error } }
# En producción esto podría ser SQLite o Redis
JOBS = {}
JOBS_LOCK = threading.Lock()


def update_job(job_id, **kwargs):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(kwargs)
            JOBS[job_id]["updated_at"] = datetime.now().isoformat()


# ── ROUTES ────────────────────────────────────────────────────────

@app.route("/api/job", methods=["POST"])
def create_job():
    job_id  = request.form.get("job_id") or str(uuid4())
    prompts = json.loads(request.form.get("prompts", "{}"))
    files   = request.files.getlist("images")

    if not files:
        return jsonify({"error": "No images received"}), 400

    # Guardar imágenes en jobs/<job_id>/input/
    input_dir  = JOBS_DIR / job_id / "input"
    output_dir = JOBS_DIR / job_id / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    for f in files:
        dest = input_dir / f.filename
        f.save(str(dest))
        saved_files.append(dest)

    # Registrar trabajo
    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id":     job_id,
            "status":     "pending",
            "total":      len(saved_files),
            "done":       0,
            "error":      None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    # Lanzar bot en hilo background
    t = threading.Thread(
        target=run_bot_job,
        args=(job_id, saved_files, prompts, input_dir, output_dir),
        daemon=True,
    )
    t.start()

    return jsonify({"job_id": job_id, "status": "accepted"}), 202


@app.route("/api/job/<job_id>", methods=["GET"])
def get_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "job_id": job["job_id"],
        "status": job["status"],
        "progress": {"total": job["total"], "done": job["done"]},
        "error":  job.get("error"),
    })


@app.route("/api/job/<job_id>/download", methods=["GET"])
def download_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        abort(404)
    if job["status"] != "done":
        abort(400)

    output_dir = JOBS_DIR / job_id / "output"
    if not output_dir.exists():
        abort(404)

    # Crear ZIP en memoria
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for video in output_dir.rglob("*.mp4"):
            arcname = video.relative_to(output_dir)
            zf.write(video, arcname)
    buf.seek(0)

    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"videos-{job_id[:8]}.zip",
    )


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "active_jobs": sum(1 for j in JOBS.values() if j["status"] == "running")})


# ── BOT RUNNER ─────────────────────────────────────────────────────

def run_bot_job(job_id, image_files, prompts, input_dir, output_dir):
    """Ejecuta el bot de Google Flow para cada imagen del trabajo."""
    import asyncio

    update_job(job_id, status="running")

    try:
        asyncio.run(flow_bot.run_job(
            job_id=job_id,
            image_files=image_files,
            prompts=prompts,
            output_dir=output_dir,
            on_progress=lambda done: update_job(job_id, done=done),
        ))
        update_job(job_id, status="done")
    except Exception as e:
        update_job(job_id, status="error", error=str(e))


# ── MAIN ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"✦ FlowGen VM Worker running at http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
