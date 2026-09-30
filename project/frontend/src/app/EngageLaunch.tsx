"use client";
import React, { useCallback, useEffect, useMemo, useState } from "react";

type Theme = Record<string, string>;
type ListSummary = { id: string; name: string; source: string; count: number; with_phone: number; with_email: number };
type Channel = "whatsapp" | "email" | "both";

const CHANNELS: { key: Channel; icon: string; label: string; hint: string }[] = [
  { key: "whatsapp", icon: "💬", label: "WhatsApp", hint: "3 mensajes: día 0, +3 y +7" },
  { key: "email", icon: "✉", label: "Gmail", hint: "3 correos: día 0, +3 y +7" },
  { key: "both", icon: "⚡", label: "Gmail + WhatsApp", hint: "Correo, WhatsApp a los 3 días, correo a los 7" },
];

/** Engage → elige leads → "Lanzar como campaña". */
export function EngageLaunch({ T, API, showToast, onCampaignCreated }: {
  T: Theme; API: string; showToast: (m: string) => void; onCampaignCreated: (campaignId: string) => void;
}) {
  const [lists, setLists] = useState<ListSummary[]>([]);
  const [listId, setListId] = useState("");
  const [leads, setLeads] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<"all" | "high" | "phone" | "email">("all");
  const [channel, setChannel] = useState<Channel>("whatsapp");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch(`${API}/lists`).then(r => r.ok ? r.json() : []).then((ls: ListSummary[]) => {
      setLists(ls);
      if (!listId && ls.length) setListId((ls.find(l => l.id === "s_all") || ls[0]).id);
    }).catch(() => {});
  }, [API]); // eslint-disable-line

  useEffect(() => {
    if (!listId) return;
    setLoading(true); setPicked(new Set());
    fetch(`${API}/lists/${listId}/leads`).then(r => r.ok ? r.json() : []).then(setLeads).catch(() => setLeads([])).finally(() => setLoading(false));
  }, [listId, API]);

  const keyOf = (l: any, i: number) => l.phone || l.email || l.name || String(i);
  const canUse = (l: any) => channel === "whatsapp" ? !!l.phone : channel === "email" ? !!l.email : !!(l.phone || l.email);

  const visible = useMemo(() => {
    const s = q.trim().toLowerCase();
    return leads.map((l, i) => ({ l, k: keyOf(l, i) })).filter(({ l }) =>
      (!s || `${l.name} ${l.category || ""} ${l.zone || ""}`.toLowerCase().includes(s)) &&
      (filter === "all" || (filter === "high" && l.priority === "high") || (filter === "phone" && l.phone) || (filter === "email" && l.email))
    );
  }, [leads, q, filter]);

  const toggle = (k: string) => setPicked(p => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const allVisibleOn = visible.length > 0 && visible.every(({ k, l }) => picked.has(k) || !canUse(l));
  const toggleAll = () => setPicked(p => {
    const n = new Set(p);
    visible.forEach(({ k, l }) => { if (canUse(l)) allVisibleOn ? n.delete(k) : n.add(k); });
    return n;
  });

  const chosen = leads.map((l, i) => ({ l, k: keyOf(l, i) })).filter(({ k, l }) => picked.has(k) && canUse(l));
  const pc = (p?: string) => p === "high" ? "#E8442A" : p === "medium" ? "#D97706" : "#6B7280";

  const launch = async () => {
    if (!chosen.length) return;
    setBusy(true);
    const r = await fetch(`${API}/campaigns/quick`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim() || undefined, channel, leads: chosen.map(c => c.l) }),
    });
    setBusy(false);
    if (r.ok) {
      const c = await r.json();
      showToast(`Campaña creada con ${c.enrolled} leads. Revisa los mensajes y pulsa Iniciar`);
      onCampaignCreated(c.id);
    } else {
      const e = await r.json().catch(() => ({}));
      showToast(e.detail || "No pude crear la campaña");
    }
  };

  const card: React.CSSProperties = { background: T.cardBg, border: `1px solid ${T.border}`, borderRadius: 10 };
  const step = (n: number, t: string) => (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
      <span style={{ width: 22, height: 22, borderRadius: 11, background: "#2563EB", color: "#fff", fontSize: 12, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center" }}>{n}</span>
      <span style={{ fontSize: 14, fontWeight: 600, color: T.text }}>{t}</span>
    </div>
  );
  const chip = (k: typeof filter, label: string) => (
    <button key={k} onClick={() => setFilter(k)} style={{ fontSize: 12, padding: "5px 11px", borderRadius: 20, cursor: "pointer", border: `1px solid ${filter === k ? "#2563EB" : T.border}`, background: filter === k ? "rgba(37,99,235,0.12)" : "transparent", color: filter === k ? "#2563EB" : T.textSecondary }}>{label}</button>
  );

  return (
    <div>
      {/* PASO 1 */}
      <div style={{ ...card, padding: 20, marginBottom: 14 }}>
        {step(1, "Elige a quiénes quieres lanzar")}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
          <select value={listId} onChange={e => setListId(e.target.value)} style={{ padding: "7px 10px", borderRadius: 6, border: `1px solid ${T.border}`, background: T.inputBg, color: T.text, fontSize: 13, minWidth: 260 }}>
            {lists.length === 0 && <option value="">Sin listas: ejecuta una búsqueda o importa un CSV en Leads</option>}
            {lists.map(l => <option key={l.id} value={l.id}>{l.name} — {l.count} leads</option>)}
          </select>
          <input placeholder="Buscar…" value={q} onChange={e => setQ(e.target.value)} style={{ padding: "7px 10px", background: T.inputBg, border: `1px solid ${T.border}`, borderRadius: 6, color: T.text, fontSize: 13, width: 180 }} />
          {chip("all", "Todos")}{chip("high", "🔥 Alta prioridad")}{chip("phone", "Con WhatsApp")}{chip("email", "Con email")}
        </div>

        <div style={{ border: `1px solid ${T.border}`, borderRadius: 8, maxHeight: 340, overflowY: "auto" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 14px", background: T.inputBg, position: "sticky", top: 0, fontSize: 12, color: T.textSecondary, cursor: "pointer", borderBottom: `1px solid ${T.border}` }}>
            <input type="checkbox" checked={allVisibleOn} onChange={toggleAll} />
            Seleccionar todos los visibles ({visible.filter(({ l }) => canUse(l)).length})
          </label>
          {loading ? <div style={{ padding: 30, textAlign: "center", color: T.textMuted }}>Cargando…</div> :
            visible.length === 0 ? <div style={{ padding: 30, textAlign: "center", color: T.textMuted, fontSize: 13 }}>No hay leads con ese filtro</div> :
              visible.map(({ l, k }) => {
                const ok = canUse(l);
                return (
                  <label key={k} style={{ display: "grid", gridTemplateColumns: "24px 1.8fr 1.1fr 1.2fr 44px", gap: 10, alignItems: "center", padding: "9px 14px", borderBottom: `1px solid ${T.borderLight}`, cursor: ok ? "pointer" : "not-allowed", opacity: ok ? 1 : 0.4, background: picked.has(k) ? "rgba(37,99,235,0.07)" : "transparent" }}>
                    <input type="checkbox" disabled={!ok} checked={picked.has(k) && ok} onChange={() => toggle(k)} />
                    <div><div style={{ fontSize: 13, fontWeight: 500, color: T.text }}>{l.name}</div><div style={{ fontSize: 11, color: T.textMuted }}>{[l.category, l.zone].filter(Boolean).join(" · ")}</div></div>
                    <div style={{ fontSize: 12, color: T.textSecondary }}>{l.phone ? "💬 " + l.phone : "—"}</div>
                    <div style={{ fontSize: 12, color: T.textSecondary, overflow: "hidden", textOverflow: "ellipsis" }}>{l.email ? "✉ " + l.email : "—"}</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: pc(l.priority) }}>{l.score ?? ""}</div>
                  </label>
                );
              })}
        </div>
      </div>

      {/* PASO 2 */}
      <div style={{ ...card, padding: 20, marginBottom: 14 }}>
        {step(2, "Elige el canal")}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10 }}>
          {CHANNELS.map(c => (
            <div key={c.key} onClick={() => setChannel(c.key)} style={{ cursor: "pointer", padding: 14, borderRadius: 10, border: `1.5px solid ${channel === c.key ? "#2563EB" : T.border}`, background: channel === c.key ? "rgba(37,99,235,0.08)" : "transparent" }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: T.text }}>{c.icon} {c.label}</div>
              <div style={{ fontSize: 11, color: T.textMuted, marginTop: 4 }}>{c.hint}</div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 12, color: T.textMuted, marginTop: 10 }}>Después podrás cambiar cada paso, sus mensajes, los días de espera, la firma y el horario.</div>
      </div>

      {/* PASO 3 */}
      <div style={{ ...card, padding: 20, display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
        {step(3, "Lánzala")}
        <input placeholder="Nombre de la campaña (opcional)" value={name} onChange={e => setName(e.target.value)} style={{ padding: "8px 10px", background: T.inputBg, border: `1px solid ${T.border}`, borderRadius: 6, color: T.text, fontSize: 13, width: 280 }} />
        <span style={{ fontSize: 13, color: T.textSecondary }}><b style={{ color: T.text }}>{chosen.length}</b> leads seleccionados</span>
        <button disabled={!chosen.length || busy} onClick={launch}
          style={{ marginLeft: "auto", padding: "10px 20px", background: T.accentBg, color: T.accentText, border: "none", borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: "pointer", opacity: !chosen.length || busy ? 0.4 : 1 }}>
          {busy ? "Creando…" : "🚀 Lanzar como campaña"}
        </button>
      </div>
    </div>
  );
}

/** Pestaña WhatsApp de Engage: estado real del canal + mensaje de prueba. */
export function WhatsAppPanel({ T, API, showToast, onGoLaunch }: { T: Theme; API: string; showToast: (m: string) => void; onGoLaunch: () => void }) {
  const [chk, setChk] = useState<{ ok: boolean; error?: string; fix?: string } | null>(null);
  const [checking, setChecking] = useState(false);
  const [phone, setPhone] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);

  const check = useCallback(async () => {
    setChecking(true);
    try { const r = await fetch(`${API}/channels/whatsapp/check`); if (r.ok) setChk(await r.json()); } catch {}
    setChecking(false);
  }, [API]);
  useEffect(() => { check(); }, [check]);

  const test = async () => {
    setSending(true); setResult(null);
    const r = await fetch(`${API}/channels/whatsapp/test`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ phone }) });
    setSending(false);
    if (r.ok) setResult({ ok: true, msg: "Mensaje de prueba enviado. Revisa tu WhatsApp." });
    else { const e = await r.json().catch(() => ({})); setResult({ ok: false, msg: e.detail || "Falló el envío" }); }
  };

  const card: React.CSSProperties = { background: T.cardBg, border: `1px solid ${T.border}`, borderRadius: 10, padding: 20, marginBottom: 14 };
  return (
    <>
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: T.text }}>Estado del envío por WhatsApp</div>
          <span style={{ fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 20, background: chk?.ok ? "rgba(22,163,74,0.14)" : "rgba(232,68,42,0.14)", color: chk?.ok ? "#16A34A" : "#E8442A" }}>
            {chk === null ? "Comprobando…" : chk.ok ? "● Listo" : "● Falta configurar"}
          </span>
        </div>
        {chk && !chk.ok && (
          <div style={{ fontSize: 12, color: T.textSecondary, lineHeight: 1.7, background: T.inputBg, borderRadius: 8, padding: 12, marginBottom: 10 }}>
            <div style={{ color: "#E8442A", marginBottom: 6 }}>{chk.error}</div>
            <div>{chk.fix}</div>
          </div>
        )}
        <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.7 }}>
          Los mensajes salen desde WhatsApp Web: deja el computador encendido con la pantalla despierta y la sesión de WhatsApp Web iniciada en tu navegador.
        </div>
        <button onClick={check} disabled={checking} style={{ marginTop: 10, padding: "6px 12px", background: "transparent", border: `1px solid ${T.border}`, borderRadius: 7, fontSize: 12, color: T.textSecondary, cursor: "pointer" }}>{checking ? "Comprobando…" : "↻ Volver a comprobar"}</button>
      </div>

      <div style={card}>
        <div style={{ fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 4 }}>Envíate un mensaje de prueba</div>
        <div style={{ fontSize: 12, color: T.textMuted, marginBottom: 12 }}>Usa tu propio número (con o sin +57). Tarda unos 25 segundos porque abre WhatsApp Web.</div>
        <div style={{ display: "flex", gap: 8 }}>
          <input placeholder="Ej. 300 123 4567" value={phone} onChange={e => setPhone(e.target.value)} style={{ padding: "8px 10px", background: T.inputBg, border: `1px solid ${T.border}`, borderRadius: 6, color: T.text, fontSize: 13, width: 220 }} />
          <button onClick={test} disabled={!phone.trim() || sending || !chk?.ok} style={{ padding: "8px 16px", background: T.accentBg, color: T.accentText, border: "none", borderRadius: 7, fontSize: 13, fontWeight: 500, cursor: "pointer", opacity: !phone.trim() || sending || !chk?.ok ? 0.4 : 1 }}>{sending ? "Enviando…" : "Enviar prueba"}</button>
        </div>
        {result && <div style={{ fontSize: 12, marginTop: 10, color: result.ok ? "#16A34A" : "#E8442A", lineHeight: 1.6 }}>{result.ok ? "✓ " : "✗ "}{result.msg}</div>}
      </div>

      <div style={{ ...card, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div style={{ fontSize: 13, color: T.textSecondary }}>Para enviar a tus leads, elige a quiénes y lánzalos como campaña.</div>
        <button onClick={onGoLaunch} style={{ padding: "8px 16px", background: T.accentBg, color: T.accentText, border: "none", borderRadius: 7, fontSize: 13, fontWeight: 500, cursor: "pointer", whiteSpace: "nowrap" }}>🚀 Ir a Lanzar campaña</button>
      </div>
    </>
  );
}
