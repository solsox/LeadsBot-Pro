# leadfinder.py  →  Buscador unificado (Google Maps + correos + tamaño de empresa + LinkedIn público)
# ─────────────────────────────────────────────────────────────────────────────
#  Código propio, sin Apify. Un solo flujo:
#    1) Google Maps (scraper.py) encuentra negocios por categoría + ciudades
#    2) Se entra al sitio web de cada uno y se extraen: correos públicos, teléfonos, redes
#    3) Se estima el tamaño (nº de empleados) desde: página pública de LinkedIn → texto del sitio
#    4) Se aplican los filtros (estilo Apify) y se guarda una lista lista para campañas
#
#  LinkedIn: SOLO la página pública de la empresa, sin iniciar sesión, sin cuentas falsas,
#  a ritmo lento. Si LinkedIn muestra el muro de login se detiene y marca "sin dato".
#  Solo se recolectan datos de contacto de empresa publicados por ellas mismas.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import html
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import sources as S            # reutiliza jobs, _say/_set, _finalize, EMAIL_RE, etc.

router = APIRouter()

UA = S.BROWSER_UA
PAGES = ["", "/contacto", "/contact", "/contactenos", "/nosotros", "/quienes-somos", "/about"]
PHONE_RE = re.compile(r"(?:\+?57[\s\-]?)?(3\d{2}[\s\-]?\d{3}[\s\-]?\d{4})\b")
SOCIAL_RE = {
    "linkedin":  re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/company/[A-Za-z0-9\-_%]+", re.I),
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.]+", re.I),
    "facebook":  re.compile(r"https?://(?:www\.)?facebook\.com/[A-Za-z0-9_.\-]+", re.I),
}
# Rangos estándar de LinkedIn → (min, max)
LI_RANGES = {"1": (1, 1), "2-10": (2, 10), "11-50": (11, 50), "51-200": (51, 200), "201-500": (201, 500),
             "501-1000": (501, 1000), "1001-5000": (1001, 5000), "5001-10000": (5001, 10000), "10001+": (10001, None)}
CHAINS = re.compile(r"\b(mcdonald|kfc|subway|burger king|domino|papa john|frisby|crepes|starbucks|juan valdez|oxxo|d1|ara|éxito|exito|olimpica|alkosto)\b", re.I)


# ═════════════════════════════════════════════════════════════════════════════
#  Parámetros (estilo Apify)
# ═════════════════════════════════════════════════════════════════════════════
class FinderIn(BaseModel):
    categories: List[str] = Field(..., description="Ej: ['restaurantes','salones de belleza']")
    locations: List[str] = Field(default_factory=lambda: ["Cali, Colombia"])
    max_results: int = Field(60, ge=1, le=500)                 # tope de negocios a revisar
    # filtros de tamaño
    employees_min: Optional[int] = None
    employees_max: Optional[int] = None
    include_unknown_size: bool = True                          # ¿dejar pasar los que no tienen dato de tamaño?
    # filtros de calidad
    min_rating: Optional[float] = None
    min_reviews: Optional[int] = None
    max_reviews: Optional[int] = None                          # útil para hallar negocios pequeños
    require_website: bool = True
    require_email: bool = True
    require_phone: bool = False
    exclude_chains: bool = True
    # enriquecimiento
    use_linkedin_public: bool = True                           # página pública, sin login
    # salida
    list_name: Optional[str] = None
    mode: Optional[str] = None                                 # modo de búsqueda de Maps (corto/medio/largo…)
    lang: str = "es"


# ═════════════════════════════════════════════════════════════════════════════
#  Parsers puros (testeables sin red)
# ═════════════════════════════════════════════════════════════════════════════
def parse_size_text(text: str) -> Optional[Tuple[int, Optional[int], str]]:
    """Busca frases tipo '25 empleados', 'equipo de 12 personas', '11-50 employees'. → (min, max, evidencia)"""
    t = html.unescape(re.sub(r"\s+", " ", text or ""))
    m = re.search(r"\b(1|2-10|11-50|51-200|201-500|501-1000|1001-5000|5001-10000|10001\+)\s+(?:employees|empleados)\b", t, re.I)
    if m:
        lo, hi = LI_RANGES[m.group(1)]
        return lo, hi, m.group(0)
    m = re.search(r"\b(?:m[aá]s de|\+)?\s*(\d{1,4})\s+(?:empleados|colaboradores|trabajadores|personas en (?:nuestro )?equipo|profesionales|employees|team members)\b", t, re.I)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 50000:
            return n, n, m.group(0).strip()
    m = re.search(r"\bequipo de (\d{1,4}) (?:personas|profesionales|colaboradores)\b", t, re.I)
    if m:
        n = int(m.group(1))
        return n, n, m.group(0)
    return None


