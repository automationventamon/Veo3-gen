"""
Inspector completo: navega todo el flujo y toma capturas en cada paso.
"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SESSION_DIR     = Path(r"C:\Users\Acer\Documents\AutomatizacionvideoFLOW\flow_session")
GOOGLE_FLOW_URL = "https://labs.google/fx/tools/flow"
IMG             = Path(r"C:\Users\Acer\Documents\AutomatizacionvideoFLOW\imagen1.jpeg")
SHOTS_DIR       = Path(r"C:\Users\Acer\AppData\Local\Temp\flow_inspect")
SHOTS_DIR.mkdir(exist_ok=True)

def dump_buttons(btns_data):
    for b in btns_data:
        print(f"  [BTN] '{b[0]}' | aria='{b[1]}' | cls='{b[2]}'")

async def get_buttons(page):
    out = []
    for btn in await page.query_selector_all("button, [role='button']"):
        try:
            if not await btn.is_visible(): continue
            txt  = (await btn.inner_text()).strip().replace("\n"," ")[:70]
            aria = await btn.get_attribute("aria-label") or ""
            cls  = (await btn.get_attribute("class") or "")[:70]
            out.append((txt, aria, cls))
        except: pass
    return out

async def snap(page, name):
    path = SHOTS_DIR / f"{name}.png"
    await page.screenshot(path=str(path), full_page=False)
    print(f"  [SNAP] {path}")

async def main():
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            str(SESSION_DIR), headless=False, channel="msedge",
            args=["--start-maximized"], no_viewport=True, accept_downloads=True,
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # ── PASO 1: Ir a Flow ──────────────────────────────────
        print("\n=== PASO 1: Flow home ===")
        await page.goto(GOOGLE_FLOW_URL, wait_until="domcontentloaded")
        await asyncio.sleep(8)
        await snap(page, "01_home")
        dump_buttons(await get_buttons(page))

        # ── PASO 2: Click New Project (exacto) ────────────────
        print("\n=== PASO 2: Click New Project ===")
        clicked = False
        for btn in await page.query_selector_all("button, [role='button']"):
            try:
                txt = (await btn.inner_text()).strip().lower()
                if "new project" in txt and await btn.is_visible():
                    print(f"  Clickeando: '{txt}'")
                    await btn.click()
                    clicked = True
                    break
            except: pass
        if not clicked:
            print("  ERROR: New Project no encontrado")
        await asyncio.sleep(5)
        await snap(page, "02_after_new_project")
        dump_buttons(await get_buttons(page))
        print("  URL:", page.url)

        # ── PASO 3: Subir imagen ───────────────────────────────
        print("\n=== PASO 3: Subir imagen ===")
        file_input = await page.query_selector("input[type='file']")
        if file_input:
            print("  Usando file input directo")
            await file_input.set_input_files(str(IMG))
        else:
            print("  Buscando upload button...")
            for btn in await page.query_selector_all("button, [role='button']"):
                try:
                    txt = (await btn.inner_text()).strip().lower()
                    if ("upload" in txt or "add image" in txt or "image" in txt) and await btn.is_visible():
                        print(f"  Click upload: '{txt}'")
                        async with page.expect_file_chooser(timeout=5000) as fc_info:
                            await btn.click()
                        fc = await fc_info.value
                        await fc.set_files(str(IMG))
                        break
                except: pass
        await asyncio.sleep(4)
        await snap(page, "03_after_upload")
        dump_buttons(await get_buttons(page))

        # ── PASO 4: Prompt ─────────────────────────────────────
        print("\n=== PASO 4: Textarea ===")
        for sel in ["textarea", "[contenteditable='true']", "[placeholder*='prompt' i]"]:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                print(f"  Textarea encontrado: {sel}")
                await el.click()
                await page.keyboard.press("Control+a")
                await el.fill("test prompt for inspection")
                break
        await asyncio.sleep(2)
        await snap(page, "04_after_prompt")

        # ── PASO 5: Buscar Start ───────────────────────────────
        print("\n=== PASO 5: Buscar Start ===")
        await asyncio.sleep(30)
        await snap(page, "05_before_start")
        dump_buttons(await get_buttons(page))

        # Buscar div.sc-* que contenga "Start"
        divs_with_start = await page.evaluate("""
        () => {
            const all = document.querySelectorAll('div');
            const found = [];
            for (const d of all) {
                if (d.innerText.trim() === 'Start') {
                    found.push({
                        cls: d.className,
                        parentCls: d.parentElement?.className || '',
                        visible: d.offsetParent !== null
                    });
                }
            }
            return found;
        }
        """)
        print("  Divs con texto 'Start':", divs_with_start)

        # Buscar boton Start
        for btn in await page.query_selector_all("button, [role='button'], div"):
            try:
                txt = (await btn.inner_text()).strip()
                if txt == "Start" and await btn.is_visible():
                    cls = await btn.get_attribute("class") or ""
                    print(f"  ENCONTRADO Start: cls='{cls}'")
                    await btn.click()
                    print("  Clickeado!")
                    break
            except: pass

        await asyncio.sleep(30)
        await snap(page, "06_after_start")
        dump_buttons(await get_buttons(page))
        print("  URL:", page.url)

        # ── PASO 6: Buscar imagen en panel ────────────────────
        print("\n=== PASO 6: Panel de imágenes ===")
        imgs_in_panel = await page.evaluate("""
        () => {
            const divs = document.querySelectorAll('div');
            const found = [];
            for (const d of divs) {
                const txt = d.innerText?.trim();
                if (txt && txt.includes('imagen1') && d.offsetParent !== null) {
                    found.push({ txt: txt.slice(0,60), cls: d.className.slice(0,60) });
                }
            }
            return found.slice(0, 10);
        }
        """)
        print("  Divs con 'imagen1':", imgs_in_panel)
        await snap(page, "07_panel")

        print("\n=== FIN INSPECCION ===")
        await asyncio.sleep(3)
        await ctx.close()

asyncio.run(main())
