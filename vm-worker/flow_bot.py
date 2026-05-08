"""
FlowGen Bot — Nano Banana 2 + ejecucion paralela (NUM_WORKERS workers).
"""
print(">>> FLOW_BOT v5 CARGADO — parallel workers <<<", flush=True)

import asyncio
import sys
import json
import time
import traceback
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# ── CONFIG ────────────────────────────────────────────────────────
SESSION_DIR      = Path(r"C:\Users\Acer\Documents\AutomatizacionvideoFLOW\flow_session")
GOOGLE_FLOW_URL  = "https://labs.google/fx/tools/flow"
HEADLESS         = False
LOGIN_TIMEOUT    = 120_000
GENERATE_TIMEOUT = 600
DEFAULT_PROMPT   = "A cinematic, smooth video transition"
NUM_WORKERS      = 3

DOWNLOAD_DIR   = Path(".")
PROCESSED_FILE = Path(r".\processed.json")

_playwright = None
_context    = None
_page       = None

FAIL_STREAK  = 0
ACTIVE_JOBS  = 0

# ── LOG ───────────────────────────────────────────────────────────

_logfile = open(r"C:\Users\Acer\AppData\Local\Temp\flowbot_log.txt", "a", buffering=1, encoding="utf-8")

def log(msg: str, level: str = "INFO"):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    icon = {"INFO": "->", "OK": "OK", "WARN": "!!", "ERR": "XX", "HEAD": "=="}.get(level, ".")
    line = f"  [{ts}] {icon}  {msg}"
    print(line, flush=True)
    _logfile.write(line + "\n")
    _logfile.flush()

def wlog(worker_id: int, img_name: str, msg: str, level: str = "INFO"):
    log(f"[W{worker_id}|{img_name}] {msg}", level)

def step(worker_id: int, img_name: str, fase: str):
    log(f"[W{worker_id}|{img_name}] === {fase} ===", "HEAD")

# ── PERSISTENCIA ──────────────────────────────────────────────────

