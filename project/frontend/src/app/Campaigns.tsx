"use client";
import React, { useCallback, useEffect, useRef, useState } from "react";

type Theme = Record<string, string>;
type Step = { id?: string; channel: "email" | "whatsapp"; delay_days: number; subject: string; body: string };
type Schedule = {
  days: number[]; start: string; end: string; tz: string;
  daily_limit_email: number; daily_limit_whatsapp: number; gap_email_sec: number; gap_whatsapp_sec: number;
};
type Campaign = {
  id: string; name: string; status: "draft" | "active" | "paused"; list_id?: string | null;
  steps: Step[]; schedule: Schedule; variables: Record<string, string>;
};
type Summary = { id: string; name: string; status: string; steps: number; leads: number; sent: number; replied: number; active: number; completed: number };
type ListSummary = { id: string; name: string; source: string; count: number; with_phone: number; with_email: number };
type VarDef = { key: string; label: string; hint: string };

const CH = { email: { icon: "✉", label: "Gmail", color: "#E8442A" }, whatsapp: { icon: "◔", label: "WhatsApp", color: "#16A34A" } };
const STATUS_LABEL: Record<string, string> = { draft: "Borrador", active: "Activa", paused: "Pausada" };
const STATUS_COLOR: Record<string, string> = { draft: "#6B7280", active: "#16A34A", paused: "#D97706" };
const ENR_LABEL: Record<string, string> = { active: "En secuencia", completed: "Completó", replied: "Respondió", stopped: "Detenido" };
const ENR_COLOR: Record<string, string> = { active: "#2563EB", completed: "#6B7280", replied: "#16A34A", stopped: "#9B9B97" };
const DAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

