"""
FlowGen VM Worker — Flask API
==============================
Un solo event loop de asyncio corre en background permanentemente.
Los jobs entran a una asyncio.Queue y se procesan uno a uno.
Usa google_flow_bot.py como motor de automatización.
"""

import os
import sys
import io

# Forzar UTF-8 en stdout para que gbot.log() no crashee con caracteres Unicode
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

import json
import shutil
import zipfile
import io
import asyncio
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from uuid import uuid4

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ── GOOGLE DRIVE ──────────────────────────────────────────────────
_DRIVE_CREDS_FILE  = r"C:\Users\Acer\Downloads\drive-467016-7a9826ce72a5.json"
_DRIVE_PARENT_ID   = "10ygHcGkQD3DP9kQxjtpOX_dHE1Dpknug"  # Videos Generados Flow
_DRIVE_DELETE_HOURS = 2  # eliminar carpetas después de X horas

def _drive_service():
    creds = service_account.Credentials.from_service_account_file(
        _DRIVE_CREDS_FILE,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

_DRIVE_LOCAL_ROOT = Path(r"G:\My Drive\Flow\Videos Generados Flow")

def upload_job_to_drive(job_id: str, output_dir: Path) -> str:
    """
    Copia los MP4 a G:\ (cuota del usuario) y usa la API solo para
    obtener el folder_id y hacer la carpeta pública.
    """
    import time as _time

    folder_name = job_id[:8]
    local_folder = _DRIVE_LOCAL_ROOT / folder_name
    local_folder.mkdir(parents=True, exist_ok=True)

    # Una subcarpeta por imagen (= un prompt por imagen).
    # Para Excel multi-prompt: imagen_p2 → subcarpeta "imagen_p2".
    count = 0
    for video in output_dir.rglob("*.mp4"):
        image_stem = video.parent.parent.name  # "11", "19", "imagen_p2", ...
        dest_dir = local_folder / image_stem
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(video), str(dest_dir / video.name))
        count += 1
    print(f"[drive] {count} video(s) copiados a {local_folder}", flush=True)

    # Esperar a que Drive sincronice y aparezca el folder_id
    svc = _drive_service()
    folder_id = None
    for _ in range(15):
        _time.sleep(4)
        res = svc.files().list(
            q=f"name='{folder_name}' and '{_DRIVE_PARENT_ID}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id)"
        ).execute()
        files = res.get("files", [])
        if files:
            folder_id = files[0]["id"]
            break

    if not folder_id:
        print("[drive] Carpeta no encontrada en Drive aun — devolviendo link al parent.", flush=True)
        return f"https://drive.google.com/drive/folders/{_DRIVE_PARENT_ID}"

    # Hacer pública
    svc.permissions().create(
        fileId=folder_id,
        body={"role": "reader", "type": "anyone"},
    ).execute()

    link = f"https://drive.google.com/drive/folders/{folder_id}"
    print(f"[drive] Job {folder_name} publico: {link}", flush=True)
    return link