def parse_linkedin_public(page_html: str) -> dict:
    """Extrae tamaño de la página pública de empresa (JSON-LD / meta / texto)."""
    out: dict = {}
    for blob in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page_html, re.S):
        try:
            data = json.loads(blob)
        except Exception:
            continue
        for d in data if isinstance(data, list) else [data]:
            if isinstance(d, dict) and d.get("@type") == "Organization":
                n = (d.get("numberOfEmployees") or {}).get("value") if isinstance(d.get("numberOfEmployees"), dict) else d.get("numberOfEmployees")
                if n:
                    try:
                        out["employees"] = int(n)
                    except Exception:
                        pass
                out["name"] = d.get("name")
                out["website"] = d.get("sameAs") or d.get("url")
    sz = parse_size_text(page_html)
    if sz:
        out.setdefault("range", (sz[0], sz[1]))
        out["evidence"] = sz[2]
    return out


def extract_contacts(text: str, host: str) -> dict:
    text = html.unescape(text)
    emails: List[str] = []
    for m in re.findall(r"mailto:([^\"'?>\s]+)", text) + S.EMAIL_RE.findall(text):
        e = m.strip().lower().rstrip(".")
        if S.EMAIL_RE.fullmatch(e) and not S.JUNK_EMAIL.search(e) and e not in emails:
            emails.append(e)
    emails.sort(key=lambda e: (host not in e, not re.match(r"(gerencia|info|contacto|ventas|hola|comercial)", e)))
    phones = []
    for m in PHONE_RE.findall(text):
        p = "57" + re.sub(r"\D", "", m)
        if p not in phones:
            phones.append(p)
    socials = {k: (rx.search(text).group(0) if rx.search(text) else "") for k, rx in SOCIAL_RE.items()}
    return {"emails": emails[:3], "phones": phones[:2], "socials": socials}


def passes(row: dict, p: FinderIn) -> Tuple[bool, str]:
    if p.exclude_chains and CHAINS.search(row["name"]):
        return False, "cadena"
    if p.min_rating is not None and (row.get("rating") or 0) < p.min_rating:
        return False, "rating"
    if p.min_reviews is not None and (row.get("reviews") or 0) < p.min_reviews:
        return False, "pocas reseñas"
    if p.max_reviews is not None and (row.get("reviews") or 0) > p.max_reviews:
        return False, "muchas reseñas"
    if p.require_email and not row.get("email"):
        return False, "sin email"
    if p.require_phone and not row.get("phone"):
        return False, "sin teléfono"
    lo, hi = row.get("employees_min"), row.get("employees_max")
    if p.employees_min is not None or p.employees_max is not None:
        if lo is None:
            return (True, "") if p.include_unknown_size else (False, "tamaño desconocido")
        hi_eff = hi if hi is not None else 10**9
        if p.employees_min is not None and hi_eff < p.employees_min:
            return False, "muy pequeña"
        if p.employees_max is not None and lo > p.employees_max:
            return False, "muy grande"
    return True, ""


# ═════════════════════════════════════════════════════════════════════════════
#  Enriquecimiento (red)
# ═════════════════════════════════════════════════════════════════════════════
def enrich_site(website: str, cl: httpx.Client) -> dict:
    base = website if website.startswith("http") else "https://" + website
    host = urlparse(base).netloc.replace("www.", "")
    blob = ""
    for path in PAGES:
        try:
            r = cl.get(urljoin(base, path) if path else base, timeout=12, follow_redirects=True)
        except Exception:
            continue
        if r.status_code < 400 and "text" in r.headers.get("content-type", ""):
            blob += "\n" + r.text
        if len(blob) > 600_000:
            break
    c = extract_contacts(blob, host)
    sz = parse_size_text(re.sub(r"<[^>]+>", " ", blob))
    c["size"] = sz
    return c


class LinkedInBlocked(Exception):
    pass


