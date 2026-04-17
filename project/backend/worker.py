from __future__ import annotations
# worker.py
import asyncio
import logging
import time
import json
import os
from datetime import datetime

from scoring   import LeadScorer, save_scored
from generator import MessageGenerator, save_with_messages
from sender    import EmailSender, save_results as save_send_results
from scraper import GoogleMapsScraper, save_results as save_raw

def get_search_configs():
    if os.path.exists("search_config.json"):
        with open("search_config.json") as f:
            import json as _json
            return _json.load(f)
    from scraper import SEARCH_CONFIGS
    return SEARCH_CONFIGS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("worker.log", encoding="utf-8"),
    ]
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  CONFIG DEL LOOP
# ─────────────────────────────────────────────
LOOP_INTERVAL_HOURS = 6      # ejecutar cada N horas
MAX_LEADS_PER_LOOP  = 999     # leads a procesar por ciclo
STATE_FILE          = "worker_state.json"


# ─────────────────────────────────────────────
#  ESTADO PERSISTENTE
# ─────────────────────────────────────────────
def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"loops": 0, "total_sent": 0, "last_run": None, "contacted_names": []}

def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ─────────────────────────────────────────────
#  PIPELINE COMPLETO
# ─────────────────────────────────────────────
async def run_pipeline(state: dict) -> dict:
    loop_num = state["loops"] + 1
    log.info(f"{'='*50}")
    log.info(f"  LOOP #{loop_num} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"{'='*50}")

    # ── PASO 1: Scraping ──────────────────────────────────────────────────
    log.info("📡 PASO 1/4: Scraping Google Maps...")
    scraper = GoogleMapsScraper(headless=True)
    raw_leads = await scraper.scrape_all(get_search_configs())
    save_raw(raw_leads, f"data/leads_raw_{loop_num}.json")
    log.info(f"  → {len(raw_leads)} leads crudos")

    # ── PASO 2: Scoring ───────────────────────────────────────────────────
    log.info("🎯 PASO 2/4: Scoring y filtrado...")
    scorer       = LeadScorer()
    raw_dicts    = [vars(l) if not isinstance(l, dict) else l for l in raw_leads]
    scored_leads = scorer.score_all(raw_dicts)

    # filtrar ya contactados
    already = set(state.get("contacted_names", []))
    new_leads = [l for l in scored_leads if l.name not in already]
    batch = new_leads[:MAX_LEADS_PER_LOOP]

    log.info(f"  → {len(scored_leads)} calificados, {len(new_leads)} nuevos, procesando {len(batch)}")

    if not batch:
        log.info("  ⚠ Sin leads nuevos en este ciclo")
        state["loops"] = loop_num
        state["last_run"] = datetime.now().isoformat()
        return state

    import dataclasses
    batch_dicts = [dataclasses.asdict(l) for l in batch]
    save_scored(batch, f"data/leads_scored_{loop_num}.json")

    # ── PASO 3: Generación de mensajes ────────────────────────────────────
    #log.info("🤖 PASO 3/4: Generando mensajes con IA...")
    #generator   = MessageGenerator()
    #ready_leads = generator.generate_batch(batch_dicts)
    #save_with_messages(ready_leads, f"data/leads_ready_{loop_num}.json")
    #log.info(f"  → {len(ready_leads)} mensajes generados")

    # ── PASO 4: Envío ─────────────────────────────────────────────────────
    #log.info("✉ PASO 4/4: Enviando emails...")
    # solo leads con email disponible
    #leads_with_email = [l for l in ready_leads if l.get("email")]

   # sent_count = 0
   # if leads_with_email:
   #     sender  = EmailSender()
   #     results = sender.send_batch(leads_with_email)
   #     save_send_results(results, f"data/send_results_{loop_num}.json")
   #     sent_count = sum(1 for r in results if r.success)
   #     log.info(f"  → {sent_count}/{len(leads_with_email)} emails enviados")
   # else:
   #     log.info("  ⚠ Sin emails disponibles en este batch (integrar hunter.io)")

    log.info("⏭ Pasos 3 y 4 desactivados — solo recolección de leads")
    sent_count = 0

    # ── actualizar estado ─────────────────────────────────────────────────
    state["loops"]      = loop_num
    state["total_sent"] = state.get("total_sent", 0) + sent_count
    state["last_run"]   = datetime.now().isoformat()
    state["contacted_names"] = list(already | {l.name for l in batch})

    log.info(f"✅ Loop #{loop_num} completo — total enviados: {state['total_sent']}")
    return state


# ─────────────────────────────────────────────
#  LOOP PRINCIPAL
# ─────────────────────────────────────────────
async def main():
    os.makedirs("data", exist_ok=True)
    state = load_state()
    log.info(f"🚀 Worker iniciado — estado previo: {state['loops']} loops, {state['total_sent']} enviados")

    while True:
        try:
            state = await run_pipeline(state)
            save_state(state)
        except Exception as e:
            log.error(f"💥 Error en pipeline: {e}", exc_info=True)

        next_run = LOOP_INTERVAL_HOURS * 3600
        log.info(f"⏳ Próximo ciclo en {LOOP_INTERVAL_HOURS}h — durmiendo...")
        await asyncio.sleep(next_run)


if __name__ == "__main__":
    asyncio.run(main())