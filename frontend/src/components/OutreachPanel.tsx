import { useState } from "react";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  Clock3,
  ExternalLink,
  Mail,
  MessageSquare,
  Paperclip,
  PenLine,
  RefreshCw,
} from "lucide-react";
import { createGmailControlDraft, registerGmailSentAction, updateOutreachStatusApi } from "../services/api";
import { STATUS_LABELS } from "../lib/agentStatus";
import type { GmailStatus, GmailSyncResult, GmailUpdate, OutreachRecord, OutreachStatus } from "../types/office";

interface OutreachPanelProps {
  token: string;
  records: OutreachRecord[];
  schemaReason?: string | null;
  gmailStatus: GmailStatus | null;
  gmailUpdates: GmailUpdate[];
  onRefresh: () => void;
  onNotice: (message: string) => void;
  onSyncGmail: () => Promise<GmailSyncResult>;
}

const FILTERS: Array<{ value: string; label: string }> = [
  { value: "all", label: "Todos" },
  { value: "enviado", label: "Enviados" },
  { value: "espera_respuesta", label: "Espera de respuesta" },
  { value: "respondido", label: "Respondidos" },
  { value: "novedad_detectada", label: "Novedades" },
  { value: "pending_approval", label: "Pendientes de aprobación" },
  { value: "cerrado", label: "Cerrados" },
];

function labelOrMissing(value: string | null | undefined): string {
  return value && value.trim() ? value : "No figura en la fuente";
}

function isControlDraft(record: OutreachRecord): boolean {
  const notes = record.notes ?? "";
  return (
    record.recipient === "caldubeheregabriel@gmail.com" &&
    (notes.includes("CORREO_CONTROL_OFICINA1") || notes.includes("ALERTA_RESPUESTA_GMAIL"))
  );
}

