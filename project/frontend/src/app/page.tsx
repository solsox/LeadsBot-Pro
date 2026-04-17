"use client";
import { useEffect, useState, useCallback, useRef } from "react";

const API = "/api";

type Lead = {
  name: string; category: string; zone: string;
  website: string | null; phone: string | null;
  score: number; priority: string; status: string;
  email_subject?: string; email_body?: string;
  whatsapp_msg?: string; address?: string;
  maps_url?: string; score_reasons?: string[];
};

type SearchConfig = { query: string; zone: string };
type Tab = "exec" | "leads" | "charts";

const PRIORITY_COLOR: Record<string, string> = {
  high: "#E8442A", medium: "#D97706", low: "#6B7280"
};
const PRIORITY_BG: Record<string, string> = {
  high: "#FEF2F0", medium: "#FFFBEB", low: "#F9FAFB"
};

export default function Home() {
  const [tab,        setTab]        = useState<Tab>("exec");
  const [leads,      setLeads]      = useState<Lead[]>([]);
  const [metrics,    setMetrics]    = useState<any>({});
  const [configs,    setConfigs]    = useState<SearchConfig[]>([]);
  const [logs,       setLogs]       = useState<string[]>(["Sistema listo. Ejecuta el pipeline para comenzar."]);
  const [running,    setRunning]    = useState(false);
  const [selected,   setSelected]   = useState<Set<string>>(new Set());
  const [expanded,   setExpanded]   = useState<string | null>(null);
  const [generating, setGenerating] = useState<string | null>(null);
  const [sending,    setSending]    = useState<string | null>(null);
  const [toast,      setToast]      = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const addLog = (msg: string) => {
    const time = new Date().toLocaleTimeString("es-ES");
    setLogs(prev => [...prev.slice(-100), `[${time}] ${msg}`]);
    setTimeout(() => logRef.current?.scrollTo(0, logRef.current.scrollHeight), 50);
  };

  const fetchAll = useCallback(async () => {
    try {
      const [lRes, mRes, cRes] = await Promise.all([
        fetch(`${API}/leads`),
        fetch(`${API}/metrics`),
        fetch(`${API}/config/search`),
      ]);
      if (lRes.ok) setLeads(await lRes.json());
      if (mRes.ok) setMetrics(await mRes.json());
      if (cRes.ok) setConfigs(await cRes.json());
    } catch {}
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);
  useEffect(() => {
    const t = setInterval(fetchAll, 30000);
    return () => clearInterval(t);
  }, [fetchAll]);

  const runPipeline = async () => {
    setRunning(true);
    addLog("▶ Iniciando pipeline...");
    try {
      const r = await fetch(`${API}/worker/run`, { method: "POST" });
      if (r.ok) {
        addLog("✓ Pipeline corriendo en background");
        configs.forEach(c => addLog(`  • ${c.query} en ${c.zone}`));
        let polls = 0;
        const t = setInterval(async () => {
          polls++;
          const res = await fetch(`${API}/metrics`);
          if (res.ok) {
            const m = await res.json();
            setMetrics(m);
            addLog(`→ scrapeados: ${m.leads_scraped} | calificados: ${m.leads_qualified}`);
            await fetchAll();
          }
          if (polls >= 120) { clearInterval(t); setRunning(false); addLog("✓ Pipeline completado"); showToast("Pipeline completado"); }
        }, 10000);
      }
    } catch { addLog("✗ Error conectando con backend"); setRunning(false); }
  };

  const saveConfig = async () => {
    await fetch(`${API}/config/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(configs),
    });
    showToast("Configuración guardada");
    addLog(`✓ Config guardada: ${configs.length} búsquedas`);
  };

  const addConfig    = () => setConfigs(p => [...p, { query: "", zone: "" }]);
  const removeConfig = (i: number) => setConfigs(p => p.filter((_, j) => j !== i));
  const updateConfig = (i: number, k: keyof SearchConfig, v: string) =>
    setConfigs(p => p.map((c, j) => j === i ? { ...c, [k]: v } : c));

  const toggleSelect = (name: string) =>
    setSelected(p => { const n = new Set(p); n.has(name) ? n.delete(name) : n.add(name); return n; });

  const generateMsg = async (lead: Lead) => {
    setGenerating(lead.name);
    addLog(`→ Generando mensaje para ${lead.name}...`);
    try {
      await fetch(`${API}/worker/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lead_name: lead.name }),
      });
      await new Promise(r => setTimeout(r, 3000));
      await fetchAll();
      addLog(`✓ Mensaje generado para ${lead.name}`);
      showToast(`Mensaje generado para ${lead.name}`);
    } catch { addLog(`✗ Error generando mensaje`); }
    setGenerating(null);
  };

  const sendLead = async (name: string) => {
    setSending(name);
    addLog(`→ Enviando email a ${name}...`);
    try {
      await fetch(`${API}/leads/${encodeURIComponent(name)}/send`, { method: "POST" });
      addLog(`✓ Email enviado a ${name}`);
      showToast(`Email enviado a ${name}`);
      await fetchAll();
    } catch { addLog(`✗ Error enviando`); }
    setSending(null);
  };

  const sendSelected = async () => {
    const names = Array.from(selected);
    for (const name of names) await sendLead(name);
    setSelected(new Set());
  };

  const exportCSV = () => {
    window.open(`${API}/export/csv`, "_blank");
    addLog("↓ Exportando CSV...");
  };

  const maxVal = Math.max(metrics.leads_scraped || 0, metrics.leads_qualified || 0, metrics.emails_sent || 0, 1);

  const TABS = [
    { key: "exec",   icon: "⚡", label: "Ejecución" },
    { key: "leads",  icon: "◎",  label: "Leads" },
    { key: "charts", icon: "▦",  label: "Métricas" },
  ] as const;

  const S = {
    // layout
    app:     { display:"flex", height:"100vh", background:"#F7F7F5", color:"#1A1A1A", fontFamily:"-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif", overflow:"hidden" } as React.CSSProperties,
    sidebar: { width:240, background:"#FFFFFF", borderRight:"1px solid #E8E8E6", display:"flex", flexDirection:"column" as const, flexShrink:0 },
    main:    { flex:1, display:"flex", flexDirection:"column" as const, overflow:"hidden" },
    scroll:  { flex:1, overflowY:"auto" as const, padding:32 },

    // sidebar
    logo:    { padding:"20px 16px 8px", borderBottom:"1px solid #E8E8E6", marginBottom:4 },
    logoText:{ fontSize:16, fontWeight:700, color:"#1A1A1A", letterSpacing:"-0.02em" },
    logoSub: { fontSize:11, color:"#9B9B97", marginTop:2 },
    navBtn:  (active: boolean): React.CSSProperties => ({
      display:"flex", alignItems:"center", gap:8, width:"100%",
      padding:"7px 12px", borderRadius:6, border:"none", cursor:"pointer",
      marginBottom:1, fontSize:13, textAlign:"left",
      background: active ? "#F0F0EE" : "transparent",
      color: active ? "#1A1A1A" : "#6B6B68",
      fontWeight: active ? 500 : 400,
    }),
    statusBar: { padding:"12px 16px", borderTop:"1px solid #E8E8E6", fontSize:12, color:"#9B9B97" },

    // cards
    card:    { background:"#FFFFFF", border:"1px solid #E8E8E6", borderRadius:10, padding:"16px 20px", marginBottom:12 } as React.CSSProperties,
    cardTitle:{ fontSize:11, fontWeight:600, color:"#9B9B97", textTransform:"uppercase" as const, letterSpacing:"0.06em", marginBottom:12 },

    // inputs
    input:   { width:"100%", background:"#F7F7F5", border:"1px solid #E8E8E6", borderRadius:6, padding:"8px 10px", fontSize:13, color:"#1A1A1A", outline:"none", fontFamily:"inherit" } as React.CSSProperties,

    // buttons
    btnPrimary: { padding:"9px 16px", background:"#1A1A1A", color:"#FFFFFF", border:"none", borderRadius:7, fontSize:13, fontWeight:500, cursor:"pointer", fontFamily:"inherit" } as React.CSSProperties,
    btnGhost:   { padding:"7px 14px", background:"transparent", color:"#6B6B68", border:"1px solid #E8E8E6", borderRadius:7, fontSize:12, cursor:"pointer", fontFamily:"inherit" } as React.CSSProperties,
    btnDanger:  { padding:"9px 16px", background:"#FEF2F0", color:"#E8442A", border:"1px solid #FECDC9", borderRadius:7, fontSize:13, fontWeight:500, cursor:"pointer", fontFamily:"inherit" } as React.CSSProperties,
    btnGreen:   { padding:"7px 14px", background:"#F0FDF4", color:"#16A34A", border:"1px solid #BBF7D0", borderRadius:7, fontSize:12, cursor:"pointer", fontFamily:"inherit" } as React.CSSProperties,

    // log
    log: { background:"#1A1A1A", borderRadius:8, padding:16, height:200, overflowY:"auto" as const, fontFamily:"'SF Mono',monospace", fontSize:11, lineHeight:1.8 },

    // metric cards
    metricCard: { background:"#FFFFFF", border:"1px solid #E8E8E6", borderRadius:10, padding:"16px 20px" } as React.CSSProperties,
    metricVal:  { fontSize:28, fontWeight:700, lineHeight:1, marginTop:6, color:"#1A1A1A" },
    metricLabel:{ fontSize:11, color:"#9B9B97", fontWeight:500 },
  };

  return (
    <div style={S.app}>

      {/* ── Toast ── */}
      {toast && (
        <div style={{ position:"fixed", bottom:24, right:24, background:"#1A1A1A", color:"#FFFFFF", padding:"10px 16px", borderRadius:8, fontSize:13, zIndex:9999, boxShadow:"0 4px 12px rgba(0,0,0,0.15)" }}>
          {toast}
        </div>
      )}

      {/* ── SIDEBAR ── */}
      <div style={S.sidebar}>
        <div style={S.logo}>
          <div style={S.logoText}>LeadAgent</div>
          <div style={S.logoSub}>v0.1.0 · MVP</div>
        </div>

        <nav style={{ padding:"8px 8px", flex:1 }}>
          {TABS.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)} style={S.navBtn(tab === t.key)}>
              <span style={{ fontSize:14 }}>{t.icon}</span>
              {t.label}
            </button>
          ))}
        </nav>

        <div style={S.statusBar}>
          <div style={{ display:"flex", alignItems:"center", gap:6, marginBottom:4 }}>
            <span style={{ width:6, height:6, borderRadius:"50%", background: running ? "#16A34A" : "#D1D1CF", display:"inline-block" }} />
            <span style={{ color: running ? "#16A34A" : "#9B9B97", fontWeight:500 }}>
              {running ? "Ejecutando" : "En espera"}
            </span>
          </div>
          <div>{metrics.leads_scraped || 0} leads · {leads.length} calificados</div>
        </div>
      </div>

      {/* ── MAIN ── */}
      <div style={S.main}>

        {/* ══ EJECUCIÓN ══ */}
        {tab === "exec" && (
          <div style={S.scroll}>
            <h2 style={{ fontSize:20, fontWeight:700, marginBottom:4, color:"#1A1A1A" }}>Ejecución</h2>
            <p style={{ fontSize:13, color:"#9B9B97", marginBottom:24 }}>Configura las búsquedas y ejecuta el pipeline completo.</p>

            {/* botones ejecutar / parar */}
            <div style={{ display:"flex", gap:10, marginBottom:24 }}>
              <button onClick={runPipeline} disabled={running}
                style={{ ...S.btnPrimary, flex:1, opacity: running ? 0.5 : 1, cursor: running ? "not-allowed" : "pointer" }}>
                {running ? "⟳  Pipeline ejecutándose..." : "▶  Ejecutar pipeline completo"}
              </button>
              {running && (
                <button onClick={async () => {
                  await fetch(`${API}/worker/stop`, { method:"POST" });
                  setRunning(false);
                  addLog("⏹ Pipeline detenido");
                  showToast("Pipeline detenido");
                }} style={S.btnDanger}>
                  ⏹ Parar
                </button>
              )}
            </div>

            {/* búsquedas */}
            <div style={S.card}>
              <div style={S.cardTitle}>Búsquedas configuradas</div>

              {/* cabecera columnas */}
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1.5fr 32px", gap:8, marginBottom:8 }}>
                <span style={{ fontSize:11, color:"#9B9B97", fontWeight:500 }}>Tema</span>
                <span style={{ fontSize:11, color:"#9B9B97", fontWeight:500 }}>Zona</span>
                <span />
              </div>

              {configs.map((c, i) => (
                <div key={i} style={{ display:"grid", gridTemplateColumns:"1fr 1.5fr 32px", gap:8, marginBottom:8, alignItems:"center" }}>
                  <input value={c.query} placeholder="restaurantes"
                    onChange={e => updateConfig(i, "query", e.target.value)}
                    style={S.input} />
                  <input value={c.zone} placeholder="Miami, Florida"
                    onChange={e => updateConfig(i, "zone", e.target.value)}
                    style={S.input} />
                  <button onClick={() => removeConfig(i)}
                    style={{ background:"none", border:"none", color:"#BCBCBA", cursor:"pointer", fontSize:18, lineHeight:1, padding:0 }}>×</button>
                </div>
              ))}

              <div style={{ display:"flex", gap:8, marginTop:16 }}>
                <button onClick={addConfig} style={S.btnGhost}>+ Añadir fila</button>
                <button onClick={saveConfig} style={S.btnPrimary}>Guardar configuración</button>
              </div>
            </div>

            {/* log */}
            <div style={S.card}>
              <div style={S.cardTitle}>Log del sistema</div>
              <div ref={logRef} style={S.log}>
                {logs.map((l, i) => (
                  <div key={i} style={{
                    color: l.includes("✗") ? "#F87171"
                         : l.includes("✓") ? "#4ADE80"
                         : l.includes("→") ? "#60A5FA"
                         : "#6B7280"
                  }}>{l}</div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ══ LEADS ══ */}
        {tab === "leads" && (
          <div style={{ flex:1, overflow:"hidden", display:"flex", flexDirection:"column" }}>

            {/* barra top */}
            <div style={{ padding:"16px 24px", borderBottom:"1px solid #E8E8E6", background:"#FFFFFF", display:"flex", alignItems:"center", justifyContent:"space-between", flexShrink:0 }}>
              <div>
                <span style={{ fontSize:15, fontWeight:600 }}>Leads</span>
                <span style={{ fontSize:13, color:"#9B9B97", marginLeft:8 }}>{leads.length} registros · {selected.size} seleccionados</span>
              </div>
              <div style={{ display:"flex", gap:8 }}>
                <button onClick={() => setSelected(new Set(leads.map(l => l.name)))} style={S.btnGhost}>
                  Seleccionar todo
                </button>
                <button onClick={() => setSelected(new Set(leads.filter(l => l.priority === "high").map(l => l.name)))}
                  style={{ ...S.btnGhost, color:"#E8442A", borderColor:"#FECDC9" }}>
                  Solo alta prioridad
                </button>
                {selected.size > 0 && (
                  <button onClick={sendSelected} style={S.btnPrimary}>
                    ✉ Enviar {selected.size} seleccionados
                  </button>
                )}
              </div>
            </div>

            {/* tabla header */}
            <div style={{ display:"grid", gridTemplateColumns:"36px 1fr 60px 130px 90px 80px", gap:12, padding:"10px 24px", background:"#F7F7F5", borderBottom:"1px solid #E8E8E6", flexShrink:0 }}>
              {["", "Negocio", "Score", "Web", "Prioridad", ""].map((h, i) => (
                <span key={i} style={{ fontSize:11, fontWeight:600, color:"#9B9B97", textTransform:"uppercase", letterSpacing:"0.05em" }}>{h}</span>
              ))}
            </div>

            {/* lista */}
            <div style={{ flex:1, overflowY:"auto", background:"#FFFFFF" }}>
              {leads.length === 0 ? (
                <div style={{ textAlign:"center", padding:60, color:"#9B9B97", fontSize:14 }}>
                  Sin leads — ejecuta el pipeline primero
                </div>
              ) : leads.map(lead => {
                const isExp = expanded === lead.name;
                const isSel = selected.has(lead.name);
                const pc    = PRIORITY_COLOR[lead.priority] || "#6B7280";
                const pb    = PRIORITY_BG[lead.priority]   || "#F9FAFB";

                return (
                  <div key={lead.name} style={{ borderBottom:"1px solid #F0F0EE" }}>
                    {/* fila */}
                    <div onClick={() => setExpanded(isExp ? null : lead.name)}
                      style={{ display:"grid", gridTemplateColumns:"36px 1fr 60px 130px 90px 80px", gap:12, padding:"12px 24px", cursor:"pointer", background: isSel ? "#FAFFFE" : "transparent", transition:"background 0.1s" }}>

                      {/* checkbox */}
                      <div onClick={e => { e.stopPropagation(); toggleSelect(lead.name); }}
                        style={{ width:16, height:16, borderRadius:4, border:`1.5px solid ${isSel ? "#1A1A1A" : "#D1D1CF"}`, background: isSel ? "#1A1A1A" : "transparent", display:"flex", alignItems:"center", justifyContent:"center", cursor:"pointer", flexShrink:0, marginTop:2 }}>
                        {isSel && <span style={{ color:"#FFF", fontSize:9 }}>✓</span>}
                      </div>

                      {/* nombre */}
                      <div>
                        <div style={{ fontSize:13, fontWeight:500, color:"#1A1A1A" }}>{lead.name}</div>
                        <div style={{ fontSize:11, color:"#9B9B97", marginTop:1 }}>{lead.category} · {lead.zone}</div>
                      </div>

                      {/* score */}
                      <div style={{ fontSize:14, fontWeight:700, color: pc }}>{lead.score}</div>

                      {/* web */}
                      <div style={{ fontSize:11, color: lead.website ? "#6B7280" : "#E8442A" }}>
                        {lead.website ? lead.website.replace(/https?:\/\//, "").slice(0, 22) : "sin web ←"}
                      </div>

                      {/* prioridad */}
                      <div>
                        <span style={{ fontSize:11, fontWeight:500, padding:"3px 8px", borderRadius:20, background: pb, color: pc }}>
                          {lead.priority === "high" ? "Alta" : lead.priority === "medium" ? "Media" : "Baja"}
                        </span>
                      </div>

                      {/* flecha */}
                      <div style={{ textAlign:"right", color:"#BCBCBA", fontSize:11, marginTop:2 }}>{isExp ? "▲" : "▼"}</div>
                    </div>

                    {/* detalle expandido */}
                    {isExp && (
                      <div style={{ background:"#F7F7F5", borderTop:"1px solid #E8E8E6", padding:"16px 24px 16px 72px" }}>
                        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:20, marginBottom:16 }}>
                          <div style={{ fontSize:12, color:"#6B7280", lineHeight:2 }}>
                            {lead.phone   && <div>📞 <span style={{ color:"#1A1A1A" }}>{lead.phone}</span></div>}
                            {lead.address && <div>📍 <span style={{ color:"#1A1A1A" }}>{lead.address.replace(/[^\x20-\x7E\u00C0-\u024F\u00F1]/g,"").trim()}</span></div>}
                            {lead.maps_url && <a href={lead.maps_url} target="_blank" rel="noreferrer" style={{ color:"#2563EB", fontSize:12 }}>Ver en Google Maps ↗</a>}
                          </div>
                          <div>
                            {lead.score_reasons?.map((r, i) => (
                              <div key={i} style={{ fontSize:11, color:"#9B9B97", lineHeight:2 }}>· {r}</div>
                            ))}
                          </div>
                        </div>

                        {lead.email_body ? (
                          <div style={{ background:"#FFFFFF", border:"1px solid #E8E8E6", borderRadius:8, padding:16, marginBottom:12 }}>
                            <div style={{ fontSize:11, fontWeight:600, color:"#9B9B97", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:8 }}>Mensaje generado</div>
                            <div style={{ fontSize:12, color:"#6B7280", marginBottom:6 }}>Asunto: <span style={{ color:"#1A1A1A", fontWeight:500 }}>{lead.email_subject}</span></div>
                            <div style={{ fontSize:12, color:"#4B5563", whiteSpace:"pre-line", lineHeight:1.7, borderTop:"1px solid #F0F0EE", paddingTop:10, marginTop:4 }}>{lead.email_body}</div>
                          </div>
                        ) : (
                          <button onClick={() => generateMsg(lead)} disabled={generating === lead.name}
                            style={{ ...S.btnGhost, marginBottom:12, opacity: generating === lead.name ? 0.5 : 1 }}>
                            {generating === lead.name ? "⟳ Generando..." : "✦ Generar mensaje con IA"}
                          </button>
                        )}

                        <div style={{ display:"flex", gap:8 }}>
                          <button onClick={() => toggleSelect(lead.name)} style={isSel ? S.btnGreen : S.btnGhost}>
                            {isSel ? "✓ Seleccionado" : "+ Seleccionar"}
                          </button>
                          <button onClick={() => sendLead(lead.name)} disabled={sending === lead.name || !lead.email_body}
                            style={{ ...S.btnPrimary, opacity: (!lead.email_body || sending === lead.name) ? 0.4 : 1, cursor: !lead.email_body ? "not-allowed" : "pointer" }}>
                            {sending === lead.name ? "Enviando..." : "✉ Enviar email"}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ══ MÉTRICAS ══ */}
        {tab === "charts" && (
          <div style={S.scroll}>
            <h2 style={{ fontSize:20, fontWeight:700, marginBottom:4, color:"#1A1A1A" }}>Métricas</h2>
            <p style={{ fontSize:13, color:"#9B9B97", marginBottom:24 }}>Resumen del rendimiento del agente.</p>

            {/* grid métricas */}
            <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:12, marginBottom:24 }}>
              {[
                { label:"Leads scrapeados",  value: metrics.leads_scraped   || 0 },
                { label:"Leads calificados", value: metrics.leads_qualified || 0 },
                { label:"Alta prioridad",    value: metrics.high_priority   || 0 },
                { label:"Emails enviados",   value: metrics.emails_sent     || 0 },
                { label:"Tasa apertura",     value: `${metrics.open_rate   || 0}%` },
                { label:"Tasa respuesta",    value: `${metrics.reply_rate  || 0}%` },
              ].map(m => (
                <div key={m.label} style={S.metricCard}>
                  <div style={S.metricLabel}>{m.label}</div>
                  <div style={S.metricVal}>{m.value}</div>
                </div>
              ))}
            </div>

            {/* funnel */}
            <div style={S.card}>
              <div style={S.cardTitle}>Funnel de conversión</div>
              {[
                { label:"Scrapeados",  value: metrics.leads_scraped   || 0, color:"#1A1A1A" },
                { label:"Calificados", value: metrics.leads_qualified || 0, color:"#2563EB" },
                { label:"Enviados",    value: metrics.emails_sent     || 0, color:"#D97706" },
                { label:"Respondieron",value: Math.round(((metrics.reply_rate||0)/100)*(metrics.emails_sent||0)), color:"#16A34A" },
              ].map(b => (
                <div key={b.label} style={{ marginBottom:16 }}>
                  <div style={{ display:"flex", justifyContent:"space-between", fontSize:13, marginBottom:6 }}>
                    <span style={{ color:"#4B5563" }}>{b.label}</span>
                    <span style={{ fontWeight:600, color:b.color }}>{b.value}</span>
                  </div>
                  <div style={{ height:6, background:"#F0F0EE", borderRadius:3, overflow:"hidden" }}>
                    <div style={{ height:"100%", width:`${Math.round((b.value/maxVal)*100)}%`, background:b.color, borderRadius:3, transition:"width 0.6s ease" }} />
                  </div>
                </div>
              ))}
            </div>

            {/* prioridad */}
            <div style={S.card}>
              <div style={S.cardTitle}>Por prioridad</div>
              {[
                { label:"Alta",  color:"#E8442A", count: leads.filter(l=>l.priority==="high").length },
                { label:"Media", color:"#D97706", count: leads.filter(l=>l.priority==="medium").length },
                { label:"Baja",  color:"#9B9B97", count: leads.filter(l=>l.priority==="low").length },
              ].map(p => (
                <div key={p.label} style={{ marginBottom:14 }}>
                  <div style={{ display:"flex", justifyContent:"space-between", fontSize:13, marginBottom:6 }}>
                    <span style={{ color:"#4B5563" }}>{p.label}</span>
                    <span style={{ fontWeight:600, color:p.color }}>{p.count}</span>
                  </div>
                  <div style={{ height:6, background:"#F0F0EE", borderRadius:3, overflow:"hidden" }}>
                    <div style={{ height:"100%", width: leads.length ? `${Math.round((p.count/leads.length)*100)}%` : "0%", background:p.color, borderRadius:3, transition:"width 0.6s ease" }} />
                  </div>
                </div>
              ))}
            </div>

            <button onClick={exportCSV} style={{ ...S.btnPrimary, width:"100%", padding:"12px 0", textAlign:"center" as const }}>
              ↓ Exportar leads como CSV
            </button>
          </div>
        )}
      </div>

      <style>{`
        * { box-sizing:border-box; margin:0; padding:0; }
        body { background:#F7F7F5; }
        ::-webkit-scrollbar { width:4px; }
        ::-webkit-scrollbar-track { background:#F7F7F5; }
        ::-webkit-scrollbar-thumb { background:#D1D1CF; border-radius:2px; }
        input:focus { border-color:#1A1A1A !important; outline:none; }
        button:hover { opacity:0.85; }
      `}</style>
    </div>
  );
}