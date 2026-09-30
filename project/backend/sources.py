# sources.py  →  Scraper de emails (pestaña «Scraper Emails»)
# ─────────────────────────────────────────────────────────────────────────────
#  Fuentes para encontrar negocios/empresas y SACAR SUS EMAILS (para campañas por Gmail):
#    · web       Busca en internet (DuckDuckGo) → entra a cada sitio → extrae correos públicos. Gratis.
#    · linkedin  Empresas de LinkedIn por palabra clave (vía Apify) → encuentra su web → extrae correos.
#    · list      Toma una lista que ya tienes (ej. leads de Google Maps con web) → extrae correos.
#  Los resultados se guardan como lista y aparecen solos en Engage → Lanzar campaña.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import csv
import html
import io
import logging
import os
import re
import threading
import time
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import campaigns as C

log = logging.getLogger("emailscraper")
router = APIRouter()

SETTINGS_FILE = os.path.join("sources_data", "settings.json")
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
LINKEDIN_ACTOR = "data_direct~linkedin-companies-scraper"

JOBS: Dict[str, dict] = {}
_jobs_lock = threading.Lock()


# ═════════════════════════════════════════════════════════════════════════════
#  Ajustes (token de Apify)
# ═════════════════════════════════════════════════════════════════════════════
def _apify_token() -> str:
    return C._read(SETTINGS_FILE, {}).get("apify_token") or os.getenv("APIFY_TOKEN", "")


class SettingsIn(BaseModel):
    apify_token: Optional[str] = None


@router.get("/emails/settings", tags=["emails"])
def get_settings():
    t = _apify_token()
    return {"apify_connected": bool(t), "apify_token_hint": ("…" + t[-4:]) if t else "", "default_actor": LINKEDIN_ACTOR}


@router.put("/emails/settings", tags=["emails"])
def put_settings(body: SettingsIn):
    s = C._read(SETTINGS_FILE, {})
    if body.apify_token is not None:
        s["apify_token"] = body.apify_token.strip()
    C._write(SETTINGS_FILE, s)
    return get_settings()


# ═════════════════════════════════════════════════════════════════════════════
#  Jobs
# ═════════════════════════════════════════════════════════════════════════════
def _new_job(source: str, title: str) -> dict:
    job = {"id": "e_" + uuid.uuid4().hex[:8], "source": source, "title": title, "status": "running",
           "progress": "Iniciando…", "log": [], "results": [], "total": 0, "checked": 0, "emails": 0,
           "list_id": None, "list_name": None, "error": None, "started": time.time(), "cancel": False}
    with _jobs_lock:
        JOBS[job["id"]] = job
        for k in sorted(JOBS, key=lambda x: JOBS[x]["started"])[:-20]:
            JOBS.pop(k, None)
    return job


def _say(job: dict, msg: str) -> None:
    with _jobs_lock:
        job["log"].append(time.strftime("%H:%M:%S ") + msg)
        job["log"] = job["log"][-200:]


def _set(job: dict, **kw) -> None:
    with _jobs_lock:
        job.update(kw)


def _add_result(job: dict, row: dict) -> bool:
    with _jobs_lock:
        if any(r["email"] == row["email"] for r in job["results"]):
            return False
        job["results"].append(row)
        job["emails"] = len(job["results"])
    return True


def _public(job: dict, full: bool) -> dict:
    d = {k: v for k, v in job.items() if k not in ("results", "log", "cancel")}
    d["log_tail"] = job["log"][-80:] if full else []
    if full:
        d["results"] = job["results"][-500:]
    return d


@router.get("/emails/jobs", tags=["emails"])
def list_jobs():
    with _jobs_lock:
        return [_public(j, False) for j in sorted(JOBS.values(), key=lambda j: j["started"], reverse=True)]


@router.get("/emails/jobs/{jid}", tags=["emails"])
def get_job(jid: str):
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, "Trabajo no encontrado")
    with _jobs_lock:
        return _public(j, True)