export default function Campaigns({ T, API, showToast, pendingListId, onConsumed, openCampaignId, onOpened }: {
  T: Theme; API: string; showToast: (m: string) => void;
  pendingListId?: string | null; onConsumed?: () => void;
  openCampaignId?: string | null; onOpened?: () => void;
}) {
  const [items, setItems] = useState<Summary[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { const r = await fetch(`${API}/campaigns`); if (r.ok) setItems(await r.json()); } catch {}
  }, [API]);

  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, [load]);

  const create = useCallback(async (listId?: string | null, name?: string) => {
    const r = await fetch(`${API}/campaigns`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name || "Campaña nueva", list_id: listId || null }),
    });
    if (r.ok) { const c = await r.json(); await load(); setOpenId(c.id); }
    else showToast("No pude crear la campaña");
  }, [API, load, showToast]);

  // abrir directo una campaña recién creada desde Engage
  useEffect(() => {
    if (openCampaignId) { setOpenId(openCampaignId); onOpened?.(); }
  }, [openCampaignId]); // eslint-disable-line

  // "Crear campaña con esta lista" desde la pestaña Leads
  useEffect(() => {
    if (pendingListId) { create(pendingListId, "Campaña nueva"); onConsumed?.(); }
  }, [pendingListId]); // eslint-disable-line

  const card: React.CSSProperties = { background: T.cardBg, border: `1px solid ${T.border}`, borderRadius: 10, padding: "16px 20px" };

  if (openId) return <CampaignDetail T={T} API={API} id={openId} showToast={showToast} onBack={() => { setOpenId(null); load(); }} />;

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: 32 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: T.text, margin: 0 }}>Campañas</h2>
          <p style={{ fontSize: 13, color: T.textMuted, margin: "4px 0 0" }}>Secuencias automáticas por Gmail y WhatsApp, con seguimiento por días.</p>
        </div>
        <button onClick={() => create()} style={{ padding: "9px 16px", background: T.accentBg, color: T.accentText, border: "none", borderRadius: 7, fontSize: 13, fontWeight: 500, cursor: "pointer" }}>
          + Nueva campaña
        </button>
      </div>

      {items.length === 0 ? (
        <div style={{ ...card, textAlign: "center", padding: 60, color: T.textMuted, fontSize: 14 }}>
          Aún no tienes campañas. Crea una y elige una lista de leads para empezar.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(320px,1fr))", gap: 12 }}>
          {items.map(c => (
            <div key={c.id} onClick={() => setOpenId(c.id)} style={{ ...card, cursor: "pointer" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                <span style={{ fontSize: 14, fontWeight: 600, color: T.text }}>{c.name}</span>
                <Pill color={STATUS_COLOR[c.status]} text={STATUS_LABEL[c.status] || c.status} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8 }}>
                {[["Leads", c.leads], ["Enviados", c.sent], ["Respuestas", c.replied], ["Pasos", c.steps]].map(([l, v]) => (
                  <div key={l as string}>
                    <div style={{ fontSize: 20, fontWeight: 700, color: T.text }}>{v}</div>
                    <div style={{ fontSize: 11, color: T.textMuted }}>{l}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Pill({ color, text }: { color: string; text: string }) {
  return <span style={{ fontSize: 11, fontWeight: 500, padding: "3px 9px", borderRadius: 20, background: color + "22", color, whiteSpace: "nowrap" }}>{text}</span>;
}

// ═════════════════════════════════════════════════════════════════════
//  DETALLE DE CAMPAÑA — pestañas como en Instantly
// ═════════════════════════════════════════════════════════════════════
function CampaignDetail({ T, API, id, onBack, showToast }: { T: Theme; API: string; id: string; onBack: () => void; showToast: (m: string) => void }) {
  const [camp, setCamp] = useState<Campaign | null>(null);
  const [tab, setTab] = useState<"analytics" | "leads" | "sequence" | "schedule" | "options">("sequence");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    const r = await fetch(`${API}/campaigns/${id}`);
    if (r.ok) setCamp(await r.json());
  }, [API, id]);
  useEffect(() => { load(); }, [load]);

  const patch = (p: Partial<Campaign>) => { setCamp(c => c ? { ...c, ...p } : c); setDirty(true); };

  const save = async () => {
    if (!camp) return;
    setSaving(true);
    const r = await fetch(`${API}/campaigns/${id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: camp.name, steps: camp.steps, schedule: camp.schedule, variables: camp.variables }),
    });
    setSaving(false);
    if (r.ok) { setCamp(await r.json()); setDirty(false); showToast("Campaña guardada"); } else showToast("Error al guardar");
  };

  const toggle = async () => {
    if (!camp) return;
    if (dirty) await save();
    const r = await fetch(`${API}/campaigns/${id}/${camp.status === "active" ? "pause" : "start"}`, { method: "POST" });
    if (r.ok) setCamp(await r.json());
    else { const e = await r.json().catch(() => ({})); showToast(e.detail || "No se pudo cambiar el estado"); }
  };

  const remove = async () => {
    if (!confirm("¿Eliminar esta campaña y su historial?")) return;
    await fetch(`${API}/campaigns/${id}`, { method: "DELETE" });
    onBack();
  };

  if (!camp) return <div style={{ padding: 32, color: T.textMuted }}>Cargando…</div>;

  const tabs = [["analytics", "Analíticas"], ["leads", "Leads"], ["sequence", "Secuencia"], ["schedule", "Horario"], ["options", "Variables"]] as const;

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ padding: "14px 24px 0", borderBottom: `1px solid ${T.border}`, background: T.cardBg, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
          <button onClick={onBack} style={{ background: "none", border: "none", color: T.textSecondary, cursor: "pointer", fontSize: 16 }}>←</button>
          <input value={camp.name} onChange={e => patch({ name: e.target.value })}
            style={{ fontSize: 15, fontWeight: 600, background: "transparent", border: "none", color: T.text, outline: "none", flex: 1 }} />
          <Pill color={STATUS_COLOR[camp.status]} text={STATUS_LABEL[camp.status]} />
          {dirty && <button onClick={save} disabled={saving} style={{ padding: "7px 14px", background: "#2563EB", color: "#fff", border: "none", borderRadius: 7, fontSize: 12, cursor: "pointer" }}>{saving ? "Guardando…" : "Guardar cambios"}</button>}
          <button onClick={toggle} style={{ padding: "7px 14px", background: camp.status === "active" ? "rgba(217,119,6,0.14)" : "rgba(22,163,74,0.14)", color: camp.status === "active" ? "#D97706" : "#16A34A", border: "none", borderRadius: 7, fontSize: 12, cursor: "pointer", fontWeight: 500 }}>
            {camp.status === "active" ? "⏸ Pausar" : "▶ Iniciar"}
          </button>
          <button onClick={remove} title="Eliminar" style={{ background: "none", border: `1px solid ${T.border}`, color: T.textMuted, borderRadius: 7, padding: "6px 10px", cursor: "pointer" }}>🗑</button>
        </div>
        <div style={{ display: "flex", gap: 22 }}>
          {tabs.map(([k, l]) => (
            <button key={k} onClick={() => setTab(k)} style={{ background: "none", border: "none", padding: "8px 0", cursor: "pointer", fontSize: 13, color: tab === k ? "#2563EB" : T.textSecondary, fontWeight: tab === k ? 600 : 400, borderBottom: `2px solid ${tab === k ? "#2563EB" : "transparent"}` }}>{l}</button>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, overflow: "hidden", display: "flex" }}>
        {tab === "analytics" && <Analytics T={T} API={API} camp={camp} />}
        {tab === "leads" && <CampLeads T={T} API={API} camp={camp} showToast={showToast} onListSet={load} />}
        {tab === "sequence" && <Sequence T={T} API={API} camp={camp} patch={patch} showToast={showToast} />}
        {tab === "schedule" && <ScheduleTab T={T} camp={camp} patch={patch} />}
        {tab === "options" && <VariablesTab T={T} camp={camp} patch={patch} />}
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════
//  ANALÍTICAS
// ═════════════════════════════════════════════════════════════════════
function Analytics({ T, API, camp }: { T: Theme; API: string; camp: Campaign }) {
  const [a, setA] = useState<any>(null);
  useEffect(() => {
    const go = async () => { const r = await fetch(`${API}/campaigns/${camp.id}/analytics`); if (r.ok) setA(await r.json()); };
    go(); const t = setInterval(go, 8000); return () => clearInterval(t);
  }, [API, camp.id]);
  if (!a) return <div style={{ padding: 32, color: T.textMuted }}>Cargando…</div>;

  const cards = [
    ["Leads", a.leads], ["Contactados", a.contacted], ["Enviados", a.sent], ["Gmail", a.sent_email], ["WhatsApp", a.sent_whatsapp],
    ["Respondieron", a.replied], ["Tasa respuesta", a.reply_rate + "%"], ["Aperturas", a.opened], ["Errores", a.errors],
  ];
  const max = Math.max(...a.series.map((s: any) => s.sent), 1);

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: 28 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(130px,1fr))", gap: 10, marginBottom: 20 }}>
        {cards.map(([l, v]) => (
          <div key={l as string} style={{ background: T.cardBg, border: `1px solid ${T.border}`, borderRadius: 10, padding: "14px 16px" }}>
            <div style={{ fontSize: 11, color: T.textMuted, fontWeight: 500 }}>{l}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: T.text, marginTop: 4 }}>{v}</div>
          </div>
        ))}
      </div>

      <div style={{ background: T.cardBg, border: `1px solid ${T.border}`, borderRadius: 10, padding: 20, marginBottom: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 14 }}>
          Envíos · últimos 14 días <span style={{ float: "right", textTransform: "none" }}>Hoy: {a.sent_today.email} Gmail · {a.sent_today.whatsapp} WhatsApp</span>
        </div>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 110 }}>
          {a.series.map((s: any) => (
            <div key={s.date} title={`${s.date}: ${s.sent}`} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", height: "100%" }}>
              <div style={{ fontSize: 10, color: T.textMuted }}>{s.sent || ""}</div>
              <div style={{ width: "100%", height: `${(s.sent / max) * 80}%`, minHeight: s.sent ? 3 : 1, background: s.sent ? "#2563EB" : T.border, borderRadius: 3 }} />
              <div style={{ fontSize: 9, color: T.textMuted, marginTop: 4 }}>{s.date.slice(8)}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ background: T.cardBg, border: `1px solid ${T.border}`, borderRadius: 10, padding: 20 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 12 }}>Rendimiento por paso</div>
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse", color: T.text }}>
          <thead><tr style={{ color: T.textMuted, fontSize: 11, textAlign: "left" }}>
            {["Paso", "Canal", "Enviados", "Errores", "Respuestas", "% resp."].map(h => <th key={h} style={{ padding: "6px 8px", fontWeight: 600 }}>{h}</th>)}
          </tr></thead>
          <tbody>{a.per_step.map((s: any) => (
            <tr key={s.id} style={{ borderTop: `1px solid ${T.borderLight}` }}>
              <td style={{ padding: 8 }}>Paso {s.index + 1}</td>
              <td style={{ padding: 8, color: CH[s.channel as "email"].color }}>{CH[s.channel as "email"].icon} {CH[s.channel as "email"].label}</td>
              <td style={{ padding: 8 }}>{s.sent}</td><td style={{ padding: 8 }}>{s.errors}</td>
              <td style={{ padding: 8 }}>{s.replies}</td><td style={{ padding: 8 }}>{s.reply_rate}%</td>
            </tr>
          ))}</tbody>
        </table>
        <div style={{ fontSize: 11, color: T.textMuted, marginTop: 12 }}>
          Las aperturas solo se cuentan en Gmail y requieren que <code>TRACKING_BASE</code> apunte a un dominio público. Las respuestas se marcan en la pestaña Leads o en el CRM.
        </div>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════
//  LEADS DE LA CAMPAÑA
// ═════════════════════════════════════════════════════════════════════
function CampLeads({ T, API, camp, showToast, onListSet }: { T: Theme; API: string; camp: Campaign; showToast: (m: string) => void; onListSet: () => void }) {
  const [rows, setRows] = useState<any[]>([]);
  const [lists, setLists] = useState<ListSummary[]>([]);
  const [pick, setPick] = useState(camp.list_id || "");

  const load = useCallback(async () => {
    const [a, b] = await Promise.all([fetch(`${API}/campaigns/${camp.id}/leads`), fetch(`${API}/lists`)]);
    if (a.ok) setRows(await a.json());
    if (b.ok) setLists(await b.json());
  }, [API, camp.id]);
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, [load]);

  const add = async () => {
    if (!pick) return;
    const r = await fetch(`${API}/campaigns/${camp.id}/leads`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ list_id: pick }) });
    if (r.ok) { const d = await r.json(); showToast(`${d.added} leads añadidos`); load(); onListSet(); }
  };
  const setStatus = async (key: string, status: string) => {
    await fetch(`${API}/campaigns/${camp.id}/leads/${encodeURIComponent(key)}/status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
    load();
  };
  const fmt = (s?: string) => s ? new Date(s).toLocaleString("es-CO", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";
  const btn: React.CSSProperties = { fontSize: 11, padding: "4px 9px", borderRadius: 6, border: `1px solid ${T.border}`, background: "transparent", color: T.textSecondary, cursor: "pointer" };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ padding: "14px 24px", display: "flex", gap: 8, alignItems: "center", borderBottom: `1px solid ${T.border}`, background: T.cardBg }}>
        <select value={pick} onChange={e => setPick(e.target.value)} style={{ padding: "7px 10px", borderRadius: 6, border: `1px solid ${T.border}`, background: T.inputBg, color: T.text, fontSize: 13, minWidth: 280 }}>
          <option value="">Elige una lista para añadir…</option>
          {lists.map(l => <option key={l.id} value={l.id}>{l.name} — {l.count} leads ({l.with_phone} tel · {l.with_email} email)</option>)}
        </select>
        <button onClick={add} disabled={!pick} style={{ ...btn, background: T.accentBg, color: T.accentText, border: "none", padding: "8px 14px", fontSize: 12, opacity: pick ? 1 : 0.4 }}>+ Añadir leads</button>
        <span style={{ marginLeft: "auto", fontSize: 12, color: T.textMuted }}>{rows.length} en la campaña</span>
      </div>
      <div style={{ flex: 1, overflowY: "auto", background: T.cardBg }}>
        {rows.length === 0 ? <div style={{ padding: 60, textAlign: "center", color: T.textMuted, fontSize: 14 }}>Añade una lista para empezar.</div> :
          rows.map(r => (
            <div key={r.key} style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr 110px 90px 150px 170px", gap: 12, padding: "11px 24px", borderBottom: `1px solid ${T.borderLight}`, alignItems: "center", fontSize: 13, color: T.text }}>
              <div><div style={{ fontWeight: 500 }}>{r.name}</div><div style={{ fontSize: 11, color: T.textMuted }}>{r.email || r.phone}</div></div>
              <div style={{ fontSize: 11, color: T.textMuted }}>{r.phone ? "◔ " : ""}{r.email ? "✉" : ""}</div>
              <Pill color={ENR_COLOR[r.status]} text={ENR_LABEL[r.status] || r.status} />
              <div style={{ fontSize: 12, color: T.textSecondary }}>Paso {Math.min(r.step + 1, camp.steps.length)}/{camp.steps.length}</div>
              <div style={{ fontSize: 11, color: T.textMuted }}>{r.status === "active" ? "Próximo: " + fmt(r.next_at) : ""}</div>
              <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                {r.status === "active" && <><button style={btn} onClick={() => setStatus(r.key, "replied")}>Respondió</button><button style={btn} onClick={() => setStatus(r.key, "stopped")}>Detener</button></>}
                {r.status !== "active" && <button style={btn} onClick={() => setStatus(r.key, "active")}>Reanudar</button>}
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════
//  SECUENCIA — pasos a la izquierda, editor a la derecha
// ═════════════════════════════════════════════════════════════════════
function Sequence({ T, API, camp, patch, showToast }: { T: Theme; API: string; camp: Campaign; patch: (p: Partial<Campaign>) => void; showToast: (m: string) => void }) {
  const [sel, setSel] = useState(0);
  const [vars, setVars] = useState<VarDef[]>([]);
  const [prev, setPrev] = useState<any>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const subjRef = useRef<HTMLInputElement>(null);
  const [focus, setFocus] = useState<"body" | "subject">("body");

  useEffect(() => { fetch(`${API}/variables`).then(r => r.ok ? r.json() : []).then(setVars).catch(() => {}); }, [API]);
  useEffect(() => { if (sel >= camp.steps.length) setSel(Math.max(0, camp.steps.length - 1)); setPrev(null); }, [camp.steps.length, sel]);

  const step = camp.steps[sel];
  const setStep = (i: number, p: Partial<Step>) => patch({ steps: camp.steps.map((s, j) => j === i ? { ...s, ...p } : s) });
  const addStep = () => {
    const last = camp.steps[camp.steps.length - 1];
    patch({ steps: [...camp.steps, { channel: last?.channel === "email" ? "whatsapp" : "email", delay_days: 3, subject: "", body: "" }] });
    setSel(camp.steps.length);
  };
  const delStep = (i: number) => { if (camp.steps.length > 1) patch({ steps: camp.steps.filter((_, j) => j !== i) }); };

  const allVars = [...vars.map(v => v.key), ...Object.keys(camp.variables).filter(k => !vars.some(v => v.key === k))];

  const insertVar = (k: string) => {
    if (!step) return;
    const tag = `{{${k}}}`;
    if (focus === "subject" && step.channel === "email" && subjRef.current) {
      const el = subjRef.current, a = el.selectionStart ?? step.subject.length, b = el.selectionEnd ?? a;
      setStep(sel, { subject: step.subject.slice(0, a) + tag + step.subject.slice(b) });
      setTimeout(() => { el.focus(); el.setSelectionRange(a + tag.length, a + tag.length); }, 0);
    } else if (bodyRef.current) {
      const el = bodyRef.current, a = el.selectionStart, b = el.selectionEnd;
      setStep(sel, { body: step.body.slice(0, a) + tag + step.body.slice(b) });
      setTimeout(() => { el.focus(); el.setSelectionRange(a + tag.length, a + tag.length); }, 0);
    }
  };

  const doPreview = async () => {
    if (!step?.id) { showToast("Guarda la campaña primero para previsualizar"); return; }
    const r = await fetch(`${API}/campaigns/${camp.id}/preview`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ step_id: step.id }) });
    if (r.ok) setPrev(await r.json());
  };

  const inp: React.CSSProperties = { width: "100%", background: T.inputBg, border: `1px solid ${T.border}`, borderRadius: 6, padding: "8px 10px", fontSize: 13, color: T.text, outline: "none", fontFamily: "inherit" };

  return (
    <>
      {/* columna de pasos */}
      <div style={{ width: 300, borderRight: `1px solid ${T.border}`, overflowY: "auto", padding: 14, flexShrink: 0 }}>
        {camp.steps.map((s, i) => (
          <div key={s.id || i}>
            <div onClick={() => setSel(i)} style={{ background: T.cardBg, border: `1.5px solid ${sel === i ? "#2563EB" : T.border}`, borderRadius: 10, padding: 12, cursor: "pointer" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: T.text }}>Paso {i + 1}</span>
                <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span style={{ fontSize: 11, color: CH[s.channel].color, fontWeight: 500 }}>{CH[s.channel].icon} {CH[s.channel].label}</span>
                  <button onClick={e => { e.stopPropagation(); delStep(i); }} title="Eliminar paso" style={{ background: "none", border: "none", color: T.textMuted, cursor: "pointer", fontSize: 12 }}>🗑</button>
                </span>
              </div>
              <div style={{ fontSize: 12, color: T.textSecondary, background: T.inputBg, borderRadius: 6, padding: "7px 9px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {(s.channel === "email" ? s.subject : s.body) || "(vacío)"}
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, justifyContent: "center", padding: "10px 0", fontSize: 11, color: T.textMuted }}>
              {i < camp.steps.length - 1 ? "Enviar siguiente mensaje en" : "Esperar tras el último paso"}
              <input type="number" min={0} step={1} value={s.delay_days} onClick={e => e.stopPropagation()}
                onChange={e => setStep(i, { delay_days: Math.max(0, Number(e.target.value)) })}
                style={{ width: 52, padding: "4px 6px", borderRadius: 6, border: `1px solid ${T.border}`, background: T.inputBg, color: T.text, fontSize: 12, textAlign: "center" }} />
              días
            </div>
          </div>
        ))}
        <button onClick={addStep} style={{ width: "100%", padding: "9px", border: `1px dashed ${T.border}`, background: "transparent", color: "#2563EB", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 500 }}>+ Añadir paso</button>
      </div>

      {/* editor */}
      <div style={{ flex: 1, overflowY: "auto", padding: 24 }}>
        {step && (
          <>
            <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center" }}>
              <span style={{ fontSize: 12, color: T.textMuted }}>Canal de este paso:</span>
              {(["email", "whatsapp"] as const).map(ch => (
                <button key={ch} onClick={() => setStep(sel, { channel: ch })} style={{
                  padding: "6px 14px", borderRadius: 20, fontSize: 12, cursor: "pointer", fontWeight: 500,
                  border: `1px solid ${step.channel === ch ? CH[ch].color : T.border}`,
                  background: step.channel === ch ? CH[ch].color + "22" : "transparent",
                  color: step.channel === ch ? CH[ch].color : T.textSecondary,
                }}>{CH[ch].icon} {CH[ch].label}</button>
              ))}
              <span style={{ marginLeft: "auto", fontSize: 12, color: T.textMuted }}>
                {sel === 0 ? "Se envía apenas inicia la campaña" : `Se envía ${camp.steps[sel - 1].delay_days} día(s) después del paso ${sel}`}
              </span>
            </div>

            {step.channel === "email" && (
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: "uppercase" }}>Asunto</label>
                <input ref={subjRef} value={step.subject} onFocus={() => setFocus("subject")} onChange={e => setStep(sel, { subject: e.target.value })} style={{ ...inp, marginTop: 4 }} />
              </div>
            )}

            <label style={{ fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: "uppercase" }}>{step.channel === "email" ? "Mensaje del correo" : "Mensaje de WhatsApp"}</label>
            <textarea ref={bodyRef} value={step.body} onFocus={() => setFocus("body")} onChange={e => setStep(sel, { body: e.target.value })}
              rows={14} style={{ ...inp, marginTop: 4, lineHeight: 1.6, resize: "vertical" }} />

            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", margin: "12px 0" }}>
              <span style={{ fontSize: 11, color: T.textMuted, fontWeight: 600 }}>VARIABLES</span>
              {allVars.map(k => (
                <button key={k} onClick={() => insertVar(k)} title={vars.find(v => v.key === k)?.label || "Variable personalizada"}
                  style={{ fontSize: 11, padding: "4px 9px", borderRadius: 6, border: `1px solid ${T.border}`, background: T.cardBg, color: "#2563EB", cursor: "pointer", fontFamily: "monospace" }}>{`{{${k}}}`}</button>
              ))}
            </div>

            <button onClick={doPreview} style={{ padding: "7px 14px", background: "transparent", border: `1px solid ${T.border}`, borderRadius: 7, fontSize: 12, color: T.textSecondary, cursor: "pointer" }}>👁 Vista previa con un lead real</button>

            {prev && (
              <div style={{ marginTop: 12, background: T.cardBg, border: `1px solid ${T.border}`, borderRadius: 10, padding: 16 }}>
                <div style={{ fontSize: 11, color: T.textMuted, marginBottom: 6 }}>Ejemplo con: {prev.lead}</div>
                {step.channel === "email" && <div style={{ fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 8 }}>{prev.subject}</div>}
                <div style={{ fontSize: 13, color: T.textSecondary, whiteSpace: "pre-line", lineHeight: 1.7 }}>{prev.body}</div>
                {prev.missing.length > 0 && <div style={{ fontSize: 12, color: "#E8442A", marginTop: 10 }}>⚠ Variables sin valor (ese lead se saltaría): {prev.missing.join(", ")}</div>}
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}

// ═════════════════════════════════════════════════════════════════════
//  HORARIO
// ═════════════════════════════════════════════════════════════════════
function ScheduleTab({ T, camp, patch }: { T: Theme; camp: Campaign; patch: (p: Partial<Campaign>) => void }) {
  const s = camp.schedule;
  const set = (p: Partial<Schedule>) => patch({ schedule: { ...s, ...p } });
  const inp: React.CSSProperties = { padding: "7px 10px", background: T.inputBg, border: `1px solid ${T.border}`, borderRadius: 6, color: T.text, fontSize: 13, width: 110 };
  const row = (label: string, el: React.ReactNode) => <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 16 }}><div style={{ width: 210, fontSize: 13, color: T.textSecondary }}>{label}</div>{el}</div>;
  return (
    <div style={{ flex: 1, overflowY: "auto", padding: 32, maxWidth: 720 }}>
      <div style={{ background: T.cardBg, border: `1px solid ${T.border}`, borderRadius: 10, padding: 24 }}>
        {row("Días de envío", <div style={{ display: "flex", gap: 6 }}>{DAYS.map((d, i) => {
          const on = s.days.includes(i);
          return <button key={d} onClick={() => set({ days: on ? s.days.filter(x => x !== i) : [...s.days, i].sort() })}
            style={{ padding: "6px 10px", borderRadius: 6, fontSize: 12, cursor: "pointer", border: `1px solid ${on ? "#2563EB" : T.border}`, background: on ? "rgba(37,99,235,0.12)" : "transparent", color: on ? "#2563EB" : T.textSecondary }}>{d}</button>;
        })}</div>)}
        {row("Desde / hasta", <div style={{ display: "flex", gap: 8, alignItems: "center" }}><input type="time" value={s.start} onChange={e => set({ start: e.target.value })} style={inp} /><span style={{ color: T.textMuted }}>→</span><input type="time" value={s.end} onChange={e => set({ end: e.target.value })} style={inp} /></div>)}
        {row("Zona horaria", <input value={s.tz} onChange={e => set({ tz: e.target.value })} style={{ ...inp, width: 200 }} />)}
        <div style={{ borderTop: `1px solid ${T.borderLight}`, margin: "20px 0" }} />
        {row("Máx. correos por día", <input type="number" min={1} value={s.daily_limit_email} onChange={e => set({ daily_limit_email: Number(e.target.value) })} style={inp} />)}
        {row("Máx. WhatsApp por día", <input type="number" min={1} value={s.daily_limit_whatsapp} onChange={e => set({ daily_limit_whatsapp: Number(e.target.value) })} style={inp} />)}
        {row("Pausa entre correos (seg)", <input type="number" min={0} value={s.gap_email_sec} onChange={e => set({ gap_email_sec: Number(e.target.value) })} style={inp} />)}
        {row("Pausa entre WhatsApp (seg)", <input type="number" min={0} value={s.gap_whatsapp_sec} onChange={e => set({ gap_whatsapp_sec: Number(e.target.value) })} style={inp} />)}
        <div style={{ fontSize: 12, color: T.textMuted }}>Los límites y pausas protegen tu Gmail y tu número de WhatsApp de bloqueos. Recuerda: WhatsApp con el bot actual abre WhatsApp Web, así que el computador debe estar encendido durante el horario.</div>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════
//  VARIABLES (firma, nombre y las que tú quieras)
// ═════════════════════════════════════════════════════════════════════
function VariablesTab({ T, camp, patch }: { T: Theme; camp: Campaign; patch: (p: Partial<Campaign>) => void }) {
  const [newKey, setNewKey] = useState("");
  const v = camp.variables;
  const set = (k: string, val: string) => patch({ variables: { ...v, [k]: val } });
  const del = (k: string) => { const c = { ...v }; delete c[k]; patch({ variables: c }); };
  const add = () => { const k = newKey.trim().replace(/[^A-Za-z0-9_]/g, ""); if (k && !(k in v)) { set(k, ""); setNewKey(""); } };
  const inp: React.CSSProperties = { width: "100%", background: T.inputBg, border: `1px solid ${T.border}`, borderRadius: 6, padding: "8px 10px", fontSize: 13, color: T.text, fontFamily: "inherit" };
  return (
    <div style={{ flex: 1, overflowY: "auto", padding: 32, maxWidth: 720 }}>
      <div style={{ background: T.cardBg, border: `1px solid ${T.border}`, borderRadius: 10, padding: 24 }}>
        <div style={{ fontSize: 13, color: T.textSecondary, marginBottom: 16, lineHeight: 1.6 }}>
          Valores fijos de esta campaña. Úsalos en cualquier mensaje como <code>{"{{signature}}"}</code>. Automáticas por lead: <code>{"{{firstName}}"}</code>, <code>{"{{companyName}}"}</code>, <code>{"{{category}}"}</code>, <code>{"{{city}}"}</code>. Si importas un CSV, sus otras columnas también quedan como variables.
        </div>
        {Object.entries(v).map(([k, val]) => (
          <div key={k} style={{ marginBottom: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <code style={{ fontSize: 12, color: "#2563EB" }}>{`{{${k}}}`}</code>
              {k !== "signature" && k !== "senderName" && <button onClick={() => del(k)} style={{ background: "none", border: "none", color: T.textMuted, cursor: "pointer", fontSize: 12 }}>Quitar</button>}
            </div>
            {k === "signature" ? <textarea rows={3} value={val} onChange={e => set(k, e.target.value)} style={inp} /> : <input value={val} onChange={e => set(k, e.target.value)} style={inp} />}
          </div>
        ))}
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <input placeholder="Nueva variable (ej. oferta)" value={newKey} onChange={e => setNewKey(e.target.value)} onKeyDown={e => e.key === "Enter" && add()} style={{ ...inp, width: 260 }} />
          <button onClick={add} style={{ padding: "8px 14px", background: T.accentBg, color: T.accentText, border: "none", borderRadius: 7, fontSize: 12, cursor: "pointer" }}>+ Añadir</button>
        </div>
      </div>
    </div>
  );
}
