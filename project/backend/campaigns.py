# campaigns.py
# ─────────────────────────────────────────────────────────────────────────────
#  Campañas tipo Instantly para LeadAgent PRO
#    · Listas  (búsquedas automáticas + CSV/XLSX importados)
#    · Historial de búsquedas
#    · Campañas con secuencia de pasos (Gmail o WhatsApp por paso, con días de espera)
#    · Variables {{firstName}}, {{companyName}}, {{signature}}, ...
#    · Scheduler automático (horario, días, límites diarios)
#    · Analíticas por campaña
#  Se guarda todo en JSON dentro de ./campaigns_data (mismo estilo que el resto del proyecto).
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import csv
import glob
import hashlib
import io
import json
import logging
import os
import re
import subprocess
import sys
import threading
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

log = logging.getLogger("campaigns")
router = APIRouter()

DATA_DIR      = "campaigns_data"
LISTS_FILE    = os.path.join(DATA_DIR, "lists.json")
CAMP_FILE     = os.path.join(DATA_DIR, "campaigns.json")
ENROLL_FILE   = os.path.join(DATA_DIR, "enrollments.json")
SENDLOG_FILE  = os.path.join(DATA_DIR, "send_log.json")
STATUS_FILE   = "lead_status.json"                       # overlay que ya usa main.py
TRACK_FILE    = "tracking_events.json"                   # pixel de apertura de main.py
WHATSAPP_DIR  = os.path.join("..", "..", "WHATSAPP_IA")
WHATSAPP_LOG  = os.path.join(WHATSAPP_DIR, "data", "enviados_log.csv")

DEFAULT_COUNTRY_CODE = os.getenv("DEFAULT_COUNTRY_CODE", "57")   # Colombia

_lock = threading.RLock()
_wa_lock = threading.Lock()
_last_send: Dict[str, float] = {}


# ═════════════════════════════════════════════════════════════════════════════
#  STORAGE
# ═════════════════════════════════════════════════════════════════════════════
def _read(path: str, default):
    with _lock:
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log.warning(f"No pude leer {path}: {e}")
        return default


def _write(path: str, data) -> None:
    with _lock:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


# ═════════════════════════════════════════════════════════════════════════════
#  LEADS: normalización y lectura de lo que ya encuentra el scraper
# ═════════════════════════════════════════════════════════════════════════════
def norm_phone(p: Any) -> str:
    if p is None:
        return ""
    raw = str(p).strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if not raw.startswith("+"):
        digits = digits.lstrip("0") if digits.startswith("00") else digits
        # celular local sin indicativo (ej. 300 555 1212) → agrega el país por defecto
        if len(digits) == 10 and DEFAULT_COUNTRY_CODE:
            digits = DEFAULT_COUNTRY_CODE + digits
    return "+" + digits if len(digits) >= 8 else ""


def norm_email(e: Any) -> str:
    s = str(e or "").strip().lower()
    return s if "@" in s and s != "nan" else ""


def lead_key(l: dict) -> str:
    """Identificador estable: teléfono > email > nombre."""
    return norm_phone(l.get("phone")) or norm_email(l.get("email")) or str(l.get("name", "")).strip().lower()


def _load_scored() -> List[dict]:
    """Igual que load_json() de main.py: junta todos los loops y deduplica por nombre."""
    files = glob.glob("data/leads_scored_*.json")

    def loop_num(fname: str) -> int:
        digits = "".join(ch for ch in fname.rsplit("_", 1)[-1] if ch.isdigit())
        return int(digits) if digits else -1

    files.sort(key=loop_num)
    merged: Dict[str, dict] = {}
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                for item in json.load(fh):
                    if item.get("name"):
                        merged[item["name"]] = item
        except Exception:
            pass
    if not merged and os.path.exists("leads_scored.json"):
        try:
            with open("leads_scored.json", encoding="utf-8") as fh:
                for item in json.load(fh):
                    if item.get("name"):
                        merged[item["name"]] = item
        except Exception:
            pass
    # emails que se subieron desde Engage
    emails = _read("lead_emails.json", {})
    out = []
    for l in merged.values():
        l = dict(l)
        if l.get("name") in emails and not l.get("email"):
            l["email"] = emails[l["name"]]
        out.append(l)
    return out


def _search_groups() -> Dict[str, dict]:
    """Agrupa los leads encontrados por (búsqueda, zona). Cada grupo es una 'lista' automática."""
    scored = _load_scored()
    groups: Dict[str, dict] = {}

    def add(gid: str, label: str, l: dict):
        g = groups.setdefault(gid, {"id": gid, "name": label, "source": "search", "leads": []})
        g["leads"].append(l)

    for l in scored:
        q, z = (l.get("query") or l.get("category") or "Búsqueda"), (l.get("zone") or "")
        gid = "s_" + hashlib.md5(f"{q}|{z}".encode()).hexdigest()[:8]
        add(gid, f"{q} · {z}".strip(" ·"), l)
    if scored:
        groups["s_all"] = {"id": "s_all", "name": "Todos los leads encontrados", "source": "search", "leads": scored}
    return groups


def _saved_lists() -> List[dict]:
    return _read(LISTS_FILE, [])


def _get_list(list_id: str) -> dict:
    if list_id.startswith("s_"):
        g = _search_groups().get(list_id)
        if g:
            return g
    else:
        for l in _saved_lists():
            if l["id"] == list_id:
                return l
    raise HTTPException(404, "Lista no encontrada")


