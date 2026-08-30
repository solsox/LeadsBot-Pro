from __future__ import annotations
# scraper.py
import asyncio
import json
import os
import re
import logging
import time
from urllib.parse import urlsplit, urlunsplit
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

    # =========================
    # COMIDA Y RESTAURANTES
    # =========================
    "restaurante": [
        "restaurante",
        "comida rápida",
        "pizzería",
        "asadero",
        "comida colombiana",
        "comida típica",
        "marisquería",
        "sushi",
        "comida japonesa",
        "comida mexicana",
        "comida italiana",
        "hamburguesería",
        "parrilla",
        "steakhouse",
        "pollería",
        "restaurante familiar",
        "restaurante gourmet",
        "restaurante saludable",
        "restaurante vegano",
        "restaurante vegetariano",
        "comida árabe",
        "comida china",
        "comida peruana",
        "comida internacional",
    ],

    "cafetería": [
        "cafetería",
        "coffee shop",
        "café",
        "café especial",
        "café artesanal",
        "coffee house",
        "café restaurante",
        "brunch",
        "café gourmet",
    ],

    "panadería": [
        "panadería",
        "pastelería",
        "repostería",
        "pan artesanal",
        "panadería artesanal",
        "dulcería",
        "confitería",
        "boulangerie",
    ],

    "heladería": [
        "heladería",
        "gelatería",
        "helados",
        "paletas",
        "paletería",
        "postres",
        "postres artesanales",
        "crepería",
        "waffles",
        "churros",
    ],

    # =========================
    # BELLEZA
    # =========================
    "peluquería": [
        "peluquería",
        "barbería",
        "barber shop",
        "salón de belleza",
        "salón de peluquería",
        "estilista",
        "peluquería masculina",
        "peluquería femenina",
        "hair salon",
        "colorista",
        "estudio de cabello",
    ],

    "estética": [
        "estética",
        "centro de estética",
        "spa",
        "spa urbano",
        "estética facial",
        "estética corporal",
        "medicina estética",
        "tratamientos faciales",
        "tratamientos corporales",
        "depilación",
        "depilación láser",
        "microblading",
        "cejas",
        "pestañas",
        "lash studio",
        "nail salon",
        "manicure",
        "pedicure",
        "uñas",
    ],

    # =========================
    # AUTOMOTRIZ
    # =========================
    "taller": [
        "taller mecánica",
        "taller automotriz",
        "mecánico automotriz",
        "taller automóviles",
        "servicio automotriz",
        "mecánica rápida",
        "mecánica especializada",
        "diagnóstico automotriz",
        "electricidad automotriz",
        "electromecánica",
        "alineación y balanceo",
        "centro de diagnóstico",
        "latonería",
        "pintura automotriz",
        "detailing",
        "lavado de autos",
        "car wash",
        "lubricentro",
        "llantas",
        "servicio de motos",
        "taller de motos",
        "mecánica de motos",
    ],

    "concesionario": [
        "concesionario",
        "venta de carros",
        "venta de vehículos",
        "autos usados",
        "vehículos usados",
        "carros usados",
        "compra y venta de carros",
        "motos",
        "venta de motos",
        "concesionario de motos",
    ],

    # =========================
    # SALUD
    # =========================
    "clínica": [
        "clínica",
        "clínica dental",
        "odontólogo",
        "dentista",
        "consultorio odontológico",
        "odontología",
        "ortodoncia",
        "implantes dentales",
        "diseño de sonrisa",
        "endodoncia",
        "periodoncia",
        "odontopediatría",
    ],

    "salud": [
        "consultorio médico",
        "centro médico",
        "médico especialista",
        "fisioterapia",
        "terapia física",
        "psicología",
        "nutricionista",
        "nutrición",
        "dermatología",
        "oftalmología",
        "ginecología",
        "pediatría",
        "cardiología",
        "cirugía plástica",
        "medicina deportiva",
        "medicina alternativa",
    ],

    # =========================
    # FITNESS Y DEPORTE
    # =========================
    "gimnasio": [
        "gimnasio",
        "gym",
        "crossfit",
        "yoga",
        "pilates",
        "boxeo",
        "artes marciales",
        "muay thai",
        "jiu jitsu",
        "entrenamiento funcional",
        "personal trainer",
        "entrenador personal",
        "fitness",
        "centro deportivo",
        "academia deportiva",
        "estudio fitness",
        "spinning",
        "calistenia",
        "danza",
        "escuela de fútbol",
    ],

    # =========================
    # HOGAR Y CONSTRUCCIÓN
    # =========================
    "construcción": [
        "constructora",
        "empresa constructora",
        "construcción",
        "obras civiles",
        "ingeniería civil",
        "arquitectura",
        "arquitecto",
        "diseño arquitectónico",
        "remodelaciones",
        "remodelación de casas",
        "interiorismo",
        "diseño de interiores",
        "carpintería",
        "muebles a medida",
        "cocinas integrales",
        "vidriería",
        "aluminio",
        "ferretería",
        "materiales de construcción",
    ],

    "hogar": [
        "decoración",
        "decoración de interiores",
        "muebles",
        "mueblería",
        "tienda de muebles",
        "colchones",
        "cortinas",
        "persianas",
        "iluminación",
        "lámparas",
        "jardinería",
        "paisajismo",
        "piscinas",
        "limpieza de casas",
        "servicios de limpieza",
    ],

    # =========================
    # MODA Y RETAIL
    # =========================
    "ropa": [
        "tienda de ropa",
        "boutique",
        "moda",
        "ropa femenina",
        "ropa masculina",
        "ropa deportiva",
        "ropa infantil",
        "ropa para mujer",
        "ropa para hombre",
        "streetwear",
        "moda urbana",
        "tienda de vestidos",
        "vestidos de fiesta",
        "ropa interior",
    ],

    "accesorios": [
        "joyería",
        "bisutería",
        "relojería",
        "tienda de accesorios",
        "bolsos",
        "carteras",
        "zapatería",
        "calzado",
        "tenis",
        "óptica",
        "gafas",
    ],

    # =========================
    # SERVICIOS PROFESIONALES
    # =========================
    "profesional": [
        "abogado",
        "bufete de abogados",
        "firma de abogados",
        "contador",
        "contabilidad",
        "consultoría",
        "consultor empresarial",
        "asesoría empresarial",
        "agencia de marketing",
        "agencia de publicidad",
        "diseño gráfico",
        "fotografía",
        "productora audiovisual",
        "agencia inmobiliaria",
        "inmobiliaria",
        "corredor de seguros",
        "seguros",
    ],

    # =========================
    # EDUCACIÓN
    # =========================
    "educación": [
        "academia",
        "instituto",
        "escuela",
        "colegio",
        "universidad",
        "educación",
        "clases particulares",
        "tutorías",
        "academia de idiomas",
        "inglés",
        "escuela de música",
        "academia de baile",
        "academia de arte",
        "curso",
        "cursos",
        "capacitación",
        "formación profesional",
    ],

    # =========================
    # TURISMO Y HOSPITALIDAD
    # =========================
    "turismo": [
        "hotel",
        "hostal",
        "hostel",
        "apartahotel",
        "alojamiento",
        "casa de huéspedes",
        "glamping",
        "finca turística",
        "agencia de viajes",
        "operador turístico",
        "tours",
        "excursiones",
        "guía turístico",
        "turismo",
    ],

    # =========================
    # EVENTOS
    # =========================
    "eventos": [
        "organización de eventos",
        "event planner",
        "wedding planner",
        "bodas",
        "decoración de eventos",
        "salón de eventos",
        "eventos empresariales",
        "fotografía de bodas",
        "fotógrafo",
        "videógrafo",
        "DJ",
        "sonido para eventos",
        "alquiler de eventos",
        "fiestas",
    ],

    # =========================
    # MASCOTAS
    # =========================
    "mascotas": [
        "veterinaria",
        "clínica veterinaria",
        "pet shop",
        "tienda de mascotas",
        "peluquería canina",
        "grooming",
        "guardería canina",
        "hotel para mascotas",
        "adiestramiento canino",
        "entrenamiento de perros",
        "accesorios para mascotas",
    ],

    # =========================
    # TECNOLOGÍA
    # =========================
    "tecnología": [
        "tienda de tecnología",
        "tienda de computadores",
        "computadores",
        "celulares",
        "reparación de computadores",
        "servicio técnico",
        "reparación de celulares",
        "electrónica",
        "electrodomésticos",
        "sistemas",
        "empresa de tecnología",
        "software",
        "desarrollo de software",
    ],

    # =========================
    # COMERCIO / E-COMMERCE
    # =========================
    "tienda": [
        "tienda",
        "local comercial",
        "comercio",
        "tienda especializada",
        "distribuidor",
        "distribuidora",
        "mayorista",
        "minorista",
        "importadora",
        "exportadora",
        "showroom",
    ],

    # =========================
    # SERVICIOS PARA EMPRESAS
    # =========================
    "empresa": [
        "empresa",
        "empresa de servicios",
        "servicios empresariales",
        "consultoría empresarial",
        "outsourcing",
        "BPO",
        "recursos humanos",
        "reclutamiento",
        "selección de personal",
        "logística",
        "transporte",
        "mensajería",
        "seguridad privada",
        "aseo empresarial",
    ],
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

