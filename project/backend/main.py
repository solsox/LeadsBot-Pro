# main.py
import os
import asyncio
import logging
import glob

from datetime import datetime
from typing import Optional, List


from fastapi              import FastAPI, HTTPException, BackgroundTasks, Query
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

class TrackEvent(BaseModel):
    lead_id: str
    event:   str          # open | click | reply


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def load_json(path: str) -> list:
    # intenta ruta directa primero
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    # busca el archivo más reciente en data/
    pattern = f"data/{path.replace('.json', '_*.json')}"
    files = sorted(glob.glob(pattern))
    if files:
        with open(files[-1], encoding="utf-8") as f:
            return json.load(f)
    return []

def load_state() -> dict:
    if os.path.exists("worker_state.json"):
        with open("worker_state.json") as f:
            return json.load(f)
    return {"loops": 0, "total_sent": 0, "last_run": None}

_worker_running = False


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
    scored = load_json("leads_scored.json")
    ready  = load_json("leads_ready.json")
    ready_names = {r["name"] for r in ready}
    leads = []
    for l in scored:
        match = next((r for r in ready if r["name"] == l["name"]), None)
        leads.append(match if match else l)    
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


@app.post("/leads/{lead_name}/send", tags=["leads"])
def send_to_lead(lead_name: str, background_tasks: BackgroundTasks):
    """Envía email manualmente a un lead específico."""
    leads = load_json("leads_ready.json")
    lead  = next((l for l in leads if l["name"] == lead_name), None)
    if not lead:
        raise HTTPException(404, "Lead no encontrado")

    def _send():
        from sender import EmailSender
        sender = EmailSender()
        result = sender.send_one(lead)
        log.info(f"Manual send → {lead_name}: {'ok' if result.success else result.error}")

    background_tasks.add_task(_send)
    return {"message": f"Enviando email a {lead_name}"}


# ─────────────────────────────────────────────
#  RUTAS: MÉTRICAS
# ─────────────────────────────────────────────
@app.get("/metrics", tags=["metrics"])
def get_metrics():
    """Métricas generales del agente."""
    raw    = load_json("leads_raw.json")
    scored = load_json("leads_scored.json")
    ready  = load_json("leads_ready.json")
    sent   = load_json("send_results.json")

    sent_ok    = [r for r in sent if r.get("success")]
    opens      = load_json("tracking_events.json")
    open_events = [e for e in opens if e.get("event") == "open"]
    replies    = [e for e in opens if e.get("event") == "reply"]

    return {
        "leads_scraped":    len(raw),
        "leads_qualified":  len(scored),
        "leads_ready":      len(ready),
        "emails_sent":      len(sent_ok),
        "open_rate":        round(len(open_events) / max(len(sent_ok), 1) * 100, 1),
        "reply_rate":       round(len(replies)     / max(len(sent_ok), 1) * 100, 1),
        "high_priority":    sum(1 for l in scored if l.get("priority") == "high"),
        "medium_priority":  sum(1 for l in scored if l.get("priority") == "medium"),
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
        from scraper import GoogleMapsScraper, save_results
        scraper = GoogleMapsScraper(headless=True)
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
    return [
        {"query": "restaurantes",      "zone": "Hialeah, Florida"},
        {"query": "peluquerías",       "zone": "Miami, Florida"},
        {"query": "talleres mecánica", "zone": "Doral, Florida"},
        {"query": "clínicas dentales", "zone": "Coral Gables, Florida"},
    ]

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

@app.post("/worker/stop", tags=["worker"])
def stop_worker():
    global _worker_running
    _worker_running = False
    return {"message": "Worker detenido"}

# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)