def _list_summary(l: dict) -> dict:
    leads = l.get("leads", [])
    return {
        "id": l["id"],
        "name": l["name"],
        "source": l.get("source", "import"),
        "created_at": l.get("created_at"),
        "count": len(leads),
        "with_phone": sum(1 for x in leads if norm_phone(x.get("phone"))),
        "with_email": sum(1 for x in leads if norm_email(x.get("email"))),
        "campaigns": [c["name"] for c in _read(CAMP_FILE, []) if c.get("list_id") == l["id"]],
    }


# ═════════════════════════════════════════════════════════════════════════════
#  LISTAS + IMPORTACIÓN (CSV / XLSX arrastrado desde el dashboard)
# ═════════════════════════════════════════════════════════════════════════════
ALIASES = {
    "name":     ["name", "nombre", "negocio", "business", "company", "empresa",
                 "razon social", "company_name", "organization", "organization_name"],
    "phone":    ["phone", "telefono", "teléfono", "celular", "whatsapp", "movil", "móvil",
                 "tel", "numero", "número", "mobile_number", "company_phone"],
    "email":    ["email", "correo", "e-mail", "mail", "personal_email", "email_address"],
    "category": ["category", "categoria", "categoría", "rubro", "tipo",
                 "industry", "job_title", "title", "headline"],
    "zone":     ["zone", "zona", "ciudad", "city", "ubicacion", "ubicación",
                 "company_city", "company_state", "state", "location", "country"],
    "contact":  ["contact", "contacto", "first name", "firstname", "nombre contacto",
                 "persona", "full_name", "contact_name"],
    "website":  ["website", "web", "sitio", "url", "pagina", "página",
                 "company_website", "company_domain", "domain", "company_url"],
}


def _read_table(content: bytes, filename: str):
    import pandas as pd
    try:
        if filename.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content), dtype=str)
        else:
            try:
                df = pd.read_csv(io.BytesIO(content), dtype=str, sep=None, engine="python", encoding="utf-8-sig")
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(content), dtype=str, sep=None, engine="python", encoding="latin-1")
    except Exception as e:
        raise HTTPException(400, f"No pude leer el archivo: {e}")
    df = df.fillna("")
    return df


def _guess_mapping(columns: List[str]) -> Dict[str, Optional[str]]:
    low = {str(c).strip().lower(): c for c in columns}
    mapping: Dict[str, Optional[str]] = {}
    for field, names in ALIASES.items():
        mapping[field] = next((low[n] for n in names if n in low), None)
    return mapping


@router.post("/lists/import/preview", tags=["lists"])
async def import_preview(file: UploadFile = File(...)):
    df = _read_table(await file.read(), file.filename or "")
    cols = [str(c) for c in df.columns]
    return {
        "filename": file.filename,
        "total": len(df),
        "columns": cols,
        "mapping": _guess_mapping(cols),
        "sample": df.head(5).to_dict(orient="records"),
    }


@router.post("/lists/import", tags=["lists"])
@router.post("/lists/import", tags=["lists"])
async def import_list(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    mapping: Optional[str] = Form(None),
):
    df = _read_table(await file.read(), file.filename or "")
    cols = [str(c) for c in df.columns]
    m = json.loads(mapping) if mapping else _guess_mapping(cols)
    if not m.get("name") and not m.get("phone") and not m.get("email"):
        raise HTTPException(400, "No encontré columnas de nombre, teléfono ni email. Revisa el mapeo.")

    mapped_cols = {v for v in m.values() if v}
    leads, seen = [], set()
    for _, row in df.iterrows():
        rec = {f: (str(row[c]).strip() if c else "") for f, c in m.items()}
        rec["phone"] = norm_phone(rec.get("phone"))
        rec["email"] = norm_email(rec.get("email"))

        # nombre del lead → alimenta {{companyName}}.
        # Prioridad: name/company_name → contact/full_name → email → phone.
        # Si el "name" quedó apuntando a lo mismo que contact, usar contact.
        name_val    = (rec.get("name") or "").strip()
        contact_val = (rec.get("contact") or "").strip()
        if not name_val or name_val.lower() == contact_val.lower():
            name_val = contact_val or rec["email"] or rec["phone"]
        rec["name"] = name_val

        # contacto (persona) → alimenta {{firstName}}
        if not contact_val or contact_val.lower() == name_val.lower():
            contact_val = ""  # dejar vacío, la plantilla usará "equipo de <empresa>"
        rec["contact"] = contact_val

        if not (rec["phone"] or rec["email"]):
            continue
        # el resto de columnas quedan disponibles como variables personalizadas
        rec["extra"] = {str(c): str(row[c]).strip() for c in df.columns
                        if c not in mapped_cols and str(row[c]).strip()}
        k = lead_key(rec)
        if k in seen:
            continue
        seen.add(k)
        leads.append(rec)

    if not leads:
        raise HTTPException(400, "El archivo no tiene filas con teléfono o email válidos")

    base = os.path.splitext(file.filename or "Lista")[0]
    lst = {
        "id": "i_" + uuid.uuid4().hex[:8],
        "name": (name or base).strip(),
        "source": "csv",
        "filename": file.filename,
        "created_at": _iso(_now()),
        "leads": leads,
    }
    with _lock:
        lists = _saved_lists()
        lists.append(lst)
        _write(LISTS_FILE, lists)
    return _list_summary(lst)


@router.get("/lists", tags=["lists"])
def get_lists():
    """Listas guardadas (CSV) + listas automáticas de cada búsqueda del scraper."""
    out = [_list_summary(g) for g in _search_groups().values()]
    out += [_list_summary(l) for l in _saved_lists()]
    return out