def linkedin_public_size(url: str, cl: httpx.Client) -> Optional[dict]:
    """Lee SOLO la página pública. Sin login. Si aparece el muro → LinkedInBlocked (se detiene todo)."""
    r = cl.get(url, timeout=15, follow_redirects=True, headers={"User-Agent": UA, "Accept-Language": "es-CO,es;q=0.9"})
    if r.status_code in (999, 429) or "authwall" in str(r.url) or "/login" in str(r.url):
        raise LinkedInBlocked("LinkedIn mostró el muro de login; dejo de consultar LinkedIn.")
    if r.status_code != 200:
        return None
    return parse_linkedin_public(r.text) or None


# ═════════════════════════════════════════════════════════════════════════════
#  Pipeline
# ═════════════════════════════════════════════════════════════════════════════
def run_finder(job: dict, p: FinderIn) -> None:
    try:
        from scraper import GoogleMapsScraper
        cfgs = [{"query": c, "zone": z} for c in p.categories for z in p.locations]
        S._say(job, f"Google Maps: {len(cfgs)} búsquedas…")
        S._set(job, progress="Buscando en Google Maps…")
        leads = asyncio.run((GoogleMapsScraper(headless=True, mode=p.mode) if p.mode else GoogleMapsScraper(headless=True)).scrape_all(cfgs))
        leads = [l for l in leads if (l.website or not p.require_website)][: p.max_results]
        S._say(job, f"{len(leads)} negocios para revisar.")
        S._set(job, total=len(leads), checked=0)

        li_blocked = threading.Event()
        li_lock = threading.Lock()
        rejected: Dict[str, int] = {}

        def work(l):
            if job["cancel"]:
                return
            row = {"name": l.name, "website": l.website or "", "category": l.category or l.query, "zone": l.zone,
                   "rating": l.rating, "reviews": l.reviews, "phone": S.C.norm_phone(l.phone) if l.phone else "",
                   "address": l.address, "maps_url": l.maps_url, "email": "", "source": "maps+web",
                   "employees_min": None, "employees_max": None, "size_source": "", "extra": {}}
            try:
                with httpx.Client(headers={"User-Agent": UA}) as cl:
                    if l.website:
                        c = enrich_site(l.website, cl)
                        if c["emails"]:
                            row["email"] = c["emails"][0]
                        if not row["phone"] and c["phones"]:
                            row["phone"] = c["phones"][0]
                        row["extra"].update(c["socials"])
                        if c["size"]:
                            row.update(employees_min=c["size"][0], employees_max=c["size"][1], size_source="sitio web")
                        li_url = c["socials"].get("linkedin")
                        if p.use_linkedin_public and li_url and not li_blocked.is_set():
                            with li_lock:                      # 1 consulta a la vez + pausa = ritmo lento
                                try:
                                    info = linkedin_public_size(li_url, cl)
                                    time.sleep(4)
                                except LinkedInBlocked as e:
                                    li_blocked.set()
                                    S._say(job, str(e))
                                    info = None
                            if info and (info.get("employees") or info.get("range")):
                                lo, hi = (info["employees"],) * 2 if info.get("employees") else info["range"]
                                row.update(employees_min=lo, employees_max=hi, size_source="LinkedIn público")
            except Exception:
                pass
            ok, why = passes(row, p)
            with S._jobs_lock:
                job["checked"] += 1
                if not ok:
                    rejected[why] = rejected.get(why, 0) + 1
            if ok and row["email"] and S._add_result(job, row):
                sz = f" · {row['employees_min']}-{row['employees_max']} emp." if row["employees_min"] else ""
                S._say(job, f"✓ {row['name']} → {row['email']}{sz}")
            S._set(job, progress=f"Revisando… {job['checked']}/{len(leads)} · {job['emails']} válidos")

        with ThreadPoolExecutor(max_workers=5) as ex:
            list(ex.map(work, leads))
        if rejected:
            S._say(job, "Descartados: " + ", ".join(f"{k} {v}" for k, v in sorted(rejected.items(), key=lambda x: -x[1])))
        S._finalize(job, p.list_name or f"Leads · {', '.join(p.categories[:2])} · {', '.join(p.locations[:2])}")
    except Exception as ex:
        S._set(job, status="error", error=str(ex), progress="Falló")
        S._say(job, f"✗ {ex}")


@router.post("/finder/run", tags=["finder"])
def finder_run(p: FinderIn):
    if not [c for c in p.categories if c.strip()]:
        raise HTTPException(400, "Escribe al menos una categoría")
    job = S._new_job("finder", f"Buscador · {', '.join(p.categories[:2])}")
    threading.Thread(target=run_finder, args=(job, p), daemon=True).start()
    return S._public(job, True)
