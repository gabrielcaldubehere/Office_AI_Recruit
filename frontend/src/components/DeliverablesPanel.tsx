import { AlertTriangle, BadgeCheck, Briefcase, Clock3, ExternalLink, FileText, Send, Target, Wallet } from "lucide-react";
import { STATUS_LABELS } from "../lib/agentStatus";
import type { DeliverableItem, DeliverableContent, MatchArgument } from "../types/office";

interface DeliverablesPanelProps {
  items: DeliverableItem[];
  busyId: string | null;
  canOperate: boolean;
  onReview: (id: string, decision: "approved" | "rejected") => void;
  onRequireLogin: () => void;
}

function contentOf(item: DeliverableItem): DeliverableContent {
  return { ...(item.content_json ?? {}), ...(item.content ?? {}) };
}

function scoreOf(content: DeliverableContent, item: DeliverableItem): number | null {
  const raw = content.match_probability ?? content.fit_score ?? item.match_probability ?? item.fit_score;
  return typeof raw === "number" ? raw : null;
}

function ScoreBar({ value, label }: { value: number; label: string }) {
  const tone = value >= 75 ? "bg-emerald-400" : value >= 50 ? "bg-amber-400" : "bg-rose-400";
  return (
    <div className="min-w-40 flex-1">
      <div className="mb-1 flex items-center justify-between text-[11px] text-slate-400">
        <span>{label}</span>
        <span className="font-semibold text-slate-200">{value}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
    </div>
  );
}

function StringList({ title, values }: { title: string; values: string[] }) {
  if (values.length === 0) return null;
  return (
    <div>
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">{title}</p>
      <ul className="list-disc space-y-0.5 pl-4 text-xs leading-relaxed text-slate-300">
        {values.map((value, index) => (
          <li key={index}>{value}</li>
        ))}
      </ul>
    </div>
  );
}

function asStrings(values: DeliverableContent["match_arguments"]): string[] {
  if (!Array.isArray(values)) return [];
  return values.map((entry) => {
    if (typeof entry === "string") return entry;
    const arg = entry as MatchArgument;
    return arg.detail ? `${arg.label}: ${arg.detail}` : arg.label ?? "";
  }).filter(Boolean);
}