def _drive_cleanup_loop():
    """Thread: elimina carpetas de Drive con más de _DRIVE_DELETE_HOURS horas."""
    svc = _drive_service()
    while True:
        try:
            cutoff = (datetime.utcnow() - timedelta(hours=_DRIVE_DELETE_HOURS)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            results = svc.files().list(
                q=f"'{_DRIVE_PARENT_ID}' in parents and mimeType='application/vnd.google-apps.folder' and createdTime < '{cutoff}'",
                fields="files(id, name)"
            ).execute()
            for f in results.get("files", []):
                svc.files().delete(fileId=f["id"]).execute()
                print(f"[drive] Carpeta eliminada: {f['name']}", flush=True)
        except Exception as e:
            print(f"[drive] Error cleanup: {e}", flush=True)
        time.sleep(1800)  # revisar cada 30 minutos

from flask import Flask, request, jsonify, send_file, abort

sys.path.insert(0, r"C:\Users\Acer\Documents\AutomatizacionvideoFLOW")
import google_flow_bot_paralelo as gbot

gbot.SESSION_DIR = Path(r"C:\Users\Acer\Documents\AutomatizacionvideoFLOW\flow_session_chrome")

async def _launch_chrome(playwright):
    gbot.SESSION_DIR.mkdir(parents=True, exist_ok=True)
    context = await playwright.chromium.launch_persistent_context(
        str(gbot.SESSION_DIR),
        headless=False,
        channel="chrome",
        args=["--start-maximized"],
        no_viewport=True,
        accept_downloads=True,
        ignore_default_args=["--enable-unsafe-swiftshader"],
    )
    page = context.pages[0] if context.pages else await context.new_page()
    return context, page

async def _ensure_logged_in(page):
    """Navega a Google Flow y espera login sin llamar sys.exit."""
    from playwright.async_api import TimeoutError as PWTimeout
    import asyncio
    GOOGLE_FLOW_URL = "https://labs.google/fx/tools/flow"
    print("[app] Navegando a Google Flow...", flush=True)
    await page.goto(GOOGLE_FLOW_URL, wait_until="domcontentloaded")
    await asyncio.sleep(5)
    is_login = await page.query_selector("input[type='email'], [data-identifier]")
    if is_login:
        print("[app] LOGIN requerido en Chrome — ingresa tu cuenta de Google ahora.", flush=True)
        # Esperar hasta 10 minutos para que el usuario haga login
        try:
            await page.wait_for_selector("input[type='email']", state="hidden", timeout=600_000)
            await asyncio.sleep(3)
            print("[app] Login completado.", flush=True)
        except PWTimeout:
            print("[app] Timeout de login — se procede igual.", flush=True)
    else:
        print("[app] Sesion activa detectada.", flush=True)
    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass

async def _hard_reset_safe(context_ref, playwright):
    """hard_reset sin cerrar el contexto — solo abre nueva página para el worker que falló."""
    print("[app] hard_reset interceptado — recargando página sin cerrar contexto", flush=True)
    page = await context_ref[0].new_page()
    await page.goto("https://labs.google/fx/tools/flow", wait_until="domcontentloaded")
    await asyncio.sleep(3)
    return page

gbot.launch_browser    = _launch_chrome
gbot.ensure_logged_in  = _ensure_logged_in
gbot.hard_reset_browser = _hard_reset_safe

app = Flask(__name__)

JOBS_DIR = Path("./jobs")
JOBS_DIR.mkdir(exist_ok=True)

JOBS      = {}
JOBS_LOCK = threading.Lock()

_loop        = None
_job_queue   = None
_playwright  = None
_context     = None
_context_ref = None


# ── ESTADO ────────────────────────────────────────────────────────

def update_job(job_id, **kwargs):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(kwargs)
            JOBS[job_id]["updated_at"] = datetime.now().isoformat()


# ── BROWSER (lazy init) ───────────────────────────────────────────

async def ensure_browser():
    global _playwright, _context, _context_ref
    if _playwright is not None:
        return
    from playwright.async_api import async_playwright
    print(f"[app] Lanzando browser — SESSION_DIR: {gbot.SESSION_DIR}", flush=True)
    _playwright = await async_playwright().start()
    _context, page0 = await gbot.launch_browser(_playwright)
    print(f"[app] Browser lanzado — version: {_context.browser.version if hasattr(_context, 'browser') else 'N/A'}", flush=True)
    _context_ref = [_context]
    await gbot.ensure_logged_in(page0)


# ── ADAPTADOR run_job ─────────────────────────────────────────────

async def run_job(job_id, image_files, prompts, output_dir, on_progress, cancel_check):
    await ensure_browser()

    gbot.DOWNLOAD_DIR   = output_dir
    gbot.PROCESSED_FILE = output_dir.parent / "processed.json"
    prompts_map = {k.lower(): [v] for k, v in prompts.items()}

    queue = asyncio.Queue()
    for img in image_files:
        await queue.put(img)

    done_count = [0]

    async def _worker(worker_id):
        print(f"[worker {worker_id}] Iniciando...", flush=True)
        try:
            page = await _context.new_page()
        except Exception as e:
            print(f"[worker {worker_id}] ERROR abriendo página: {e}", flush=True)
            # vaciar la cola para no bloquear queue.join()
            while not queue.empty():
                try:
                    queue.get_nowait()
                    queue.task_done()
                except Exception:
                    break
            return
        print(f"[worker {worker_id}] Página abierta OK", flush=True)
        try:
            while True:
                img_path = await queue.get()
                if img_path is None:
                    queue.task_done()
                    break
                if cancel_check():
                    queue.task_done()
                    break
                print(f"[worker {worker_id}] Procesando {img_path.name}", flush=True)
                try:
                    await gbot.process_image(
                        page           = page,
                        img_path       = img_path,
                        default_prompt = gbot.DEFAULT_PROMPT,
                        prompts_map    = prompts_map,
                        worker_id      = worker_id,
                        context_ref    = _context_ref,
                        playwright     = _playwright,
                    )
                except Exception as e:
                    print(f"[worker {worker_id}] Error {img_path.name}: {e}", flush=True)
                finally:
                    # Si la página se cerró (hard_reset interno), recrearla para la siguiente imagen
                    if page.is_closed():
                        try:
                            page = await _context.new_page()
                            print(f"[worker {worker_id}] Página recreada tras cierre", flush=True)
                        except Exception as pe:
                            print(f"[worker {worker_id}] No se pudo recrear página: {pe}", flush=True)
                            queue.task_done()
                            break
                    done_count[0] += 1
                    on_progress(done_count[0])
                    queue.task_done()
        finally:
            if not page.is_closed():
                await page.close()

    NUM_WORKERS = 3
    workers = [asyncio.create_task(_worker(i + 1)) for i in range(NUM_WORKERS)]
    await queue.join()
    for _ in workers:
        await queue.put(None)
    await asyncio.gather(*workers)


# ── LOOP PERSISTENTE ──────────────────────────────────────────────

async def job_worker():
    """Consume la cola de jobs indefinidamente en el loop permanente."""
    await ensure_browser()  # inicializar Chrome al arrancar, no en el primer job
    while True:
        job_id, image_files, prompts, output_dir = await _job_queue.get()
        update_job(job_id, status="running")
        try:
            await run_job(
                job_id       = job_id,
                image_files  = image_files,
                prompts      = prompts,
                output_dir   = output_dir,
                on_progress  = lambda done: update_job(job_id, done=done),
                cancel_check = lambda: JOBS.get(job_id, {}).get("cancelled", False),
            )
            if not JOBS.get(job_id, {}).get("cancelled", False):
                try:
                    drive_link = upload_job_to_drive(job_id, JOBS_DIR / job_id / "output")
                    update_job(job_id, status="done", drive_link=drive_link)
                except Exception as de:
                    print(f"[drive] Error subiendo job {job_id[:8]}: {de}", flush=True)
                    update_job(job_id, status="done")
        except Exception as e:
            if not JOBS.get(job_id, {}).get("cancelled", False):
                update_job(job_id, status="error", error=str(e))
            print(f"[worker] Error en job {job_id[:8]}: {e}", flush=True)
        finally:
            _job_queue.task_done()


def start_loop():
    global _loop, _job_queue
    _loop      = asyncio.new_event_loop()
    _job_queue = asyncio.Queue()
    asyncio.set_event_loop(_loop)
    _loop.run_until_complete(job_worker())


def start_cleanup():
    t = threading.Thread(target=_drive_cleanup_loop, daemon=True)
    t.start()


def enqueue(job_id, image_files, prompts, output_dir):
    asyncio.run_coroutine_threadsafe(
        _job_queue.put((job_id, image_files, prompts, output_dir)),
        _loop,
    )


# ── ROUTES ────────────────────────────────────────────────────────

@app.route("/api/job", methods=["POST"])
def create_job():
    job_id  = request.form.get("job_id") or str(uuid4())
    prompts = json.loads(request.form.get("prompts", "{}"))
    files   = request.files.getlist("images")

    if not files:
        return jsonify({"error": "No images received"}), 400

    input_dir  = JOBS_DIR / job_id / "input"
    output_dir = JOBS_DIR / job_id / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for f in files:
        dest = input_dir / f.filename
        f.save(str(dest))
        saved.append(dest)

    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id":     job_id,
            "status":     "pending",
            "total":      len(saved),
            "done":       0,
            "error":      None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    enqueue(job_id, saved, prompts, output_dir)
    return jsonify({"job_id": job_id, "status": "accepted"}), 202


@app.route("/api/job/<job_id>", methods=["GET"])
def get_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "job_id":     job["job_id"],
        "status":     job["status"],
        "progress":   {"total": job["total"], "done": job["done"]},
        "error":      job.get("error"),
        "drive_link": job.get("drive_link"),
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
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for video in output_dir.rglob("*.mp4"):
            zf.write(video, video.relative_to(output_dir))
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"videos-{job_id[:8]}.zip")


@app.route("/api/job/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    update_job(job_id, cancelled=True, status="error", error="Cancelado por el usuario")
    return jsonify({"status": "cancelling"})


@app.route("/api/health", methods=["GET"])
def health():
    active = sum(1 for j in JOBS.values() if j["status"] in ("pending", "running"))
    return jsonify({"status": "ok", "active_jobs": active, "queue_size": _job_queue.qsize() if _job_queue else 0})


# ── MAIN ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    t = threading.Thread(target=start_loop, daemon=True)
    t.start()

    start_cleanup()

    port = int(os.environ.get("PORT", 8000))
    print(f"[FlowGen] VM Worker running at http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