SCROLL_PAUSE_MS       = 350  # pausa base entre scrolls; el scroll usa espera adaptativa
HEADLESS              = True  # False para ver el browser en tiempo real

QUERY_CONCURRENCY     = 4    # nº de búsquedas (query+zona) corriendo en paralelo
DETAIL_CONCURRENCY    = 8    # nº de fichas de negocio abiertas en paralelo (pool de páginas)
MAX_RESULTS_PER_QUERY = 30   # tope por defecto (fallback si no se especifica modo)

# ─────────────────────────────────────────────
#  MODOS DE BÚSQUEDA — cuánto pedir por query, para no scrollear/extraer
#  siempre el máximo si no hace falta. El total real de leads depende de
#  cuántas queries expandidas termines corriendo (ver QUERY_EXPANSIONS),
#  así que los rangos son aproximados para una config típica de 4 búsquedas.
# ─────────────────────────────────────────────
SEARCH_MODES = {
    "corto": {"label": "Corto (~30-50 leads totales, más rápido)",        "max_results_per_query": 12},
    "medio": {"label": "Medio (~100-200 leads totales)",                   "max_results_per_query": 45},
    "largo":  {"label": "Largo / máximo (prioriza cobertura sobre tiempo)", "max_results_per_query": 200},
}
DEFAULT_SEARCH_MODE = "medio"