@router.get("/lists/{list_id}/leads", tags=["lists"])
def get_list_leads(list_id: str):
    return _get_list(list_id).get("leads", [])


@router.delete("/lists/{list_id}", tags=["lists"])
def delete_list(list_id: str):
    if list_id.startswith("s_"):
        raise HTTPException(400, "Las listas de búsqueda son automáticas; se limpian con 'Reiniciar' en Buscar")
    with _lock:
        lists = [l for l in _saved_lists() if l["id"] != list_id]
        _write(LISTS_FILE, lists)
    return {"ok": True}


def export_leads_file():
    """Exporta los leads con teléfono a Excel (.xlsx). Si falta openpyxl, entrega CSV en vez de fallar."""
    from fastapi.responses import Response
    rows, seen = [], set()
    for l in _load_scored():
        ph = norm_phone(l.get("phone"))
        if not l.get("name") or not ph or ph in seen:
            continue
        seen.add(ph)
        rows.append([l.get("name"), ph, l.get("category") or "", norm_email(l.get("email")), l.get("zone") or "", l.get("score") if l.get("score") is not None else ""])
    head = ["name", "phone", "category", "email", "zone", "score"]
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "leads"
        ws.append(head)
        for r in rows:
            ws.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        return Response(content=buf.getvalue(),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": "attachment; filename=leads_whatsapp.xlsx"})
    except ImportError:
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(head)
        w.writerows(rows)
        return Response(content="\ufeff" + out.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=leads_whatsapp.csv"})


@router.get("/history", tags=["lists"])
def search_history():
    """Historial de búsquedas: una entrada por corrida del worker (loop), con desglose por búsqueda/zona."""
    items = []
    for f in glob.glob("data/leads_scored_*.json"):
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        by = Counter(f"{d.get('query') or d.get('category') or '—'} · {d.get('zone') or ''}".strip(" ·") for d in data)
        items.append({
            "id": os.path.basename(f),
            "date": datetime.fromtimestamp(os.path.getmtime(f)).isoformat(),
            "total": len(data),
            "high": sum(1 for d in data if d.get("priority") == "high"),
            "with_phone": sum(1 for d in data if d.get("phone")),
            "searches": [{"label": k, "count": v} for k, v in by.most_common()],
        })
    items.sort(key=lambda x: x["date"], reverse=True)
    return items


# ═════════════════════════════════════════════════════════════════════════════
#  VARIABLES
# ═════════════════════════════════════════════════════════════════════════════
BUILTIN_VARS = [
    {"key": "firstName",   "label": "Nombre del contacto",   "hint": "Si no hay contacto pone \"equipo de <negocio>\""},
    {"key": "companyName", "label": "Nombre del negocio",    "hint": "Sin dirección ni sede"},
    {"key": "category",    "label": "Categoría",             "hint": "Ej: Restaurante"},
    {"key": "city",        "label": "Ciudad",                "hint": "Primera parte de la zona"},
    {"key": "website",     "label": "Sitio web",             "hint": ""},
    {"key": "senderName",  "label": "Tu nombre",             "hint": "Se define en la campaña"},
    {"key": "signature",   "label": "Firma",                 "hint": "Se define en la campaña"},
]


def clean_company(name: str) -> str:
    n = re.split(r"\s[-–|·]\s|#|,|\s\d{2,}", str(name or ""))[0].strip(" .-")
    return n or str(name or "").strip()


def build_vars(lead: dict, camp: dict) -> Dict[str, str]:
    company = clean_company(lead.get("name", ""))
    v = {
        "companyName": company,
        "firstName":   (lead.get("contact") or "").strip().split(" ")[0] or f"equipo de {company}",
        "category":    lead.get("category") or "",
        "city":        (lead.get("zone") or "").split(",")[0].strip(),
        "website":     lead.get("website") or "",
    }
    v.update({k: str(x) for k, x in (lead.get("extra") or {}).items()})
    v.update({k: str(x) for k, x in (camp.get("variables") or {}).items()})   # senderName, signature y personalizadas
    return v


_VAR_RE = re.compile(r"\{\{\s*([A-Za-z0-9_ ]+?)\s*\}\}")


def render(text: str, vars_: Dict[str, str]) -> tuple[str, List[str]]:
    missing: List[str] = []

    def sub(m):
        k = m.group(1).strip()
        val = vars_.get(k)
        if val is None or val == "":
            missing.append(k)
            return m.group(0)
        return val

    return _VAR_RE.sub(sub, text or ""), missing


# ═════════════════════════════════════════════════════════════════════════════
#  CAMPAÑAS
# ═════════════════════════════════════════════════════════════════════════════
DEFAULT_SCHEDULE = {
    "days": [0, 1, 2, 3, 4],          # lunes=0 ... domingo=6
    "start": "09:00",
    "end": "18:00",
    "tz": "America/Bogota",
    "daily_limit_email": 40,
    "daily_limit_whatsapp": 25,
    "gap_email_sec": 45,
    "gap_whatsapp_sec": 60,
}


def _default_steps() -> List[dict]:
    return [
        {"id": uuid.uuid4().hex[:6], "channel": "email", "delay_days": 3,
         "subject": "¿Le suena una web que traiga más clientes a {{companyName}}?",
         "body": "Hola {{firstName}},\n\nVi {{companyName}} en Google Maps y creo que una página enfocada en convertir visitas en pedidos o reservas puede ayudarles bastante.\n\n¿Te muestro una idea pensada para tu negocio?\n\n{{signature}}"},
        {"id": uuid.uuid4().hex[:6], "channel": "whatsapp", "delay_days": 3, "subject": "",
         "body": "Hola {{firstName}} 👋 te escribí por correo hace unos días sobre una web para {{companyName}}. ¿Te la envío por aquí?"},
        {"id": uuid.uuid4().hex[:6], "channel": "email", "delay_days": 7,
         "subject": "¿Lo vemos, {{firstName}}?",
         "body": "Hola {{firstName}}, solo retomo mi mensaje anterior. Si no es prioridad ahora, no pasa nada.\n\n{{signature}}"},
    ]


class StepIn(BaseModel):
    id: Optional[str] = None
    channel: str = "email"              # email | whatsapp
    delay_days: float = 3               # días de espera DESPUÉS de este paso, antes del siguiente
    subject: str = ""
    body: str = ""


class CampaignIn(BaseModel):
    name: Optional[str] = None
    list_id: Optional[str] = None
    steps: Optional[List[StepIn]] = None
    schedule: Optional[dict] = None
    variables: Optional[Dict[str, str]] = None
    email_account_ids: Optional[List[str]] = None      # ← NUEVO: ids de cuentas
    account_strategy: Optional[str] = None             # ← NUEVO: least_used | round_robin | random


def _campaigns() -> List[dict]:
    return _read(CAMP_FILE, [])


def _get_campaign(cid: str) -> dict:
    for c in _campaigns():
        if c["id"] == cid:
            return c
    raise HTTPException(404, "Campaña no encontrada")


def _save_campaign(c: dict) -> None:
    with _lock:
        cs = _campaigns()
        for i, x in enumerate(cs):
            if x["id"] == c["id"]:
                cs[i] = c
                break
        else:
            cs.append(c)
        _write(CAMP_FILE, cs)


def _enrollments() -> Dict[str, Dict[str, dict]]:
    return _read(ENROLL_FILE, {})


def _validate_steps(steps: List[StepIn]) -> List[dict]:
    out = []
    for s in steps:
        if s.channel not in ("email", "whatsapp"):
            raise HTTPException(400, f"Canal inválido: {s.channel}")
        d = s.dict()
        d["id"] = d.get("id") or uuid.uuid4().hex[:6]
        d["delay_days"] = max(0.0, float(d["delay_days"]))
        out.append(d)
    return out


def _camp_summary(c: dict, enr: Dict[str, dict], log_rows: List[dict]) -> dict:
    rows = [r for r in log_rows if r["campaign_id"] == c["id"] and r.get("ok")]
    states = Counter(e["status"] for e in enr.values())
    return {
        "id": c["id"], "name": c["name"], "status": c["status"], "list_id": c.get("list_id"),
        "steps": len(c["steps"]), "leads": len(enr),
        "sent": len(rows),
        "replied": states.get("replied", 0),
        "active": states.get("active", 0),
        "completed": states.get("completed", 0),
        "created_at": c.get("created_at"),
    }


@router.get("/campaigns", tags=["campaigns"])
def list_campaigns():
    enr, rows = _enrollments(), _read(SENDLOG_FILE, [])
    return [_camp_summary(c, enr.get(c["id"], {}), rows) for c in _campaigns()]


@router.post("/campaigns", tags=["campaigns"])
def create_campaign(body: CampaignIn):
    c = {
        "id": "c_" + uuid.uuid4().hex[:8],
        "name": body.name or "Campaña nueva",
        "status": "draft",
        "list_id": body.list_id,
        "steps": _validate_steps(body.steps) if body.steps else _default_steps(),
        "schedule": {**DEFAULT_SCHEDULE, **(body.schedule or {})},
        "variables": body.variables or {"senderName": "Tu nombre", "signature": "Saludos,\nTu nombre"},
        "email_account_ids": body.email_account_ids or [],          # ← NUEVO ([] = todas)
        "account_strategy": body.account_strategy or "least_used",  # ← NUEVO
        "created_at": _iso(_now()),
    }
    _save_campaign(c)
    if c["list_id"]:
        _enroll(c, c["list_id"])
    return c


class QuickIn(BaseModel):
    name: Optional[str] = None
    channel: str = "whatsapp"          # whatsapp | email | both
    leads: List[dict]


def _preset_steps(channel: str) -> List[dict]:
    def st(ch, d, subj, body):
        return {"id": uuid.uuid4().hex[:6], "channel": ch, "delay_days": d, "subject": subj, "body": body}
    wa1 = ("Hola {{firstName}} 👋\n\nVi {{companyName}} y te digo algo directo: hoy muchos clientes te buscan en internet y no encuentran una web que convierta visitas en pedidos o reservas.\n\n"
           "Creo páginas y menús digitales enfocados en eso y en pocos días puedo mostrarte una versión pensada para tu negocio. ¿Te la envío?")
    wa2 = "Hola {{firstName}}, retomo mi mensaje de hace unos días sobre la web para {{companyName}}. ¿Te muestro una idea sin compromiso?"
    wa3 = "{{firstName}}, último mensaje de mi parte 🙌 Si más adelante quieres ver la propuesta para {{companyName}}, me escribes y te la envío."
    em1 = ("¿Le suena una web que traiga más clientes a {{companyName}}?",
           "Hola {{firstName}},\n\nVi {{companyName}} en Google Maps y creo que una página enfocada en convertir visitas en pedidos o reservas puede ayudarles bastante.\n\n¿Te muestro una idea pensada para tu negocio?\n\n{{signature}}")
    em2 = ("¿Lo vemos, {{firstName}}?", "Hola {{firstName}}, solo retomo mi mensaje anterior. Si no es prioridad ahora, no pasa nada.\n\n{{signature}}")
    if channel == "email":
        return [st("email", 3, *em1), st("email", 4, *em2), st("email", 7, "Último aviso para {{companyName}}", "Hola {{firstName}}, cierro mi seguimiento por aquí. Quedo atento si quieres ver la propuesta.\n\n{{signature}}")]
    if channel == "both":
        return [st("email", 3, *em1), st("whatsapp", 4, "", wa2), st("email", 7, *em2)]
    return [st("whatsapp", 3, "", wa1), st("whatsapp", 4, "", wa2), st("whatsapp", 7, "", wa3)]


@router.post("/campaigns/quick", tags=["campaigns"])
def quick_campaign(body: QuickIn):
    """Engage → 'Lanzar como campaña': crea la lista con los leads elegidos y la campaña con una secuencia base."""
    if body.channel not in ("whatsapp", "email", "both"):
        raise HTTPException(400, "Canal inválido")
    leads, seen = [], set()
    for l in body.leads:
        rec = {k: l.get(k) for k in ("name", "phone", "email", "category", "zone", "website", "contact", "score", "priority") if l.get(k) is not None}
        rec["phone"], rec["email"] = norm_phone(l.get("phone")), norm_email(l.get("email"))
        if body.channel == "whatsapp" and not rec["phone"]:
            continue
        if body.channel == "email" and not rec["email"]:
            continue
        if not (rec["phone"] or rec["email"]):
            continue
        k = lead_key(rec)
        if k and k not in seen:
            seen.add(k)
            leads.append(rec)
    if not leads:
        raise HTTPException(400, "Ninguno de los leads elegidos tiene teléfono/email para ese canal")

    label = {"whatsapp": "WhatsApp", "email": "Gmail", "both": "Gmail + WhatsApp"}[body.channel]
    name = (body.name or f"Campaña {label} · {datetime.now().strftime('%d %b')}").strip()
    lst = {"id": "i_" + uuid.uuid4().hex[:8], "name": name, "source": "selection", "created_at": _iso(_now()), "leads": leads}
    with _lock:
        lists = _saved_lists()
        lists.append(lst)
        _write(LISTS_FILE, lists)

    c = {
        "id": "c_" + uuid.uuid4().hex[:8], "name": name, "status": "draft", "list_id": lst["id"],
        "steps": _preset_steps(body.channel), "schedule": dict(DEFAULT_SCHEDULE),
        "variables": {"senderName": "Tu nombre", "signature": "Saludos,\nTu nombre"},
        "created_at": _iso(_now()),
    }
    _save_campaign(c)
    _enroll(c, lst["id"])
    return {**c, "enrolled": len(leads), "skipped": len(body.leads) - len(leads)}


@router.get("/campaigns/{cid}", tags=["campaigns"])
def get_campaign(cid: str):
    return _get_campaign(cid)


@router.put("/campaigns/{cid}", tags=["campaigns"])
def update_campaign(cid: str, body: CampaignIn):
    c = _get_campaign(cid)
    if body.name is not None:
        c["name"] = body.name
    if body.steps is not None:
        c["steps"] = _validate_steps(body.steps)
    if body.schedule is not None:
        c["schedule"] = {**DEFAULT_SCHEDULE, **body.schedule}
    if body.variables is not None:
        c["variables"] = body.variables
    if body.email_account_ids is not None:
        c["email_account_ids"] = body.email_account_ids
    if body.account_strategy is not None:
        c["account_strategy"] = body.account_strategy
    _save_campaign(c)
    return c


@router.delete("/campaigns/{cid}", tags=["campaigns"])
def delete_campaign(cid: str):
    with _lock:
        _write(CAMP_FILE, [c for c in _campaigns() if c["id"] != cid])
        enr = _enrollments()
        enr.pop(cid, None)
        _write(ENROLL_FILE, enr)
    return {"ok": True}


@router.post("/campaigns/{cid}/start", tags=["campaigns"])
def start_campaign(cid: str):
    c = _get_campaign(cid)
    if not _enrollments().get(cid):
        raise HTTPException(400, "Añade leads a la campaña antes de iniciarla")
    if not c["steps"]:
        raise HTTPException(400, "La campaña no tiene pasos")
    c["status"] = "active"
    _save_campaign(c)
    return c


@router.post("/campaigns/{cid}/pause", tags=["campaigns"])
def pause_campaign(cid: str):
    c = _get_campaign(cid)
    c["status"] = "paused"
    _save_campaign(c)
    return c


# ── Leads dentro de la campaña ───────────────────────────────────────────────
def _enroll(c: dict, list_id: str) -> int:
    lst = _get_list(list_id)
    added = 0
    with _lock:
        enr = _enrollments()
        bucket = enr.setdefault(c["id"], {})
        for l in lst.get("leads", []):
            k = lead_key(l)
            if not k or k in bucket:
                continue
            snap = {f: l.get(f) for f in ("name", "phone", "email", "category", "zone", "website", "contact", "extra", "score", "priority") if l.get(f) is not None}
            snap["phone"], snap["email"] = norm_phone(l.get("phone")), norm_email(l.get("email"))
            bucket[k] = {"lead": snap, "step": 0, "next_at": _iso(_now()), "status": "active", "history": []}
            added += 1
        _write(ENROLL_FILE, enr)
    return added


class AddLeadsIn(BaseModel):
    list_id: str


@router.post("/campaigns/{cid}/leads", tags=["campaigns"])
def add_leads(cid: str, body: AddLeadsIn):
    c = _get_campaign(cid)
    c["list_id"] = body.list_id
    _save_campaign(c)
    return {"ok": True, "added": _enroll(c, body.list_id)}


@router.get("/campaigns/{cid}/leads", tags=["campaigns"])
def campaign_leads(cid: str):
    _get_campaign(cid)
    out = []
    for k, e in _enrollments().get(cid, {}).items():
        out.append({
            "key": k, "name": e["lead"].get("name"), "phone": e["lead"].get("phone"), "email": e["lead"].get("email"),
            "status": e["status"], "step": e["step"], "next_at": e.get("next_at"),
            "last_event": (e["history"][-1] if e["history"] else None),
        })
    return out


class LeadStatusIn(BaseModel):
    status: str      # active | replied | stopped


@router.post("/campaigns/{cid}/leads/{key:path}/status", tags=["campaigns"])
def set_enrollment_status(cid: str, key: str, body: LeadStatusIn):
    if body.status not in ("active", "replied", "stopped"):
        raise HTTPException(400, "status inválido")
    with _lock:
        enr = _enrollments()
        e = enr.get(cid, {}).get(key)
        if not e:
            raise HTTPException(404, "Lead no está en la campaña")
        e["status"] = body.status
        if body.status == "replied":
            e["replied_at"] = _iso(_now())
            e["replied_at_step"] = max(0, e["step"] - 1)
        if body.status == "active":
            e["next_at"] = _iso(_now())
        _write(ENROLL_FILE, enr)
    return {"ok": True}


@router.delete("/campaigns/{cid}/leads/{key:path}", tags=["campaigns"])
def remove_enrollment(cid: str, key: str):
    with _lock:
        enr = _enrollments()
        enr.get(cid, {}).pop(key, None)
        _write(ENROLL_FILE, enr)
    return {"ok": True}


# ── Vista previa con variables ───────────────────────────────────────────────
class PreviewIn(BaseModel):
    step_id: str
    lead_key: Optional[str] = None


@router.get("/variables", tags=["campaigns"])
def variables():
    return BUILTIN_VARS


@router.post("/campaigns/{cid}/preview", tags=["campaigns"])
def preview(cid: str, body: PreviewIn):
    c = _get_campaign(cid)
    step = next((s for s in c["steps"] if s["id"] == body.step_id), None)
    if not step:
        raise HTTPException(404, "Paso no encontrado")
    enr = _enrollments().get(cid, {})
    e = enr.get(body.lead_key) if body.lead_key else next(iter(enr.values()), None)
    lead = e["lead"] if e else {"name": "Restaurante El Sabor - Sede Norte", "category": "Restaurante", "zone": "Cali, Colombia"}
    v = build_vars(lead, c)
    subj, m1 = render(step.get("subject", ""), v)
    body_txt, m2 = render(step.get("body", ""), v)
    return {"lead": lead.get("name"), "subject": subj, "body": body_txt, "missing": sorted(set(m1 + m2))}


# ═════════════════════════════════════════════════════════════════════════════
#  ANALÍTICAS
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/campaigns/{cid}/analytics", tags=["campaigns"])
def analytics(cid: str):
    c = _get_campaign(cid)
    enr = _enrollments().get(cid, {})
    rows = [r for r in _read(SENDLOG_FILE, []) if r["campaign_id"] == cid]
    ok = [r for r in rows if r.get("ok")]
    states = Counter(e["status"] for e in enr.values())

    # aperturas (solo email; requiere TRACKING_BASE público, ver README)
    opened = set()
    for ev in _read(TRACK_FILE, []):
        if ev.get("event") == "open" and str(ev.get("lead_id", "")).startswith(cid + "__"):
            opened.add(ev["lead_id"])

    per_step = []
    for i, s in enumerate(c["steps"]):
        sent = [r for r in ok if r["step"] == i]
        replies = sum(1 for e in enr.values() if e["status"] == "replied" and e.get("replied_at_step") == i)
        per_step.append({
            "index": i, "id": s["id"], "channel": s["channel"],
            "sent": len(sent), "errors": sum(1 for r in rows if r["step"] == i and not r.get("ok")),
            "replies": replies,
            "reply_rate": round(replies / len(sent) * 100, 1) if sent else 0,
        })

    today = datetime.now(ZoneInfo(c["schedule"].get("tz", "America/Bogota"))).date()
    series = []
    for d in range(13, -1, -1):
        day = today - timedelta(days=d)
        n = sum(1 for r in ok if _local_date(r["ts"], c) == day)
        series.append({"date": day.isoformat(), "sent": n})

    contacted = len({r["lead_key"] for r in ok})

    by_account = {}
    for r in ok:
        if r.get("account_email"):
            by_account.setdefault(r["account_email"], 0)
            by_account[r["account_email"]] += 1
    return {
        "leads": len(enr),
        "contacted": contacted,
        "sent": len(ok),
        "sent_email": sum(1 for r in ok if r["channel"] == "email"),
        "sent_whatsapp": sum(1 for r in ok if r["channel"] == "whatsapp"),
        "errors": len(rows) - len(ok),
        "opened": len(opened),
        "replied": states.get("replied", 0),
        "reply_rate": round(states.get("replied", 0) / contacted * 100, 1) if contacted else 0,
        "active": states.get("active", 0),
        "completed": states.get("completed", 0),
        "stopped": states.get("stopped", 0),
        "per_step": per_step,
        "series": series,
        "sent_today": _sent_today(rows, c),
        "by_account": by_account,
    }


def _local_date(ts: str, c: dict):
    dt = _parse(ts)
    return dt.astimezone(ZoneInfo(c["schedule"].get("tz", "America/Bogota"))).date() if dt else None


def _sent_today(rows: List[dict], c: dict) -> Dict[str, int]:
    today = datetime.now(ZoneInfo(c["schedule"].get("tz", "America/Bogota"))).date()
    out = {"email": 0, "whatsapp": 0}
    for r in rows:
        if r.get("ok") and _local_date(r["ts"], c) == today:
            out[r["channel"]] = out.get(r["channel"], 0) + 1
    return out


# ═════════════════════════════════════════════════════════════════════════════
#  SCHEDULER — envía solo los pasos que ya tocan, dentro del horario
# ═════════════════════════════════════════════════════════════════════════════
def in_window(sched: dict, now: Optional[datetime] = None) -> bool:
    tz = ZoneInfo(sched.get("tz", "America/Bogota"))
    local = (now or _now()).astimezone(tz)
    if local.weekday() not in sched.get("days", []):
        return False
    hh, mm = map(int, sched.get("start", "09:00").split(":"))
    eh, em = map(int, sched.get("end", "18:00").split(":"))
    return (hh, mm) <= (local.hour, local.minute) < (eh, em)


def _sync_replies_from_overlay(camp_id: str) -> None:
    """Si en el CRM marcas a alguien como Respondió/Interesado/Cliente/Descartado, su secuencia se detiene."""
    overlay = _read(STATUS_FILE, {})
    if not overlay:
        return
    with _lock:
        enr = _enrollments()
        changed = False
        for k, e in enr.get(camp_id, {}).items():
            if e["status"] != "active":
                continue
            st = overlay.get(e["lead"].get("phone") or "", {}).get("status")
            if st in ("replied", "interested", "won"):
                e["status"], e["replied_at"], e["replied_at_step"] = "replied", _iso(_now()), max(0, e["step"] - 1)
                changed = True
            elif st == "lost":
                e["status"] = "stopped"
                changed = True
        if changed:
            _write(ENROLL_FILE, enr)


_rr_cursor: Dict[str, int] = {}    # cursor por campaña para round-robin


def _send_email(c: dict, lead: dict, subject: str, body: str, tracking_id: str):
    """
    Devuelve (error|None, account|None).
    Reparte entre las cuentas asignadas a la campaña (o todas las habilitadas si no hay).
    """
    import email_accounts as EA
    acc_ids  = c.get("email_account_ids") or None
    strategy = c.get("account_strategy") or "least_used"

    cursor = _rr_cursor.get(c["id"], 0)
    acc, new_cursor = EA.pick_account(acc_ids, strategy, cursor)
    if strategy == "round_robin":
        _rr_cursor[c["id"]] = new_cursor

    if not acc:
        return "Sin cuentas disponibles (todas al límite diario o ninguna habilitada)", None

    err = EA.send_via_account(acc, lead["email"], subject, body, tracking_id)
    return err, acc

_wa_py_cache: Dict[str, str] = {}


def _wa_python() -> tuple[Optional[str], str]:
    """Busca un Python que tenga pywhatkit + pyautogui. Devuelve (ruta, motivo_si_falla)."""
    if _wa_py_cache.get("py"):
        return _wa_py_cache["py"], ""
    venv = os.path.join(WHATSAPP_DIR, "venv")
    venv_py = os.path.join(venv, "Scripts", "python.exe") if sys.platform == "win32" else os.path.join(venv, "bin", "python")
    cands = [c for c in (venv_py, sys.executable) if c and os.path.exists(c)]
    last = ""
    for py in cands:
        try:
            r = subprocess.run([py, "-c", "import pywhatkit, pyautogui"], capture_output=True, text=True, timeout=90)
        except Exception as e:
            last = str(e)
            continue
        if r.returncode == 0:
            _wa_py_cache["py"] = py
            return py, ""
        last = (r.stderr or "").strip().splitlines()[-1] if (r.stderr or "").strip() else "import falló"
    return None, last or "No encontré Python"


WA_FIX = "Falta pywhatkit. En una terminal:  cd ~/Desktop/LeadsBot-Pro/project && source .venv/bin/activate && pip install pywhatkit pyautogui   (usa el mismo entorno con el que arrancas el backend)"


def _send_whatsapp(lead: dict, body: str) -> Optional[str]:
    """Envía por WhatsApp Web con pywhatkit. Autónomo: no depende de WHATSAPP_IA/src ni de Ollama."""
    py, why = _wa_python()
    if not py:
        return f"{WA_FIX}  ·  detalle: {why}"
    code = ("import sys, pywhatkit as kit, pyautogui\n"
            "kit.sendwhatmsg_instantly(phone_no=sys.argv[1], message=sys.argv[2], wait_time=20, tab_close=True, close_time=3)\n"
            "pyautogui.press('enter')\n")
    with _wa_lock:
        try:
            r = subprocess.run([py, "-c", code, lead["phone"], body], capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            return "WhatsApp: tiempo agotado (¿WhatsApp Web está abierto y con sesión iniciada?)"
    if r.returncode != 0:
        return (r.stderr or r.stdout or "WhatsApp falló").strip()[-300:]
    try:                                            # compatible con el log que lee main.py para marcar 'Contactado'
        new = not os.path.exists(WHATSAPP_LOG)
        os.makedirs(os.path.dirname(WHATSAPP_LOG), exist_ok=True)
        with open(WHATSAPP_LOG, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["name", "phone"])
            w.writerow([lead.get("name", ""), lead["phone"]])
    except Exception:
        pass
    return None


@router.get("/channels/whatsapp/check", tags=["campaigns"])
def whatsapp_check():
    _wa_py_cache.clear()
    py, why = _wa_python()
    return {"ok": bool(py), "python": py, "error": None if py else why, "fix": None if py else WA_FIX}


class WaTestIn(BaseModel):
    phone: str
    message: str = "Prueba de Beacon AI ✅"


@router.post("/channels/whatsapp/test", tags=["campaigns"])
def whatsapp_test(body: WaTestIn):
    ph = norm_phone(body.phone)
    if not ph:
        raise HTTPException(400, "Teléfono inválido")
    err = _send_whatsapp({"phone": ph, "name": "Prueba"}, body.message)
    if err:
        raise HTTPException(500, err)
    return {"ok": True}


def _log_send(row: dict) -> None:
    with _lock:
        rows = _read(SENDLOG_FILE, [])
        rows.append(row)
        _write(SENDLOG_FILE, rows[-20000:])


def process_campaign(c: dict) -> int:
    """Un tick para una campaña. Devuelve cuántos mensajes intentó enviar."""
    import time as _t
    if c["status"] != "active" or not in_window(c["schedule"]):
        return 0
    _sync_replies_from_overlay(c["id"])

    sched, steps = c["schedule"], c["steps"]
    rows = _read(SENDLOG_FILE, [])
    today = _sent_today([r for r in rows if r["campaign_id"] == c["id"]], c)
    limits = {"email": sched["daily_limit_email"], "whatsapp": sched["daily_limit_whatsapp"]}
    gaps = {"email": sched["gap_email_sec"], "whatsapp": sched["gap_whatsapp_sec"]}
    now = _now()
    attempted = 0

    enr = _enrollments().get(c["id"], {})
    due = sorted(((k, e) for k, e in enr.items()
                  if e["status"] == "active" and (_parse(e.get("next_at")) or now) <= now),
                 key=lambda kv: kv[1].get("next_at") or "")

    for k, e in due:
        if e["step"] >= len(steps):
            _update_enrollment(c["id"], k, status="completed")
            continue
        step, lead = steps[e["step"]], e["lead"]
        ch = step["channel"]

        # no puede recibir este canal → salta al siguiente paso sin esperar
        if (ch == "email" and not lead.get("email")) or (ch == "whatsapp" and not lead.get("phone")):
            _advance(c, k, e, step, skipped=True)
            continue
        if today.get(ch, 0) >= limits[ch]:
            continue
        if _t.time() - _last_send.get(ch, 0) < gaps[ch]:
            continue

        v = build_vars(lead, c)
        subj, m1 = render(step.get("subject", ""), v)
        body, m2 = render(step.get("body", ""), v)
        miss = sorted(set(m1 + m2))
        row = {"ts": _iso(_now()), "campaign_id": c["id"], "lead_key": k, "lead": lead.get("name"),
               "step": e["step"], "channel": ch}
        if miss:
            _log_send({**row, "ok": False, "error": f"Variables sin valor: {', '.join(miss)}"})
            _advance(c, k, e, step, skipped=True)
            continue

        attempted += 1
        _last_send[ch] = _t.time()
        tracking_id = f"{c['id']}__{hashlib.md5(k.encode()).hexdigest()[:10]}"
        account = None
        try:
            if ch == "email":
                err, account = _send_email(c, lead, subj, body, tracking_id)
            else:
                err = _send_whatsapp(lead, body)
        except Exception as ex:
            err = str(ex)

        account_email = account["email"] if account else None
        if err:
            _log_send({**row, "ok": False, "error": err, "account_email": account_email})
            _update_enrollment(c["id"], k, history_add={"ts": row["ts"], "step": e["step"], "channel": ch,
                                                        "ok": False, "error": err, "account_email": account_email},
                               next_at=_iso(now + timedelta(hours=1)))
            log.error(f"[{c['name']}] ✗ {lead.get('name')} ({ch}): {err}")
        else:
            _log_send({**row, "ok": True, "account_email": account_email})
            today[ch] = today.get(ch, 0) + 1
            _advance(c, k, e, step, sent=True)
            log.info(f"[{c['name']}] ✓ paso {e['step'] + 1} ({ch}) → {lead.get('name')}"
                     + (f"  vía {account_email}" if account_email else ""))    
            return attempted


def _advance(c: dict, key: str, e: dict, step: dict, sent: bool = False, skipped: bool = False) -> None:
    nxt = e["step"] + 1
    done = nxt >= len(c["steps"])
    delay = 0 if skipped else float(step.get("delay_days", 0))
    _update_enrollment(
        c["id"], key,
        step=nxt,
        status="completed" if done else "active",
        next_at=_iso(_now() + timedelta(days=delay)),
        history_add={"ts": _iso(_now()), "step": e["step"], "channel": step["channel"], "ok": sent, "skipped": skipped},
    )


def _update_enrollment(cid: str, key: str, history_add: Optional[dict] = None, **fields) -> None:
    with _lock:
        enr = _enrollments()
        e = enr.get(cid, {}).get(key)
        if not e:
            return
        e.update(fields)
        if history_add:
            e["history"].append(history_add)
        _write(ENROLL_FILE, enr)


async def scheduler_loop(interval: int = 30) -> None:
    log.info("⏱ Scheduler de campañas iniciado")
    while True:
        try:
            for c in _campaigns():
                if c["status"] == "active":
                    await asyncio.to_thread(process_campaign, c)
        except Exception as e:
            log.exception(f"Scheduler: {e}")
        await asyncio.sleep(interval)
