import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bell,
  Briefcase,
  CheckCircle2,
  Clock3,
  Lock,
  LogOut,
  Pause,
  Play,
  RefreshCw,
  ShieldCheck,
  Square,
  Users,
  XCircle,
} from "lucide-react";
import { AgentAvatar } from "./components/AgentAvatar";
import { AgentSidebar } from "./components/AgentSidebar";
import { STATUS_LABELS } from "./lib/agentStatus";
import { DeliverablesPanel } from "./components/DeliverablesPanel";
import { LoginModal } from "./components/LoginModal";
import { LucianoDesk } from "./components/LucianoDesk";
import { OutreachPanel } from "./components/OutreachPanel";
import { SourcePanel } from "./components/SourcePanel";
import {
  UnauthorizedError,
  fetchAutomationStatus,
  fetchGmailStatus,
  fetchOperatorMe,
  fetchOutreachFeed,
  fetchPendingDeliverables,
  fetchPublicOfficeSummary,
  loginOperator,
  pauseAutomation,
  resumeAutomation,
  reviewDeliverable,
  runBatchEvaluationApi,
  startAutomation,
  stopAutomation,
  syncGmailResponses,
} from "./services/api";
import type {
  AgentActivityItem,
  AgentStateItem,
  AutomationStatus,
  BatchPayload,
  BatchResult,
  DeliverableItem,
  GmailStatus,
  GmailUpdate,
  OutreachRecord,
  PublicOfficeSummary,
} from "./types/office";

const CORE_AGENTS = [
  { id: "sara", name: "Sara", role: "Orquestación & Briefing", tone: "indigo" },
  { id: "mateo", name: "Mateo", role: "Empleo remoto / híbrido", tone: "emerald" },
  { id: "valeria", name: "Valeria", role: "Clientes & propuestas", tone: "amber" },
  { id: "luciano", name: "Luciano", role: "Mentoría AI & Full Stack", tone: "sky" },
] as const;

const TONE_CLASSES: Record<string, string> = {
  indigo: "hover:border-indigo-400/60 focus:border-indigo-400",
  emerald: "hover:border-emerald-400/60 focus:border-emerald-400",
  amber: "hover:border-amber-400/60 focus:border-amber-400",
  sky: "hover:border-sky-400/60 focus:border-sky-400",
};

