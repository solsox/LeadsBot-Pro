from __future__ import annotations

# generator.py
import json
import os
import time
import logging
from dataclasses import dataclass
from typing import Optional
from openai import OpenAI

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
MODEL          = "phi3"   # barato y suficiente para esto
DELAY_BETWEEN  = 0.3             # segundos entre llamadas a la API


# ─────────────────────────────────────────────
#  MODELO
# ─────────────────────────────────────────────
@dataclass
class GeneratedMessage:
    lead_name:   str
    subject:     str
    body:        str
    whatsapp:    str   # versión corta para WhatsApp
    language:    str = "es"


# ─────────────────────────────────────────────
#  GENERADOR
# ─────────────────────────────────────────────
class MessageGenerator:

    def __init__(self):
     self.client = OpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama",
    )

    def generate(self, lead: dict) -> Optional[GeneratedMessage]:
        context = self._build_context(lead)
        try:
            result = self._call_api(context)
            return self._parse(lead["name"], result)
        except Exception as e:
            log.error(f"Error generando mensaje para {lead['name']}: {e}")
            return None

    def generate_batch(self, leads: list[dict]) -> list[dict]:
        """Genera mensajes para todos los leads y devuelve leads enriquecidos."""
        enriched = []
        for i, lead in enumerate(leads):
            log.info(f"[{i+1}/{len(leads)}] Generando para: {lead['name']}")
            msg = self.generate(lead)
            if msg:
                lead["email_subject"] = msg.subject
                lead["email_body"]    = msg.body
                lead["whatsapp_msg"]  = msg.whatsapp
                enriched.append(lead)
            time.sleep(DELAY_BETWEEN)
        return enriched

    # ── construcción del prompt ───────────────────────────────────────────
    def _build_context(self, lead: dict) -> str:
        web_status = (
            "no tiene página web"
            if not lead.get("website")
            else f"su web actual es {lead['website']} (plataforma genérica, necesita mejora)"
        )
        rating_note = (
            f"tiene {lead['rating']} estrellas en Google Maps con {lead['reviews']} reseñas"
            if lead.get("rating") else "no tiene reseñas visibles"
        )

        return f"""
Negocio: {lead['name']}
Categoría: {lead.get('category', 'negocio local')}
Zona: {lead.get('zone', '')}
Web: {web_status}
Reseñas: {rating_note}
Teléfono: {lead.get('phone', 'no disponible')}
""".strip()

    # ── llamada a OpenAI ──────────────────────────────────────────────────
    def _call_api(self, context: str) -> str:
        system = """
Eres un experto en ventas B2B para una agencia de desarrollo web.
Tu trabajo es escribir mensajes de prospección CORTOS, personalizados y directos.

REGLAS ESTRICTAS:
- Nunca uses plantillas genéricas. El negocio debe sentir que investigaste su caso.
- Señala UN problema específico que tiene (sin web, web en Wix, pocas reseñas).
- Propón UNA solución concreta (web profesional, rediseño, SEO local).
- Tono: cercano, profesional, sin ser agresivo ni desesperado.
- NO uses palabras como "potenciar", "impulsar", "sinergia", "robusto".
- Email: máximo 5 oraciones. Asunto: máximo 8 palabras.
- WhatsApp: máximo 2 oraciones, muy casual.

Responde ÚNICAMENTE en este JSON (sin markdown):
{
  "subject": "...",
  "body": "...",
  "whatsapp": "..."
}
"""
        response = self.client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": f"Escribe el mensaje para este negocio:\n{context}"}
            ],
            temperature=0.85,
            max_tokens=400,
        )
        return response.choices[0].message.content.strip()

    # ── parseo del JSON devuelto ──────────────────────────────────────────
    def _parse(self, name: str, raw: str) -> Optional[GeneratedMessage]:
        try:
            # limpiar posibles bloques ```json
            clean = raw.replace("```json", "").replace("```", "").strip()
            data  = json.loads(clean)
            return GeneratedMessage(
                lead_name  = name,
                subject    = data["subject"],
                body       = data["body"],
                whatsapp   = data["whatsapp"],
            )
        except Exception as e:
            log.error(f"Error parseando respuesta OpenAI: {e}\nRaw: {raw}")
            return None


# ─────────────────────────────────────────────
#  I/O
# ─────────────────────────────────────────────
def load_scored(path: str = "leads_scored.json") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def save_with_messages(leads: list[dict], path: str = "leads_ready.json") -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(leads, f, ensure_ascii=False, indent=2)
    print(f"💾 {len(leads)} leads con mensajes guardados en {path}")


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    leads     = load_scored()
    generator = MessageGenerator()
    ready     = generator.generate_batch(leads)
    save_with_messages(ready)

    # preview del primero
    if ready:
        l = ready[0]
        print(f"\n--- PREVIEW: {l['name']} ---")
        print(f"ASUNTO: {l['email_subject']}")
        print(f"EMAIL:\n{l['email_body']}")
        print(f"WHATSAPP: {l['whatsapp_msg']}")