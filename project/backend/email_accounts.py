# email_accounts.py
# Multi-cuenta de Gmail con rotación y límites diarios por cuenta.
from __future__ import annotations

import json
import logging
import os
import random as _r
import smtplib
import threading
import uuid
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from typing import List, Optional

log = logging.getLogger("email_accounts")

ACCOUNTS_FILE = "email_accounts.json"
LEGACY_FILE   = "email_settings.json"
_lock = threading.RLock()


def _today() -> str:
    return date.today().isoformat()


def _read() -> dict:
    with _lock:
        if os.path.exists(ACCOUNTS_FILE):
            try:
                with open(ACCOUNTS_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "accounts" in data:
                        return data
                    if isinstance(data, list):
                        return {"accounts": data}
            except Exception as e:
                log.warning(f"No pude leer {ACCOUNTS_FILE}: {e}")
        # migración desde email_settings.json (formato viejo, una sola cuenta)
        if os.path.exists(LEGACY_FILE):
            try:
                with open(LEGACY_FILE, encoding="utf-8") as f:
                    legacy = json.load(f)
                if legacy.get("email"):
                    acc = {
                        "id": "acc_" + uuid.uuid4().hex[:8],
                        "email": legacy.get("email"),
                        "app_password": legacy.get("app_password", ""),
                        "smtp_host": legacy.get("smtp_host") or "smtp.gmail.com",
                        "smtp_port": int(legacy.get("smtp_port") or 587),
                        "from_name": legacy.get("from_name") or "Tu Nombre",
                        "daily_limit": 40,
                        "enabled": True,
                        "primary": True,
                        "created_at": datetime.utcnow().isoformat(),
                        "sent_today": 0,
                        "last_sent_date": _today(),
                    }
                    data = {"accounts": [acc]}
                    _write(data)
                    log.info(f"Migrada cuenta legacy: {acc['email']}")
                    return data
            except Exception as e:
                log.warning(f"Migración legacy falló: {e}")
        return {"accounts": []}


def _write(data: dict) -> None:
    with _lock:
        tmp = ACCOUNTS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ACCOUNTS_FILE)


def _sync_legacy() -> None:
    """Mantiene email_settings.json con la cuenta primaria para que sender.py siga funcionando."""
    primary = get_primary()
    try:
        if primary:
            with open(LEGACY_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "smtp_host":    primary["smtp_host"],
                    "smtp_port":    primary["smtp_port"],
                    "email":        primary["email"],
                    "app_password": primary["app_password"],
                    "from_name":    primary["from_name"],
                }, f, ensure_ascii=False, indent=2)
        else:
            if os.path.exists(LEGACY_FILE):
                os.remove(LEGACY_FILE)
    except Exception as e:
        log.warning(f"No pude sincronizar {LEGACY_FILE}: {e}")


def _reset_daily_if_needed(acc: dict) -> None:
    if acc.get("last_sent_date") != _today():
        acc["sent_today"] = 0
        acc["last_sent_date"] = _today()


# ── API pública ────────────────────────────────────────────────────────────
def list_accounts(include_secrets: bool = False) -> List[dict]:
    data = _read()
    changed = False
    out = []
    for a in data["accounts"]:
        before = (a.get("last_sent_date"), a.get("sent_today"))
        _reset_daily_if_needed(a)
        if (a.get("last_sent_date"), a.get("sent_today")) != before:
            changed = True
        d = dict(a)
        if not include_secrets:
            d.pop("app_password", None)
            d["app_password_masked"] = "••••••••" if a.get("app_password") else ""
        out.append(d)
    if changed:
        _write(data)
    return out


def get_account(acc_id: str) -> Optional[dict]:
    for a in _read()["accounts"]:
        if a["id"] == acc_id:
            return a
    return None


def get_primary() -> Optional[dict]:
    accounts = _read()["accounts"]
    for a in accounts:
        if a.get("primary"):
            return a
    return accounts[0] if accounts else None


def add_account(email: str, app_password: str, from_name: str = "Tu Nombre",
                smtp_host: str = "smtp.gmail.com", smtp_port: int = 587,
                daily_limit: int = 40) -> dict:
    data = _read()
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("Email inválido")
    for a in data["accounts"]:
        if a["email"].lower() == email:
            raise ValueError(f"La cuenta {email} ya está registrada")
    is_first = len(data["accounts"]) == 0
    acc = {
        "id": "acc_" + uuid.uuid4().hex[:8],
        "email": email,
        "app_password": app_password,
        "smtp_host": smtp_host or "smtp.gmail.com",
        "smtp_port": int(smtp_port or 587),
        "from_name": from_name or "Tu Nombre",
        "daily_limit": int(daily_limit or 40),
        "enabled": True,
        "primary": is_first,
        "created_at": datetime.utcnow().isoformat(),
        "sent_today": 0,
        "last_sent_date": _today(),
    }
    data["accounts"].append(acc)
    _write(data)
    _sync_legacy()
    return {k: v for k, v in acc.items() if k != "app_password"}


