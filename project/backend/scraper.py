from __future__ import annotations
# scraper.py
import asyncio
import json
import re
import logging
from dataclasses import dataclass, asdict
from typing import Optional
from playwright.async_api import async_playwright, Page, BrowserContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  CONFIGURACIÓN DE BÚSQUEDA — editar aquí
# ─────────────────────────────────────────────

# Añade este diccionario arriba del todo
QUERY_EXPANSIONS = {
    "restaurantes": ["restaurantes", "comida rápida", "cafetería"],
    "peluquerías":  ["peluquerías", "barbería", "salón de belleza"],
    "heladería":    ["heladería", "gelatería", "paletas"],
    "talleres":     ["taller mecánica", "mecánico automotriz", "taller automóviles"],
    "clínicas":     ["clínica dental", "odontólogo", "dentista"],
    "gimnasios":    ["gimnasio", "crossfit", "yoga"],
}

def expand_queries(configs: list) -> list:
    """Expande cada query con sus variantes automáticamente."""
    expanded = []
    for cfg in configs:
        query = cfg["query"].lower()
        # buscar si hay expansiones para este tema
        matched = False
        for key, variants in QUERY_EXPANSIONS.items():
            if key in query or query in key:
                for v in variants:
                    expanded.append({"query": v, "zone": cfg["zone"]})
                matched = True
                break
        if not matched:
            expanded.append(cfg)  # sin expansión, usar tal cual
    return expanded

SEARCH_CONFIGS = [
    {"query": "restaurantes",     "zone": "Hialeah, Florida"},
    {"query": "peluquerías",      "zone": "Miami, Florida"},
    {"query": "talleres mecánica","zone": "Doral, Florida"},
    {"query": "clínicas dentales","zone": "Coral Gables, Florida"},
]

# Ejemplo con Zona Colombia :
# SEARCH_CONFIGS = [
#    {"query": "gimnasios",     "zone": "Bogotá, Colombia"},
#    {"query": "notarías",      "zone": "Ciudad de México, CDMX"},
#    {"query": "ferreterías",   "zone": "Medellín, Antioquia"},
#    {"query": "restaurantes",  "zone": "Miraflores, Lima, Perú"},
#]
#

SCROLL_PAUSE_MS       = 600  # ms entre scrolls (más = más lento pero más estable)
HEADLESS              = True  # False para ver el browser en tiempo real

 
# ─────────────────────────────────────────────
#  MODELO DE DATOS
# ─────────────────────────────────────────────
@dataclass
class Lead:
    name:     str
    address:  str
    phone:    Optional[str]
    website:  Optional[str]
    rating:   Optional[float]
    reviews:  Optional[int]
    category: Optional[str]
    zone:     str
    query:    str
    maps_url: Optional[str]


