from __future__ import annotations
# sender.py
import os
import json
import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  CONFIG SMTP — primero busca email_settings.json (configurado desde
#  la pestaña "Cuentas de Email" del dashboard), si no existe usa .env
# ─────────────────────────────────────────────
SETTINGS_FILE = "email_settings.json"
TRACKING_BASE = os.getenv("TRACKING_BASE", "https://tudominio.com/track")

def _load_smtp_config() -> dict:
    cfg = {
        "smtp_host":    os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "smtp_port":    int(os.getenv("SMTP_PORT", "587")),
        "email":        os.getenv("SMTP_USER", ""),
        "app_password": os.getenv("SMTP_PASSWORD", ""),
        "from_name":    os.getenv("FROM_NAME", "Tu Nombre"),
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                saved = json.load(f)
            for k in cfg:
                if saved.get(k):
                    cfg[k] = saved[k]
        except Exception as e:
            log.warning(f"No pude leer {SETTINGS_FILE}: {e}")
    return cfg

DELAY_BETWEEN_EMAILS = 45   # segundos entre envíos (evitar spam filters)
MAX_PER_DAY          = 50   # límite diario


# ─────────────────────────────────────────────
#  MODELO
# ─────────────────────────────────────────────
@dataclass
class SendResult:
    lead_name:  str
    email:      str
    success:    bool
    error:      Optional[str] = None
    message_id: Optional[str] = None


# ─────────────────────────────────────────────
#  SENDER
# ─────────────────────────────────────────────
class EmailSender:

    def __init__(self):
        cfg = _load_smtp_config()
        self.smtp_host     = cfg["smtp_host"]
        self.smtp_port     = cfg["smtp_port"]
        self.smtp_user     = cfg["email"]
        self.smtp_password = cfg["app_password"]
        self.from_name     = cfg["from_name"]
        self._validate_config()

    def send_batch(self, leads: list[dict]) -> list[SendResult]:
        results = []
        sent    = 0

        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            log.info(f"✅ SMTP conectado como {self.smtp_user}")

            for lead in leads:
                if sent >= MAX_PER_DAY:
                    log.warning(f"⚠ Límite diario ({MAX_PER_DAY}) alcanzado")
                    break

                email = self._extract_email(lead)
                if not email:
                    log.warning(f"  skip {lead['name']}: sin email")
                    continue

                result = self._send_one(server, lead, email)
                results.append(result)

                if result.success:
                    sent += 1
                    log.info(f"  ✉ enviado → {lead['name']} <{email}>")
                    time.sleep(DELAY_BETWEEN_EMAILS)
                else:
                    log.error(f"  ✗ error → {lead['name']}: {result.error}")

        return results

    def send_one(self, lead: dict) -> SendResult:
        """Envío individual para el worker."""
        email = self._extract_email(lead)
        if not email:
            return SendResult(lead["name"], "", False, "sin email")

        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            return self._send_one(server, lead, email)

    # ── construcción del email ────────────────────────────────────────────
    def _send_one(self, server: smtplib.SMTP, lead: dict, to_email: str) -> SendResult:
        try:
            msg = self._build_mime(lead, to_email)
            server.sendmail(self.smtp_user, to_email, msg.as_string())
            return SendResult(
                lead_name  = lead["name"],
                email      = to_email,
                success    = True,
                message_id = msg["Message-ID"],
            )
        except Exception as e:
            return SendResult(lead["name"], to_email, False, str(e))

    def _build_mime(self, lead: dict, to_email: str) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["From"]       = f"{self.from_name} <{self.smtp_user}>"
        msg["To"]         = to_email
        msg["Subject"]    = lead.get("email_subject", "Hola desde nuestra agencia")
        msg["Message-ID"] = f"<{int(time.time())}.{lead['name'][:8]}@agencia>"

        body_text = lead.get("email_body", "")
        tracking_pixel = self._tracking_pixel(lead)

        # versión plain text
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        # versión HTML con pixel de tracking
        html_body = self._to_html(body_text, tracking_pixel)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        return msg

    def _to_html(self, plain: str, pixel: str) -> str:
        paragraphs = "".join(f"<p>{p}</p>" for p in plain.split("\n") if p.strip())
        return f"""
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;font-size:15px;color:#222;max-width:560px">
{paragraphs}
{pixel}
</body></html>"""

    def _tracking_pixel(self, lead: dict) -> str:
        lead_id = lead.get("id", lead["name"].replace(" ", "_")[:20])
        url = f"{TRACKING_BASE}/open/{lead_id}"
        return f'<img src="{url}" width="1" height="1" style="display:none" />'

    # ── helpers ───────────────────────────────────────────────────────────
    def _extract_email(self, lead: dict) -> Optional[str]:
        """
        Intenta obtener email del lead.
        En el flujo real vendría del scraper o de hunter.io.
        """
        return lead.get("email")

    def _validate_config(self) -> None:
        if not self.smtp_user or not self.smtp_password:
            raise ValueError(
                "No hay una cuenta de Gmail conectada. Ve a la pestaña "
                "'Cuentas de Email' del dashboard y conéctala (usa una "
                "contraseña de aplicación de Google, no tu contraseña normal)."
            )


# ─────────────────────────────────────────────
#  I/O
# ─────────────────────────────────────────────
def load_ready(path: str = "leads_ready.json") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def save_results(results: list[SendResult], path: str = "send_results.json") -> None:
    import dataclasses
    data = [dataclasses.asdict(r) for r in results]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    ok  = sum(1 for r in results if r.success)
    err = len(results) - ok
    print(f"💾 Resultados: {ok} enviados, {err} errores → {path}")


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    leads   = load_ready()
    sender  = EmailSender()
    results = sender.send_batch(leads)
    save_results(results)