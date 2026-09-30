"use client";
import { useEffect, useState, useCallback, useRef } from "react";

const API = "/api";

type Lead = {
  name: string; category: string; zone: string;
  website: string | null; phone: string | null;
  score: number; priority: string; status: string;
  email?: string; email_subject?: string; email_body?: string;
  whatsapp_msg?: string; address?: string;
  maps_url?: string; score_reasons?: string[];
};

type SearchConfig = { query: string; zone: string };
type SearchMode = { label: string; max_results_per_query: number };
type Tab = "exec" | "leads" | "crm" | "engage" | "accounts" | "charts";

const PRIORITY_COLOR: Record<string, string> = {
  high: "#E8442A", medium: "#D97706", low: "#6B7280"
};
const PRIORITY_BG: Record<string, string> = {
  high: "rgba(232,68,42,0.12)", medium: "rgba(217,119,6,0.14)", low: "rgba(107,114,128,0.10)"
};

const STAGES = ["new", "contacted", "replied", "interested", "won", "lost"] as const;
const STAGE_LABEL: Record<string, string> = {
  new: "Nuevo", contacted: "Contactado", replied: "Respondió",
  interested: "Interesado", won: "Cliente", lost: "Descartado",
};
const STAGE_COLOR: Record<string, string> = {
  new: "#6B7280", contacted: "#D97706", replied: "#2563EB",
  interested: "#7C3AED", won: "#16A34A", lost: "#9B9B97",
};
// tintes translúcidos: se ven bien tanto en modo claro como oscuro
const STAGE_BG: Record<string, string> = {
  new: "rgba(107,114,128,0.10)", contacted: "rgba(217,119,6,0.14)", replied: "rgba(37,99,235,0.12)",
  interested: "rgba(124,58,237,0.12)", won: "rgba(22,163,74,0.14)", lost: "rgba(107,114,128,0.10)",
};

const THEMES = {
  light: {
    bg: "#F7F7F5", sidebarBg: "#FFFFFF", border: "#E8E8E6", borderLight: "#F0F0EE",
    text: "#1A1A1A", textSecondary: "#6B7280", textMuted: "#9B9B97",
    cardBg: "#FFFFFF", inputBg: "#F7F7F5", navActiveBg: "#F0F0EE",
    rowHover: "rgba(37,99,235,0.04)", logBg: "#1A1A1A", logText: "#E8E8E6",
    accentBg: "#1A1A1A", accentText: "#FFFFFF",
  },
  dark: {
    bg: "#0F0F11", sidebarBg: "#17171A", border: "#2A2A2E", borderLight: "#222225",
    text: "#F3F3F1", textSecondary: "#A8A8A5", textMuted: "#75756F",
    cardBg: "#1B1B1F", inputBg: "#232327", navActiveBg: "#28282D",
    rowHover: "rgba(37,99,235,0.08)", logBg: "#000000", logText: "#D4D4D2",
    accentBg: "#F3F3F1", accentText: "#111113",
  },
} as const;