def update_account(acc_id: str, **fields) -> dict:
    data = _read()
    for a in data["accounts"]:
        if a["id"] == acc_id:
            for k in ("from_name", "daily_limit", "enabled", "smtp_host", "smtp_port"):
                if k in fields and fields[k] is not None:
                    a[k] = fields[k]
            _write(data)
            _sync_legacy()
            return {k: v for k, v in a.items() if k != "app_password"}
    raise KeyError("Cuenta no encontrada")


def delete_account(acc_id: str) -> None:
    data = _read()
    before = len(data["accounts"])
    data["accounts"] = [a for a in data["accounts"] if a["id"] != acc_id]
    if len(data["accounts"]) == before:
        raise KeyError("Cuenta no encontrada")
    if data["accounts"] and not any(a.get("primary") for a in data["accounts"]):
        data["accounts"][0]["primary"] = True
    _write(data)
    _sync_legacy()


def mark_sent(acc_id: str) -> None:
    data = _read()
    for a in data["accounts"]:
        if a["id"] == acc_id:
            _reset_daily_if_needed(a)
            a["sent_today"] = int(a.get("sent_today") or 0) + 1
            a["last_sent_date"] = _today()
            _write(data)
            return


def available_accounts(account_ids: Optional[List[str]] = None) -> List[dict]:
    """Cuentas habilitadas con cupo diario restante. Incluye password (uso interno)."""
    data = _read()
    out = []
    for a in data["accounts"]:
        _reset_daily_if_needed(a)
        if account_ids and a["id"] not in account_ids:
            continue
        if not a.get("enabled", True):
            continue
        if int(a.get("sent_today") or 0) >= int(a.get("daily_limit") or 40):
            continue
        out.append(a)
    return out


def pick_account(account_ids: Optional[List[str]], strategy: str = "least_used",
                 cursor: int = 0):
    """Devuelve (cuenta|None, nuevo_cursor)."""
    avail = available_accounts(account_ids)
    if not avail:
        return None, cursor
    if strategy == "round_robin":
        avail_sorted = sorted(avail, key=lambda a: a["id"])
        chosen = avail_sorted[cursor % len(avail_sorted)]
        return chosen, cursor + 1
    if strategy == "random":
        return _r.choice(avail), cursor
    avail.sort(key=lambda a: (int(a.get("sent_today") or 0), a["id"]))
    return avail[0], cursor


def send_via_account(account: dict, to_email: str, subject: str, body: str,
                     tracking_id: Optional[str] = None) -> Optional[str]:
    """
    Envía un correo con la cuenta dada.
    Devuelve None si OK, o string con el error.
    """
    from_name = account.get("from_name") or "Tu Nombre"
    sender    = account["email"]

    import html as _html
    body_html = _html.escape(body or "").replace("\n", "<br>")
    base = os.getenv("TRACKING_BASE", "").rstrip("/")
    if tracking_id and base:
        body_html += (f'<img src="{base}/track/open/{tracking_id}" '
                      f'width="1" height="1" style="display:none" alt="" />')

    msg = MIMEMultipart("alternative")
    msg["Subject"]    = subject or "(sin asunto)"
    msg["From"]       = formataddr((from_name, sender))
    msg["To"]         = to_email
    msg["Message-ID"] = make_msgid()
    msg.attach(MIMEText(body or "", "plain", "utf-8"))
    msg.attach(MIMEText(
        "<html><body style='font-family:system-ui,-apple-system,sans-serif;"
        "font-size:15px;color:#111;line-height:1.65'>" + body_html + "</body></html>",
        "html", "utf-8",
    ))

    try:
        with smtplib.SMTP(account["smtp_host"], int(account["smtp_port"]), timeout=25) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(sender, account["app_password"])
            smtp.sendmail(sender, [to_email], msg.as_string())
        mark_sent(account["id"])
        return None
    except smtplib.SMTPAuthenticationError as e:
        raw = e.smtp_error.decode() if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
        return f"SMTP auth ({sender}): {raw}"
    except smtplib.SMTPRecipientsRefused as e:
        return f"Destinatario rechazado: {list(e.recipients.values())[0]}"
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def test_account(acc_id: str) -> dict:
    acc = get_account(acc_id)
    if not acc:
        return {"ok": False, "error": "Cuenta no encontrada"}
    try:
        with smtplib.SMTP(acc["smtp_host"], int(acc["smtp_port"]), timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(acc["email"], acc["app_password"])
        return {"ok": True, "email": acc["email"]}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "error": "Auth falló. Revisa la contraseña de aplicación."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}