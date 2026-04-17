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
#  CONFIG SMTP — usar variables de entorno
# ─────────────────────────────────────────────
SMTP_HOST     = os.getenv("SMTP_HOST",     "smtp-relay.brevo.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER",     "")   # tu@gmail.com
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")   # app password de Google
FROM_NAME     = os.getenv("FROM_NAME",     "Tu Nombre")
TRACKING_BASE = os.getenv("TRACKING_BASE", "https://tudominio.com/track")

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
        self._validate_config()

    def send_batch(self, leads: list[dict]) -> list[SendResult]:
        results = []
        sent    = 0

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            log.info(f"✅ SMTP conectado como {SMTP_USER}")

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

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            return self._send_one(server, lead, email)

    # ── construcción del email ────────────────────────────────────────────
    def _send_one(self, server: smtplib.SMTP, lead: dict, to_email: str) -> SendResult:
        try:
            msg = self._build_mime(lead, to_email)
            server.sendmail(SMTP_USER, to_email, msg.as_string())
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
        msg["From"]       = f"{FROM_NAME} <{SMTP_USER}>"
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
        if not SMTP_USER or not SMTP_PASSWORD:
            raise ValueError(
                "Faltan SMTP_USER y/o SMTP_PASSWORD en variables de entorno.\n"
                "Para Gmail: activa 'Contraseñas de aplicaciones' en tu cuenta."
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