# ─────────────────────────────────────────────
#  SCRAPER PRINCIPAL
# ─────────────────────────────────────────────
class GoogleMapsScraper:

    def __init__(self, headless: bool = HEADLESS):
        self.headless = headless

    async def scrape_all(self, configs: list) -> list:
        # AÑADE esta línea al inicio:
        configs = expand_queries(configs)
        log.info(f"📋 Búsquedas expandidas: {len(configs)} queries totales")
        all_leads = []
        
        """Ejecuta todas las búsquedas definidas en SEARCH_CONFIGS."""
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            context = await self._build_context(browser)

            for cfg in configs:
                query = cfg["query"]
                zone  = cfg["zone"]
                log.info(f"🔍 Buscando '{query}' en '{zone}'")
                try:
                    leads = await self._scrape_query(context, query, zone)
                    all_leads.extend(leads)
                    log.info(f"✅ {len(leads)} leads extraídos para '{query}' en '{zone}'")
                except Exception as e:
                    log.error(f"❌ Error en '{query}' / '{zone}': {e}")

            await browser.close()

        return all_leads

    # ── contexto con headers humanos ──────────────────────────────────────
    async def _build_context(self, browser) -> BrowserContext:
        return await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-ES",
            timezone_id="America/New_York",
        )

    # ── búsqueda individual ───────────────────────────────────────────────
    async def _scrape_query(
        self, context: BrowserContext, query: str, zone: str
    ) -> list[Lead]:

        page = await context.new_page()
        search_term = f"{query} en {zone}"
        url = f"https://www.google.com/maps/search/?api=1&query={search_term.replace(' ', '+')}"

        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(4000)  # espera más
        # simula movimiento de mouse
        await page.mouse.move(300, 400)
        await page.wait_for_timeout(1000)
        await page.mouse.move(500, 300)
        await page.wait_for_timeout(1500)

        # aceptar cookies si aparece el banner
        await self._dismiss_cookies(page)

        # scroll del panel de resultados hasta MAX_RESULTS
        await self._scroll_results(page)

        # extraer URLs de los negocios listados
        place_links = await self._collect_place_links(page)
        log.info(f"  → {len(place_links)} fichas encontradas")

        leads: list[Lead] = []
    # PON:
        semaphore = asyncio.Semaphore(5)

        async def fetch(link: str) -> Optional[Lead]:
            async with semaphore:
                try:
                    return await self._extract_place(context, link, zone, query)
                except Exception as e:
                    log.warning(f"  ⚠ skip ficha ({e})")
                    return None

        results = await asyncio.gather(*[fetch(l) for l in (place_links or [])])
        leads = [r for r in results if r is not None]

        await page.close()
        return leads

    # ── scroll del panel izquierdo ────────────────────────────────────────
    async def _scroll_results(self, page: Page) -> None:
        """Scrollea el panel de resultados para cargar más fichas."""
        panel_selector = 'div[role="feed"]'
        try:
            await page.wait_for_selector(panel_selector, timeout=8000)
        except Exception:
            log.warning("  ⚠ Panel de resultados no encontrado, continuando...")
            return

        for i in range(50):  # máximo 15 scrolls
            await page.eval_on_selector(
                panel_selector,
                "el => el.scrollBy(0, 800)"
            )
            await page.wait_for_timeout(SCROLL_PAUSE_MS)

            # detectar fin de resultados
            end_msg = page.locator('span:has-text("Has llegado al final")')
            if await end_msg.count() > 0:
                log.debug(f"  → fin de resultados tras {i+1} scrolls")
                break

    # ── recopilar links de fichas ─────────────────────────────────────────
    async def _collect_place_links(self, page: Page) -> list[str]:
        links = await page.eval_on_selector_all(
            'a[href*="/maps/place/"]',
            "els => [...new Set(els.map(e => e.href))]"
        )
        return [l for l in links if "/maps/place/" in l]

    # ── extraer datos de una ficha ────────────────────────────────────────
    async def _extract_place(
        self, context: BrowserContext, url: str, zone: str, query: str
    ) -> Optional[Lead]:

        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            await page.wait_for_timeout(1500)

            name     = await self._get_text(page, 'h1.DUwDvf, h1[class*="fontHeadlineLarge"]')
            address  = await self._get_text(page, '[data-item-id="address"] .Io6YTe, button[data-item-id="address"]')
            phone    = await self._get_phone(page)
            website  = await self._get_website(page)
            rating   = await self._get_rating(page)
            reviews  = await self._get_review_count(page)
            category = await self._get_text(page, 'button.DkEaL')

            if not name:
                return None

            return Lead(
                name=name.strip(),
                address=address or "",
                phone=phone,
                website=website,
                rating=rating,
                reviews=reviews,
                category=category,
                zone=zone,
                query=query,
                maps_url=url,
            )
        finally:
            await page.close()

    # ── helpers de extracción ─────────────────────────────────────────────
    async def _get_text(self, page: Page, selector: str) -> Optional[str]:
        try:
            el = page.locator(selector).first
            return await el.inner_text(timeout=3000)
        except Exception:
            return None

    async def _get_phone(self, page: Page) -> Optional[str]:
        try:
            # botón de teléfono tiene data-item-id que empieza con "phone"
            btn = page.locator('[data-item-id^="phone"] .Io6YTe').first
            text = await btn.inner_text(timeout=3000)
            # limpiar y validar formato
            cleaned = re.sub(r"[^\d\+\-\s\(\)]", "", text).strip()
            return cleaned if len(cleaned) >= 7 else None
        except Exception:
            return None

    async def _get_website(self, page: Page) -> Optional[str]:
        try:
            link = page.locator('a[data-item-id="authority"]').first
            href = await link.get_attribute("href", timeout=3000)
            return href.split("?")[0] if href else None
        except Exception:
            return None

    async def _get_rating(self, page: Page) -> Optional[float]:
        try:
            el = page.locator('div.F7nice span[aria-hidden="true"]').first
            text = await el.inner_text(timeout=3000)
            return float(text.replace(",", "."))
        except Exception:
            return None

    async def _get_review_count(self, page: Page) -> Optional[int]:
        try:
            el = page.locator('div.F7nice span[aria-label*="reseña"]').first
            text = await el.get_attribute("aria-label", timeout=3000)
            nums = re.findall(r"\d+", text.replace(".", "").replace(",", ""))
            return int(nums[0]) if nums else None
        except Exception:
            return None

    async def _dismiss_cookies(self, page: Page) -> None:
        try:
            btn = page.locator('button:has-text("Aceptar todo"), button:has-text("Accept all")').first
            if await btn.count() > 0:
                await btn.click(timeout=3000)
                await page.wait_for_timeout(500)
        except Exception:
            pass