def load_processed() -> set:
    if PROCESSED_FILE.exists():
        try:
            return set(json.loads(PROCESSED_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()

def save_processed(processed: set):
    PROCESSED_FILE.write_text(
        json.dumps(sorted(processed), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

# ── PLAYWRIGHT HELPERS ────────────────────────────────────────────

async def wait_for_any(page, selectors: list, timeout: int = 10_000) -> object:
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

async def launch_browser(playwright):
    log("Iniciando navegador...")
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    for lock in (SESSION_DIR / "Default" / "LOCK", SESSION_DIR / "LOCK", SESSION_DIR / "lockfile"):
        try:
            lock.unlink(missing_ok=True)
        except Exception:
            pass
    ctx = await playwright.chromium.launch_persistent_context(
        str(SESSION_DIR), headless=HEADLESS, channel="msedge",
        args=["--start-maximized", "--enable-gpu"],
        no_viewport=True, accept_downloads=True,
    )
    pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
    log("Navegador listo", "OK")
    return ctx, pg

async def ensure_logged_in(page):
    log("Navegando a Flow...")
    await page.goto(GOOGLE_FLOW_URL, wait_until="domcontentloaded")
    await asyncio.sleep(8)
    url = page.url

    # Caso 1: redirect real a accounts.google.com
    if "accounts.google.com" in url:
        log(f"Auth requerida (redirect) — {LOGIN_TIMEOUT // 1000}s para completarlo.", "WARN")
        try:
            await page.wait_for_url("**/fx/tools/flow**", timeout=LOGIN_TIMEOUT)
            await asyncio.sleep(3)
            log("Login completado.", "OK")
        except PlaywrightTimeoutError:
            log("Timeout de login.", "ERR")
            sys.exit(1)
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        return

    # Caso 2: overlay en página (iframe accounts.google.com o elementos de auth)
    auth_overlay = False
    try:
        auth_overlay = await page.evaluate("""() => {
            for (const f of document.querySelectorAll('iframe')) {
                if ((f.src || '').includes('accounts.google.com')) return true;
            }
            return false;
        }""")
    except Exception:
        pass
    if not auth_overlay:
        try:
            el = await page.query_selector("input[type='email'], [data-identifier], button:has-text('Use another account')")
            if el:
                auth_overlay = True
        except Exception:
            pass

    if auth_overlay:
        log(f"Auth requerida (overlay) — completá el login en Edge ({LOGIN_TIMEOUT // 1000}s).", "WARN")
        deadline = asyncio.get_event_loop().time() + LOGIN_TIMEOUT / 1000
        while True:
            await asyncio.sleep(3)
            # Esperar que el overlay desaparezca y "New project" sea visible
            try:
                btn = await page.query_selector("button:has-text('New project'), button:has-text('add_2')")
                if btn and await btn.is_visible():
                    log("Login completado.", "OK")
                    break
            except Exception:
                pass
            if asyncio.get_event_loop().time() > deadline:
                log("Timeout de login.", "ERR")
                sys.exit(1)
    else:
        log("Sesion activa.", "OK")

    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass

def _snap(page, name: str):
    return page.screenshot(path=f"C:/Users/Acer/AppData/Local/Temp/{name}.png")

async def set_tab_status(page, worker_id: int, img_name: str, status: str):
    try:
        await page.evaluate(
            "(d) => { document.title = `W${d.w} | ${d.img} | ${d.s}`; }",
            {"w": worker_id, "img": img_name, "s": status}
        )
    except Exception:
        pass

async def activate_worker_tab(page, worker_id: int, step_name: str = ""):
    try:
        await page.bring_to_front()
        await asyncio.sleep(0.5)
        wlog(worker_id, "", f"Tab activa -> {step_name}", "OK")
    except Exception:
        pass

async def hard_reset_browser(context_ref: list, playwright_ref):
    log("Reiniciando navegador completo...", "WARN")
    try:
        await context_ref[0].close()
    except Exception:
        pass
    ctx, pg = await launch_browser(playwright_ref)
    context_ref[0] = ctx
    await ensure_logged_in(pg)
    log("Navegador reiniciado", "OK")
    return pg

# ── HELPERS v2 (Nano Banana 2) ────────────────────────────────────

async def wait_create_ready(page, timeout=30_000):
    """Espera que la pantalla Create esté lista (upload area visible)."""
    log("Esperando pantalla Create...")
    return await wait_for_any(page, [
        "button:has-text('Nano')",
        "button:has-text('Banana')",
        "input[type='file']",
        "button:has-text('Upload')",
        "textarea",
        "[contenteditable='true']",
    ], timeout=timeout)

async def handle_notice_popup(page):
    """Cierra popup 'Notice / I agree' si aparece."""
    try:
        dialog = await page.query_selector("div[role='dialog']")
        if dialog:
            agree_btn = await page.query_selector("button:has-text('I agree')")
            if agree_btn and await agree_btn.is_visible():
                log("Popup Notice detectado — aceptando...", "WARN")
                await agree_btn.click()
                await asyncio.sleep(1)
                log("Notice cerrado", "OK")
                return True
    except Exception:
        pass
    return False

async def wait_image_ready(page, timeout=90):
    """Espera que el thumbnail de la imagen subida sea válido."""
    log("Esperando imagen lista en canvas...")
    start = asyncio.get_event_loop().time()
    while True:
        tiles = page.locator("[data-tile-id], div.sc-adc89304-0")
        count = await tiles.count()
        if count > 0:
            tile = tiles.nth(count - 1)
            loading = await tile.locator(
                "svg, [class*='spinner'], [aria-busy='true'], [role='progressbar']"
            ).count()
            img     = tile.locator("img")
            has_img = await img.count()
            img_ok  = False
            if has_img > 0:
                try:
                    src = await img.first.get_attribute("src")
                    box = await img.first.bounding_box()
                    if src and box and box["width"] > 30 and box["height"] > 30:
                        img_ok = True
                except Exception:
                    pass
            has_canvas = await tile.locator("canvas").count()
            if img_ok or has_canvas > 0:
                log("Imagen lista", "OK")
                return tile
            if not loading:
                # sin spinner ni imagen — puede que la UI no use tiles, continuar
                pass
        elapsed = asyncio.get_event_loop().time() - start
        if elapsed > timeout:
            log("Timeout imagen lista — continuando de todas formas", "WARN")
            return None
        await asyncio.sleep(1)

async def get_tiles_status(page) -> dict:
    """Retorna {video, failed, processing} contando los últimos 4 tiles."""
    tiles = page.locator("div.sc-adc89304-0")
    total = await tiles.count()
    start = max(0, total - 4)
    current = [tiles.nth(i) for i in range(start, total)]
    status = {"failed": 0, "video": 0, "processing": 0}
    for tile in current:
        has_video    = await tile.locator("video").count() > 0
        has_unusual  = await tile.locator("text=unusual activity").count() > 0
        has_audiofail= await tile.locator("text=Audio generation failed").count() > 0
        has_policy   = await tile.locator("text=violate our policies").count() > 0
        still_loading= await tile.locator("svg, [class*='spinner'], [aria-busy='true']").count() > 0
        if has_video:
            status["video"] += 1
        elif still_loading:
            status["processing"] += 1
        elif has_unusual or has_audiofail or has_policy:
            status["failed"] += 1
        else:
            status["processing"] += 1
    return status

async def soft_reset(page):
    """Limpia localStorage, sessionStorage y cache de red via CDP."""
    log("Limpiando cache + storage...", "WARN")
    try:
        await page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
        client = await page.context.new_cdp_session(page)
        await client.send("Network.clearBrowserCache")
        log("Cache limpiado", "OK")
    except Exception as e:
        log(f"soft_reset error: {e}", "WARN")

async def configure_video(page, worker_id: int = 1, name: str = ""):
    """Abre menú Nano Banana y configura: Video / 9:16 / x4."""
    try:
        wlog(worker_id, name, "Configurando video (Nano Banana)...")
        btn = await wait_for_any(page, [
            "button:has-text('Nano')",
            "button:has-text('Banana')",
            "button[aria-haspopup='menu']",
        ], timeout=8_000)
        await btn.click()
        await asyncio.sleep(1)
        try:
            vt = await wait_for_any(page, [
                "button:has-text('Video')", "[role='tab']:has-text('Video')",
            ], timeout=5_000)
            await vt.click()
            await asyncio.sleep(0.5)
        except Exception:
            pass
        try:
            rb = await wait_for_any(page, [
                "[role='tab']:has-text('9:16')", "button:has-text('9:16')",
            ], timeout=5_000)
            await rb.click()
            await asyncio.sleep(0.5)
        except Exception:
            pass
        try:
            x4 = await wait_for_any(page, [
                "[role='tab']:has-text('x4')", "button:has-text('x4')",
            ], timeout=5_000)
            await x4.click()
            await asyncio.sleep(0.5)
        except Exception:
            pass
        wlog(worker_id, name, "Video configurado (Video / 9:16 / x4)", "OK")
    except Exception as e:
        wlog(worker_id, name, f"configure_video no disponible ({e}) — continuando", "WARN")

async def download_video(page, index, save_dir: Path):
    log(f"Descargando video {index + 1}...")
    btn = await wait_for_any(page, [
        "button:has-text('Download')", "[aria-label*='download' i]"
    ], timeout=20_000)
    await btn.click()
    await page.wait_for_timeout(2_000)
    final = await wait_for_any(page, [
        "text=720p", "button:has-text('720p')", "div:has-text('720p')"
    ], timeout=10_000)
    async with page.expect_download(timeout=120_000) as dl_info:
        await final.click()
    download = await dl_info.value
    save_dir.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = save_dir / f"video_{index + 1}_{ts}.mp4"
    await download.save_as(path)
    log(f"Video {index + 1} guardado: {path.name}", "OK")

# ── FLUJO PRINCIPAL ───────────────────────────────────────────────

async def process_image(page, img_path: Path, default_prompt: str, prompts_map: dict,
                        cancel_check=None, worker_id: int = 1, context_ref: list = None) -> bool:
    global FAIL_STREAK
    start_img_time = time.time()
    name = img_path.name
    key  = name.strip().lower()
    image_prompts = prompts_map.get(key, [default_prompt])
    processed = load_processed()

    for idx, single_prompt in enumerate(image_prompts):
        key_prompt = f"{name}|{idx}"
        save_dir   = DOWNLOAD_DIR / Path(name).stem / f"prompt_{idx + 1}"

        if key_prompt in processed:
            wlog(worker_id, name, f"Saltando prompt {idx+1} (ya procesado)", "WARN")
            continue

        step(worker_id, name, f"PROMPT {idx+1}/{len(image_prompts)}")

        try:
            # 1. Navegar + esperar UI o auth
            wlog(worker_id, name, "Paso 1: navegar a Flow")
            await page.goto(GOOGLE_FLOW_URL, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass
            log(f"URL: {page.url}")
            await _snap(page, f"s1_home_{idx}")

            # Polling: esperar "New project" o detectar auth overlay
            auth_warned = False
            deadline = asyncio.get_event_loop().time() + LOGIN_TIMEOUT / 1000
            new_proj_btn = None
            while True:
                if cancel_check and cancel_check():
                    log("Cancelado durante espera de New project.", "WARN")
                    return False
                # Detectar auth overlay PRIMERO (iframe Google accounts)
                auth_detected = False
                try:
                    auth_in_iframe = await page.evaluate("""() => {
                        const frames = document.querySelectorAll('iframe');
                        for (const f of frames) {
                            const src = f.src || '';
                            if (src.includes('accounts.google.com') || src.includes('signin')) return true;
                        }
                        return false;
                    }""")
                    if auth_in_iframe:
                        auth_detected = True
                except Exception:
                    pass
                if not auth_detected:
                    for asel in ["text=Choose an account", "text=Elegir una cuenta",
                                 "button:has-text('Use another account')", "input[type='email']"]:
                        try:
                            el = await page.query_selector(asel)
                            if el and await el.is_visible():
                                auth_detected = True
                                break
                        except Exception:
                            pass
                if auth_detected and not auth_warned:
                    log(f"Auth detectada (overlay) — completa el login ({LOGIN_TIMEOUT // 1000}s).", "WARN")
                    auth_warned = True
                if auth_detected:
                    if asyncio.get_event_loop().time() > deadline:
                        raise Exception("Timeout esperando login")
                    await asyncio.sleep(2)
                    continue

                # Buscar "New project" exacto (sin fallback genérico 'New')
                for sel in ["button:has-text('New project')", "button:has-text('add_2')"]:
                    try:
                        el = await page.query_selector(sel)
                        if el and await el.is_visible():
                            txt = (await el.inner_text()).strip()
                            log(f"Botón encontrado: '{txt}'")
                            new_proj_btn = el
                            break
                    except Exception:
                        pass
                if new_proj_btn:
                    break

                if asyncio.get_event_loop().time() > deadline:
                    raise Exception("Timeout: no se encontró 'New project'")
                await asyncio.sleep(2)

            if auth_warned:
                log("Login completado, continuando.", "OK")

            # 2. New Project
            log("Paso 2: New Project")
            await new_proj_btn.click()
            await wait_create_ready(page)
            await handle_notice_popup(page)
            await _snap(page, f"s2_newproject_{idx}")
            log("Proyecto creado", "OK")

            # 3. Subir imagen
            log(f"Paso 3: subir {name}")
            file_input = await page.query_selector("input[type='file']")
            if file_input:
                await file_input.set_input_files(str(img_path))
                log("Imagen subida via file input", "OK")
            else:
                up = await wait_for_any(page, [
                    "button:has-text('Add Media')",
                    "button:has-text('Upload')",
                    "[aria-label*='upload' i]",
                ], timeout=10_000)
                async with page.expect_file_chooser() as fc_info:
                    await up.click()
                fc = await fc_info.value
                await fc.set_files(str(img_path))
                log("Imagen subida via chooser", "OK")

            await wait_create_ready(page)
            await handle_notice_popup(page)
            await wait_image_ready(page)
            await asyncio.sleep(1)
            await _snap(page, f"s3_upload_{idx}")

            # 4. Abrir frame picker (Start)
            log("Paso 4: abrir frame picker")
            found_start = await page.evaluate("""
            () => {
                const all = document.querySelectorAll('div, button, span');
                for (const el of all) {
                    if (el.innerText?.trim() === 'Start' && el.offsetParent !== null) {
                        el.click();
                        return el.className || 'clicked';
                    }
                }
                return null;
            }
            """)
            log(f"Start click: {found_start}")
            await asyncio.sleep(3)
            await _snap(page, f"s4_picker_{idx}")

            # 5. Seleccionar imagen en picker
            log(f"Paso 5: seleccionar {name} en picker")
            clicked = await page.evaluate(f"""
            () => {{
                const all = [...document.querySelectorAll('div, span, p')];
                const label = all.find(el =>
                    el.innerText?.trim() === '{name}' && el.offsetParent !== null
                );
                if (label) {{
                    let card = label;
                    for (let i = 0; i < 3; i++) {{
                        if (card.parentElement) card = card.parentElement;
                    }}
                    card.click();
                    return 'card3up:' + card.className.slice(0, 40);
                }}
                for (const img of document.querySelectorAll('img')) {{
                    if (img.offsetParent !== null && img.naturalWidth > 50) {{
                        img.click();
                        return 'img-fallback';
                    }}
                }}
                return 'not-found';
            }}
            """)
            log(f"Seleccion resultado: {clicked}")
            await asyncio.sleep(2)
            await _snap(page, f"s5_selected_{idx}")

            # 6. Escribir prompt
            log("Paso 6: escribir prompt")
            preview = single_prompt[:80] + ("..." if len(single_prompt) > 80 else "")
            log(f"Prompt: '{preview}'")
            textarea = await wait_for_any(page, [
                "[contenteditable='true']",
                "textarea",
                "[placeholder*='create' i]",
                "[placeholder*='prompt' i]",
            ], timeout=10_000)
            await textarea.click()
            await page.keyboard.press("Control+a")
            await textarea.fill(single_prompt)
            await asyncio.sleep(1)

            # 7. Configurar video
            wlog(worker_id, name, "Paso 7: configurar video")
            await configure_video(page, worker_id=worker_id, name=name)

            # 8. Click Create
            log("Paso 8: click Create")
            gen_btn = await wait_for_any(page, [
                "button:has-text('Create')",
                "button:has-text('Generate')",
                "[aria-label*='create' i]",
            ], timeout=10_000)
            await gen_btn.click()
            log("Generacion iniciada", "OK")
            await asyncio.sleep(5)
            await _snap(page, f"s8_generating_{idx}")

            # 9. Esperar videos
            log("Paso 9: esperando videos...")
            start_t = asyncio.get_event_loop().time()
            while True:
                if cancel_check and cancel_check():
                    log("Cancelado durante espera de videos.", "WARN")
                    return False

                status    = await get_tiles_status(page)
                n_video   = status["video"]
                n_failed  = status["failed"]
                n_proc    = status["processing"]
                n_total   = await page.locator("video").count()

                log(f"Estado -> videos: {n_total} | failed: {n_failed} | processing: {n_proc}")

                if n_failed >= 3:
                    wlog(worker_id, name, "Demasiados failed — soft reset y cooldown", "WARN")
                    await soft_reset(page)
                    await page.goto(GOOGLE_FLOW_URL)
                    await asyncio.sleep(30)
                    FAIL_STREAK += 1
                    return False

                if (n_total + n_failed >= 4) and n_proc == 0:
                    log("Generacion completa (video+failed=4)", "OK")
                    break

                if asyncio.get_event_loop().time() - start_t > GENERATE_TIMEOUT:
                    log("Timeout esperando videos", "WARN")
                    break

                await asyncio.sleep(2)

            await asyncio.sleep(2)
            videos = page.locator("video")
            count  = min(await videos.count(), 4)
            log(f"Descargando {count} video(s)")

            if count == 0:
                await _snap(page, f"s9_novideo_{idx}")
                log("No hay videos — fallo generacion", "ERR")
                return False

            # 10. Descargar cada video
            for i in range(count):
                try:
                    log(f"=== VIDEO {i+1}/{count} ===")
                    video     = videos.nth(i)
                    container = video.locator("..")
                    await container.scroll_into_view_if_needed()
                    await container.evaluate("""
                    (el) => {
                        el.style.border = '4px solid red';
                        el.style.boxShadow = '0 0 10px red';
                    }
                    """)
                    await asyncio.sleep(1.5)
                    await container.click(force=True)
                    await asyncio.sleep(2)
                    await download_video(page, i, save_dir)
                    log("Volviendo atras...")
                    await page.go_back()
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(3)
                except Exception as e:
                    log(f"Error en video {i+1}: {e}", "WARN")

                processed.add(key_prompt)
                save_processed(processed)
                log(f"Prompt {idx+1} completado", "OK")

        except Exception as ex:
            wlog(worker_id, name, f"EXCEPCION en prompt {idx+1}: {ex}", "ERR")
            traceback.print_exc()
            _logfile.write(traceback.format_exc())
            _logfile.flush()
            try:
                await _snap(page, f"error_w{worker_id}_{idx}")
            except Exception:
                pass
            raise

    elapsed = int(time.time() - start_img_time)
    wlog(worker_id, name, f"Tiempo total: {elapsed // 60}m {elapsed % 60}s", "OK")
    return True

# ── BROWSER STATE ─────────────────────────────────────────────────

async def _check_auth(page):
    """Navega a Flow y espera login manual si hay redirect o overlay de Google auth."""
    await page.goto(GOOGLE_FLOW_URL, wait_until="domcontentloaded")
    await asyncio.sleep(6)
    # Detectar redirect de URL
    if "accounts.google.com" in page.url:
        log(f"Auth requerida (redirect) — {LOGIN_TIMEOUT // 1000}s para login.", "WARN")
        try:
            await page.wait_for_url("**/fx/tools/flow**", timeout=LOGIN_TIMEOUT)
            await asyncio.sleep(3)
            log("Login completado.", "OK")
        except PlaywrightTimeoutError:
            log("Timeout de login.", "ERR")
            sys.exit(1)
        return
    # Detectar overlay en página (iframe accounts.google.com)
    try:
        auth_overlay = await page.evaluate("""() => {
            const frames = document.querySelectorAll('iframe');
            for (const f of frames) {
                if ((f.src || '').includes('accounts.google.com')) return true;
            }
            return false;
        }""")
        if auth_overlay:
            log(f"Auth requerida (overlay) — completa el login en el browser ({LOGIN_TIMEOUT // 1000}s).", "WARN")
            deadline = asyncio.get_event_loop().time() + LOGIN_TIMEOUT / 1000
            while True:
                await asyncio.sleep(3)
                still_auth = await page.evaluate("""() => {
                    const frames = document.querySelectorAll('iframe');
                    for (const f of frames) {
                        if ((f.src || '').includes('accounts.google.com')) return true;
                    }
                    return false;
                }""")
                if not still_auth:
                    log("Login completado.", "OK")
                    break
                if asyncio.get_event_loop().time() > deadline:
                    log("Timeout de login.", "ERR")
                    sys.exit(1)
    except Exception as e:
        log(f"_check_auth iframe check error: {e}", "WARN")

async def ensure_browser():
    global _playwright, _context, _page
    if _page is not None:
        try:
            await _page.evaluate("1")
            await _check_auth(_page)
            return
        except Exception:
            pass
    if _playwright is None:
        _playwright = await async_playwright().start()
    _context, _page = await launch_browser(_playwright)
    await ensure_logged_in(_page)

async def _restart_browser():
    global _context, _page
    log("Reiniciando browser...", "WARN")
    try:
        await _context.close()
    except Exception:
        pass
    _context, _page = await launch_browser(_playwright)
    await ensure_logged_in(_page)
    return _page

# ── PARALLEL WORKER ───────────────────────────────────────────────

async def _worker_task(worker_id: int, queue: asyncio.Queue, context_ref: list,
                       prompts: dict, done_counter: list, on_progress,
                       cancel_check=None):
    global ACTIVE_JOBS
    page = await context_ref[0].new_page()
    wlog(worker_id, "", "Worker iniciado", "OK")

    while True:
        img_path = await queue.get()
        if img_path is None:
            queue.task_done()
            break

        if cancel_check and cancel_check():
            queue.task_done()
            continue

        ACTIVE_JOBS += 1
        step(worker_id, img_path.name, "INICIANDO")
        prompt      = prompts.get(img_path.name, DEFAULT_PROMPT)
        prompts_map = {img_path.name.strip().lower(): [prompt]}

        for attempt in range(2):
            if cancel_check and cancel_check():
                break
            try:
                await process_image(
                    page, img_path, prompt, prompts_map,
                    cancel_check=cancel_check,
                    worker_id=worker_id,
                    context_ref=context_ref,
                )
                break
            except Exception as e:
                wlog(worker_id, img_path.name, f"Error (intento {attempt+1}): {e}", "ERR")
                if attempt == 0:
                    try:
                        await page.goto(GOOGLE_FLOW_URL, wait_until="domcontentloaded")
                        await asyncio.sleep(5)
                    except Exception:
                        pass
                else:
                    wlog(worker_id, img_path.name, "Abandonando tras 2 intentos.", "WARN")

        ACTIVE_JOBS -= 1
        done_counter[0] += 1
        on_progress(done_counter[0])
        wlog(worker_id, img_path.name, f"Progreso: {done_counter[0]}", "OK")
        queue.task_done()

    try:
        await page.close()
    except Exception:
        pass
    wlog(worker_id, "", "Worker terminado", "OK")


# ── ENTRY POINT ───────────────────────────────────────────────────

async def run_job(job_id, image_files, prompts, output_dir, on_progress, cancel_check=None):
    global DOWNLOAD_DIR, PROCESSED_FILE

    log(f"=== Job {job_id[:8]} — {len(image_files)} imagen(es) | {NUM_WORKERS} workers ===")
    await ensure_browser()

    DOWNLOAD_DIR   = output_dir
    PROCESSED_FILE = output_dir / "processed.json"

    context_ref  = [_context]
    queue        = asyncio.Queue()
    done_counter = [0]

    for img in image_files:
        await queue.put(img)

    n_workers = min(NUM_WORKERS, len(image_files))
    tasks = [
        asyncio.create_task(
            _worker_task(i + 1, queue, context_ref, prompts, done_counter,
                         on_progress, cancel_check=cancel_check)
        )
        for i in range(n_workers)
    ]

    await queue.join()

    for _ in tasks:
        await queue.put(None)

    await asyncio.gather(*tasks)

    log(f"Job {job_id[:8]} completado.", "OK")
