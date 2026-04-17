from __future__ import annotations
# scoring.py
import json
import re
from dataclasses import dataclass, field
from typing import Optional

# ─────────────────────────────────────────────
#  CONFIGURACIÓN DE SCORING — edita aquí
# ─────────────────────────────────────────────
MIN_SCORE = 5  # score mínimo para guardar el lead

WEAK_PLATFORMS = [
    "wix.com", "facebook.com", "instagram.com",
    "linktr.ee", "linktree.com", "negocio.site",
    "sites.google.com", "weebly.com", "jimdo.com",
    "wordpress.com", "blogspot.com",
]

BAD_RATING_THRESHOLD = 3.5   # rating por debajo de esto suma puntos
LOW_REVIEWS_THRESHOLD = 20   # pocas reseñas = poca presencia digital


# ─────────────────────────────────────────────
#  MODELO
# ─────────────────────────────────────────────
@dataclass
class ScoredLead:
    # datos originales
    name:     str
    address:  str
    phone:    Optional[str]
    website:  Optional[str]
    rating:   Optional[float]
    reviews:  Optional[int]
    category: Optional[str]
    zone:     str
    query:    str
    maps_url: Optional[str]
    # scoring
    score:        int = 0
    priority:     str = "low"       # high | medium | low
    score_reasons: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────
#  MOTOR DE SCORING
# ─────────────────────────────────────────────
class LeadScorer:

    def score(self, lead: dict) -> ScoredLead:
        sl = ScoredLead(**lead, score=0, priority="low", score_reasons=[])
        self._apply_rules(sl)
        sl.priority = self._priority(sl.score)
        return sl

    def score_all(self, leads: list[dict]) -> list[ScoredLead]:
        scored = [self.score(l) for l in leads]
        scored.sort(key=lambda x: x.score, reverse=True)
        return [s for s in scored if s.score >= MIN_SCORE]

    # ── reglas individuales ───────────────────────────────────────────────
    def _apply_rules(self, sl: ScoredLead) -> None:

        # R1: sin web → máxima prioridad
        if not sl.website:
            sl.score += 5
            sl.score_reasons.append("sin web (+5)")

        # R2: web en plataforma genérica
        elif self._is_weak_platform(sl.website):
            platform = self._detect_platform(sl.website)
            sl.score += 3
            sl.score_reasons.append(f"web en {platform} (+3)")

        # R3: web existe pero parece abandonada (dominio muy corto, sin TLD propio)
        elif self._looks_abandoned(sl.website):
            sl.score += 2
            sl.score_reasons.append("web posiblemente abandonada (+2)")

        # R4: rating bajo → dolor evidente
        if sl.rating and sl.rating < BAD_RATING_THRESHOLD:
            sl.score += 2
            sl.score_reasons.append(f"rating bajo {sl.rating} (+2)")

        # R5: pocas reseñas → poca visibilidad online
        if sl.reviews is not None and sl.reviews < LOW_REVIEWS_THRESHOLD:
            sl.score += 2
            sl.score_reasons.append(f"pocas reseñas ({sl.reviews}) (+2)")

        # R6: tiene teléfono directo → más fácil contactar
        if sl.phone:
            sl.score += 1
            sl.score_reasons.append("teléfono disponible (+1)")

        # R7: sin teléfono → más dependiente de web
        if not sl.phone and not sl.website:
            sl.score += 1
            sl.score_reasons.append("sin tel ni web (+1 extra)")

        # R8: categorías de alto valor (negocios locales con alto ticket)
        if sl.category and self._is_high_value_category(sl.category):
            sl.score += 1
            sl.score_reasons.append(f"categoría high-value (+1)")

        # R9: tiene Instagram como web → oportunidad
        if sl.website and "instagram.com" in sl.website.lower():
            sl.score += 3
            sl.score_reasons.append("solo Instagram como web (+3)")

    # ── helpers ───────────────────────────────────────────────────────────
    def _is_weak_platform(self, url: str) -> bool:
        return any(p in url.lower() for p in WEAK_PLATFORMS)

    def _detect_platform(self, url: str) -> str:
        for p in WEAK_PLATFORMS:
            if p in url.lower():
                return p.replace(".com", "").replace(".site", "")
        return "plataforma genérica"

    def _looks_abandoned(self, url: str) -> bool:
        # dominios muy cortos o sin subdominio propio
        clean = re.sub(r"https?://", "", url).split("/")[0]
        parts = clean.split(".")
        return len(parts) < 2 or len(clean) < 8

    def _is_high_value_category(self, category: str) -> bool:
        high_value = [
            "dentista", "clínica", "médico", "abogado", "notaría",
            "contable", "inmobiliaria", "constructor", "arquitecto",
            "restaurante", "hotel", "spa", "gimnasio", "taller",
        ]
        cat_lower = category.lower()
        return any(kw in cat_lower for kw in high_value)

    def _priority(self, score: int) -> str:
        if score >= 8:  return "high"
        if score >= 5:  return "medium"
        return "low"


# ─────────────────────────────────────────────
#  I/O
# ─────────────────────────────────────────────
def load_raw_leads(path: str = "leads_raw.json") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def save_scored(leads: list[ScoredLead], path: str = "leads_scored.json") -> None:
    import dataclasses
    data = [dataclasses.asdict(l) for l in leads]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 {len(data)} leads calificados guardados en {path}")

def print_summary(leads: list[ScoredLead]) -> None:
    high   = [l for l in leads if l.priority == "high"]
    medium = [l for l in leads if l.priority == "medium"]
    print(f"\n{'─'*50}")
    print(f"LEADS CALIFICADOS (score ≥ {MIN_SCORE}): {len(leads)}")
    print(f"  🔴 Alta prioridad:   {len(high)}")
    print(f"  🟡 Media prioridad:  {len(medium)}")
    print(f"\nTOP 5:")
    for l in leads[:5]:
        print(f"  {l.score:>2}pts [{l.priority:>6}] {l.name} — {', '.join(l.score_reasons)}")
    print(f"{'─'*50}\n")


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    raw    = load_raw_leads()
    scorer = LeadScorer()
    scored = scorer.score_all(raw)
    print_summary(scored)
    save_scored(scored)