export function OutreachPanel({
  token,
  records,
  schemaReason,
  gmailStatus,
  gmailUpdates,
  onRefresh,
  onNotice,
  onSyncGmail,
}: OutreachPanelProps) {
  const [filter, setFilter] = useState("all");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [messageIds, setMessageIds] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const visible = filter === "all" ? records : records.filter((record) => record.status === filter);

  const handleSync = async () => {
    setSyncing(true);
    setError(null);
    try {
      const result = await onSyncGmail();
      onRefresh();
      onNotice(
        result.checked
          ? `Gmail revisado: ${result.updates.length} novedades.`
          : result.reason ?? "No se pudo revisar Gmail.",
      );
    } catch (syncError) {
      setError(syncError instanceof Error ? syncError.message : "No se pudo sincronizar Gmail.");
    } finally {
      setSyncing(false);
    }
  };

  const handleStatus = async (record: OutreachRecord, status: OutreachStatus) => {
    setBusyId(record.id);
    setError(null);
    try {
      await updateOutreachStatusApi(token, record.id, status);
      onRefresh();
      onNotice(`Seguimiento actualizado: ${STATUS_LABELS[status] ?? status}.`);
    } catch (statusError) {
      setError(statusError instanceof Error ? statusError.message : "No se pudo actualizar el estado.");
    } finally {
      setBusyId(null);
    }
  };

  const handleRegister = async (record: OutreachRecord) => {
    const messageId = (messageIds[record.id] ?? "").trim();
    if (!messageId) {
      setError("Pegá el ID del mensaje ya enviado desde la cuenta autorizada.");
      return;
    }
    const label = record.category === "job_application" ? "Postulaciones" : "Clientes";
    setBusyId(record.id);
    setError(null);
    try {
      const result = await registerGmailSentAction(token, {
        outreach_id: record.id,
        gmail_message_id: messageId,
        label,
      });
      if (result.external_action === "none") {
        setError(result.error ?? "No se pudo registrar el mensaje en Gmail.");
        return;
      }
      onRefresh();
      onNotice(`Mensaje etiquetado como ${label} y seguimiento actualizado.`);
    } catch (registerError) {
      setError(registerError instanceof Error ? registerError.message : "No se pudo registrar en Gmail.");
    } finally {
      setBusyId(null);
    }
  };

  const handleCreateDraft = async (record: OutreachRecord) => {
    const confirmed = window.confirm(
      `¿Crear un borrador en Gmail para ${record.recipient}? No se enviará nada automáticamente.`,
    );
    if (!confirmed) return;
    setBusyId(record.id);
    setError(null);
    try {
      const result = await createGmailControlDraft(token, record.id);
      onNotice(
        `Borrador creado (${result.draft_id || "id no informado"}) con ${
          result.attachments?.length ?? 0
        } adjunto(s). Revisá y enviá manualmente desde Gmail.`,
      );
    } catch (draftError) {
      setError(draftError instanceof Error ? draftError.message : "No se pudo crear el borrador.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section id="seguimiento" className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-white">Enviados y Seguimiento</h2>
          <p className="text-xs text-slate-400">
            Postulaciones y propuestas aprobadas, con estado verificable y sin respuesta automática.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] ${
              gmailStatus?.enabled
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                : "border-slate-700 bg-slate-800 text-slate-400"
            }`}
          >
            <Mail className="h-3.5 w-3.5" />
            {gmailStatus?.enabled ? `Gmail: ${gmailStatus.account}` : "Gmail sin conexión"}
          </span>
          <button
            type="button"
            onClick={() => void handleSync()}
            disabled={syncing}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-[11px] text-slate-200 hover:bg-slate-700 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} /> Revisar respuestas
          </button>
        </div>
      </div>

      {schemaReason && (
        <p className="mb-3 flex items-start gap-1.5 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-200">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{schemaReason}</span>
        </p>
      )}

      {gmailStatus?.reason && (
        <p className="mb-3 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-200">
          {gmailStatus.reason}
        </p>
      )}

      {gmailUpdates.length > 0 && (
        <div className="mb-3 rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-[11px] text-sky-100">
          <p className="flex items-center gap-1.5 font-semibold">
            <MessageSquare className="h-3.5 w-3.5" /> Sara detectó {gmailUpdates.length} mensaje
            {gmailUpdates.length === 1 ? "" : "s"} nuevo{gmailUpdates.length === 1 ? "" : "s"} en Gmail.
          </p>
          <ul className="mt-1 space-y-0.5">
            {gmailUpdates.slice(0, 5).map((update) => (
              <li key={update.gmail_message_id} className="space-y-0.5">
                <p className="truncate">
                  [{update.gmail_label}] {update.from || "Remitente no informado"} — {update.subject || "Sin asunto"}
                </p>
                {update.suggested_action && (
                  <p className="truncate pl-2 text-sky-200/70">
                    {STATUS_LABELS[update.response_status ?? ""] ?? "Novedad"}: {update.suggested_action}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && (
        <p className="mb-3 flex items-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-200">
          <AlertTriangle className="h-3.5 w-3.5" /> {error}
        </p>
      )}

      <div className="mb-3 flex flex-wrap gap-1.5">
        {FILTERS.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => setFilter(option.value)}
            className={`rounded-full border px-2.5 py-1 text-[11px] ${
              filter === option.value
                ? "border-indigo-400/60 bg-indigo-500/20 text-indigo-100"
                : "border-slate-700 bg-slate-800 text-slate-400 hover:text-slate-200"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-700 p-5 text-center text-xs text-slate-500">
          Todavía no hay registros en este estado. Aprobá un entregable para preparar la trazabilidad.
        </p>
      ) : (
        <div className="space-y-3">
          {visible.map((record) => (
            <article key={record.id} className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold text-slate-100">{record.title}</h3>
                  <p className="mt-0.5 text-[11px] text-slate-400">
                    {record.agent_id === "mateo" ? "Mateo" : "Valeria"} · {labelOrMissing(record.company_or_client_name)}
                  </p>
                </div>
                <span className="rounded-full bg-slate-800 px-2.5 py-1 text-[10px] uppercase tracking-wide text-slate-300">
                  {STATUS_LABELS[record.status] ?? record.status}
                </span>
              </div>

              {isControlDraft(record) && (
                <div className="mt-2 rounded-lg border border-indigo-500/30 bg-indigo-500/10 p-2.5 text-[11px] text-indigo-100">
                  <p className="flex items-center gap-1.5 font-medium">
                    <PenLine className="h-3.5 w-3.5" /> Borrador de correo de control para el dueño de la cuenta
                  </p>
                  <p className="mt-1 text-indigo-200/80">
                    Preparado con trazabilidad real; pendiente de aprobación y sin envío automático.
                  </p>
                  {record.draft_attachments && record.draft_attachments.length > 0 && (
                    <ul className="mt-1 space-y-0.5">
                      {record.draft_attachments.map((attachment) => (
                        <li key={attachment.name} className="flex items-center gap-1.5 truncate">
                          <Paperclip className="h-3 w-3" />
                          {attachment.name} · {attachment.mime_type} · {attachment.size_bytes} bytes
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                <span className="rounded-md bg-slate-800 px-2 py-0.5 text-slate-300">
                  Plataforma: {labelOrMissing(record.source_platform)}
                </span>
                <span className="rounded-md bg-slate-800 px-2 py-0.5 text-slate-300">
                  Canal: {labelOrMissing(record.contact_channel)}
                </span>
                <span className="rounded-md bg-slate-800 px-2 py-0.5 text-slate-300">
                  Contacto: {labelOrMissing(record.contact_ref)}
                </span>
                {record.hourly_rate_usd != null && (
                  <span className="rounded-md bg-emerald-500/10 px-2 py-0.5 text-emerald-200">
                    {record.hourly_rate_usd} USD/hora
                  </span>
                )}
              </div>

              {record.contact_ref_pending && (
                <p className="mt-2 flex items-center gap-1.5 text-[11px] text-amber-300">
                  <AlertTriangle className="h-3.5 w-3.5" /> No figura en la fuente: no se inventó correo ni contacto.
                </p>
              )}

              {record.source_url && (
                <a
                  href={record.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-flex items-center gap-1 text-[11px] text-sky-300 hover:text-sky-200"
                >
                  <ExternalLink className="h-3.5 w-3.5" /> Fuente verificable
                </a>
              )}

              {record.cv_reference && (
                <p className="mt-1 text-[11px] text-slate-400">CV/perfil usado: {record.cv_reference}</p>
              )}

              <details className="mt-2 rounded-lg border border-slate-800 bg-slate-900/70 p-2.5">
                <summary className="cursor-pointer text-[11px] font-medium text-slate-300">
                  {isControlDraft(record) ? "Correo de control preparado (no enviado)" : "Texto preparado / enviado"}
                </summary>
                <p className="mt-2 whitespace-pre-line text-[11px] leading-relaxed text-slate-400">
                  {record.full_text || record.summary || "Sin texto cargado."}
                </p>
              </details>

              {record.gmail_label && (
                <p className="mt-2 flex items-center gap-1.5 text-[11px] text-sky-300">
                  <Mail className="h-3.5 w-3.5" /> Etiqueta Gmail: {record.gmail_label}
                  {record.gmail_thread_id ? ` · Hilo ${record.gmail_thread_id.slice(0, 10)}…` : ""}
                </p>
              )}

              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-800 pt-3">
                <select
                  value={record.status}
                  onChange={(event) => void handleStatus(record, event.target.value as OutreachStatus)}
                  disabled={busyId === record.id}
                  className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1.5 text-[11px] text-slate-200 disabled:opacity-50"
                >
                  {FILTERS.filter((option) => option.value !== "all").map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                  <option value="approved">Aprobado</option>
                  <option value="rejected">Rechazado</option>
                </select>
                <input
                  value={messageIds[record.id] ?? ""}
                  onChange={(event) => setMessageIds((prev) => ({ ...prev, [record.id]: event.target.value }))}
                  placeholder="ID de mensaje ya enviado"
                  className="min-w-44 flex-1 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-[11px] text-slate-200 placeholder:text-slate-600"
                />
                <button
                  type="button"
                  disabled={busyId === record.id}
                  onClick={() => void handleRegister(record)}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-sky-600 px-2.5 py-1.5 text-[11px] font-medium text-white hover:bg-sky-500 disabled:opacity-50"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" /> Registrar en Gmail
                </button>
                {isControlDraft(record) && (
                  <button
                    type="button"
                    disabled={busyId === record.id}
                    onClick={() => void handleCreateDraft(record)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-500/40 bg-indigo-500/10 px-2.5 py-1.5 text-[11px] font-medium text-indigo-100 hover:bg-indigo-500/20 disabled:opacity-50"
                  >
                    <PenLine className="h-3.5 w-3.5" /> Crear borrador en Gmail
                  </button>
                )}
                {record.status === "cerrado" && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
                    <Archive className="h-3.5 w-3.5" /> Cerrado
                  </span>
                )}
                {record.status === "espera_respuesta" && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-amber-300">
                    <Clock3 className="h-3.5 w-3.5" /> Esperando respuesta
                  </span>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      <p className="mt-3 text-[10px] text-slate-500">
        Sara solo lee, etiqueta y registra acciones humanas. No borra, no marca spam, no cambia configuración y no responde sola.
      </p>
    </section>
  );
}
