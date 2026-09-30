"use client";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

type Theme = Record<string, string>;
type ListSummary = { id: string; name: string; source: string; created_at?: string; count: number; with_phone: number; with_email: number; campaigns: string[] };
type HistoryItem = { id: string; date: string; total: number; high: number; with_phone: number; searches: { label: string; count: number }[] };
type Preview = { filename: string; total: number; columns: string[]; mapping: Record<string, string | null>; sample: Record<string, string>[]; file: File };

const FIELD_LABEL: Record<string, string> = { name: "Negocio", phone: "Teléfono / WhatsApp", email: "Email", category: "Categoría", zone: "Ciudad / zona", contact: "Nombre del contacto", website: "Web" };
const SRC_ICON: Record<string, string> = { search: "⚡", csv: "⬆" };

export default function LeadsLibrary({ T, API, showToast, onCreateCampaign }: {
  T: Theme; API: string; showToast: (m: string) => void; onCreateCampaign: (listId: string) => void;
}) {
  const [lists, setLists] = useState<ListSummary[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [selId, setSelId] = useState<string | null>(null);
  const [leads, setLeads] = useState<any[]>([]);
  const [loadingLeads, setLoadingLeads] = useState(false);
  const [drag, setDrag] = useState(false);
  const [previews, setPreviews] = useState<Preview[]>([]);
  const [importing, setImporting] = useState(false);
  const [q, setQ] = useState("");
  const [chip, setChip] = useState<"all" | "high" | "phone" | "email">("all");
  const [view, setView] = useState<"table" | "cards">("table");
  const [page, setPage] = useState(0);
  const [showHist, setShowHist] = useState(true);
  const fileRef = useRef<HTMLInputElement>(null);
  const PAGE = 25;

  const load = useCallback(async () => {
    try {
      const [a, b] = await Promise.all([fetch(`${API}/lists`), fetch(`${API}/history`)]);
      if (a.ok) setLists(await a.json());
      if (b.ok) setHistory(await b.json());
    } catch {}
  }, [API]);
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, [load]);

  // primera lista seleccionada por defecto
  useEffect(() => { if (!selId && lists.length) setSelId(lists.find(l => l.id === "s_all")?.id || lists[0].id); }, [lists, selId]);

  useEffect(() => {
    if (!selId) return;
    setLoadingLeads(true); setPage(0);
    fetch(`${API}/lists/${selId}/leads`).then(r => r.ok ? r.json() : []).then(setLeads).catch(() => setLeads([])).finally(() => setLoadingLeads(false));
  }, [selId, API]);

  // ── importar ──
  const onFiles = async (files: FileList | File[]) => {
    const next: Preview[] = [];
    for (const f of Array.from(files)) {
      if (!/\.(csv|xlsx|xls)$/i.test(f.name)) { showToast(`${f.name}: solo CSV o Excel`); continue; }
      const fd = new FormData(); fd.append("file", f);
      const r = await fetch(`${API}/lists/import/preview`, { method: "POST", body: fd });
      if (r.ok) next.push({ ...(await r.json()), file: f });
      else { const e = await r.json().catch(() => ({})); showToast(e.detail || `No pude leer ${f.name}`); }
    }
    if (next.length) setPreviews(p => [...p, ...next]);
  };

  const confirmImport = async (p: Preview, name: string, mapping: Record<string, string | null>) => {
    setImporting(true);
    const fd = new FormData();
    fd.append("file", p.file); fd.append("name", name); fd.append("mapping", JSON.stringify(mapping));
    const r = await fetch(`${API}/lists/import`, { method: "POST", body: fd });
    setImporting(false);
    if (r.ok) {
      const l: ListSummary = await r.json();
      showToast(`${l.count} leads importados`);
      setPreviews(ps => ps.filter(x => x !== p));
      await load(); setSelId(l.id);
    } else { const e = await r.json().catch(() => ({})); showToast(e.detail || "No se pudo importar"); }
  };

  const delList = async (id: string) => {
    if (!confirm("¿Eliminar esta lista? (Las campañas que ya la usan conservan sus leads)")) return;
    await fetch(`${API}/lists/${id}`, { method: "DELETE" });
    if (selId === id) setSelId(null);
    load();
  };

  const sel = lists.find(l => l.id === selId);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    return leads.filter(l =>
      (!s || `${l.name} ${l.category || ""} ${l.zone || ""} ${l.phone || ""} ${l.email || ""}`.toLowerCase().includes(s)) &&
      (chip === "all" || (chip === "high" && l.priority === "high") || (chip === "phone" && l.phone) || (chip === "email" && l.email))
    );
  }, [leads, q, chip]);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE));
  const slice = filtered.slice(page * PAGE, page * PAGE + PAGE);

  const fmtDate = (s?: string) => s ? new Date(s).toLocaleString("es-CO", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
  const chipBtn = (k: typeof chip, label: string, n: number) => (
    <button key={k} onClick={() => { setChip(k); setPage(0); }} style={{ fontSize: 12, padding: "5px 11px", borderRadius: 20, cursor: "pointer", border: `1px solid ${chip === k ? "#2563EB" : T.border}`, background: chip === k ? "rgba(37,99,235,0.12)" : "transparent", color: chip === k ? "#2563EB" : T.textSecondary }}>{label} <span style={{ opacity: 0.6 }}>{n}</span></button>
  );
  const pc = (p?: string) => p === "high" ? "#E8442A" : p === "medium" ? "#D97706" : "#6B7280";

  return (
    <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
      {/* ═════ panel izquierdo: importar + listas + historial ═════ */}
      <div style={{ width: 300, borderRight: `1px solid ${T.border}`, background: T.cardBg, display: "flex", flexDirection: "column", flexShrink: 0 }}>
        <div style={{ padding: 14 }}>
          <div
            onDragOver={e => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
            onDrop={e => { e.preventDefault(); setDrag(false); onFiles(e.dataTransfer.files); }}
            onClick={() => fileRef.current?.click()}
            style={{ border: `1.5px dashed ${drag ? "#2563EB" : T.border}`, background: drag ? "rgba(37,99,235,0.08)" : T.inputBg, borderRadius: 10, padding: "16px 10px", textAlign: "center", cursor: "pointer", transition: "all .15s" }}>
            <div style={{ fontSize: 20 }}>⬆</div>
            <div style={{ fontSize: 13, fontWeight: 500, color: T.text, marginTop: 4 }}>Suelta un CSV o Excel aquí</div>
            <div style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>o haz clic para elegirlo</div>
            <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" multiple hidden onChange={e => { if (e.target.files) onFiles(e.target.files); e.target.value = ""; }} />
          </div>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "0 10px 10px" }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", padding: "4px 6px 8px" }}>Mis listas</div>
          {lists.length === 0 && <div style={{ fontSize: 12, color: T.textMuted, padding: 8 }}>Aún no hay listas. Ejecuta una búsqueda o importa un CSV.</div>}
          {lists.map(l => (
            <div key={l.id} onClick={() => setSelId(l.id)} style={{ padding: "9px 10px", borderRadius: 8, cursor: "pointer", marginBottom: 2, background: selId === l.id ? T.navActiveBg : "transparent" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 6 }}>
                <span style={{ fontSize: 13, color: T.text, fontWeight: selId === l.id ? 600 : 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{SRC_ICON[l.source] || "•"} {l.name}</span>
                <span style={{ fontSize: 12, color: T.textMuted }}>{l.count}</span>
              </div>
              <div style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>◔ {l.with_phone} · ✉ {l.with_email}{l.campaigns.length ? ` · en ${l.campaigns.length} campaña(s)` : ""}</div>
            </div>
          ))}

          <div onClick={() => setShowHist(!showHist)} style={{ fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", padding: "16px 6px 8px", cursor: "pointer" }}>
            Historial de búsquedas {showHist ? "▾" : "▸"}
          </div>
          {showHist && history.length === 0 && <div style={{ fontSize: 12, color: T.textMuted, padding: 8 }}>Sin búsquedas todavía.</div>}
          {showHist && history.map(h => (
            <div key={h.id} style={{ padding: "8px 10px", borderLeft: `2px solid ${T.border}`, marginLeft: 6, marginBottom: 6 }}>
              <div style={{ fontSize: 12, color: T.text, fontWeight: 500 }}>{h.total} leads <span style={{ color: T.textMuted, fontWeight: 400 }}>· {fmtDate(h.date)}</span></div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 5 }}>
                {h.searches.slice(0, 4).map(s => {
                  const target = lists.find(l => l.name === s.label);
                  return <span key={s.label} onClick={() => target && setSelId(target.id)} style={{ fontSize: 10, padding: "2px 7px", borderRadius: 10, background: T.inputBg, color: T.textSecondary, cursor: target ? "pointer" : "default" }}>{s.label} · {s.count}</span>;
                })}
              </div>
              <div style={{ fontSize: 10, color: T.textMuted, marginTop: 4 }}>🔥 {h.high} alta prioridad · ◔ {h.with_phone} con teléfono</div>
            </div>
          ))}
        </div>
      </div>

      {/* ═════ panel derecho: leads de la lista ═════ */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: "14px 24px", borderBottom: `1px solid ${T.border}`, background: T.cardBg }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, color: T.text }}>{sel?.name || "Selecciona una lista"}</div>
              {sel && <div style={{ fontSize: 12, color: T.textMuted, marginTop: 2 }}>{sel.count} leads · {sel.with_phone} con WhatsApp · {sel.with_email} con email</div>}
            </div>
            {sel && (
              <div style={{ display: "flex", gap: 8 }}>
                {sel.source === "csv" && <button onClick={() => delList(sel.id)} style={{ padding: "7px 12px", background: "transparent", border: `1px solid ${T.border}`, borderRadius: 7, fontSize: 12, color: T.textMuted, cursor: "pointer" }}>Eliminar lista</button>}
                <button onClick={() => onCreateCampaign(sel.id)} style={{ padding: "8px 14px", background: T.accentBg, color: T.accentText, border: "none", borderRadius: 7, fontSize: 12, fontWeight: 500, cursor: "pointer" }}>▶ Crear campaña con esta lista</button>
              </div>
            )}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <input placeholder="Buscar negocio, ciudad, teléfono…" value={q} onChange={e => { setQ(e.target.value); setPage(0); }}
              style={{ padding: "7px 10px", background: T.inputBg, border: `1px solid ${T.border}`, borderRadius: 6, color: T.text, fontSize: 13, width: 260 }} />
            {chipBtn("all", "Todos", leads.length)}
            {chipBtn("high", "Alta prioridad", leads.filter(l => l.priority === "high").length)}
            {chipBtn("phone", "Con WhatsApp", leads.filter(l => l.phone).length)}
            {chipBtn("email", "Con email", leads.filter(l => l.email).length)}
            <div style={{ marginLeft: "auto", display: "flex", border: `1px solid ${T.border}`, borderRadius: 6, overflow: "hidden" }}>
              {(["table", "cards"] as const).map(v => <button key={v} onClick={() => setView(v)} style={{ padding: "5px 10px", fontSize: 12, border: "none", cursor: "pointer", background: view === v ? T.navActiveBg : "transparent", color: T.text }}>{v === "table" ? "≡ Tabla" : "▦ Tarjetas"}</button>)}
            </div>
          </div>
        </div>

        <div style={{ flex: 1, overflowY: "auto", background: view === "table" ? T.cardBg : T.bg }}>
          {loadingLeads ? <div style={{ padding: 40, textAlign: "center", color: T.textMuted }}>Cargando…</div> :
            filtered.length === 0 ? <div style={{ padding: 60, textAlign: "center", color: T.textMuted, fontSize: 14 }}>{leads.length ? "Ningún lead coincide con el filtro" : "Esta lista está vacía"}</div> :
              view === "table" ? slice.map((l, i) => (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "1.8fr 1.2fr 1.2fr 60px 90px", gap: 12, padding: "11px 24px", borderBottom: `1px solid ${T.borderLight}`, alignItems: "center" }}>
                  <div><div style={{ fontSize: 13, fontWeight: 500, color: T.text }}>{l.name}</div><div style={{ fontSize: 11, color: T.textMuted }}>{[l.category, l.zone].filter(Boolean).join(" · ")}</div></div>
                  <div style={{ fontSize: 12, color: l.phone ? T.textSecondary : T.textMuted }}>{l.phone ? "◔ " + l.phone : "—"}</div>
                  <div style={{ fontSize: 12, color: l.email ? T.textSecondary : T.textMuted, overflow: "hidden", textOverflow: "ellipsis" }}>{l.email ? "✉ " + l.email : "—"}</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: pc(l.priority) }}>{l.score ?? ""}</div>
                  <div>{l.priority && <span style={{ fontSize: 11, padding: "3px 8px", borderRadius: 20, background: pc(l.priority) + "22", color: pc(l.priority) }}>{l.priority === "high" ? "Alta" : l.priority === "medium" ? "Media" : "Baja"}</span>}</div>
                </div>
              )) : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(240px,1fr))", gap: 10, padding: 20 }}>
                  {slice.map((l, i) => (
                    <div key={i} style={{ background: T.cardBg, border: `1px solid ${T.border}`, borderRadius: 10, padding: 14 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{l.name}</div>
                        {l.score != null && <div style={{ fontSize: 16, fontWeight: 700, color: pc(l.priority) }}>{l.score}</div>}
                      </div>
                      <div style={{ fontSize: 11, color: T.textMuted, margin: "4px 0 10px" }}>{[l.category, l.zone].filter(Boolean).join(" · ")}</div>
                      <div style={{ fontSize: 12, color: T.textSecondary, lineHeight: 1.8 }}>{l.phone && <div>◔ {l.phone}</div>}{l.email && <div>✉ {l.email}</div>}{l.website && <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>🌐 {l.website.replace(/https?:\/\//, "")}</div>}</div>
                    </div>
                  ))}
                </div>
              )}
        </div>

        {filtered.length > PAGE && (
          <div style={{ padding: "10px 24px", borderTop: `1px solid ${T.border}`, background: T.cardBg, display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12, color: T.textMuted }}>
            <span>{page * PAGE + 1}–{Math.min((page + 1) * PAGE, filtered.length)} de {filtered.length}</span>
            <span style={{ display: "flex", gap: 6 }}>
              <button disabled={page === 0} onClick={() => setPage(page - 1)} style={{ padding: "4px 10px", border: `1px solid ${T.border}`, background: "transparent", color: T.text, borderRadius: 6, cursor: "pointer", opacity: page === 0 ? 0.4 : 1 }}>←</button>
              <span style={{ padding: "4px 6px" }}>{page + 1} / {pages}</span>
              <button disabled={page >= pages - 1} onClick={() => setPage(page + 1)} style={{ padding: "4px 10px", border: `1px solid ${T.border}`, background: "transparent", color: T.text, borderRadius: 6, cursor: "pointer", opacity: page >= pages - 1 ? 0.4 : 1 }}>→</button>
            </span>
          </div>
        )}
      </div>

      {/* ═════ modal: confirmar importación con mapeo de columnas ═════ */}
      {previews[0] && <ImportModal key={previews[0].filename} T={T} p={previews[0]} busy={importing}
        onCancel={() => setPreviews(ps => ps.slice(1))} onConfirm={confirmImport} />}
    </div>
  );
}

function ImportModal({ T, p, busy, onCancel, onConfirm }: {
  T: Theme; p: Preview; busy: boolean; onCancel: () => void;
  onConfirm: (p: Preview, name: string, mapping: Record<string, string | null>) => void;
}) {
  const [name, setName] = useState(p.filename.replace(/\.[^.]+$/, ""));
  const [map, setMap] = useState<Record<string, string | null>>(p.mapping);
  const sel: React.CSSProperties = { padding: "6px 8px", background: T.inputBg, border: `1px solid ${T.border}`, borderRadius: 6, color: T.text, fontSize: 13, width: 220 };
  const ok = !!(map.name || map.phone || map.email);
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 9000, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: T.cardBg, border: `1px solid ${T.border}`, borderRadius: 12, width: 640, maxHeight: "88vh", overflowY: "auto", padding: 24 }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: T.text }}>Importar {p.filename}</div>
        <div style={{ fontSize: 12, color: T.textMuted, margin: "4px 0 16px" }}>{p.total} filas · revisa qué columna es cada dato (ya intenté adivinarlo)</div>

        <label style={{ fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: "uppercase" }}>Nombre de la lista</label>
        <input value={name} onChange={e => setName(e.target.value)} style={{ ...sel, width: "100%", margin: "4px 0 16px" }} />

        {Object.keys(FIELD_LABEL).map(f => (
          <div key={f} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <span style={{ fontSize: 13, color: T.textSecondary }}>{FIELD_LABEL[f]}</span>
            <select value={map[f] || ""} onChange={e => setMap({ ...map, [f]: e.target.value || null })} style={sel}>
              <option value="">— no usar —</option>
              {p.columns.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        ))}

        <div style={{ fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: "uppercase", margin: "16px 0 6px" }}>Primeras filas</div>
        <div style={{ overflowX: "auto", border: `1px solid ${T.border}`, borderRadius: 8 }}>
          <table style={{ fontSize: 11, color: T.textSecondary, borderCollapse: "collapse", width: "100%" }}>
            <thead><tr>{p.columns.map(c => <th key={c} style={{ padding: "6px 8px", textAlign: "left", color: T.textMuted, whiteSpace: "nowrap" }}>{c}</th>)}</tr></thead>
            <tbody>{p.sample.map((r, i) => <tr key={i} style={{ borderTop: `1px solid ${T.borderLight}` }}>{p.columns.map(c => <td key={c} style={{ padding: "5px 8px", whiteSpace: "nowrap" }}>{String(r[c] ?? "").slice(0, 28)}</td>)}</tr>)}</tbody>
          </table>
        </div>
        {!ok && <div style={{ fontSize: 12, color: "#E8442A", marginTop: 10 }}>Elige al menos la columna de nombre, teléfono o email.</div>}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
          <button onClick={onCancel} style={{ padding: "8px 14px", background: "transparent", border: `1px solid ${T.border}`, borderRadius: 7, color: T.textSecondary, cursor: "pointer", fontSize: 13 }}>Cancelar</button>
          <button disabled={!ok || busy} onClick={() => onConfirm(p, name, map)} style={{ padding: "8px 16px", background: T.accentBg, color: T.accentText, border: "none", borderRadius: 7, fontSize: 13, fontWeight: 500, cursor: "pointer", opacity: !ok || busy ? 0.5 : 1 }}>{busy ? "Importando…" : `Importar ${p.total} filas`}</button>
        </div>
      </div>
    </div>
  );
}
