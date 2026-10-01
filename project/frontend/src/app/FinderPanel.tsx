"use client";
import React, { useEffect, useRef, useState } from "react";

type Row = { email: string; name: string; website: string; category: string; zone: string; phone?: string; extra?: Record<string, any> };
type Job = { id: string; status: "running" | "done" | "error"; progress: string; total: number; checked: number; emails: number;
  list_name: string | null; error: string | null; log_tail: string[]; results: Row[] };

// Panel "Leads + Emails": usa las búsquedas, el modo y el log de la pestaña Buscar.
export default function FinderPanel({ T, S, API, configs, maxResults, mode, addLog, showToast }: {
  T: Record<string, string>; S: any; API: string; configs: { query: string; zone: string }[];
  maxResults: number; mode: string; addLog: (m: string) => void; showToast: (m: string) => void;
}) {
  const [f, setF] = useState({ employees_min: "", employees_max: "", include_unknown_size: true, min_rating: "", min_reviews: "",
    max_reviews: "", require_website: true, require_email: true, require_phone: false, exclude_chains: true, use_linkedin_public: true, list_name: "" });
  const [job, setJob] = useState<Job | null>(null);
  const seen = useRef(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  const num = (v: string) => (v.trim() === "" ? null : Number(v));
  const running = job?.status === "running";

  const follow = (id: string) => {
    seen.current = 0;
    const tick = async () => {
      const r = await fetch(`${API}/emails/jobs/${id}`).catch(() => null);
      if (!r || !r.ok) return;
      const j: Job = await r.json();
      setJob(j);
      const fresh = j.log_tail.filter((_, i) => i >= seen.current);
      fresh.forEach(l => addLog(l.replace(/^\d\d:\d\d:\d\d /, "")));
      seen.current = j.log_tail.length;
      if (j.status !== "running") {
        if (timer.current) clearInterval(timer.current);
        if (j.status === "done") showToast(j.progress); else showToast(j.error || "Falló");
      }
    };
    tick(); timer.current = setInterval(tick, 1500);
  };

  const run = async () => {
    const rows = configs.filter(c => c.query.trim());
    if (!rows.length) { showToast("Añade al menos una búsqueda arriba"); return; }
    const body = {
      categories: Array.from(new Set(rows.map(c => c.query.trim()))),
      locations: Array.from(new Set(rows.map(c => c.zone.trim()).filter(Boolean))),
      max_results: Math.min(500, maxResults * rows.length), mode,
      employees_min: num(f.employees_min), employees_max: num(f.employees_max), include_unknown_size: f.include_unknown_size,
      min_rating: num(f.min_rating), min_reviews: num(f.min_reviews), max_reviews: num(f.max_reviews),
      require_website: f.require_website, require_email: f.require_email, require_phone: f.require_phone,
      exclude_chains: f.exclude_chains, use_linkedin_public: f.use_linkedin_public, list_name: f.list_name || null,
    };
    const r = await fetch(`${API}/finder/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).catch(() => null);
    if (!r || !r.ok) { showToast("No pude iniciar la búsqueda de emails"); return; }
    const j: Job = await r.json();
    addLog("▶ Leads + Emails iniciado"); setJob(j); follow(j.id);
  };

  const stop = async () => { if (job) { await fetch(`${API}/emails/jobs/${job.id}/cancel`, { method: "POST" }); addLog("⏹ Búsqueda de emails detenida"); } };
  const copy = async () => { if (job) { try { await navigator.clipboard.writeText(job.results.map(r => r.email).join("\n")); showToast(`${job.results.length} emails copiados`); } catch { showToast("No pude copiar"); } } };

  const Chk = ({ k, label }: { k: keyof typeof f; label: string }) => (
    <label style={{ fontSize: 12, color: T.textSecondary, display: "flex", gap: 6, alignItems: "center" }}>
      <input type="checkbox" checked={f[k] as boolean} onChange={e => setF({ ...f, [k]: e.target.checked })} /> {label}
    </label>);
  const Num = ({ k, label, ph }: { k: keyof typeof f; label: string; ph: string }) => (
    <div><div style={{ fontSize: 11, color: T.textMuted, marginBottom: 4 }}>{label}</div>
      <input type="number" value={f[k] as string} placeholder={ph} onChange={e => setF({ ...f, [k]: e.target.value })} style={S.input} /></div>);

  return (
    <div style={S.card}>
      <div style={S.cardTitle}>Leads + Emails (Gmail)</div>
      <p style={{ fontSize: 12, color: T.textMuted, marginTop: 0 }}>
        Usa las búsquedas y el modo de arriba. Encuentra negocios en Google Maps, saca su correo público y filtra por tamaño.
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, marginBottom: 12 }}>
        <Num k="employees_min" label="Empleados mín." ph="ej. 5" />
        <Num k="employees_max" label="Empleados máx." ph="ej. 50" />
        <Num k="min_rating" label="Rating mín." ph="ej. 4" />
        <Num k="min_reviews" label="Reseñas mín." ph="0" />
        <Num k="max_reviews" label="Reseñas máx." ph="sin límite" />
        <div><div style={{ fontSize: 11, color: T.textMuted, marginBottom: 4 }}>Nombre de la lista</div>
          <input value={f.list_name} placeholder="automático" onChange={e => setF({ ...f, list_name: e.target.value })} style={S.input} /></div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8, marginBottom: 14 }}>
        <Chk k="include_unknown_size" label="Incluir si no se conoce el tamaño" />
        <Chk k="require_website" label="Debe tener sitio web" />
        <Chk k="require_email" label="Debe tener email" />
        <Chk k="require_phone" label="Debe tener teléfono" />
        <Chk k="exclude_chains" label="Excluir cadenas grandes" />
        <Chk k="use_linkedin_public" label="Tamaño desde LinkedIn público (sin login)" />
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={run} disabled={running} style={{ ...S.btnPrimary, flex: 1, opacity: running ? 0.5 : 1 }}>
          {running ? `⟳ ${job?.progress}` : "▶  Buscar leads + emails"}
        </button>
        {running && <button onClick={stop} style={S.btnDanger}>⏹ Parar</button>}
      </div>

      {job && job.results.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>
              {job.results.length} emails{job.list_name ? ` · guardado en «${job.list_name}» (Engage → Lanzar campaña)` : ""}
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button onClick={copy} style={S.btnGhost}>Copiar emails</button>
              <a href={`${API}/emails/jobs/${job.id}/csv`} style={{ ...S.btnGhost, textDecoration: "none" }}>CSV</a>
            </div>
          </div>
          <div style={{ maxHeight: 260, overflowY: "auto", border: `1px solid ${T.border}`, borderRadius: 6 }}>
            {job.results.map(r => (
              <div key={r.email} style={{ display: "grid", gridTemplateColumns: "1.3fr 1.5fr 0.7fr", gap: 8, padding: "7px 10px", fontSize: 12, borderBottom: `1px solid ${T.border}`, color: T.textSecondary }}>
                <span style={{ color: T.text }}>{r.name}</span><span>{r.email}</span>
                <span>{r.extra?.employees_min != null ? `${r.extra.employees_min}${r.extra.employees_max !== r.extra.employees_min ? "–" + (r.extra.employees_max ?? "+") : ""} emp.` : "tamaño ?"}</span>
              </div>))}
          </div>
        </div>
      )}
    </div>
  );
}
