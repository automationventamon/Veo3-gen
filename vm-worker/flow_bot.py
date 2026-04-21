"""
FlowGen Bot — adaptado de google_flow_bot.py
Recibe trabajos via API (no monitorea carpetas), notifica progreso via callback.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

SESSION_DIR      = Path("./flow_session")
GOOGLE_FLOW_URL  = "https://labs.google/fx/tools/flow"
HEADLESS         = False          # False necesario para Google Flow
LOGIN_TIMEOUT    = 120_000        # ms para login manual (solo primera vez)
GENERATE_TIMEOUT = 600            # segundos max esperando videos
DEFAULT_PROMPT   = "A cinematic, smooth video transition"

# Instancia global del browser (se reutiliza entre trabajos)
_playwright = None
_context    = None
_page       = None
_lock       = asyncio.Lock()      # un trabajo a la vez


def log(msg, level="INFO"):
    ts   = datetime.now().strftime("%H:%M:%S")
    icon = {"INFO": "→", "OK": "✓", "WARN": "⚠", "ERR": "✗"}.get(level, "·")
    print(f"  [{ts}] {icon}  {msg}", flush=True)


async def get_browser():
    """Inicia o reutiliza la instancia global del browser."""
    global _playwright, _context, _page

    if _context is not None:
        try:
            await _page.evaluate("1")  # check if alive
            return _page
        except Exception:
            log("Browser muerto — reiniciando...", "WARN")
            _context = None
            _page    = None

    if _playwright is None:
        _playwright = await async_playwright().start()

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    _context = await _playwright.chromium.launch_persistent_context(
        str(SESSION_DIR),
        headless=HEADLESS,
        channel="msedge",
        args=["--start-maximized", "--enable-gpu"],
        no_viewport=True,
        accept_downloads=True,
    )
    _page = _context.pages[0] if _context.pages else await _context.new_page()
    log("Browser listo", "OK")

    await ensure_logged_in(_page)
    return _page


async def ensure_logged_in(page):
    log(f"Navegando a Google Flow...")
    await page.goto(GOOGLE_FLOW_URL, wait_until="domcontentloaded")
    await asyncio.sleep(5)

    login_el = await page.query_selector("input[type='email'], [data-identifier]")
    if login_el:
        log(f"Login requerido. Tenés {LOGIN_TIMEOUT // 1000}s para completarlo.", "WARN")
        try:
            await page.wait_for_selector("input[type='email']", state="hidden", timeout=LOGIN_TIMEOUT)
            await asyncio.sleep(3)
            log("Login completado. Sesión guardada.", "OK")
        except PlaywrightTimeoutError:
            log("Timeout de login agotado.", "ERR")
            sys.exit(1)
    else:
        log("Sesión activa.", "OK")

    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass


async def wait_for_any(page, selectors, timeout=10_000):
    deadline = asyncio.get_event_loop().time() + timeout / 1000
    while True:
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    return el
            except Exception:
                pass
        if asyncio.get_event_loop().time() > deadline:
            raise PlaywrightTimeoutError(f"Selectores no encontrados: {selectors}")
        await asyncio.sleep(0.5)


async def download_video(page, index, save_dir: Path):
    log(f"Descargando video {index + 1}...")
    btn = await wait_for_any(page, ["button:has-text('Download')", "[aria-label*='download' i]"], timeout=20_000)
    await btn.click()
    await page.wait_for_timeout(2000)

    final_btn = await wait_for_any(page, ["text=720p", "button:has-text('720p')", "div:has-text('720p')"], timeout=10_000)

    async with page.expect_download(timeout=120_000) as dl_info:
        await final_btn.click()

    download  = await dl_info.value
    save_dir.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = save_dir / f"video_{index + 1}_{ts}.mp4"
    await download.save_as(path)
    log(f"Video {index + 1} guardado: {path.name}", "OK")


async def process_one_image(page, img_path: Path, prompt: str, output_dir: Path):
    """Procesa una sola imagen: sube → prompt → genera → descarga."""
    name = img_path.name
    log(f"Procesando: {name}")

    # 1. Navegar limpio
    await page.goto(GOOGLE_FLOW_URL, wait_until="domcontentloaded")
    await asyncio.sleep(4)

    # 2. New Project
    btn = await wait_for_any(page, [
        "button:has-text('New project')",
        "button:has-text('add_2')",
        "button:has-text('New')",
    ], timeout=20_000)
    await btn.click()
    await asyncio.sleep(3)

    # 3. Subir imagen
    file_input = await page.query_selector("input[type='file']")
    if file_input:
        await file_input.set_input_files(str(img_path))
    else:
        upload_btn = await wait_for_any(page, [
            "button:has-text('Upload')", "button:has-text('Add image')", "[aria-label*='upload' i]"
        ], timeout=10_000)
        async with page.expect_file_chooser() as fc_info:
            await upload_btn.click()
        fc = await fc_info.value
        await fc.set_files(str(img_path))
    await asyncio.sleep(2)

    # 4. Escribir prompt
    textarea = await wait_for_any(page, [
        "textarea", "[contenteditable='true']",
        "[placeholder*='prompt' i]", "[aria-label*='prompt' i]"
    ], timeout=10_000)
    await textarea.click()
    await page.keyboard.press("Control+a")
    await textarea.fill(prompt)
    await asyncio.sleep(1)

    # 5. Start (espera UI)
    log("Esperando UI (30s)...")
    await asyncio.sleep(30)
    try:
        container = await page.wait_for_selector("div.sc-5496b68c-0", timeout=15_000)
        start_btn = await container.query_selector("div:has-text('Start')")
        if start_btn:
            await start_btn.click()
        else:
            raise Exception("Start no encontrado")
    except Exception:
        await page.evaluate("""
        () => {
            const containers = document.querySelectorAll('div.sc-5496b68c-0');
            for (const c of containers) {
                const btn = [...c.querySelectorAll('div')].find(el => el.innerText.trim() === 'Start');
                if (btn) { btn.click(); break; }
            }
        }
        """)
    await asyncio.sleep(30)

    # 6. Seleccionar imagen en panel
    img_element = await wait_for_any(page, [
        f"text={name}", f"div:has-text('{name}')", "div.sc-3038c00b-11"
    ], timeout=60_000)
    await img_element.click()
    await asyncio.sleep(30)

    # 7. Generate
    gen_btn = await wait_for_any(page, [
        "button:has-text('Generate')", "button:has-text('Generar')", "button:has-text('Create')"
    ], timeout=10_000)
    await gen_btn.click()
    log("Generación iniciada", "OK")

    # 8. Esperar videos
    start_t = asyncio.get_event_loop().time()
    while True:
        count = await page.locator("video").count()
        if count >= 4:
            log(f"4 videos detectados", "OK")
            break
        if asyncio.get_event_loop().time() - start_t > GENERATE_TIMEOUT:
            log("Timeout esperando videos", "WARN")
            break
        await asyncio.sleep(5)

    await asyncio.sleep(5)

    # 9. Descargar todos los videos
    videos    = page.locator("video")
    count     = await videos.count()
    stem      = img_path.stem
    save_dir  = output_dir / stem

    for i in range(count):
        try:
            video     = videos.nth(i)
            container = video.locator("..")
            await container.scroll_into_view_if_needed()
            await container.click(force=True)
            await asyncio.sleep(2)
            await download_video(page, i, save_dir)
            await page.go_back()
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)
        except Exception as e:
            log(f"Error en video {i + 1}: {e}", "WARN")

    return count > 0


async def run_job(job_id, image_files, prompts, output_dir, on_progress):
    """
    Punto de entrada llamado por app.py.
    Procesa todas las imágenes del trabajo secuencialmente.
    """
    global _context, _page

    async with _lock:
        log(f"=== Trabajo {job_id[:8]} — {len(image_files)} imagen(es) ===")

        page = await get_browser()
        done = 0

        for img_path in image_files:
            prompt = prompts.get(img_path.name, DEFAULT_PROMPT)
            try:
                await process_one_image(page, img_path, prompt, output_dir)
            except Exception as e:
                log(f"Error en {img_path.name}: {e} — reiniciando browser", "ERR")
                try:
                    await _context.close()
                except Exception:
                    pass
                _context = None
                _page    = None
                page     = await get_browser()

            done += 1
            on_progress(done)
            log(f"Progreso: {done}/{len(image_files)}", "OK")

        log(f"Trabajo {job_id[:8]} completado.", "OK")