export default function Home() {
  const [tab,        setTab]        = useState<Tab>("exec");
  const [darkMode,   setDarkMode]   = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("beacon-theme");
    if (saved === "dark") setDarkMode(true);
  }, []);
  useEffect(() => {
    localStorage.setItem("beacon-theme", darkMode ? "dark" : "light");
  }, [darkMode]);

  const T = THEMES[darkMode ? "dark" : "light"];
  const [leads,      setLeads]      = useState<Lead[]>([]);
  const [metrics,    setMetrics]    = useState<any>({});
  const [configs,    setConfigs]    = useState<SearchConfig[]>([]);
  const [modeOptions, setModeOptions] = useState<Record<string, SearchMode>>({});
  const [mode,        setMode]        = useState<string>("medio");
  const [logs,       setLogs]       = useState<string[]>(["Sistema listo. Ejecuta el pipeline para comenzar."]);
  const [running,    setRunning]    = useState(false);
  const [selected,   setSelected]   = useState<Set<string>>(new Set());
  const [expanded,   setExpanded]   = useState<string | null>(null);
  const [generating, setGenerating] = useState<string | null>(null);
  const [sending,    setSending]    = useState<string | null>(null);
  const [toast,      setToast]      = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  // ── Engage (campañas Gmail + canal WhatsApp) ──
  const [channelTab, setChannelTab] = useState<"gmail" | "whatsapp">("gmail");
  const [engageLeads, setEngageLeads] = useState<Lead[]>([]);
  const [uploadingEmails, setUploadingEmails] = useState(false);
  const [sendingCampaign, setSendingCampaign] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [whatsappStatus, setWhatsappStatus] = useState<{running:boolean; log_tail:string; exit_code:number|null}>({ running:false, log_tail:"", exit_code:null });
  const [whatsappSummary, setWhatsappSummary] = useState<{total:number; pending:number; sent:number}>({ total:0, pending:0, sent:0 });
  const [launchingWa, setLaunchingWa] = useState(false);

  // ── Cuentas de Email (Gmail) ──
  const [emailAccount, setEmailAccount] = useState<any>(null);
  const [emailForm, setEmailForm] = useState({ email: "", app_password: "", from_name: "" });
  const [savingEmail, setSavingEmail] = useState(false);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const addLog = (msg: string) => {
    const time = new Date().toLocaleTimeString("es-ES");
    setLogs(prev => [...prev.slice(-100), `[${time}] ${msg}`]);
    setTimeout(() => logRef.current?.scrollTo(0, logRef.current.scrollHeight), 50);
  };

  const fetchLeadsAndMetrics = useCallback(async () => {
    try {
      const [lRes, mRes] = await Promise.all([
        fetch(`${API}/leads`),
        fetch(`${API}/metrics`),
      ]);
      if (lRes.ok) setLeads(await lRes.json());
      if (mRes.ok) setMetrics(await mRes.json());
    } catch {}
  }, []);

  const fetchConfig = useCallback(async () => {
    try {
      const cRes = await fetch(`${API}/config/search`);
      if (cRes.ok) setConfigs(await cRes.json());
    } catch {}
  }, []);

  const fetchModeConfig = useCallback(async () => {
    try {
      const [optsRes, curRes] = await Promise.all([
        fetch(`${API}/config/modes`),
        fetch(`${API}/config/mode`),
      ]);
      if (optsRes.ok) setModeOptions(await optsRes.json());
      if (curRes.ok) setMode((await curRes.json()).mode);
    } catch {}
  }, []);

  const saveMode = async (newMode: string) => {
    setMode(newMode);
    try {
      await fetch(`${API}/config/mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: newMode }),
      });
      addLog(`✓ Modo de búsqueda: ${modeOptions[newMode]?.label ?? newMode}`);
      showToast("Modo actualizado");
    } catch { addLog("✗ No se pudo guardar el modo"); }
  };

  const fetchAll = useCallback(async () => {
    await Promise.all([fetchLeadsAndMetrics(), fetchConfig()]);
  }, [fetchLeadsAndMetrics, fetchConfig]);

  // La config de búsquedas solo se carga UNA VEZ al abrir la página.
  // Así nunca se pisa lo que el usuario está escribiendo.
  useEffect(() => { fetchConfig(); }, [fetchConfig]);
  useEffect(() => { fetchModeConfig(); }, [fetchModeConfig]);
  useEffect(() => { fetchLeadsAndMetrics(); }, [fetchLeadsAndMetrics]);
  useEffect(() => {
    const t = setInterval(fetchLeadsAndMetrics, 30000);
    return () => clearInterval(t);
  }, [fetchLeadsAndMetrics]);

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

  const [resetting, setResetting] = useState(false);

const resetSearch = async () => {
  if (!window.confirm("Esto borra el historial de contactados y las métricas acumuladas para empezar de cero. ¿Continuar?")) return;
  setResetting(true);
  try {
    const r = await fetch(`${API}/worker/reset`, { method: "POST" });
    if (r.ok) {
      setMetrics({});
      setLeads([]);
      setLogs(["Sistema reiniciado. Ejecuta el pipeline para comenzar."]);
      showToast("Búsqueda reiniciada");
    } else {
      const err = await r.json().catch(() => ({}));
      addLog(`✗ No se pudo reiniciar: ${err.detail || r.status}`);
    }
  } catch { addLog("✗ Error conectando con backend"); }
  setResetting(false);
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

  const updateStatus = async (name: string, status: string) => {
    // actualización optimista: cambia en pantalla de una, sin esperar la respuesta
    setLeads(prev => prev.map(l => l.name === name ? { ...l, status } : l));
    try {
      const res = await fetch(`${API}/leads/${encodeURIComponent(name)}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) throw new Error();
      addLog(`→ ${name}: movido a "${STAGE_LABEL[status]}"`);
    } catch {
      addLog(`✗ No se pudo actualizar el estado de ${name}`);
      await fetchLeadsAndMetrics(); // revierte al valor real si falló
    }
  };

  // ── Engage: leads con email, subir excel, generar y enviar campaña ──
  const fetchEngageLeads = useCallback(async () => {
    try {
      const res = await fetch(`${API}/engage/leads`);
      if (res.ok) setEngageLeads(await res.json());
    } catch {}
  }, []);

  const uploadEmails = async (file: File) => {
    setUploadingEmails(true);
    addLog(`→ Subiendo ${file.name}...`);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API}/engage/upload-emails`, { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "error");
      addLog(`✓ ${data.added} emails asociados a leads`);
      showToast(`${data.added} emails cargados`);
      await fetchEngageLeads();
    } catch (e: any) {
      addLog(`✗ Error subiendo emails: ${e.message || e}`);
    }
    setUploadingEmails(false);
  };

  const sendCampaign = async (names: string[]) => {
    if (names.length === 0) return;
    setSendingCampaign(true);
    addLog(`→ Enviando campaña a ${names.length} leads...`);
    try {
      const res = await fetch(`${API}/engage/send-campaign`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lead_names: names }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "error");
      addLog(`✓ Campaña en cola: ${data.queued} emails`);
      showToast(`Campaña enviada a ${data.queued} leads`);
    } catch (e: any) {
      addLog(`✗ Error enviando campaña: ${e.message || e}`);
    }
    setSendingCampaign(false);
  };

  // ── Cuentas de Email (Gmail) ──
  const fetchEmailAccount = useCallback(async () => {
    try {
      const res = await fetch(`${API}/settings/email`);
      if (res.ok) {
        const data = await res.json();
        setEmailAccount(data.email ? data : null);
      }
    } catch {}
  }, []);

  const saveEmailAccount = async () => {
    if (!emailForm.email || !emailForm.app_password) {
      showToast("Falta el email o la contraseña de aplicación");
      return;
    }
    setSavingEmail(true);
    try {
      const res = await fetch(`${API}/settings/email`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: emailForm.email,
          app_password: emailForm.app_password,
          from_name: emailForm.from_name || "Tu Nombre",
        }),
      });
      if (!res.ok) throw new Error();
      addLog(`✓ Cuenta de Gmail conectada: ${emailForm.email}`);
      showToast("Cuenta de Gmail conectada");
      setEmailForm({ email: "", app_password: "", from_name: "" });
      await fetchEmailAccount();
    } catch {
      addLog(`✗ Error conectando la cuenta de Gmail`);
    }
    setSavingEmail(false);
  };

  const disconnectEmailAccount = async () => {
    await fetch(`${API}/settings/email`, { method: "DELETE" });
    setEmailAccount(null);
    addLog(`→ Cuenta de Gmail desconectada`);
  };

  // ── Canal WhatsApp: lanzar/parar el bot desde el dashboard ──
  const fetchWhatsappStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API}/channels/whatsapp/status`);
      if (res.ok) setWhatsappStatus(await res.json());
    } catch {}
  }, []);

  const fetchWhatsappSummary = useCallback(async () => {
    try {
      const res = await fetch(`${API}/channels/whatsapp/exports`);
      if (res.ok) setWhatsappSummary(await res.json());
    } catch {}
  }, []);

  const launchWhatsapp = async () => {
    setLaunchingWa(true);
    try {
      const res = await fetch(`${API}/channels/whatsapp/launch`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "error");
      addLog(`🚀 Bot de WhatsApp lanzado`);
      showToast("Bot de WhatsApp corriendo");
    } catch (e: any) {
      addLog(`✗ No se pudo lanzar el bot: ${e.message || e}`);
    }
    setLaunchingWa(false);
    fetchWhatsappStatus();
  };

  const stopWhatsapp = async () => {
    try {
      const res = await fetch(`${API}/channels/whatsapp/stop`, { method: "POST" });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail); }
      addLog(`■ Bot de WhatsApp detenido`);
    } catch (e: any) {
      addLog(`✗ ${e.message || e}`);
    }
    fetchWhatsappStatus();
  };

  useEffect(() => {
    if (tab === "engage") fetchEngageLeads();
    if (tab === "accounts") fetchEmailAccount();
    if (tab === "engage" && channelTab === "whatsapp") { fetchWhatsappStatus(); fetchWhatsappSummary(); }
  }, [tab, channelTab, fetchEngageLeads, fetchEmailAccount, fetchWhatsappStatus, fetchWhatsappSummary]);

  // mientras el bot esté corriendo (o estemos viendo esa pestaña), refresca el status cada 3s
  useEffect(() => {
    if (tab !== "engage" || channelTab !== "whatsapp") return;
    const t = setInterval(fetchWhatsappStatus, 3000);
    return () => clearInterval(t);
  }, [tab, channelTab, fetchWhatsappStatus]);

  const sendSelected = async () => {
    const names = Array.from(selected);
    for (const name of names) await sendLead(name);
    setSelected(new Set());
  };

  const exportCSV = () => {
    window.open(`${API}/export/csv`, "_blank");
    addLog("↓ Exportando CSV...");
  };

  const exportWhatsAppExcel = () => {
    window.open(`${API}/export/whatsapp`, "_blank");
    addLog("↓ Exportando Excel para WhatsApp...");
  };

  const maxVal = Math.max(metrics.leads_scraped || 0, metrics.leads_qualified || 0, 1);
  const pipelineMax = Math.max(metrics.leads_qualified || 0, 1);

  const TABS = [
    { key: "exec",     icon: "⚡", label: "Buscar" },
    { key: "leads",    icon: "◎",  label: "Leads" },
    { key: "crm",      icon: "▤",  label: "CRM" },
    { key: "engage",   icon: "✉",  label: "Engage" },
    { key: "accounts", icon: "⚙",  label: "Cuentas de Email" },
    { key: "charts",   icon: "▦",  label: "Reports" },
  ] as const;

  const S = {
    // layout
    app:     { display:"flex", height:"100vh", background:T.bg, color:T.text, fontFamily:"-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif", overflow:"hidden", transition:"background 0.15s,color 0.15s" } as React.CSSProperties,
    sidebar: { width:240, background:T.sidebarBg, borderRight:`1px solid ${T.border}`, display:"flex", flexDirection:"column" as const, flexShrink:0 },
    main:    { flex:1, display:"flex", flexDirection:"column" as const, overflow:"hidden" },
    scroll:  { flex:1, overflowY:"auto" as const, padding:32 },

    // sidebar
    logo:    { padding:"20px 16px 8px", borderBottom:`1px solid ${T.border}`, marginBottom:4, display:"flex", alignItems:"center", justifyContent:"space-between" },
    logoText:{ fontSize:16, fontWeight:700, color:T.text, letterSpacing:"-0.02em" },
    logoSub: { fontSize:11, color:T.textMuted, marginTop:2 },
    themeToggle: { width:28, height:28, borderRadius:7, border:`1px solid ${T.border}`, background:T.inputBg, color:T.text, cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center", fontSize:14 } as React.CSSProperties,
    navBtn:  (active: boolean): React.CSSProperties => ({
      display:"flex", alignItems:"center", gap:8, width:"100%",
      padding:"7px 12px", borderRadius:6, border:"none", cursor:"pointer",
      marginBottom:1, fontSize:13, textAlign:"left",
      background: active ? T.navActiveBg : "transparent",
      color: active ? T.text : T.textSecondary,
      fontWeight: active ? 500 : 400,
    }),
    statusBar: { padding:"12px 16px", borderTop:`1px solid ${T.border}`, fontSize:12, color:T.textMuted },

    // cards
    card:    { background:T.cardBg, border:`1px solid ${T.border}`, borderRadius:10, padding:"16px 20px", marginBottom:12 } as React.CSSProperties,
    cardTitle:{ fontSize:11, fontWeight:600, color:T.textMuted, textTransform:"uppercase" as const, letterSpacing:"0.06em", marginBottom:12 },

    // inputs
    input:   { width:"100%", background:T.inputBg, border:`1px solid ${T.border}`, borderRadius:6, padding:"8px 10px", fontSize:13, color:T.text, outline:"none", fontFamily:"inherit" } as React.CSSProperties,

    // buttons
    btnPrimary: { padding:"9px 16px", background:T.accentBg, color:T.accentText, border:"none", borderRadius:7, fontSize:13, fontWeight:500, cursor:"pointer", fontFamily:"inherit" } as React.CSSProperties,
    btnGhost:   { padding:"7px 14px", background:"transparent", color:T.textSecondary, border:`1px solid ${T.border}`, borderRadius:7, fontSize:12, cursor:"pointer", fontFamily:"inherit" } as React.CSSProperties,
    btnDanger:  { padding:"9px 16px", background:"rgba(232,68,42,0.12)", color:"#E8442A", border:"1px solid rgba(232,68,42,0.35)", borderRadius:7, fontSize:13, fontWeight:500, cursor:"pointer", fontFamily:"inherit" } as React.CSSProperties,
    btnGreen:   { padding:"7px 14px", background:"rgba(22,163,74,0.14)", color:"#16A34A", border:"1px solid rgba(22,163,74,0.35)", borderRadius:7, fontSize:12, cursor:"pointer", fontFamily:"inherit" } as React.CSSProperties,

    // log
    log: { background:T.logBg, borderRadius:8, padding:16, height:200, overflowY:"auto" as const, fontFamily:"'SF Mono',monospace", fontSize:11, lineHeight:1.8, color:T.logText },

    // metric cards
    metricCard: { background:T.cardBg, border:`1px solid ${T.border}`, borderRadius:10, padding:"16px 20px" } as React.CSSProperties,
    metricVal:  { fontSize:28, fontWeight:700, lineHeight:1, marginTop:6, color:T.text },
    metricLabel:{ fontSize:11, color:T.textMuted, fontWeight:500 },
  };

  return (
    <div style={S.app}>

      {/* ── Toast ── */}
      {toast && (
        <div style={{ position:"fixed", bottom:24, right:24, background:T.text, color:T.cardBg, padding:"10px 16px", borderRadius:8, fontSize:13, zIndex:9999, boxShadow:"0 4px 12px rgba(0,0,0,0.15)" }}>
          {toast}
        </div>
      )}

      {/* ── SIDEBAR ── */}
      <div style={S.sidebar}>
        <div style={S.logo}>
          <div>
            <div style={S.logoText}>Beacon AI</div>
            <div style={S.logoSub}>v0.1.0 · MVP</div>
          </div>
          <button
            onClick={() => setDarkMode(!darkMode)}
            style={S.themeToggle}
            title={darkMode ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
          >
            {darkMode ? "☀" : "☾"}
          </button>
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
            <span style={{ width:6, height:6, borderRadius:"50%", background: running ? "#16A34A" : T.textMuted, display:"inline-block" }} />
            <span style={{ color: running ? "#16A34A" : T.textMuted, fontWeight:500 }}>
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
            <h2 style={{ fontSize:20, fontWeight:700, marginBottom:4, color:T.text }}>Ejecución</h2>
            <p style={{ fontSize:13, color:T.textMuted, marginBottom:24 }}>Configura las búsquedas y ejecuta el pipeline completo.</p>

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

            {/* modo de búsqueda */}
            <div style={S.card}>
              <div style={S.cardTitle}>Modo de búsqueda</div>
              <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
                {Object.entries(modeOptions).map(([key, opt]) => (
                  <button key={key} onClick={() => saveMode(key)}
                    style={mode === key ? S.btnPrimary : S.btnGhost}>
                    {opt.label}
                  </button>
                ))}
              </div>
              {mode && modeOptions[mode] && (
                <p style={{ fontSize:12, color:T.textMuted, marginTop:10, marginBottom:0 }}>
                  Hasta {modeOptions[mode].max_results_per_query} fichas por búsqueda.
                </p>
              )}
            </div>

            {/* búsquedas */}
            <div style={S.card}>
              <div style={S.cardTitle}>Búsquedas configuradas</div>

              {/* cabecera columnas */}
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1.5fr 32px", gap:8, marginBottom:8 }}>
                <span style={{ fontSize:11, color:T.textMuted, fontWeight:500 }}>Tema</span>
                <span style={{ fontSize:11, color:T.textMuted, fontWeight:500 }}>Zona</span>
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
                    style={{ background:"none", border:"none", color:T.textMuted, cursor:"pointer", fontSize:18, lineHeight:1, padding:0 }}>×</button>
                </div>
              ))}

              <div style={{ display:"flex", gap:8, marginTop:16 }}>
                <button onClick={addConfig} style={S.btnGhost}>+ Añadir fila</button>
                <button onClick={saveConfig} style={S.btnPrimary}>Guardar configuración</button>
                <button onClick={resetSearch} disabled={resetting || running}
    style={{ ...S.btnDanger, opacity: (resetting || running) ? 0.5 : 1, cursor: (resetting || running) ? "not-allowed" : "pointer" }}>
    {resetting ? "⟳ Reiniciando..." : "↺ Reiniciar búsqueda"}
  </button>
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
                         : T.textSecondary
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
            <div style={{ padding:"16px 24px", borderBottom:`1px solid ${T.border}`, background:T.cardBg, display:"flex", alignItems:"center", justifyContent:"space-between", flexShrink:0 }}>
              <div>
                <span style={{ fontSize:15, fontWeight:600 }}>Leads</span>
                <span style={{ fontSize:13, color:T.textMuted, marginLeft:8 }}>{leads.length} registros · {selected.size} seleccionados</span>
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
            <div style={{ display:"grid", gridTemplateColumns:"36px 1fr 60px 130px 90px 100px 30px", gap:12, padding:"10px 24px", background:T.inputBg, borderBottom:`1px solid ${T.border}`, flexShrink:0 }}>
              {["", "Negocio", "Score", "Web", "Prioridad", "Estado", ""].map((h, i) => (
                <span key={i} style={{ fontSize:11, fontWeight:600, color:T.textMuted, textTransform:"uppercase", letterSpacing:"0.05em" }}>{h}</span>
              ))}
            </div>

            {/* lista */}
            <div style={{ flex:1, overflowY:"auto", background:T.cardBg }}>
              {leads.length === 0 ? (
                <div style={{ textAlign:"center", padding:60, color:T.textMuted, fontSize:14 }}>
                  Sin leads — ejecuta el pipeline primero
                </div>
              ) : leads.map(lead => {
                const isExp = expanded === lead.name;
                const isSel = selected.has(lead.name);
                const pc    = PRIORITY_COLOR[lead.priority] || T.textSecondary;
                const pb    = PRIORITY_BG[lead.priority]   || T.inputBg;

                return (
                  <div key={lead.name} style={{ borderBottom:`1px solid ${T.borderLight}` }}>
                    {/* fila */}
                    <div onClick={() => setExpanded(isExp ? null : lead.name)}
                      style={{ display:"grid", gridTemplateColumns:"36px 1fr 60px 130px 90px 100px 30px", gap:12, padding:"12px 24px", cursor:"pointer", background: isSel ? T.rowHover : "transparent", transition:"background 0.1s" }}>

                      {/* checkbox */}
                      <div onClick={e => { e.stopPropagation(); toggleSelect(lead.name); }}
                        style={{ width:16, height:16, borderRadius:4, border:`1.5px solid ${isSel ? T.text : T.textMuted}`, background: isSel ? T.text : "transparent", display:"flex", alignItems:"center", justifyContent:"center", cursor:"pointer", flexShrink:0, marginTop:2 }}>
                        {isSel && <span style={{ color:"#FFF", fontSize:9 }}>✓</span>}
                      </div>

                      {/* nombre */}
                      <div>
                        <div style={{ fontSize:13, fontWeight:500, color:T.text }}>{lead.name}</div>
                        <div style={{ fontSize:11, color:T.textMuted, marginTop:1 }}>{lead.category} · {lead.zone}</div>
                      </div>

                      {/* score */}
                      <div style={{ fontSize:14, fontWeight:700, color: pc }}>{lead.score}</div>

                      {/* web */}
                      <div style={{ fontSize:11, color: lead.website ? T.textSecondary : "#E8442A" }}>
                        {lead.website ? lead.website.replace(/https?:\/\//, "").slice(0, 22) : "sin web ←"}
                      </div>

                      {/* prioridad */}
                      <div>
                        <span style={{ fontSize:11, fontWeight:500, padding:"3px 8px", borderRadius:20, background: pb, color: pc }}>
                          {lead.priority === "high" ? "Alta" : lead.priority === "medium" ? "Media" : "Baja"}
                        </span>
                      </div>

                      {/* estado del pipeline */}
                      <div>
                        <span style={{ fontSize:11, fontWeight:500, padding:"3px 8px", borderRadius:20, background: STAGE_BG[lead.status || "new"], color: STAGE_COLOR[lead.status || "new"] }}>
                          {STAGE_LABEL[lead.status || "new"]}
                        </span>
                      </div>

                      {/* flecha */}
                      <div style={{ textAlign:"right", color:T.textMuted, fontSize:11, marginTop:2 }}>{isExp ? "▲" : "▼"}</div>
                    </div>

                    {/* detalle expandido */}
                    {isExp && (
                      <div style={{ background:T.inputBg, borderTop:`1px solid ${T.border}`, padding:"16px 24px 16px 72px" }}>
                        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:20, marginBottom:16 }}>
                          <div style={{ fontSize:12, color:T.textSecondary, lineHeight:2 }}>
                            {lead.phone   && <div>📞 <span style={{ color:T.text }}>{lead.phone}</span></div>}
                            {lead.address && <div>📍 <span style={{ color:T.text }}>{lead.address.replace(/[^\x20-\x7E\u00C0-\u024F\u00F1]/g,"").trim()}</span></div>}
                            {lead.maps_url && <a href={lead.maps_url} target="_blank" rel="noreferrer" style={{ color:"#2563EB", fontSize:12 }}>Ver en Google Maps ↗</a>}
                          </div>
                          <div>
                            {lead.score_reasons?.map((r, i) => (
                              <div key={i} style={{ fontSize:11, color:T.textMuted, lineHeight:2 }}>· {r}</div>
                            ))}
                          </div>
                        </div>

                        {lead.email_body ? (
                          <div style={{ background:T.cardBg, border:`1px solid ${T.border}`, borderRadius:8, padding:16, marginBottom:12 }}>
                            <div style={{ fontSize:11, fontWeight:600, color:T.textMuted, textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:8 }}>Mensaje generado</div>
                            <div style={{ fontSize:12, color:T.textSecondary, marginBottom:6 }}>Asunto: <span style={{ color:T.text, fontWeight:500 }}>{lead.email_subject}</span></div>
                            <div style={{ fontSize:12, color:T.textSecondary, whiteSpace:"pre-line", lineHeight:1.7, borderTop:`1px solid ${T.borderLight}`, paddingTop:10, marginTop:4 }}>{lead.email_body}</div>
                          </div>
                        ) : (
                          <button onClick={() => generateMsg(lead)} disabled={generating === lead.name}
                            style={{ ...S.btnGhost, marginBottom:12, opacity: generating === lead.name ? 0.5 : 1 }}>
                            {generating === lead.name ? "⟳ Generando..." : "✦ Generar mensaje con IA"}
                          </button>
                        )}

                        <div style={{ display:"flex", gap:8, alignItems:"center", flexWrap:"wrap" }}>
                          <button onClick={() => toggleSelect(lead.name)} style={isSel ? S.btnGreen : S.btnGhost}>
                            {isSel ? "✓ Seleccionado" : "+ Seleccionar"}
                          </button>
                          <button onClick={() => sendLead(lead.name)} disabled={sending === lead.name || !lead.email_body}
                            style={{ ...S.btnPrimary, opacity: (!lead.email_body || sending === lead.name) ? 0.4 : 1, cursor: !lead.email_body ? "not-allowed" : "pointer" }}>
                            {sending === lead.name ? "Enviando..." : "✉ Enviar email"}
                          </button>

                          {lead.phone && (
                            <select
                              value={lead.status || "new"}
                              onChange={e => updateStatus(lead.name, e.target.value)}
                              onClick={e => e.stopPropagation()}
                              style={{ fontSize:12, fontWeight:500, padding:"7px 10px", borderRadius:8, border:`1px solid ${T.border}`, background:T.cardBg, color:T.text, cursor:"pointer" }}
                            >
                              {STAGES.map(s => (
                                <option key={s} value={s}>{STAGE_LABEL[s]}</option>
                              ))}
                            </select>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ══ CRM (pipeline tipo Kanban) ══ */}
        {tab === "crm" && (
          <div style={S.scroll}>
            <h2 style={{ fontSize:20, fontWeight:700, marginBottom:4, color:T.text }}>CRM</h2>
            <p style={{ fontSize:13, color:T.textMuted, marginBottom:24 }}>Tu pipeline de leads, etapa por etapa.</p>

            <div style={{ display:"flex", gap:12, overflowX:"auto", paddingBottom:12 }}>
              {STAGES.map(stage => {
                const inStage = leads.filter(l => (l.status || "new") === stage);
                return (
                  <div key={stage} style={{ minWidth:240, flex:"0 0 240px", background:T.cardBg, border:`1px solid ${T.border}`, borderRadius:10, display:"flex", flexDirection:"column", maxHeight:"calc(100vh - 180px)" }}>
                    <div style={{ padding:"12px 14px", borderBottom:`1px solid ${T.borderLight}`, display:"flex", alignItems:"center", justifyContent:"space-between" }}>
                      <span style={{ fontSize:12, fontWeight:600, color: STAGE_COLOR[stage] }}>{STAGE_LABEL[stage]}</span>
                      <span style={{ fontSize:11, color:T.textMuted, background:T.inputBg, padding:"2px 7px", borderRadius:10 }}>{inStage.length}</span>
                    </div>
                    <div style={{ overflowY:"auto", padding:8, flex:1 }}>
                      {inStage.length === 0 ? (
                        <div style={{ fontSize:11, color:T.textMuted, textAlign:"center", padding:"20px 0" }}>—</div>
                      ) : inStage.map(l => (
                        <div key={l.name} style={{ background:T.inputBg, border:`1px solid ${T.borderLight}`, borderRadius:8, padding:10, marginBottom:8 }}>
                          <div style={{ fontSize:12, fontWeight:500, color:T.text, marginBottom:2 }}>{l.name}</div>
                          <div style={{ fontSize:10, color:T.textMuted, marginBottom:8 }}>{l.category} · {l.zone}</div>
                          {l.phone && (
                            <select
                              value={l.status || "new"}
                              onChange={e => updateStatus(l.name, e.target.value)}
                              style={{ width:"100%", fontSize:11, padding:"5px 6px", borderRadius:6, border:`1px solid ${T.border}`, background:T.cardBg, color:T.text, cursor:"pointer" }}
                            >
                              {STAGES.map(s => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}
                            </select>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ══ ENGAGE (canales: Gmail + WhatsApp) ══ */}
        {tab === "engage" && (
          <div style={S.scroll}>
            <h2 style={{ fontSize:20, fontWeight:700, marginBottom:4, color:T.text }}>Engage</h2>
            <p style={{ fontSize:13, color:T.textMuted, marginBottom:20 }}>Tus canales de contacto, cada uno con su propia data.</p>

            {/* sub-nav de canales */}
            <div style={{ display:"flex", gap:6, marginBottom:20, borderBottom:`1px solid ${T.border}`, paddingBottom:2 }}>
              {[
                { key: "gmail" as const,    label: "✉  Gmail" },
                { key: "whatsapp" as const, label: "💬  WhatsApp" },
              ].map(c => (
                <button
                  key={c.key}
                  onClick={() => setChannelTab(c.key)}
                  style={{
                    padding:"8px 16px", borderRadius:"8px 8px 0 0", border:"none", cursor:"pointer",
                    fontSize:13, fontWeight:500, fontFamily:"inherit",
                    background: channelTab === c.key ? T.cardBg : "transparent",
                    color: channelTab === c.key ? T.text : T.textMuted,
                    borderBottom: channelTab === c.key ? "2px solid #2563EB" : "2px solid transparent",
                    marginBottom:-3,
                  }}
                >
                  {c.label}
                </button>
              ))}
            </div>

            {/* ── canal Gmail ── */}
            {channelTab === "gmail" && (
              <>
                <div style={S.card}>
                  <div style={S.cardTitle}>Subir emails</div>
                  <p style={{ fontSize:12, color:T.textSecondary, marginBottom:12 }}>
                    Google Maps no expone emails — sube un CSV o Excel con columnas <b>name</b> y <b>email</b> (por ejemplo, de Hunter.io o del sitio web de cada negocio).
                  </p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,.xlsx,.xls"
                    style={{ display:"none" }}
                    onChange={e => { const f = e.target.files?.[0]; if (f) uploadEmails(f); e.target.value = ""; }}
                  />
                  <button onClick={() => fileInputRef.current?.click()} disabled={uploadingEmails} style={{ ...S.btnGhost, opacity: uploadingEmails ? 0.5 : 1 }}>
                    {uploadingEmails ? "⟳ Subiendo..." : "↑ Subir CSV / Excel"}
                  </button>
                </div>

                <div style={S.card}>
                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:12 }}>
                    <div style={S.cardTitle}>Leads con email ({engageLeads.length})</div>
                    <button
                      onClick={() => sendCampaign(engageLeads.filter(l => l.email_body).map(l => l.name))}
                      disabled={sendingCampaign || !emailAccount || engageLeads.filter(l => l.email_body).length === 0}
                      style={{ ...S.btnPrimary, opacity: (sendingCampaign || !emailAccount || engageLeads.filter(l => l.email_body).length === 0) ? 0.4 : 1 }}
                    >
                      {sendingCampaign ? "Enviando..." : `✉ Enviar campaña (${engageLeads.filter(l => l.email_body).length})`}
                    </button>
                  </div>

                  {!emailAccount && (
                    <div style={{ fontSize:12, color:"#D97706", background:"rgba(217,119,6,0.14)", border:"1px solid rgba(217,119,6,0.35)", borderRadius:8, padding:10, marginBottom:12 }}>
                      ⚠ No tienes una cuenta de Gmail conectada. Ve a "Cuentas de Email" primero.
                    </div>
                  )}

                  {engageLeads.length === 0 ? (
                    <div style={{ textAlign:"center", padding:40, color:T.textMuted, fontSize:13 }}>
                      Ningún lead tiene email todavía — sube un archivo arriba.
                    </div>
                  ) : engageLeads.map(lead => (
                    <div key={lead.name} style={{ display:"flex", justifyContent:"space-between", alignItems:"center", padding:"10px 0", borderBottom:`1px solid ${T.borderLight}` }}>
                      <div>
                        <div style={{ fontSize:13, fontWeight:500, color:T.text }}>{lead.name}</div>
                        <div style={{ fontSize:11, color:T.textMuted }}>{lead.email}</div>
                      </div>
                      {lead.email_body ? (
                        <span style={{ fontSize:11, color:"#16A34A", background:"rgba(22,163,74,0.14)", padding:"3px 8px", borderRadius:20 }}>✓ Mensaje listo</span>
                      ) : (
                        <button onClick={() => generateMsg(lead)} disabled={generating === lead.name} style={{ ...S.btnGhost, opacity: generating === lead.name ? 0.5 : 1 }}>
                          {generating === lead.name ? "⟳ Generando..." : "✦ Generar mensaje"}
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* ── canal WhatsApp ── */}
            {channelTab === "whatsapp" && (
              <>
                <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:12, marginBottom:12 }}>
                  <div style={S.metricCard}>
                    <div style={S.metricLabel}>Leads con teléfono</div>
                    <div style={S.metricVal}>{whatsappSummary.total}</div>
                  </div>
                  <div style={S.metricCard}>
                    <div style={S.metricLabel}>Pendientes</div>
                    <div style={S.metricVal}>{whatsappSummary.pending}</div>
                  </div>
                  <div style={S.metricCard}>
                    <div style={S.metricLabel}>Ya contactados</div>
                    <div style={S.metricVal}>{whatsappSummary.sent}</div>
                  </div>
                </div>

                <div style={S.card}>
                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:12 }}>
                    <div style={S.cardTitle}>Bot de WhatsApp</div>
                    <span style={{ fontSize:11, fontWeight:500, padding:"3px 10px", borderRadius:20, background: whatsappStatus.running ? "rgba(22,163,74,0.14)" : "rgba(107,114,128,0.10)", color: whatsappStatus.running ? "#16A34A" : "#6B7280" }}>
                      {whatsappStatus.running ? "● Corriendo" : "○ Detenido"}
                    </span>
                  </div>

                  <p style={{ fontSize:12, color:T.textSecondary, marginBottom:14 }}>
                    Lee el Excel que exportaste en <b>Métricas → Exportar Excel para WhatsApp</b> (colócalo en <code>WHATSAPP_IA/data/</code>) y envía los mensajes usando WhatsApp Web. Necesita la pantalla de esta PC despierta y WhatsApp Web ya logueado.
                  </p>

                  <div style={{ display:"flex", gap:8, marginBottom:14 }}>
                    <button onClick={exportWhatsAppExcel} style={S.btnGhost}>↓ Exportar Excel</button>
                    {whatsappStatus.running ? (
                      <button onClick={stopWhatsapp} style={S.btnDanger}>■ Detener bot</button>
                    ) : (
                      <button onClick={launchWhatsapp} disabled={launchingWa} style={{ ...S.btnPrimary, opacity: launchingWa ? 0.5 : 1 }}>
                        {launchingWa ? "Lanzando..." : "▶ Lanzar bot de WhatsApp"}
                      </button>
                    )}
                  </div>

                  <div style={S.log}>
                    {whatsappStatus.log_tail
                      ? whatsappStatus.log_tail.split("\n").map((line, i) => <div key={i}>{line}</div>)
                      : <div style={{ opacity:0.5 }}>Sin actividad todavía. Lanza el bot para ver el log aquí.</div>}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* ══ CUENTAS DE EMAIL ══ */}
        {tab === "accounts" && (
          <div style={S.scroll}>
            <h2 style={{ fontSize:20, fontWeight:700, marginBottom:4, color:T.text }}>Cuentas de Email</h2>
            <p style={{ fontSize:13, color:T.textMuted, marginBottom:24 }}>Conecta la cuenta de Gmail que va a enviar tus campañas.</p>

            {emailAccount ? (
              <div style={S.card}>
                <div style={S.cardTitle}>Cuenta conectada</div>
                <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                  <div>
                    <div style={{ fontSize:14, fontWeight:500, color:T.text }}>{emailAccount.email}</div>
                    <div style={{ fontSize:11, color:T.textMuted }}>{emailAccount.smtp_host}:{emailAccount.smtp_port} · {emailAccount.from_name}</div>
                  </div>
                  <button onClick={disconnectEmailAccount} style={S.btnDanger}>Desconectar</button>
                </div>
              </div>
            ) : (
              <div style={S.card}>
                <div style={S.cardTitle}>Conectar Gmail</div>
                <p style={{ fontSize:12, color:T.textSecondary, marginBottom:14 }}>
                  Necesitas una <b>contraseña de aplicación</b> de Google (no tu contraseña normal).
                  Actívala en tu cuenta de Google → Seguridad → Verificación en 2 pasos → Contraseñas de aplicaciones.
                </p>
                <div style={{ display:"grid", gap:10, maxWidth:420 }}>
                  <div>
                    <div style={{ fontSize:11, color:T.textMuted, marginBottom:4 }}>Tu Gmail</div>
                    <input style={S.input} placeholder="tu@gmail.com" value={emailForm.email}
                      onChange={e => setEmailForm({ ...emailForm, email: e.target.value })} />
                  </div>
                  <div>
                    <div style={{ fontSize:11, color:T.textMuted, marginBottom:4 }}>Contraseña de aplicación</div>
                    <input style={S.input} type="password" placeholder="xxxx xxxx xxxx xxxx" value={emailForm.app_password}
                      onChange={e => setEmailForm({ ...emailForm, app_password: e.target.value })} />
                  </div>
                  <div>
                    <div style={{ fontSize:11, color:T.textMuted, marginBottom:4 }}>Nombre para mostrar</div>
                    <input style={S.input} placeholder="Tu Nombre / Tu Agencia" value={emailForm.from_name}
                      onChange={e => setEmailForm({ ...emailForm, from_name: e.target.value })} />
                  </div>
                  <button onClick={saveEmailAccount} disabled={savingEmail} style={{ ...S.btnPrimary, opacity: savingEmail ? 0.5 : 1, width:"fit-content" }}>
                    {savingEmail ? "Conectando..." : "Conectar cuenta"}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ══ MÉTRICAS ══ */}
        {tab === "charts" && (
          <div style={S.scroll}>
            <h2 style={{ fontSize:20, fontWeight:700, marginBottom:4, color:T.text }}>Métricas</h2>
            <p style={{ fontSize:13, color:T.textMuted, marginBottom:24 }}>Resumen del rendimiento del agente.</p>

            {/* grid métricas */}
            <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:12, marginBottom:24 }}>
              {[
                { label:"Leads scrapeados",   value: metrics.leads_scraped   || 0 },
                { label:"Leads calificados",  value: metrics.leads_qualified || 0 },
                { label:"Alta prioridad",     value: metrics.high_priority   || 0 },
                { label:"Enviados WhatsApp",  value: metrics.whatsapp_sent   || 0 },
                { label:"Tasa de respuesta",  value: `${metrics.reply_rate  || 0}%` },
                { label:"Clientes ganados",   value: metrics.pipeline?.won   || 0 },
              ].map(m => (
                <div key={m.label} style={S.metricCard}>
                  <div style={S.metricLabel}>{m.label}</div>
                  <div style={S.metricVal}>{m.value}</div>
                </div>
              ))}
            </div>

            {/* pipeline (funnel tipo CRM) */}
            <div style={S.card}>
              <div style={S.cardTitle}>Pipeline de leads</div>
              {STAGES.map(s => ({ label: STAGE_LABEL[s], value: metrics.pipeline?.[s] || 0, color: STAGE_COLOR[s] })).map(b => (
                <div key={b.label} style={{ marginBottom:16 }}>
                  <div style={{ display:"flex", justifyContent:"space-between", fontSize:13, marginBottom:6 }}>
                    <span style={{ color:T.textSecondary }}>{b.label}</span>
                    <span style={{ fontWeight:600, color:b.color }}>{b.value}</span>
                  </div>
                  <div style={{ height:6, background:T.borderLight, borderRadius:3, overflow:"hidden" }}>
                    <div style={{ height:"100%", width:`${Math.round((b.value/pipelineMax)*100)}%`, background:b.color, borderRadius:3, transition:"width 0.6s ease" }} />
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
                { label:"Baja",  color:T.textMuted, count: leads.filter(l=>l.priority==="low").length },
              ].map(p => (
                <div key={p.label} style={{ marginBottom:14 }}>
                  <div style={{ display:"flex", justifyContent:"space-between", fontSize:13, marginBottom:6 }}>
                    <span style={{ color:T.textSecondary }}>{p.label}</span>
                    <span style={{ fontWeight:600, color:p.color }}>{p.count}</span>
                  </div>
                  <div style={{ height:6, background:T.borderLight, borderRadius:3, overflow:"hidden" }}>
                    <div style={{ height:"100%", width: leads.length ? `${Math.round((p.count/leads.length)*100)}%` : "0%", background:p.color, borderRadius:3, transition:"width 0.6s ease" }} />
                  </div>
                </div>
              ))}
            </div>

            <button onClick={exportWhatsAppExcel} style={{ ...S.btnPrimary, width:"100%", padding:"12px 0", textAlign:"center" as const, marginBottom:10 }}>
              ↓ Exportar Excel para WhatsApp
            </button>

            <button onClick={exportCSV} style={{ ...S.btnGhost, width:"100%", padding:"12px 0", textAlign:"center" as const }}>
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