def resolve_max_results(mode: str) -> int:
    cfg = SEARCH_MODES.get(mode, SEARCH_MODES[DEFAULT_SEARCH_MODE])
    return cfg["max_results_per_query"]

# Benchmark: permite medir si una modificación realmente mejora leads/minuto.
BENCHMARK              = True
BLOCK_HEAVY_RESOURCES   = True
SCROLL_STABLE_ROUNDS    = 2
SCROLL_POLL_MS           = 100
SCROLL_MAX_WAIT_MS       = 900

 
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

    def __init__(self, headless: bool = HEADLESS, mode: str = DEFAULT_SEARCH_MODE):
        self.headless = headless
        self.mode = mode if mode in SEARCH_MODES else DEFAULT_SEARCH_MODE
        self.max_results_per_query = resolve_max_results(self.mode)
        log.info(
            f"🎚 Modo de búsqueda: {SEARCH_MODES[self.mode]['label']} "
            f"(máx {self.max_results_per_query} fichas/query)"
        )

    async def scrape_all(self, configs: list) -> list:
        # AÑADE esta línea al inicio:
        configs = expand_queries(configs)
        log.info(f"📋 Búsquedas expandidas: {len(configs)} queries totales")

        # Dedup global: si dos queries expandidas (ej. "restaurantes" y
        # "comida rápida") devuelven el mismo negocio, solo se extrae una vez.
        seen_urls: set[str] = set()

        """Ejecuta todas las búsquedas definidas en SEARCH_CONFIGS, en paralelo."""
        run_started = time.perf_counter()
        all_leads: list = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            page_pool: Optional[asyncio.Queue] = None
            try:
                context = await self._build_context(browser)

                # Pool de páginas reutilizables para extraer fichas de detalle.
                # Se comparte entre TODAS las queries (paralelas o no), así el
                # tamaño del pool es el único límite real de fichas simultáneas.
                page_pool = await self._build_page_pool(context, DETAIL_CONCURRENCY)

                query_sem = asyncio.Semaphore(QUERY_CONCURRENCY)

                async def run_query(cfg: dict) -> list:
                    async with query_sem:
                        query = cfg["query"]
                        zone  = cfg["zone"]
                        log.info(f"🔍 Buscando '{query}' en '{zone}'")
                        try:
                            leads = await self._scrape_query(context, query, zone, seen_urls, page_pool)
                            log.info(f"✅ {len(leads)} leads nuevos para '{query}' en '{zone}'")
                            return leads
                        except Exception as e:
                            log.error(f"❌ Error en '{query}' / '{zone}': {e}")
                            return []

                results = await asyncio.gather(*[run_query(cfg) for cfg in configs])
                all_leads = [lead for batch in results for lead in batch]
            finally:
                # se ejecuta también si algo falló antes (ej. error creando
                # el context o el pool) — nunca deja el browser/páginas abiertas
                if page_pool is not None:
                    while not page_pool.empty():
                        p = await page_pool.get()
                        try:
                            await p.close()
                        except Exception:
                            pass
                try:
                    await browser.close()
                except Exception:
                    pass

        elapsed = time.perf_counter() - run_started
        if BENCHMARK:
            leads_per_min = (len(all_leads) / elapsed * 60) if elapsed else 0
            log.info(
                "📊 BENCHMARK | queries=%d | leads=%d | tiempo=%.2fs | leads/min=%.1f",
                len(configs), len(all_leads), elapsed, leads_per_min
            )

        return all_leads

    # ── pool de páginas reutilizables para fichas de detalle ───────────────
    async def _build_page_pool(self, context: BrowserContext, size: int) -> asyncio.Queue:
        pool: asyncio.Queue = asyncio.Queue()
        for _ in range(size):
            page = await context.new_page()
            pool.put_nowait(page)
        return pool

    # ── contexto con headers humanos ──────────────────────────────────────
    async def _build_context(self, browser) -> BrowserContext:
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-ES",
            timezone_id="America/New_York",
        )

        if BLOCK_HEAVY_RESOURCES:
            async def route_handler(route):
                resource_type = route.request.resource_type
                if resource_type in {"image", "media", "font"}:
                    await route.abort()
                else:
                    await route.continue_()

            await context.route("**/*", route_handler)

        return context

    # ── búsqueda individual ───────────────────────────────────────────────
    async def _scrape_query(
        self,
        context: BrowserContext,
        query: str,
        zone: str,
        seen_urls: set[str],
        page_pool: asyncio.Queue,
    ) -> list[Lead]:

        page = await context.new_page()
        search_term = f"{query} en {zone}"
        url = f"https://www.google.com/maps/search/?api=1&query={search_term.replace(' ', '+')}"

        query_started = time.perf_counter()
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        # Movimiento mínimo; evitamos una espera fija larga.
        await page.mouse.move(400, 350)

        # aceptar cookies si aparece el banner
        await self._dismiss_cookies(page)

        # scroll del panel de resultados hasta el tope del modo elegido,
        # o hasta que deje de haber fichas nuevas (lo que ocurra primero)
        await self._scroll_results(page, self.max_results_per_query)

        # extraer URLs de los negocios listados
        place_links = await self._collect_place_links(page)
        place_links = list(dict.fromkeys(place_links))[:self.max_results_per_query]
        await page.close()

        # dedup global: la clave (place ID o path normalizado) decide si ya
        # se vio el negocio, pero la URL REAL se conserva intacta en
        # new_links — es la que se usa después para navegar en _extract_place.
        new_links = []
        skipped = 0
        for link in place_links:
            key = self._normalize_maps_url(link)
            if key not in seen_urls:
                seen_urls.add(key)
                new_links.append(link)
            else:
                skipped += 1
        log.info(f"  → {len(place_links)} fichas encontradas, {skipped} duplicadas (omitidas)")

        async def fetch(link: str) -> Optional[Lead]:
            detail_page = await page_pool.get()
            try:
                return await self._extract_place(detail_page, link, zone, query)
            except Exception as e:
                log.warning(f"  ⚠ skip ficha ({e})")
                return None
            finally:
                await page_pool.put(detail_page)

        results = await asyncio.gather(*[fetch(l) for l in new_links])
        elapsed = time.perf_counter() - query_started
        valid = [r for r in results if r is not None]
        log.info(
            "⏱ '%s' | fichas=%d | leads=%d | tiempo=%.2fs",
            query, len(new_links), len(valid), elapsed
        )
        return valid

    # ── scroll del panel izquierdo ────────────────────────────────────────
    async def _scroll_results(self, page: Page, max_results: int = MAX_RESULTS_PER_QUERY) -> None:
        """Scroll adaptativo: corta por máximo, fin de resultados o falta de novedades."""
        panel_selector = 'div[role="feed"]'
        try:
            await page.wait_for_selector(panel_selector, timeout=8000)
        except Exception:
            log.warning("  ⚠ Panel de resultados no encontrado, continuando...")
            return

        last_count = 0
        stable_rounds = 0

        for i in range(50):
            before = await page.eval_on_selector_all(
                'a[href*="/maps/place/"]',
                "els => new Set(els.map(e => e.href)).size"
            )

            await page.eval_on_selector(
                panel_selector,
                "el => el.scrollBy(0, 900)"
            )

            # Espera adaptativa: sale en cuanto aparecen nuevos links.
            deadline = time.perf_counter() + (SCROLL_MAX_WAIT_MS / 1000)
            count = before
            while time.perf_counter() < deadline:
                await page.wait_for_timeout(SCROLL_POLL_MS)
                count = await page.eval_on_selector_all(
                    'a[href*="/maps/place/"]',
                    "els => new Set(els.map(e => e.href)).size"
                )
                if count > before:
                    break

            if count >= max_results:
                log.debug(f"  → alcanzado tope de {max_results} resultados tras {i+1} scrolls")
                break

            if count == last_count:
                stable_rounds += 1
                if stable_rounds >= SCROLL_STABLE_ROUNDS:
                    log.debug(f"  → sin fichas nuevas tras {i+1} scrolls, cortando")
                    break
            else:
                stable_rounds = 0

            last_count = count

            end_msg = page.locator('span:has-text("Has llegado al final")')
            if await end_msg.count() > 0:
                log.debug(f"  → fin de resultados tras {i+1} scrolls")
                break

    @staticmethod
    def _normalize_maps_url(url: str) -> str:
        """Clave estable para dedup. El path de un link de Maps suele traer
        @lat,lng,zoom, que puede variar entre apariciones del MISMO negocio
        en queries distintas — normalizar solo query/fragment no basta.
        Se intenta extraer el place ID de Google (patrón !1s0x...:0x...
        dentro del segmento 'data='), que es estable. Si no aparece, se cae
        al path sin query/fragment como respaldo."""
        match = re.search(r"!1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)", url)
        if match:
            return match.group(1)
        try:
            parts = urlsplit(url)
            return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
        except Exception:
            return url

    # ── recopilar links de fichas ─────────────────────────────────────────
    async def _collect_place_links(self, page: Page) -> list[str]:
        links = await page.eval_on_selector_all(
            'a[href*="/maps/place/"]',
            "els => [...new Set(els.map(e => e.href))]"
        )
        return [l for l in links if "/maps/place/" in l]

    # ── extraer datos de una ficha ────────────────────────────────────────
    async def _extract_place(
        self, page: Page, url: str, zone: str, query: str
    ) -> Optional[Lead]:
        # `page` viene del pool compartido (ver page_pool) y se reutiliza
        # entre fichas — ya no se crea/cierra una página por negocio.
        await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        try:
            # espera a que aparezca el nombre en vez de un timeout fijo
            await page.wait_for_selector(
                'h1.DUwDvf, h1[class*="fontHeadlineLarge"]', timeout=5000
            )
        except Exception:
            pass  # si no aparece en 5s, igual intentamos leer lo que haya

        # Los campos son independientes: se leen en paralelo para evitar
        # una cadena de awaits secuenciales de hasta varios segundos.
        (
            name,
            address,
            phone,
            website,
            rating,
            reviews,
            category,
        ) = await asyncio.gather(
            self._get_text(page, 'h1.DUwDvf, h1[class*="fontHeadlineLarge"]'),
            self._get_text(page, '[data-item-id="address"] .Io6YTe, button[data-item-id="address"]'),
            self._get_phone(page),
            self._get_website(page),
            self._get_rating(page),
            self._get_review_count(page),
            self._get_text(page, 'button.DkEaL'),
        )

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
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
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