export function DeliverablesPanel({
  items,
  busyId,
  canOperate,
  onReview,
  onRequireLogin,
}: DeliverablesPanelProps) {
  return (
    <section id="aprobaciones" className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-white">Bandeja de aprobación</h2>
          <p className="text-xs text-slate-400">
            {items.length} ítem{items.length === 1 ? "" : "s"} listo{items.length === 1 ? "" : "s"} para revisión humana.
          </p>
        </div>
        {!canOperate && (
          <span className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-[11px] text-slate-400">
            Solo lectura · iniciá sesión para aprobar
          </span>
        )}
      </div>

      {items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-700 p-6 text-center text-xs text-slate-500">
          No hay entregables pendientes. Sara avisará cuando haya reportes listos.
        </p>
      ) : (
        <div className="space-y-3">
          {items.map((item) => {
            const content = contentOf(item);
            const isJob = item.category === "job_application" || item.category === "job";
            const score = scoreOf(content, item);
            const variants = content.outreach_variants ?? [];
            return (
              <article key={item.id} className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <div className={`rounded-lg p-2 ${isJob ? "bg-emerald-500/10 text-emerald-300" : "bg-amber-500/10 text-amber-300"}`}>
                      {isJob ? <Briefcase className="h-4 w-4" /> : <Target className="h-4 w-4" />}
                    </div>
                    <div className="min-w-0">
                      <h3 className="text-sm font-semibold text-slate-100">{item.title ?? "Entregable"}</h3>
                      <p className="truncate text-[11px] text-slate-500">
                        {item.traceability?.source_platform || content.source_platform || item.source || "No figura en la fuente"}
                      </p>
                    </div>
                  </div>
                  <span className="rounded-lg bg-slate-800 px-2 py-1 text-[10px] uppercase tracking-wide text-slate-400">
                    {isJob ? "Mateo" : "Valeria"}
                  </span>
                </div>

                <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                  <span className="rounded-md bg-slate-800 px-2 py-0.5 text-slate-300">
                    Empresa/cliente: {item.traceability?.company_or_client_name || content.company_or_client_name || "No figura en la fuente"}
                  </span>
                  <span className="rounded-md bg-slate-800 px-2 py-0.5 text-slate-300">
                    Contacto: {item.traceability?.contact_ref || content.contact_ref || "No figura en la fuente"}
                  </span>
                  {content.complexity && (
                    <span className="rounded-md bg-indigo-500/10 px-2 py-0.5 text-indigo-200">
                      Complejidad: {content.complexity}
                    </span>
                  )}
                  {content.estimated_hours_per_day && (
                    <span className="rounded-md bg-slate-800 px-2 py-0.5 text-slate-300">
                      {content.estimated_hours_per_day}
                    </span>
                  )}
                  {content.estimated_timeline && (
                    <span className="rounded-md bg-slate-800 px-2 py-0.5 text-slate-300">
                      Plazo: {content.estimated_timeline}
                    </span>
                  )}
                </div>

                {(item.traceability?.contact_pending || content.contact_pending) && (
                  <p className="mt-2 flex items-center gap-1.5 text-[10px] text-amber-300">
                    <AlertTriangle className="h-3 w-3" /> Sin datos de contacto verificados; queda pendiente de revisión humana.
                  </p>
                )}

                {(item.traceability?.source_url || content.source_url) && (
                  <a
                    href={item.traceability?.source_url || content.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-flex items-center gap-1 text-[10px] text-sky-300 hover:text-sky-200"
                  >
                    <ExternalLink className="h-3 w-3" /> Fuente verificable
                  </a>
                )}

                {(score !== null || content.hourly_rate_usd) && (
                  <div className="mt-3 flex flex-wrap items-center gap-4">
                    {score !== null && <ScoreBar value={score} label="Probabilidad de coincidencia" />}
                    {content.hourly_rate_usd != null && (
                      <div className="flex items-center gap-1.5 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1.5 text-xs text-emerald-200">
                        <Wallet className="h-3.5 w-3.5" />
                        {content.hourly_rate_usd} USD/hora
                      </div>
                    )}
                  </div>
                )}

                <p className="mt-3 text-xs leading-relaxed text-slate-300">
                  {item.summary || content.tailored_summary || content.proposed_solution || "Sin resumen cargado."}
                </p>

                <StringList title="Por qué destacar (datos verificados)" values={asStrings(content.match_arguments)} />
                {isJob && <StringList title="Brechas detectadas" values={content.gaps ?? []} />}
                {!isJob && <StringList title="Faltante por confirmar" values={content.missing_info ?? []} />}
                {content.rate_justification && (
                  <p className="mt-2 text-[11px] text-slate-400">
                    <strong className="text-slate-300">Tarifa:</strong> {content.rate_justification}
                  </p>
                )}

                {(content.delivery_modalities?.length ?? 0) > 0 && (
                  <details className="mt-2 rounded-lg border border-slate-800 bg-slate-900/70 p-2.5">
                    <summary className="cursor-pointer text-[11px] font-medium text-slate-300">
                      2 modelos de entrega (sin compromiso automático)
                    </summary>
                    <ul className="mt-2 space-y-1.5">
                      {(content.delivery_modalities ?? []).map((modality, index) => (
                        <li key={index} className="text-[11px] leading-relaxed text-slate-400">
                          <strong className="text-slate-200">{modality.model}:</strong> {modality.description}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}

                {content.preview_policy && (
                  <p className="mt-2 text-[10px] text-slate-500">Previsualizaciones: {content.preview_policy}</p>
                )}
                {content.detailed_budget_note && (
                  <p className="mt-1 text-[10px] text-slate-500">Presupuesto detallado: {content.detailed_budget_note}</p>
                )}

                {variants.length > 0 && (
                  <div className="mt-3 space-y-2">
                    <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                      <Send className="h-3.5 w-3.5" /> 3 variantes de presentación
                    </p>
                    {variants.map((variant, index) => (
                      <details key={index} className="rounded-lg border border-slate-800 bg-slate-900/70 p-2.5">
                        <summary className="cursor-pointer text-xs font-medium text-sky-300">{variant.subject || `Variante ${index + 1}`}</summary>
                        <p className="mt-2 whitespace-pre-line text-[11px] leading-relaxed text-slate-300">{variant.body}</p>
                      </details>
                    ))}
                  </div>
                )}

                <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-800 pt-3">
                  <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
                    <Clock3 className="h-3.5 w-3.5" /> {STATUS_LABELS.waiting_approval}
                  </span>
                  <div className="flex gap-2">
                    {canOperate ? (
                      <>
                        <button
                          type="button"
                          disabled={busyId === item.id}
                          onClick={() => onReview(item.id, "rejected")}
                          className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-200 hover:bg-rose-500/20 disabled:opacity-50"
                        >
                          Rechazar
                        </button>
                        <button
                          type="button"
                          disabled={busyId === item.id}
                          onClick={() => onReview(item.id, "approved")}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                        >
                          <BadgeCheck className="h-3.5 w-3.5" /> Aprobar y preparar
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        onClick={onRequireLogin}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-3 py-1.5 text-xs font-medium text-indigo-200 hover:bg-indigo-500/20"
                      >
                        <FileText className="h-3.5 w-3.5" /> Iniciá sesión para revisar
                      </button>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