const MOCK_BATCHES: Record<"job" | "client", BatchPayload> = {
  job: {
    item_type: "job",
    items: [
      {
        job_url: "https://remoteok.com/remote-jobs/sample-junior-react-node",
        published_at: new Date().toISOString(),
        raw_job_text: "Junior Full Stack Developer (React, Node, TypeScript). Remoto LATAM/Global.",
        source: "RemoteOK",
        market: "GLOBAL_EN",
      },
    ],
    market: "GLOBAL_EN",
    min_fit_score: 60,
  },
  client: {
    item_type: "client",
    items: [
      {
        client_ref: "pyme-turnos-01",
        published_at: new Date().toISOString(),
        raw_client_text: "Negocio local busca sistema web de turnos y gestión de clientes con panel administrativo. Solicita presupuesto por hora.",
        source: "Directos-PyMEs",
        market: "LATAM_ES",
        channel: "web",
      },
    ],
    market: "LATAM_ES",
    min_fit_score: 60,
  },
};

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export default function App() {
  const [summary, setSummary] = useState<PublicOfficeSummary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const [operatorName, setOperatorName] = useState<string | null>(null);
  const [loginOpen, setLoginOpen] = useState(false);
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [deliverables, setDeliverables] = useState<DeliverableItem[]>([]);
  const [outreach, setOutreach] = useState<OutreachRecord[]>([]);
  const [outreachReason, setOutreachReason] = useState<string | null>(null);
  const [gmailStatus, setGmailStatus] = useState<GmailStatus | null>(null);
  const [gmailUpdates, setGmailUpdates] = useState<GmailUpdate[]>([]);
  const [actionBusyId, setActionBusyId] = useState<string | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);
  const [feedbackBanner, setFeedbackBanner] = useState<string | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [activities, setActivities] = useState<Record<string, AgentActivityItem[]>>({});
  const [notificationPermission, setNotificationPermission] =
    useState<NotificationPermission | "unsupported">("unsupported");
  const previousReportCount = useRef<number | null>(null);
  const [automationStatus, setAutomationStatus] = useState<AutomationStatus | null>(null);
  const [automationBusy, setAutomationBusy] = useState<string | null>(null);

  const loadPublicData = useCallback(async (silent = false) => {
    if (!silent) setLoadingSummary(true);
    try {
      const data = await fetchPublicOfficeSummary();
      setSummary(data);
    } catch (error) {
      setFeedbackBanner(getErrorMessage(error, "No se pudo cargar la oficina."));
    } finally {
      if (!silent) setLoadingSummary(false);
    }
  }, []);

  const loadOperatorDeliverables = useCallback(async (authToken: string) => {
    const [deliverablesResult, outreachResult, gmailResult, automationResult] = await Promise.allSettled([
      fetchPendingDeliverables(authToken),
      fetchOutreachFeed(authToken),
      fetchGmailStatus(authToken),
      fetchAutomationStatus(authToken),
    ]);
    if (
      [deliverablesResult, outreachResult, gmailResult, automationResult].some(
        (result) => result.status === "rejected" && result.reason instanceof UnauthorizedError,
      )
    ) {
      setToken(null);
      setOperatorName(null);
    }
    setDeliverables(deliverablesResult.status === "fulfilled" ? deliverablesResult.value : []);
    setOutreach(outreachResult.status === "fulfilled" ? outreachResult.value.items ?? [] : []);
    setOutreachReason(
      outreachResult.status === "fulfilled" ? outreachResult.value.reason ?? null : null,
    );
    setGmailStatus(gmailResult.status === "fulfilled" ? gmailResult.value : null);
    if (automationResult.status === "fulfilled") setAutomationStatus(automationResult.value.status);
  }, []);

  useEffect(() => {
    queueMicrotask(() => void loadPublicData());
  }, [loadPublicData]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void loadPublicData(true);
      if (token) void loadOperatorDeliverables(token);
    }, 20000);
    return () => window.clearInterval(interval);
  }, [token, loadPublicData, loadOperatorDeliverables]);

  useEffect(() => {
    if (!token) return;
    let active = true;
    void fetchOperatorMe(token)
      .then((me) => {
        if (!active) return;
        setOperatorName(me.operator);
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof UnauthorizedError) {
          setToken(null);
          setOperatorName(null);
          setFeedbackBanner("La sesión expiró. Iniciá sesión nuevamente.");
        }
      });
    queueMicrotask(() => {
      if (active) void loadOperatorDeliverables(token);
    });
    return () => {
      active = false;
    };
  }, [token, loadOperatorDeliverables]);

  useEffect(() => {
    if (typeof Notification === "undefined") return;
    queueMicrotask(() => setNotificationPermission(Notification.permission));
  }, []);

  const reportsReady = summary?.daily_briefing.reports_ready ?? 0;
  useEffect(() => {
    const previous = previousReportCount.current;
    previousReportCount.current = reportsReady;
    if (previous === null || reportsReady <= previous || typeof Notification === "undefined") return;
    if (Notification.permission !== "granted") return;
    new Notification("AI Office · Reportes listos", {
      body: `Sara tiene ${reportsReady} reporte${reportsReady === 1 ? "" : "s"} listo${reportsReady === 1 ? "" : "s"} para revisión.`,
    });
  }, [reportsReady]);

  const requestNotifications = async () => {
    if (typeof Notification === "undefined") return;
    try {
      const permission = await Notification.requestPermission();
      setNotificationPermission(permission);
      setFeedbackBanner(
        permission === "granted"
          ? "Notificaciones de navegador activadas para los reportes listos."
          : "Notificaciones no habilitadas. El aviso en pantalla sigue activo.",
      );
    } catch {
      setFeedbackBanner("El navegador no permitió activar notificaciones. El aviso en pantalla sigue activo.");
    }
  };

  const openLogin = () => {
    setLoginError(null);
    setLoginOpen(true);
  };

  const handleLogin = async (username: string, password: string) => {
    setLoginLoading(true);
    setLoginError(null);
    try {
      const auth = await loginOperator(username, password);
      setToken(auth.access_token);
      setOperatorName(auth.operator);
      setLoginOpen(false);
      setFeedbackBanner(`Sesión iniciada como ${auth.operator}. Controles operativos habilitados.`);
    } catch (error) {
      setLoginError(getErrorMessage(error, "Credenciales inválidas."));
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = () => {
    setToken(null);
    setOperatorName(null);
    setDeliverables([]);
    setOutreach([]);
    setOutreachReason(null);
    setGmailStatus(null);
    setGmailUpdates([]);
    setActivities({});
    setAutomationStatus(null);
    setFeedbackBanner("Sesión cerrada. La oficina volvió al modo resumen de exhibición.");
  };

  const refreshAll = async (authToken: string) => {
    await Promise.all([loadPublicData(), loadOperatorDeliverables(authToken)]);
  };

  const handleNotice = (message: string) => setFeedbackBanner(message);

  const handleSyncGmail = async () => {
    if (!token) throw new Error("Iniciá sesión para revisar Gmail.");
    const result = await syncGmailResponses(token);
    setGmailUpdates(result.updates);
    return result;
  };

  const handleAutomationAction = async (action: "start" | "pause" | "resume" | "stop") => {
    if (!token) return openLogin();
    setAutomationBusy(action);
    setFeedbackBanner(null);
    try {
      const response = await {
        start: () => startAutomation(token),
        pause: () => pauseAutomation(token),
        resume: () => resumeAutomation(token),
        stop: () => stopAutomation(token),
      }[action]();
      setAutomationStatus(response.status);
      setFeedbackBanner(
        `Automatización: ${response.status.state}. ` +
          (response.status.reason || "Mateo y Valeria están listos para continuar."),
      );
      await loadPublicData(true);
    } catch (error) {
      if (error instanceof UnauthorizedError) {
        setToken(null);
        setOperatorName(null);
      }
      setFeedbackBanner(getErrorMessage(error, "No se pudo cambiar el estado de la automatización."));
    } finally {
      setAutomationBusy(null);
    }
  };

  const recordActivity = (result: BatchResult) => {
    const next: Record<string, AgentActivityItem[]> = {};
    for (const entry of result.results ?? []) {
      for (const agentId of ["mateo", "valeria"]) {
        const activity = entry.activity ?? [];
        if (activity.length > 0) next[agentId] = activity;
      }
    }
    if (Object.keys(next).length > 0) setActivities((prev) => ({ ...prev, ...next }));
  };

  const handleReview = async (id: string, decision: "approved" | "rejected") => {
    if (!token) return openLogin();
    setActionBusyId(id);
    setFeedbackBanner(null);
    try {
      const result = await reviewDeliverable(token, id, decision);
      await refreshAll(token);
      setFeedbackBanner(result.message);
    } catch (error) {
      if (error instanceof UnauthorizedError) {
        setToken(null);
        setOperatorName(null);
      }
      setFeedbackBanner(getErrorMessage(error, "Error al procesar la revisión."));
    } finally {
      setActionBusyId(null);
    }
  };

  const handleBatch = async (itemType: "job" | "client") => {
    if (!token) return openLogin();
    setBatchBusy(true);
    setFeedbackBanner(null);
    try {
      const response = await runBatchEvaluationApi(token, MOCK_BATCHES[itemType]);
      recordActivity(response.result);
      await refreshAll(token);
      const { result } = response;
      setFeedbackBanner(
        result.reason ??
          `Lote procesado: ${result.processed} evaluados, ${result.saved_for_approval} guardados para aprobación, ${result.duplicates} duplicados.`,
      );
    } catch (error) {
      if (error instanceof UnauthorizedError) {
        setToken(null);
        setOperatorName(null);
      }
      setFeedbackBanner(getErrorMessage(error, "Error al correr el lote."));
    } finally {
      setBatchBusy(false);
    }
  };

  const agentStates = useMemo(() => {
    const states = new Map<string, AgentStateItem>();
    for (const agent of summary?.agents ?? []) states.set(agent.agent_id?.toLowerCase(), agent);
    return states;
  }, [summary]);

  const selectedAgent = selectedAgentId ? (agentStates.get(selectedAgentId) ?? null) : null;
  const selectedActivity = selectedAgentId ? (activities[selectedAgentId] ?? selectedAgent?.activity ?? []) : [];

  const handleQuickAction = (target: string) => {
    setSelectedAgentId(null);
    window.setTimeout(() => {
      document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
              <h1 className="text-lg font-bold tracking-tight sm:text-xl">AI Office</h1>
              <span className="rounded-full border border-slate-700 bg-slate-900 px-2.5 py-0.5 text-[11px] text-slate-300">
                {token ? `Operador: ${operatorName ?? "activo"}` : "Modo Resumen / Portfolio"}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-slate-400">
              {token
                ? "Controles habilitados: aprobaciones, lotes, automatizaciones preparadas y mentoría."
                : "Vista pública de solo lectura. Iniciá sesión para ejecutar acciones."}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void loadPublicData()}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loadingSummary ? "animate-spin" : ""}`} /> Actualizar
            </button>
            <button
              type="button"
              onClick={() => void requestNotifications()}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800"
              title="Avisos de reportes listos sin servicios externos"
            >
              <Bell className="h-3.5 w-3.5 text-amber-300" />
              {notificationPermission === "granted" ? "Avisos activos" : "Activar avisos"}
            </button>
            {token ? (
              <button
                type="button"
                onClick={handleLogout}
                className="inline-flex items-center gap-1.5 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs font-medium text-rose-200 hover:bg-rose-500/20"
              >
                <LogOut className="h-3.5 w-3.5" /> Cerrar sesión
              </button>
            ) : (
              <button
                type="button"
                onClick={openLogin}
                className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-500"
              >
                <Lock className="h-3.5 w-3.5" /> Iniciar sesión
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
        {feedbackBanner && (
          <div className="flex items-start justify-between gap-3 rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-4 py-2.5 text-xs text-indigo-200">
            <span>{feedbackBanner}</span>
            <button type="button" onClick={() => setFeedbackBanner(null)} aria-label="Cerrar aviso" className="text-indigo-300 hover:text-white">
              <XCircle className="h-4 w-4" />
            </button>
          </div>
        )}

        {reportsReady > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-100">
            <span className="inline-flex items-center gap-2">
              <Bell className="h-4 w-4" />
              <strong>Sara tiene {reportsReady} reporte{reportsReady === 1 ? "" : "s"} listo{reportsReady === 1 ? "" : "s"}.</strong>
              Revisá la bandeja de aprobación.
            </span>
            <button
              type="button"
              onClick={() => handleQuickAction("aprobaciones")}
              className="rounded-lg bg-amber-500/20 px-3 py-1.5 font-medium hover:bg-amber-500/30"
            >
              Ver reportes
            </button>
          </div>
        )}

        <section id="reportes" className="rounded-2xl border border-slate-800 bg-linear-to-r from-indigo-950/50 via-slate-900 to-slate-900 p-5 shadow-lg">
          <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
            <div className="flex items-start gap-4">
              <AgentAvatar agentId="sara" status={agentStates.get("sara")?.status} />
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-indigo-300">Reporte del día · Sara</p>
                <p className="mt-1 text-sm leading-relaxed text-slate-100 sm:text-base">
                  {summary?.daily_briefing.sara_message ?? "Cargando reporte diario de la oficina..."}
                </p>
                <div className="mt-2.5 flex flex-wrap gap-3 text-xs text-slate-300">
                  <span className="inline-flex items-center gap-1 rounded-lg bg-slate-800/90 px-2.5 py-1">
                    <Briefcase className="h-3.5 w-3.5 text-emerald-400" />
                    Vacantes detectadas: <strong>{summary?.daily_briefing.jobs_count ?? 0}</strong>
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-lg bg-slate-800/90 px-2.5 py-1">
                    <Users className="h-3.5 w-3.5 text-amber-400" />
                    Clientes detectados: <strong>{summary?.daily_briefing.clients_count ?? 0}</strong>
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-lg bg-slate-800/90 px-2.5 py-1">
                    <Bell className="h-3.5 w-3.5 text-sky-400" />
                    Enviados: <strong>{summary?.follow_up?.sent ?? 0}</strong>
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-lg bg-slate-800/90 px-2.5 py-1">
                    <Clock3 className="h-3.5 w-3.5 text-amber-400" />
                    Espera de respuesta: <strong>{summary?.follow_up?.awaiting_reply ?? 0}</strong>
                  </span>
                  {(summary?.follow_up?.responded ?? 0) > 0 && (
                    <span className="inline-flex items-center gap-1 rounded-lg bg-sky-500/10 px-2.5 py-1 text-sky-200">
                      Respondidos: <strong>{summary?.follow_up?.responded}</strong>
                    </span>
                  )}
                </div>
              </div>
            </div>
            {token && (
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={batchBusy}
                  onClick={() => void handleBatch("job")}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                >
                  <Play className="h-3.5 w-3.5" /> Correr lote empleos
                </button>
                <button
                  type="button"
                  disabled={batchBusy}
                  onClick={() => void handleBatch("client")}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-amber-600 px-3 py-2 text-xs font-medium text-white hover:bg-amber-500 disabled:opacity-50"
                >
                  <Play className="h-3.5 w-3.5" /> Correr lote clientes
                </button>
              </div>
            )}
          </div>
        </section>

        {summary?.advisor && (
          <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-lg">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-sky-300">
                  Consejos de Sara · trazabilidad
                </p>
                <p className="mt-1 text-sm text-slate-200">
                  Te digo qué encontró cada agente, de dónde viene y si ya se postuló o sigue pendiente.
                </p>
              </div>
              <span
                className={`rounded-full border px-2.5 py-1 text-[11px] ${
                  summary.advisor.token_alert.alert
                    ? "border-amber-500/30 bg-amber-500/10 text-amber-200"
                    : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                }`}
              >
                Tokens {summary.advisor.token_alert.used}/{summary.advisor.token_alert.limit}
              </span>
            </div>
            {summary.advisor.token_alert.alert && (
              <p className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                {summary.advisor.token_alert.message}
              </p>
            )}
            <ul className="mt-3 space-y-1 text-xs text-slate-300">
              {summary.advisor.suggestions.map((suggestion, index) => (
                <li key={`advice-${index}`} className="flex gap-2">
                  <span className="text-sky-400">•</span>
                  <span>{suggestion}</span>
                </li>
              ))}
            </ul>
            {summary.advisor.findings.length > 0 && (
              <div className="mt-4 grid gap-2 md:grid-cols-2">
                {summary.advisor.findings.map((finding, index) => (
                  <div key={`finding-${index}`} className="rounded-xl border border-slate-800 bg-slate-950/70 p-3">
                    <p className="text-xs font-medium text-slate-100">{finding.message}</p>
                    <p className="mt-1 text-[11px] text-slate-400">
                      Fuente: {finding.source_platform}
                      {finding.source_url && (
                        <a
                          href={finding.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="ml-2 text-sky-300 hover:text-sky-200"
                        >
                          Ver publicación
                        </a>
                      )}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {token && (
          <section id="automatizacion" className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-lg">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-indigo-300">
                  Automatización · Sara
                </p>
                <p className="mt-1 text-sm text-slate-200">
                  Mateo y Valeria arrancan al iniciar sesión y trabajan en paralelo con ventanas de 15 días.
                </p>
              </div>
              <span className="rounded-full border border-slate-700 bg-slate-800 px-2.5 py-1 text-[11px] text-slate-200">
                Estado: {automationStatus?.state ?? "stopped"}
              </span>
            </div>
            {automationStatus?.reason && (
              <p className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                {automationStatus.reason}
              </p>
            )}
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {automationStatus && Object.entries(automationStatus.agents).map(([name, values]) => (
                <div key={name} className="rounded-xl border border-slate-800 bg-slate-950/70 p-3 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold capitalize text-slate-100">{name}</span>
                    <span className={values.running ? "text-emerald-300" : "text-slate-400"}>
                      {values.running ? "activo" : "en espera"}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-400">
                    Corridas: {values.runs} · Última: {values.last_run ? new Date(values.last_run).toLocaleString("es-AR") : "sin datos"}
                  </p>
                  {values.last_error && (
                    <p className="mt-1 text-[11px] text-rose-300">{values.last_error}</p>
                  )}
                </div>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={automationBusy !== null}
                onClick={() => void handleAutomationAction("start")}
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-[11px] font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                <Play className="h-3.5 w-3.5" /> Iniciar
              </button>
              <button
                type="button"
                disabled={automationBusy !== null}
                onClick={() => void handleAutomationAction("pause")}
                className="inline-flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] font-medium text-amber-200 hover:bg-amber-500/20 disabled:opacity-50"
              >
                <Pause className="h-3.5 w-3.5" /> Pausar
              </button>
              <button
                type="button"
                disabled={automationBusy !== null}
                onClick={() => void handleAutomationAction("resume")}
                className="inline-flex items-center gap-1.5 rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-[11px] font-medium text-sky-200 hover:bg-sky-500/20 disabled:opacity-50"
              >
                <RefreshCw className="h-3.5 w-3.5" /> Reanudar
              </button>
              <button
                type="button"
                disabled={automationBusy !== null}
                onClick={() => void handleAutomationAction("stop")}
                className="inline-flex items-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[11px] font-medium text-rose-200 hover:bg-rose-500/20 disabled:opacity-50"
              >
                <Square className="h-3.5 w-3.5" /> Detener
              </button>
            </div>
          </section>
        )}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">Puestos de la Oficina</h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {CORE_AGENTS.map((agent) => {
                const state = agentStates.get(agent.id);
                const status = state?.status ?? "idle";
                return (
                  <button
                    key={agent.id}
                    type="button"
                    onClick={() => setSelectedAgentId(agent.id)}
                    className={`flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/80 p-4 text-left transition focus:outline-none ${TONE_CLASSES[agent.tone]}`}
                  >
                    <AgentAvatar agentId={agent.id} status={status} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-semibold text-white">{agent.name}</h3>
                        <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300">
                          {STATUS_LABELS[status] ?? status}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400">{agent.role}</p>
                      <p className="mt-1 truncate text-[11px] text-slate-500">
                        {state?.current_task ?? "Listo en su puesto de trabajo"}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
            <p className="mt-3 text-[11px] text-slate-500">
              Tocá un cubículo para ver estado, tarea en curso, actividad reciente y accesos rápidos.
            </p>
          </section>

          <AgentSidebar
            agent={selectedAgent ?? (selectedAgentId ? {
              agent_id: selectedAgentId,
              display_name: CORE_AGENTS.find((a) => a.id === selectedAgentId)?.name,
              role: CORE_AGENTS.find((a) => a.id === selectedAgentId)?.role,
              status: "idle",
              current_task: "Sin estado reportado por el backend",
            } : null)}
            activity={selectedActivity}
            isOpen={selectedAgentId !== null}
            onClose={() => setSelectedAgentId(null)}
            onQuickAction={handleQuickAction}
            canOperate={Boolean(token)}
          />
        </div>

        <DeliverablesPanel
          items={deliverables}
          busyId={actionBusyId}
          canOperate={Boolean(token)}
          onReview={(id, decision) => void handleReview(id, decision)}
          onRequireLogin={openLogin}
        />

        {token && (
          <>
            <SourcePanel
              token={token}
              onNotice={handleNotice}
              onEvaluated={() => void refreshAll(token)}
            />
            <OutreachPanel
              token={token}
              records={outreach}
              schemaReason={outreachReason}
              gmailStatus={gmailStatus}
              gmailUpdates={gmailUpdates}
              onRefresh={() => void loadOperatorDeliverables(token)}
              onNotice={handleNotice}
              onSyncGmail={handleSyncGmail}
            />
          </>
        )}

        <LucianoDesk token={token} onRequireLogin={openLogin} />

        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-800 pt-4 text-[11px] text-slate-500">
          <span className="inline-flex items-center gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5" /> Sin envíos automáticos: toda acción externa requiere aprobación humana.
          </span>
          <span className="inline-flex items-center gap-1.5">
            {token ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> : <Lock className="h-3.5 w-3.5" />}
            {token ? "Sesión operativa activa" : "Modo exhibición"}
          </span>
        </footer>
      </main>

      <LoginModal
        isOpen={loginOpen}
        onClose={() => setLoginOpen(false)}
        onSubmit={handleLogin}
        loading={loginLoading}
        errorMsg={loginError}
      />
    </div>
  );
}
