"use client";
import React, { useCallback, useEffect, useRef, useState } from "react";

type Theme = Record<string, string>;
type Row = { email: string; name: string; website: string; category: string; zone: string; source: string };
type Job = {
  id: string; source: string; title: string; status: "running" | "done" | "error"; progress: string;
  total: number; checked: number; emails: number; list_name: string | null; error: string | null;
  log_tail: string[]; results: Row[];
};
type ListSummary = { id: string; name: string; count: number; with_email: number };
type Src = "web" | "linkedin" | "list";

const SOURCES: { key: Src; icon: string; label: string; desc: string }[] = [
  { key: "web", icon: "🌐", label: "Web (gratis)", desc: "Busca negocios en internet, entra a cada sitio y saca sus correos públicos." },
  { key: "linkedin", icon: "💼", label: "LinkedIn", desc: "Empresas de LinkedIn por palabra clave (vía Apify). Luego busca su web y saca el correo." },
  { key: "list", icon: "📍", label: "Leads que ya tengo", desc: "Toma tus leads de Google Maps que tienen web pero no correo y se lo busca." },
];

export default function EmailScraper({ T, API, showToast }: { T: Theme; API: string; showToast: (m: string) => void }) {
  const [src, setSrc] = useState<Src>("web");
  const [query, setQuery] = useState("");
  const [zone, setZone] = useState("Cali, Colombia");
  const [limit, setLimit] = useState(40);
  const [lists, setLists] = useState<ListSummary[]>([]);
  const [listId, setListId] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [history, setHistory] = useState<Job[]>([]);
  const [conn, setConn] = useState<{ apify_connected: boolean; apify_token_hint: string; default_actor: string } | null>(null);
  const [token, setToken] = useState("");
  const [actor, setActor] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const loadConn = useCallback(() => fetch(`${API}/emails/settings`).then(r => r.ok ? r.json() : null).then(c => { setConn(c); if (c && !actor) setActor(c.default_actor); }).catch(() => {}), [API]); // eslint-disable-line
  const loadHistory = useCallback(() => fetch(`${API}/emails/jobs`).then(r => r.ok ? r.json() : []).then(setHistory).catch(() => {}), [API]);
  useEffect(() => {
    loadConn(); loadHistory();
    fetch(`${API}/lists`).then(r => r.ok ? r.json() : []).then((l: ListSummary[]) => { setLists(l); if (l.length) setListId(l[0].id); }).catch(() => {});
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [API]); // eslint-disable-line

  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [job?.log_tail.length]);

  const follow = (id: string) => {
    if (timer.current) clearInterval(timer.current);
    const tick = async () => {
      const r = await fetch(`${API}/emails/jobs/${id}`).catch(() => null);
      if (!r || !r.ok) return;
      const j: Job = await r.json();
      setJob(j);
      if (j.status !== "running") {
        if (timer.current) clearInterval(timer.current);
        loadHistory();
        if (j.status === "done") showToast(j.progress);
      }
    };
    tick(); timer.current = setInterval(tick, 1500);
  };

  const run = async () => {
    const r = await fetch(`${API}/emails/run`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: src, query, zone, limit, list_id: listId || null, actor: src === "linkedin" && advanced ? actor : null }),
    });
    if (r.ok) { const j = await r.json(); setJob(j); follow(j.id); }
    else showToast((await r.json().catch(() => ({}))).detail || "No pude iniciar");
  };
  const stop = async () => { if (job) await fetch(`${API}/emails/jobs/${job.id}/cancel`, { method: "POST" }); };
  const saveToken = async () => {
    const r = await fetch(`${API}/emails/settings`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ apify_token: token }) });
    if (r.ok) { setToken(""); showToast("Token de Apify guardado"); loadConn(); }
  };
  const copyAll = async () => {
    if (!job) return;
    try { await navigator.clipboard.writeText(job.results.map(r => r.email).join("\n")); showToast(`${job.results.length} emails copiados`); } catch { showToast("No pude copiar"); }
  };

  const running = job?.status === "running";
  const needsToken = src === "linkedin" && !conn?.apify_connected;
  const canRun = !running && !needsToken && (src === "list" ? !!listId : !!query.trim());
  const pct = job && job.total ? Math.round((job.checked / job.total) * 100) : 0;

  const card: React.CSSProperties = { background: T.cardBg, border: `1px solid ${T.border}`, borderRadius: 10, padding: 20, marginBottom: 14 };
  const inp: React.CSSProperties = { width: "100%", padding: "8px 10px", background: T.inputBg, border: `1px solid ${T.border}`, borderRadius: 6, color: T.text, fontSize: 13, fontFamily: "inherit" };
  const lab: React.CSSProperties = { fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 4 };
  const btn: React.CSSProperties = { padding: "10px 20px", background: T.accentBg, color: T.accentText, border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer" };
  const fmtT = (s: string) => s;

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: 32 }}>
      <h2 style={{ fontSize: 20, fontWeight: 700, margin: "0 0 4px", color: T.text }}>Scraper de emails</h2>
      <p style={{ fontSize: 13, color: T.textMuted, margin: "0 0 20px" }}>Encuentra correos de negocios y empresas para tus campañas por Gmail. Lo que encuentres queda guardado como lista y aparece solo en Engage.</p>

      {/* fuente */}
      <div style={card}>
        <div style={{ fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 12 }}>¿De dónde sacamos los correos?</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10 }}>
          {SOURCES.map(s => (
            <div key={s.key} onClick={() => !running && setSrc(s.key)} style={{ cursor: running ? "default" : "pointer", padding: 14, borderRadius: 10, border: `1.5px solid ${src === s.key ? "#2563EB" : T.border}`, background: src === s.key ? "rgba(37,99,235,0.08)" : "transparent" }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: T.text }}>{s.icon} {s.label}</div>
              <div style={{ fontSize: 11, color: T.textMuted, marginTop: 4, lineHeight: 1.5 }}>{s.desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* token de Apify (solo LinkedIn) */}
      {src === "linkedin" && (
        <div style={card}>
          {conn?.apify_connected ? (
            <div>
              <div style={{ fontSize: 12, color: "#16A34A", marginBottom: 8 }}>● Apify conectado ({conn.apify_token_hint})
                <span style={{ marginLeft: 10, color: T.textMuted, cursor: "pointer", textDecoration: "underline" }} onClick={() => setAdvanced(!advanced)}>{advanced ? "ocultar avanzado" : "avanzado"}</span>
                <span style={{ marginLeft: 10, color: T.textMuted, cursor: "pointer", textDecoration: "underline" }} onClick={async () => { await fetch(`${API}/emails/settings`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ apify_token: "" }) }); loadConn(); }}>desconectar</span>
              </div>
              {advanced && (
                <div style={{ marginTop: 8 }}>
                  <label style={lab}>Actor de Apify (debe aceptar «query» y «page»)</label>
                  <input style={{ ...inp, maxWidth: 420 }} value={actor} onChange={e => setActor(e.target.value)} />
                </div>
              )}
              <div style={{ fontSize: 11, color: T.textMuted, marginTop: 8, lineHeight: 1.6 }}>LinkedIn prohíbe el scraping en sus términos de uso; este actor solo lee páginas públicas de empresas, bajo tu responsabilidad. Cada búsqueda consume un poco del crédito de tu cuenta de Apify.</div>
            </div>
          ) : (
            <div>
              <div style={{ fontSize: 13, color: T.textSecondary, lineHeight: 1.8, marginBottom: 12 }}>
                <b>Conecta Apify (una sola vez):</b> crea una cuenta gratis en <b>apify.com</b> → <b>Settings → API &amp; Integrations</b> → copia tu <b>Personal API token</b> y pégalo aquí.
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <input type="password" style={{ ...inp, maxWidth: 380 }} placeholder="apify_api_…" value={token} onChange={e => setToken(e.target.value)} />
                <button style={{ ...btn, opacity: token.trim() ? 1 : 0.5 }} disabled={!token.trim()} onClick={saveToken}>Guardar token</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* formulario */}
      <div style={card}>
        {src === "list" ? (
          <div style={{ marginBottom: 14 }}>
            <label style={lab}>Lista a revisar</label>
            <select style={{ ...inp, maxWidth: 480 }} value={listId} onChange={e => setListId(e.target.value)}>
              {lists.length === 0 && <option value="">Aún no tienes listas (corre el scraper de Google Maps primero)</option>}
              {lists.map(l => <option key={l.id} value={l.id}>{l.name} — {l.count} leads ({l.with_email} con email)</option>)}
            </select>
            <div style={{ fontSize: 11, color: T.textMuted, marginTop: 6 }}>Solo revisa los leads que tienen web y todavía no tienen email; los correos encontrados se suman a esa misma lista.</div>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1.2fr 110px", gap: 12, marginBottom: 14 }}>
            <div><label style={lab}>{src === "linkedin" ? "Tipo de empresa" : "Tipo de negocio"}</label>
              <input style={inp} placeholder={src === "linkedin" ? "agencias de marketing, software…" : "restaurantes, clínicas dentales…"} value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === "Enter" && canRun && run()} /></div>
            <div><label style={lab}>Ciudad / país</label><input style={inp} value={zone} onChange={e => setZone(e.target.value)} /></div>
            <div><label style={lab}>{src === "linkedin" ? "Empresas" : "Sitios"}</label><input type="number" min={1} max={200} style={inp} value={limit} onChange={e => setLimit(Number(e.target.value))} /></div>
          </div>
        )}
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          {running ? (
            <button onClick={stop} style={{ ...btn, background: "rgba(232,68,42,0.14)", color: "#E8442A" }}>■ Detener</button>
          ) : (
            <button onClick={run} disabled={!canRun} style={{ ...btn, opacity: canRun ? 1 : 0.4 }}>▶ Buscar emails</button>
          )}
          {needsToken && <span style={{ fontSize: 12, color: "#D97706" }}>Conecta tu token de Apify arriba para usar LinkedIn.</span>}
        </div>
      </div>

      {/* progreso + log */}
      {job && (
        <div style={card}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: job.status === "error" ? "#E8442A" : T.text }}>
              {job.status === "running" ? "⏳ " : job.status === "done" ? "✓ " : "✗ "}{job.status === "error" ? (job.error || "Falló") : job.progress}
            </div>
            <div style={{ fontSize: 12, color: T.textMuted }}>{job.emails} emails · {job.checked}/{job.total || "–"} sitios</div>
          </div>
          {job.total > 0 && <div style={{ height: 6, background: T.inputBg, borderRadius: 3, overflow: "hidden", marginBottom: 12 }}><div style={{ width: `${pct}%`, height: "100%", background: "#2563EB", transition: "width .3s" }} /></div>}
          <div ref={logRef} style={{ background: "#000", color: "#9CDCAB", fontFamily: "monospace", fontSize: 12, lineHeight: 1.7, padding: 12, borderRadius: 8, height: 130, overflowY: "auto" }}>
            {job.log_tail.length ? job.log_tail.map((l, i) => <div key={i}>{fmtT(l)}</div>) : <div style={{ opacity: 0.5 }}>Esperando actividad…</div>}
          </div>
        </div>
      )}

      {/* resultados */}
      {job && job.results.length > 0 && (
        <div style={{ ...card, padding: 0, overflow: "hidden" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 20px", borderBottom: `1px solid ${T.border}` }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: T.text }}>{job.results.length} emails encontrados</div>
              {job.list_name && <div style={{ fontSize: 11, color: "#16A34A", marginTop: 2 }}>Guardados como lista «{job.list_name}» · ya disponible en Engage</div>}
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={copyAll} style={{ padding: "6px 12px", background: "transparent", border: `1px solid ${T.border}`, borderRadius: 7, fontSize: 12, color: T.textSecondary, cursor: "pointer" }}>Copiar emails</button>
              <a href={`${API}/emails/jobs/${job.id}/csv`} style={{ padding: "6px 12px", border: `1px solid ${T.border}`, borderRadius: 7, fontSize: 12, color: T.textSecondary, textDecoration: "none" }}>↓ CSV</a>
            </div>
          </div>
          <div style={{ maxHeight: 360, overflowY: "auto" }}>
            {job.results.map(r => (
              <div key={r.email} style={{ display: "grid", gridTemplateColumns: "1.3fr 1.3fr 1.4fr", gap: 12, padding: "9px 20px", borderBottom: `1px solid ${T.borderLight}`, alignItems: "center" }}>
                <div style={{ fontSize: 13, fontWeight: 500, color: "#2563EB" }}>✉ {r.email}</div>
                <div style={{ fontSize: 13, color: T.text }}>{r.name}</div>
                <div style={{ fontSize: 12, color: T.textMuted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.website.replace(/^https?:\/\//, "")}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* historial */}
      {history.length > 0 && (
        <div style={card}>
          <div style={{ fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10 }}>Búsquedas recientes</div>
          {history.slice(0, 8).map(h => (
            <div key={h.id} onClick={() => { setJob(null); follow(h.id); }} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderTop: `1px solid ${T.borderLight}`, cursor: "pointer", fontSize: 13, color: T.text }}>
              <span>{h.title}</span>
              <span style={{ color: T.textMuted, fontSize: 12 }}>{h.status === "running" ? "en curso…" : h.status === "error" ? "falló" : `${h.emails} emails`}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
