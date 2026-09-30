# main.py
# main.py
import os
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import logging
import glob

from datetime import datetime
from typing import Optional, List


from fastapi              import FastAPI, HTTPException, BackgroundTasks, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic             import BaseModel
import json

log = logging.getLogger(__name__)

app = FastAPI(
    title="LeadAgent API",
    description="Agente de adquisición automática de clientes",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
#  SCHEMAS
# ─────────────────────────────────────────────
class LeadOut(BaseModel):
    model_config = {"extra": "allow"}

    name:          str
    address:       Optional[str] = None
    phone:         Optional[str] = None
    email:         Optional[str] = None
    website:       Optional[str] = None
    rating:        Optional[float] = None
    score:         Optional[int] = None
    priority:      Optional[str] = None
    status:        Optional[str] = "new"
    email_subject: Optional[str] = None
    email_body:    Optional[str] = None
    whatsapp_msg:  Optional[str] = None
    zone:          Optional[str] = None
    category:      Optional[str] = None
    maps_url:      Optional[str] = None

class WorkerStatus(BaseModel):
    loops:        int
    total_sent:   int
    last_run:     Optional[str]
    is_running:   bool

class ScrapeRequest(BaseModel):
    queries: List[dict]   # [{"query": "restaurantes", "zone": "Miami, FL"}]
    mode: Optional[str] = None   # "corto" | "medio" | "largo" — None usa el default

class TrackEvent(BaseModel):
    lead_id: str
    event:   str          # open | click | reply


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def load_json(path: str) -> list:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    pattern = f"data/{path.replace('.json', '_*.json')}"
    files = glob.glob(pattern)
    if not files:
        return []

    def loop_num(fname: str) -> int:
        digits = "".join(ch for ch in fname.rsplit("_", 1)[-1] if ch.isdigit())
        return int(digits) if digits else -1

    files.sort(key=loop_num)  # de más viejo a más nuevo

    # acumula TODOS los loops; si un negocio aparece en varios,
    # se queda con la versión más reciente (dedup por nombre)
    merged: dict[str, dict] = {}
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for item in json.load(fh):
                key = item.get("name")
                if key:
                    merged[key] = item
    return list(merged.values())

def load_state() -> dict:
    if os.path.exists("worker_state.json"):
        with open("worker_state.json") as f:
            return json.load(f)
    return {"loops": 0, "total_sent": 0, "last_run": None}

_worker_running = False


# ─────────────────────────────────────────────
#  PIPELINE DE ESTADOS (tipo CRM / Instantly)
#  new → contacted → replied → interested → won / lost
# ─────────────────────────────────────────────
STAGES     = ["new", "contacted", "replied", "interested", "won", "lost"]
STAGE_RANK = {s: i for i, s in enumerate(STAGES)}

STATUS_FILE  = "lead_status.json"
WHATSAPP_LOG = os.path.join("..", "..", "WHATSAPP_IA", "data", "enviados_log.csv")

def load_status_overlay() -> dict:
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_status_overlay(overlay: dict) -> None:
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(overlay, f, indent=2, ensure_ascii=False)

def set_lead_status(phone: str, status: str, allow_downgrade: bool = False) -> None:
    """Guarda el estado de un lead por teléfono. Por defecto nunca retrocede el pipeline solo."""
    if not phone:
        return
    overlay = load_status_overlay()
    current = overlay.get(phone, {}).get("status", "new")
    if not allow_downgrade and STAGE_RANK.get(status, 0) < STAGE_RANK.get(current, 0):
        return
    overlay[phone] = {"status": status, "updated_at": datetime.now().isoformat()}
    save_status_overlay(overlay)

def sync_whatsapp_sent() -> None:
    """
    Lee WHATSAPP_IA/data/enviados_log.csv (el log real que escribe el bot al enviar)
    y marca como 'contacted' a cualquier lead que siga en 'new'. Cero pasos manuales.
    """
    if not os.path.exists(WHATSAPP_LOG):
        return
    try:
        import csv
        overlay = load_status_overlay()
        changed = False
        with open(WHATSAPP_LOG, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                phone = (row.get("phone") or "").strip()
                if not phone:
                    continue
                current = overlay.get(phone, {}).get("status", "new")
                if STAGE_RANK.get(current, 0) < STAGE_RANK["contacted"]:
                    overlay[phone] = {"status": "contacted", "updated_at": datetime.now().isoformat()}
                    changed = True
        if changed:
            save_status_overlay(overlay)
    except Exception as e:
        log.warning(f"No se pudo sincronizar el log de WhatsApp: {e}")

def apply_status_overlay(leads: list) -> list:
    overlay = load_status_overlay()
    for l in leads:
        phone = l.get("phone")
        if phone and phone in overlay:
            l["status"] = overlay[phone]["status"]
        else:
            l.setdefault("status", "new")
    return leads


# ─────────────────────────────────────────────
#  CUENTAS DE EMAIL (Gmail) — tipo "Email Accounts" de Instantly
# ─────────────────────────────────────────────
EMAIL_SETTINGS_FILE = "email_settings.json"

class EmailSettings(BaseModel):
    smtp_host:    Optional[str] = "smtp.gmail.com"
    smtp_port:    Optional[int] = 587
    email:        str
    app_password: str
    from_name:    Optional[str] = "Tu Nombre"

def load_email_settings() -> dict:
    if os.path.exists(EMAIL_SETTINGS_FILE):
        with open(EMAIL_SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

@app.get("/settings/email", tags=["settings"])
def get_email_settings():
    """Devuelve la config de la cuenta de Gmail conectada (sin exponer la contraseña real)."""
    s = load_email_settings()
    if s.get("app_password"):
        s = {**s, "app_password": "••••••••"}
    return s

@app.post("/settings/email", tags=["settings"])
def save_email_settings(body: EmailSettings):
    """Guarda/actualiza la cuenta de Gmail que se usa para enviar campañas."""
    with open(EMAIL_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(body.dict(), f, indent=2, ensure_ascii=False)
    return {"ok": True, "connected": True, "email": body.email}

@app.delete("/settings/email", tags=["settings"])
def disconnect_email():
    if os.path.exists(EMAIL_SETTINGS_FILE):
        os.remove(EMAIL_SETTINGS_FILE)
    return {"ok": True}


# ─────────────────────────────────────────────
#  EMAILS DE LEADS (overlay: name -> email)
#  Se suben manualmente porque el scraper de Maps no expone emails.
# ─────────────────────────────────────────────
LEAD_EMAILS_FILE = "lead_emails.json"

def load_lead_emails() -> dict:
    if os.path.exists(LEAD_EMAILS_FILE):
        with open(LEAD_EMAILS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_lead_emails(d: dict) -> None:
    with open(LEAD_EMAILS_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)

def apply_email_overlay(leads: list) -> list:
    emails = load_lead_emails()
    for l in leads:
        if l.get("name") in emails:
            l["email"] = emails[l["name"]]
    return leads

@app.post("/engage/upload-emails", tags=["engage"])
async def upload_emails(file: UploadFile = File(...)):
    """Sube un CSV/XLSX con columnas 'name' y 'email' y las asocia a los leads existentes."""
    import pandas as pd, io
    content = await file.read()
    try:
        if file.filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, f"No pude leer el archivo: {e}")

    cols = {str(c).lower().strip(): c for c in df.columns}
    if "name" not in cols or "email" not in cols:
        raise HTTPException(400, "El archivo debe tener columnas 'name' y 'email'")

    emails = load_lead_emails()
    added = 0
    for _, row in df.iterrows():
        name  = str(row[cols["name"]]).strip()
        email = str(row[cols["email"]]).strip()
        if name and email and "@" in email and name.lower() != "nan":
            emails[name] = email
            added += 1
    save_lead_emails(emails)
    return {"ok": True, "added": added, "total": len(emails)}

@app.get("/engage/leads", tags=["engage"])
def get_engage_leads():
    """Leads que ya tienen email asociado (candidatos a campaña de Gmail)."""
    sync_whatsapp_sent()
    scored = load_json("leads_scored.json")
    ready  = load_json("leads_ready.json")
    leads = []
    for l in scored:
        match = next((r for r in ready if r["name"] == l["name"]), None)
        leads.append(match if match else l)
    leads = apply_status_overlay(leads)
    leads = apply_email_overlay(leads)
    return [l for l in leads if l.get("email")]


# ─────────────────────────────────────────────
#  RUTAS: LEADS
# ─────────────────────────────────────────────
@app.get("/leads", response_model=List[LeadOut], tags=["leads"])
def get_leads(
    priority: Optional[str] = Query(None, description="high | medium | low"),
    status:   Optional[str] = Query(None, description="new | contacted | replied"),
    limit:    int = Query(50, le=200),
):
    """Lista todos los leads calificados."""
    sync_whatsapp_sent()
    scored = load_json("leads_scored.json")
    ready  = load_json("leads_ready.json")
    ready_names = {r["name"] for r in ready}
    leads = []
    for l in scored:
        match = next((r for r in ready if r["name"] == l["name"]), None)
        leads.append(match if match else l)
    leads = apply_status_overlay(leads)
    if priority:
        leads = [l for l in leads if l.get("priority") == priority]
    if status:
        leads = [l for l in leads if l.get("status", "new") == status]
    return leads[:limit]


@app.get("/leads/{lead_name}", response_model=LeadOut, tags=["leads"])
def get_lead(lead_name: str):
    """Detalle de un lead por nombre."""
    leads = load_json("leads_ready.json")
    match = next((l for l in leads if l["name"] == lead_name), None)
    if not match:
        raise HTTPException(404, "Lead no encontrado")
    return match


class StatusUpdate(BaseModel):
    status: str  # uno de STAGES

@app.post("/leads/{lead_name}/status", tags=["leads"])
def update_lead_status(lead_name: str, body: StatusUpdate):
    """Mueve un lead manualmente en el pipeline (ej: marcar 'Respondió' o 'Cliente')."""
    if body.status not in STAGES:
        raise HTTPException(400, f"status inválido, debe ser uno de: {STAGES}")
    scored = load_json("leads_scored.json")
    lead = next((l for l in scored if l["name"] == lead_name), None)
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    phone = lead.get("phone")
    if not phone:
        raise HTTPException(400, "Este lead no tiene teléfono, no se puede trackear en el pipeline")
    set_lead_status(phone, body.status, allow_downgrade=True)
    return {"ok": True, "name": lead_name, "status": body.status}


@app.get("/pipeline", tags=["leads"])
def get_pipeline():
    """Conteo de leads por etapa del pipeline (para el tablero tipo CRM)."""
    sync_whatsapp_sent()
    scored = apply_status_overlay(load_json("leads_scored.json"))
    return {stage: sum(1 for l in scored if l.get("status", "new") == stage) for stage in STAGES}


@app.post("/leads/{lead_name}/send", tags=["leads"])
def send_to_lead(lead_name: str, background_tasks: BackgroundTasks):
    """Envía email manualmente a un lead específico."""
    leads = load_json("leads_ready.json")
    lead  = next((l for l in leads if l["name"] == lead_name), None)
    if not lead:
        raise HTTPException(404, "Lead no encontrado")

    lead = dict(lead)
    emails = load_lead_emails()
    if lead["name"] in emails:
        lead["email"] = emails[lead["name"]]
    if not lead.get("email"):
        raise HTTPException(400, "Este lead no tiene email. Súbelo en la pestaña Engage.")

    def _send():
        from sender import EmailSender
        sender = EmailSender()
        result = sender.send_one(lead)
        log.info(f"Manual send → {lead_name}: {'ok' if result.success else result.error}")

    background_tasks.add_task(_send)
    return {"message": f"Enviando email a {lead_name}"}


class CampaignRequest(BaseModel):
    lead_names: List[str]

@app.post("/engage/send-campaign", tags=["engage"])
def send_campaign(body: CampaignRequest, background_tasks: BackgroundTasks):
    """Envía una campaña de Gmail a varios leads de una vez (necesitan email + mensaje generado)."""
    scored = load_json("leads_scored.json")
    ready  = load_json("leads_ready.json")
    emails = load_lead_emails()

    targets = []
    for name in body.lead_names:
        lead = next((l for l in ready if l["name"] == name), None) or next((l for l in scored if l["name"] == name), None)
        if not lead:
            continue
        lead = dict(lead)
        if name in emails:
            lead["email"] = emails[name]
        if lead.get("email") and lead.get("email_body"):
            targets.append(lead)

    if not targets:
        raise HTTPException(400, "Ninguno de los leads seleccionados tiene email + mensaje generado")

    def _run():
        from sender import EmailSender, save_results
        sender  = EmailSender()
        results = sender.send_batch(targets)
        save_results(results)
        log.info(f"Campaña Gmail: {sum(1 for r in results if r.success)}/{len(targets)} enviados")

    background_tasks.add_task(_run)
    return {"ok": True, "queued": len(targets)}


# ─────────────────────────────────────────────
#  RUTAS: MÉTRICAS
# ─────────────────────────────────────────────
@app.get("/metrics", tags=["metrics"])
def get_metrics():
    """Métricas generales del agente."""
    sync_whatsapp_sent()
    raw    = load_json("leads_raw.json")
    scored = load_json("leads_scored.json")
    ready  = load_json("leads_ready.json")

    scored = apply_status_overlay(scored)
    pipeline = {stage: sum(1 for l in scored if l.get("status", "new") == stage) for stage in STAGES}
    contacted_or_beyond = sum(pipeline[s] for s in STAGES if s != "new")

    return {
        "leads_scraped":    len(raw),
        "leads_qualified":  len(scored),
        "leads_ready":      len(ready),
        "whatsapp_sent":    contacted_or_beyond,
        "reply_rate":       round(pipeline["replied"] / max(contacted_or_beyond, 1) * 100, 1),
        "high_priority":    sum(1 for l in scored if l.get("priority") == "high"),
        "medium_priority":  sum(1 for l in scored if l.get("priority") == "medium"),
        "pipeline":         pipeline,
    }


# ─────────────────────────────────────────────
#  RUTAS: WORKER
# ─────────────────────────────────────────────
@app.get("/worker/status", response_model=WorkerStatus, tags=["worker"])
def worker_status():
    state = load_state()
    return WorkerStatus(**state, is_running=_worker_running)


@app.post("/worker/run", tags=["worker"])
def trigger_worker(background_tasks: BackgroundTasks):
    """Dispara el pipeline completo manualmente."""
    global _worker_running
    if _worker_running:
        raise HTTPException(409, "Worker ya está ejecutándose")

    async def _run():
        global _worker_running
        _worker_running = True
        try:
            from worker import run_pipeline, load_state, save_state
            state = load_state()
            state = await run_pipeline(state)
            save_state(state)
        finally:
            _worker_running = False

    background_tasks.add_task(asyncio.run, _run())
    return {"message": "Pipeline iniciado en background"}


@app.post("/worker/scrape", tags=["worker"])
def trigger_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    """Scraping con zonas personalizadas."""
    async def _scrape():
        from scraper import GoogleMapsScraper, save_results, DEFAULT_SEARCH_MODE
        scraper = GoogleMapsScraper(headless=True, mode=req.mode or DEFAULT_SEARCH_MODE)
        leads   = await scraper.scrape_all(req.queries)
        save_results(leads)

    background_tasks.add_task(asyncio.run, _scrape())
    return {"message": f"Scraping iniciado para {len(req.queries)} búsquedas"}


# ─────────────────────────────────────────────
#  RUTAS: TRACKING
# ─────────────────────────────────────────────
@app.get("/track/open/{lead_id}", tags=["tracking"], include_in_schema=False)
def track_open(lead_id: str):
    """Pixel de tracking — registra apertura de email."""
    _record_event(lead_id, "open")
    # devuelve pixel 1x1 transparente
    from fastapi.responses import Response
    pixel = b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
    return Response(content=pixel, media_type="image/gif")


@app.post("/track/event", tags=["tracking"])
def track_event(event: TrackEvent):
    """Registra cualquier evento de tracking."""
    _record_event(event.lead_id, event.event)
    return {"ok": True}


def _record_event(lead_id: str, event: str) -> None:
    events = load_json("tracking_events.json")
    events.append({
        "lead_id":  lead_id,
        "event":    event,
        "timestamp": datetime.now().isoformat(),
    })
    with open("tracking_events.json", "w") as f:
        json.dump(events, f, indent=2)

@app.post("/worker/generate", tags=["worker"])
def generate_single(data: dict, background_tasks: BackgroundTasks):
    lead_name = data.get("lead_name")
    def _gen():
        from generator import MessageGenerator
        scored = load_json("data/leads_scored_1.json") or load_json("leads_scored.json")
        lead = next((l for l in scored if l.get("name") == lead_name), None)
        if not lead: return
        gen = MessageGenerator()
        msg = gen.generate(lead)
        if msg:
            lead["email_subject"] = msg.subject
            lead["email_body"]    = msg.body
            lead["whatsapp_msg"]  = msg.whatsapp
            ready = load_json("leads_ready.json") or []
            ready = [l for l in ready if l.get("name") != lead_name]
            ready.append(lead)
            with open("leads_ready.json", "w") as f:
                json.dump(ready, f, ensure_ascii=False, indent=2)
    background_tasks.add_task(_gen)
    return {"ok": True}

CONFIG_FILE = "search_config.json"

def load_search_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return []

def save_search_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

@app.get("/config/search", tags=["config"])
def get_search_config():
    return load_search_config()

from typing import List
from pydantic import BaseModel

class SearchConfigItem(BaseModel):
    query: str
    zone: str

@app.post("/config/search", tags=["config"])
def update_search_config(config: List[SearchConfigItem]):
    save_search_config([c.dict() for c in config])
    return {"ok": True}

MODE_FILE = "search_mode.json"

class SearchModeItem(BaseModel):
    mode: str   # "corto" | "medio" | "largo"

@app.get("/config/mode", tags=["config"])
def get_search_mode():
    """Modo de búsqueda que usará el worker automático (loop de 6h)."""
    from scraper import DEFAULT_SEARCH_MODE, SEARCH_MODES
    if os.path.exists(MODE_FILE):
        with open(MODE_FILE) as f:
            data = json.load(f)
            if data.get("mode") in SEARCH_MODES:
                return data
    return {"mode": DEFAULT_SEARCH_MODE}

@app.get("/config/modes", tags=["config"])
def list_search_modes():
    """Opciones disponibles (corto/medio/largo) con su descripción, para poblar el selector del dashboard."""
    from scraper import SEARCH_MODES
    return SEARCH_MODES

@app.post("/config/mode", tags=["config"])
def update_search_mode(item: SearchModeItem):
    from scraper import SEARCH_MODES
    if item.mode not in SEARCH_MODES:
        raise HTTPException(400, f"Modo inválido. Usa uno de: {list(SEARCH_MODES.keys())}")
    with open(MODE_FILE, "w") as f:
        json.dump({"mode": item.mode}, f, indent=2)
    return {"ok": True}

@app.get("/export/csv", tags=["export"])
def export_csv():
    import csv, io, glob
    todos = []
    for f in sorted(glob.glob("data/leads_scored_*.json")):
        todos += load_json(f)
    output = io.StringIO()
    if todos:
        writer = csv.DictWriter(output, fieldnames=todos[0].keys())
        writer.writeheader()
        writer.writerows(todos)
    from fastapi.responses import Response
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"}
    )

@app.get("/export/whatsapp", tags=["export"])
def export_whatsapp_excel():
    """
    Exporta los leads calificados (con teléfono) a un .xlsx con las columnas
    name, phone, category — listo para meter en WHATSAPP_IA/data/ y correr el bot.
    """
    import pandas as pd, io, glob
    from fastapi.responses import Response

    todos = []
    for f in sorted(glob.glob("data/leads_scored_*.json")):
        todos += load_json(f)
    if not todos:
        todos = load_json("leads_scored.json")

    seen = set()
    rows = []
    for l in todos:
        name  = l.get("name")
        phone = l.get("phone")
        if not name or not phone or name in seen:
            continue
        seen.add(name)
        rows.append({"name": name, "phone": phone, "category": l.get("category", "")})

    df = pd.DataFrame(rows, columns=["name", "phone", "category"])
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=leads_whatsapp.xlsx"}
    )


@app.post("/worker/stop", tags=["worker"])
def stop_worker():
    global _worker_running
    _worker_running = False
    return {"message": "Worker detenido"}

@app.post("/worker/reset", tags=["worker"])
def reset_worker():
    """Borra el estado y los datos acumulados para arrancar una búsqueda limpia."""
    global _worker_running
    if _worker_running:
        raise HTTPException(409, "Detén el worker antes de reiniciar")

    # 1. estado persistente a cero (loops, total_sent, contacted_names)
    fresh_state = {"loops": 0, "total_sent": 0, "last_run": None, "contacted_names": []}
    with open("worker_state.json", "w") as f:
        json.dump(fresh_state, f, indent=2)

    # 2. borrar todos los archivos de corridas anteriores (evita mezclar loops)
    patterns = [
        "data/leads_raw_*.json", "data/leads_scored_*.json",
        "data/leads_ready_*.json", "data/send_results_*.json",
        "leads_raw.json", "leads_scored.json",
        "leads_ready.json", "send_results.json", "tracking_events.json",
    ]
    for pattern in patterns:
        for f_path in glob.glob(pattern):
            os.remove(f_path)

    return {"ok": True, "message": "Estado reiniciado. La próxima búsqueda empieza desde cero."}

# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)