# ─────────────────────────────────────────────
#  SALIDA
# ─────────────────────────────────────────────
def save_results(leads: list[Lead], path: str = "leads_raw.json") -> None:
    data = [asdict(l) for l in leads]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"💾 {len(data)} leads guardados en {path}")


def print_summary(leads: list[Lead]) -> None:
    print(f"\n{'─'*50}")
    print(f"TOTAL LEADS: {len(leads)}")
    no_web   = [l for l in leads if not l.website]
    bad_web  = [l for l in leads if l.website and any(
        x in (l.website or "") for x in ["wix.com", "facebook.com", "instagram.com", "linktr.ee"]
    )]
    print(f"  Sin web:       {len(no_web)}  ← alta prioridad")
    print(f"  Web genérica:  {len(bad_web)}  ← media prioridad")
    print(f"  Con teléfono:  {sum(1 for l in leads if l.phone)}")
    print(f"{'─'*50}\n")


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
async def main():
    scraper = GoogleMapsScraper(headless=HEADLESS)
    leads   = await scraper.scrape_all(SEARCH_CONFIGS)
    print_summary(leads)
    save_results(leads)

# ── SEARCH CONFIG dinámica ─────────────────────────────────────
CONFIG_FILE = "search_config.json"

def load_search_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    # default si no existe
    return [
        {"query": "restaurantes",      "zone": "Hialeah, Florida"},
        {"query": "peluquerías",       "zone": "Miami, Florida"},
        {"query": "talleres mecánica", "zone": "Doral, Florida"},
        {"query": "clínicas dentales", "zone": "Coral Gables, Florida"},
    ]

def save_search_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ── INSTAGRAM SCRAPER ─────────────────────────────────────────
async def scrape_instagram(queries: list) -> list:
    """Busca negocios en Instagram via hashtags y ubicación."""
    leads = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS)
        context = await browser._build_context(browser) if False else await pw.chromium.launch(headless=HEADLESS).new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        for cfg in queries:
            hashtag = cfg["query"].replace(" ", "")
            url = f"https://www.instagram.com/explore/tags/{hashtag}/?hl=es"
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(3000)
                # extraer links de posts
                links = await page.eval_on_selector_all(
                    'a[href*="/p/"]',
                    "els => [...new Set(els.map(e => e.href))].slice(0, 20)"
                )
                for link in links:
                    post_page = await context.new_page()
                    try:
                        await post_page.goto(link, wait_until="domcontentloaded", timeout=15_000)
                        await post_page.wait_for_timeout(1500)
                        # extraer username del post
                        username = await post_page.eval_on_selector(
                            'a[href*="/"][role="link"]',
                            "el => el.href"
                        )
                        if username:
                            profile_url = username if "instagram.com/" in username else None
                            if profile_url:
                                leads.append({
                                    "name":     profile_url.split("instagram.com/")[-1].strip("/"),
                                    "website":  profile_url,
                                    "phone":    None,
                                    "address":  None,
                                    "rating":   None,
                                    "reviews":  None,
                                    "category": cfg["query"],
                                    "zone":     cfg.get("zone", "Instagram"),
                                    "query":    cfg["query"],
                                    "maps_url": profile_url,
                                    "source":   "instagram"
                                })
                    except: pass
                    finally: await post_page.close()
            except Exception as e:
                log.error(f"Instagram error: {e}")
            finally:
                await page.close()
        await context.close()
    return leads

if __name__ == "__main__":
    asyncio.run(main())