@router.post("/emails/jobs/{jid}/cancel", tags=["emails"])
def cancel_job(jid: str):
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, "Trabajo no encontrado")
    j["cancel"] = True
    _say(j, "Deteniendo…")
    return {"ok": True}


@router.get("/emails/jobs/{jid}/csv", tags=["emails"])
def job_csv(jid: str):
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, "Trabajo no encontrado")
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["email", "name", "website", "category", "zone", "source"])
    for r in j["results"]:
        w.writerow([r["email"], r["name"], r.get("website", ""), r.get("category", ""), r.get("zone", ""), r.get("source", "")])
    return Response("\ufeff" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=emails_{jid}.csv"})


# ═════════════════════════════════════════════════════════════════════════════
#  Utilidades web
# ═════════════════════════════════════════════════════════════════════════════
def _plain(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")


BLOCKED_DOMAINS = (
    "facebook.", "instagram.", "linkedin.", "twitter.", "x.com", "youtube.", "tiktok.", "pinterest.", "wikipedia.", "reddit.",
    "tripadvisor.", "yelp.", "foursquare.", "booking.", "airbnb.", "despegar.", "rappi.", "ubereats.", "didi", "mercadolibre.",
    "olx.", "amazon.", "ebay.", "google.", "bing.", "waze.", "paginasamarillas.", "cylex.", "infobel.", "civitatis.",
    "lonelyplanet.", "milanuncios.", "glassdoor.", "indeed.", "computrabajo.", "elempleo.", "whatsapp.", "wa.me", "linktr.ee",
    "wixsite.com", "blogspot.", "medium.com", "issuu.", "scribd.", "slideshare.", "apple.com", "duckduckgo.",
)


def _ok_site(url: str) -> bool:
    host = urlparse(url if "//" in url else "https://" + url).netloc.lower()
    return bool(host) and not any(b in host for b in BLOCKED_DOMAINS)


def _root(url: str) -> str:
    p = urlparse(url if "//" in url else "https://" + url)
    return f"{p.scheme or 'https'}://{p.netloc}/"


class SearchBlocked(Exception):
    pass


def ddg_search(client: httpx.Client, q: str, offset: int = 0) -> List[tuple]:
    data = {"q": q, "kl": "co-es"}
    if offset:
        data["s"] = str(offset)
    r = client.post("https://html.duckduckgo.com/html/", data=data, headers={"User-Agent": BROWSER_UA}, timeout=25)
    if r.status_code != 200 or "anomaly" in r.text.lower():
        raise SearchBlocked("El buscador pidió una pausa (demasiadas consultas seguidas).")
    out = []
    for m in re.finditer(r"<a\b([^>]*result__a[^>]*)>(.*?)</a>", r.text, re.S):
        attrs, inner = m.groups()
        h = re.search(r'href="([^"]+)"', attrs)
        if not h:
            continue
        href = html.unescape(h.group(1))
        if "uddg=" in href:
            href = parse_qs(urlparse("https:" + href if href.startswith("//") else href).query).get("uddg", [""])[0]
        if href.startswith("http"):
            out.append((re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", inner))).strip(), href))
    return out


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
JUNK_EMAIL = re.compile(r"(\.(png|jpe?g|gif|svg|webp|css|js|woff2?)$|sentry|wixpress|example\.|domain\.com|tu@|usuario@|name@|correo@|email@|@2x|noreply|no-reply)", re.I)
CONTACT_PATHS = ["", "/contacto", "/contact", "/contactenos", "/contactanos", "/nosotros", "/about", "/quienes-somos"]


def find_emails(website: str, client: httpx.Client) -> List[str]:
    base = website if website.startswith("http") else "https://" + website
    host = urlparse(base).netloc.replace("www.", "")
    found: List[str] = []
    for path in CONTACT_PATHS:
        try:
            r = client.get(urljoin(base, path) if path else base, timeout=12, follow_redirects=True)
        except Exception:
            continue
        if r.status_code >= 400 or "text" not in r.headers.get("content-type", ""):
            continue
        text = html.unescape(r.text)
        for m in re.findall(r"mailto:([^\"'?>\s]+)", text) + EMAIL_RE.findall(text):
            e = m.strip().lower().rstrip(".")
            if EMAIL_RE.fullmatch(e) and not JUNK_EMAIL.search(e) and e not in found:
                found.append(e)
        if found:
            break
    found.sort(key=lambda e: (host not in e, not re.match(r"(info|contacto|ventas|hola|hello|contact|gerencia|comercial)", e)))
    return found[:2]


# ═════════════════════════════════════════════════════════════════════════════
#  Extracción de emails (común a todas las fuentes)
# ═════════════════════════════════════════════════════════════════════════════
def _extract_all(job: dict, cands: List[dict]) -> None:
    """cands: [{name, website, category, zone, source, extra}] → busca emails en paralelo y los publica en vivo."""
    cands = [c for c in cands if c.get("website")]
    _set(job, total=len(cands), checked=0)
    if not cands:
        return
    _say(job, f"Revisando {len(cands)} sitios web…")

    def work(c: dict):
        if job["cancel"]:
            return
        try:
            with httpx.Client(headers={"User-Agent": BROWSER_UA}) as cl:
                em = find_emails(c["website"], cl)
        except Exception:
            em = []
        with _jobs_lock:
            job["checked"] += 1
        if em and _add_result(job, {"email": em[0], "name": c["name"], "website": c["website"], "category": c.get("category", ""),
                                    "zone": c.get("zone", ""), "source": c.get("source", ""), "extra": c.get("extra", {})}):
            _say(job, f"✓ {c['name']} → {em[0]}")
        _set(job, progress=f"Revisando webs… {job['checked']}/{len(cands)} · {job['emails']} emails")

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(work, cands))


def _finalize(job: dict, name: str, save_list: bool = True) -> None:
    if job["cancel"]:
        _say(job, "Detenido por ti.")
    n = job["emails"]
    if save_list and n:
        leads = [{"name": r["name"], "email": r["email"], "website": r.get("website", ""), "category": r.get("category", ""),
                  "zone": r.get("zone", ""), "phone": "", "extra": r.get("extra", {}), "score": None} for r in job["results"]]
        lst = {"id": "i_" + uuid.uuid4().hex[:8], "name": name, "source": "emails", "created_at": C._iso(C._now()), "leads": leads}
        with C._lock:
            lists = C._saved_lists()
            lists.append(lst)
            C._write(C.LISTS_FILE, lists)
        _set(job, list_id=lst["id"], list_name=name)
    _set(job, status="done", progress=f"{n} emails encontrados en {job['checked']} sitios revisados")
    if not n:
        _say(job, "No se encontraron emails. Prueba otra búsqueda o revisa más negocios.")


# ═════════════════════════════════════════════════════════════════════════════
#  Fuente 1: WEB (DuckDuckGo → sitios → emails)
# ═════════════════════════════════════════════════════════════════════════════
def run_web(job: dict, query: str, zone: str, limit: int, name: str) -> None:
    try:
        seen, cands = set(), []
        variants = [f"{query} {zone}", f"{query} {zone} contacto email", f"{query} {zone} correo electrónico", f"{query} {zone} sitio oficial"]
        with httpx.Client() as cl:
            for q in variants:
                for off in (0, 30):
                    if job["cancel"] or len(cands) >= limit:
                        break
                    _set(job, progress=f"Buscando negocios… ({len(cands)} sitios)")
                    try:
                        res = ddg_search(cl, q, off)
                    except SearchBlocked as e:
                        if not cands:
                            raise RuntimeError(str(e) + " Espera unos minutos y reintenta, o usa LinkedIn / Leads que ya tengo.")
                        _say(job, "El buscador pidió pausa; sigo con lo encontrado.")
                        break
                    if not res:
                        break
                    for title, url in res:
                        if not _ok_site(url):
                            continue
                        root = _root(url)
                        host = urlparse(root).netloc.replace("www.", "")
                        if host in seen:
                            continue
                        seen.add(host)
                        cands.append({"name": re.split(r"\s[-–|·:]\s", title)[0][:80] or host, "website": root,
                                      "category": query, "zone": zone, "source": "web"})
                    time.sleep(1.2)
                if len(cands) >= limit:
                    break
        cands = cands[:limit]
        if not cands:
            raise RuntimeError("La búsqueda no devolvió sitios web. Prueba otras palabras.")
        _say(job, f"{len(cands)} sitios candidatos encontrados.")
        _extract_all(job, cands)
        _finalize(job, name or f"Emails · {query} · {zone}".strip(" ·"))
    except Exception as ex:
        _set(job, status="error", error=str(ex), progress="Falló")
        _say(job, f"✗ {ex}")


# ═════════════════════════════════════════════════════════════════════════════
#  Fuente 2: LINKEDIN (Apify) → empresas → web → emails
# ═════════════════════════════════════════════════════════════════════════════
def _apify_companies(job: dict, query: str, zone: str, limit: int, actor: str) -> List[dict]:
    token = _apify_token()
    if not token:
        raise RuntimeError("Falta el token de Apify. Pégalo en el recuadro de esta pestaña.")
    actor = actor.strip().replace("/", "~")
    pages = max(1, min(10, -(-limit // 10)))
    out: List[dict] = []
    for p in range(1, pages + 1):
        if job["cancel"] or len(out) >= limit:
            break
        _set(job, progress=f"Buscando empresas en LinkedIn… página {p}/{pages}")
        r = httpx.post(f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items",
                       params={"token": token, "timeout": 120}, json={"query": f"{query} {zone}".strip(), "page": p}, timeout=150)
        if r.status_code == 401:
            raise RuntimeError("Token de Apify inválido.")
        if r.status_code == 404:
            raise RuntimeError(f"El actor «{actor}» ya no existe en Apify. Cámbialo en «Avanzado».")
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", r.text[:200])
            except Exception:
                msg = r.text[:200]
            raise RuntimeError(f"Apify respondió {r.status_code}: {msg}")
        items = r.json()
        got = 0
        for it in items if isinstance(items, list) else []:
            rows = it.get("companies") if isinstance(it, dict) and isinstance(it.get("companies"), list) else [it]
            for c in rows:
                if isinstance(c, dict) and (c.get("name") or c.get("title") or c.get("companyName")):
                    out.append(c)
                    got += 1
        _say(job, f"Página {p}: {got} empresas")
        if got == 0:
            break
    return out[:limit]


def _site_for(cl: httpx.Client, name: str, zone: str) -> str:
    """Busca la web oficial de una empresa por su nombre y valida que dominio/título se parezcan al nombre."""
    toks = [t for t in re.findall(r"[a-z0-9]{4,}", _plain(name)) if t not in ("empresa", "group", "grupo", "solutions", "services", "company")]
    if not toks:
        return ""
    for title, url in ddg_search(cl, f"{name} {zone} sitio web oficial"):
        if not _ok_site(url):
            continue
        root = _root(url)
        if any(t in _plain(urlparse(root).netloc) for t in toks) or toks[0] in _plain(title):
            return root
    return ""


def run_linkedin(job: dict, query: str, zone: str, limit: int, name: str, actor: str) -> None:
    try:
        comps = _apify_companies(job, query, zone, limit, actor or LINKEDIN_ACTOR)
        if not comps:
            raise RuntimeError("LinkedIn no devolvió empresas para esa búsqueda.")
        _say(job, f"{len(comps)} empresas encontradas. Buscando la web de cada una…")
        cands, blocked = [], False
        with httpx.Client() as cl:
            for i, c in enumerate(comps):
                if job["cancel"]:
                    break
                cname = str(c.get("name") or c.get("title") or c.get("companyName")).strip()
                cat, _, loc = str(c.get("subtitle") or "").partition("•")
                site = str(c.get("website") or c.get("websiteUrl") or "").strip()
                if not site and not blocked:
                    _set(job, progress=f"Buscando la web de cada empresa… {i + 1}/{len(comps)}")
                    try:
                        site = _site_for(cl, cname, zone)
                    except SearchBlocked:
                        blocked = True
                        _say(job, "El buscador pidió pausa; las empresas restantes quedan sin web.")
                    time.sleep(1.2)
                if site and _ok_site(site):
                    cands.append({"name": cname, "website": _root(site), "category": cat.strip() or query,
                                  "zone": loc.strip() or zone, "source": "linkedin",
                                  "extra": {"linkedin": str(c.get("url") or c.get("linkedinUrl") or "")}})
        _say(job, f"{len(cands)} de {len(comps)} empresas con web encontrada.")
        _extract_all(job, cands)
        _finalize(job, name or f"Emails LinkedIn · {query} · {zone}".strip(" ·"))
    except Exception as ex:
        _set(job, status="error", error=str(ex), progress="Falló")
        _say(job, f"✗ {ex}")


# ═════════════════════════════════════════════════════════════════════════════
#  Fuente 3: LEADS QUE YA TENGO (ej. Google Maps con web) → emails
# ═════════════════════════════════════════════════════════════════════════════
def run_list(job: dict, list_id: str) -> None:
    try:
        lst = C._get_list(list_id)
        cands = [{"name": l["name"], "website": l["website"], "category": l.get("category", ""), "zone": l.get("zone", ""), "source": "lista"}
                 for l in lst.get("leads", [])
                 if l.get("website") and not C.norm_email(l.get("email")) and _ok_site(l["website"])]
        if not cands:
            raise RuntimeError("Ningún lead de esa lista tiene web sin email. No hay nada que revisar.")
        _extract_all(job, cands)
        found = {r["name"]: r["email"] for r in job["results"]}
        if found:                                   # los emails se suman a la misma lista
            if lst["id"].startswith("s_"):
                cur = C._read("lead_emails.json", {})
                cur.update(found)
                C._write("lead_emails.json", cur)
            else:
                with C._lock:
                    lists = C._saved_lists()
                    for L in lists:
                        if L["id"] == lst["id"]:
                            for l in L["leads"]:
                                if l.get("name") in found:
                                    l["email"] = found[l["name"]]
                    C._write(C.LISTS_FILE, lists)
            _set(job, list_id=lst["id"], list_name=lst["name"])
        _finalize(job, lst["name"], save_list=False)
    except Exception as ex:
        _set(job, status="error", error=str(ex), progress="Falló")
        _say(job, f"✗ {ex}")


# ═════════════════════════════════════════════════════════════════════════════
#  Endpoint de ejecución
# ═════════════════════════════════════════════════════════════════════════════
class RunIn(BaseModel):
    source: str                         # web | linkedin | list
    query: str = ""
    zone: str = ""
    limit: int = 40
    name: Optional[str] = None
    list_id: Optional[str] = None
    actor: Optional[str] = None


@router.post("/emails/run", tags=["emails"])
def run(b: RunIn):
    limit = max(1, min(int(b.limit), 200))
    if b.source in ("web", "linkedin") and not b.query.strip():
        raise HTTPException(400, "Escribe qué tipo de negocios o empresas buscar")
    if b.source == "web":
        job = _new_job("web", f"Web · {b.query} · {b.zone}")
        threading.Thread(target=run_web, args=(job, b.query.strip(), b.zone.strip(), limit, b.name or ""), daemon=True).start()
    elif b.source == "linkedin":
        if not _apify_token():
            raise HTTPException(400, "Conecta tu token de Apify primero")
        job = _new_job("linkedin", f"LinkedIn · {b.query} · {b.zone}")
        threading.Thread(target=run_linkedin, args=(job, b.query.strip(), b.zone.strip(), limit, b.name or "", b.actor or ""), daemon=True).start()
    elif b.source == "list":
        if not b.list_id:
            raise HTTPException(400, "Elige una lista")
        C._get_list(b.list_id)
        job = _new_job("list", "Leads que ya tengo")
        threading.Thread(target=run_list, args=(job, b.list_id), daemon=True).start()
    else:
        raise HTTPException(400, "Fuente no soportada")
    return _public(job, True)
