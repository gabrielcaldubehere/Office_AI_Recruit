import { ArrowUpRight, Clock3, X } from "lucide-react";
import { STATUS_LABELS } from "../lib/agentStatus";
import { AgentAvatar } from "./AgentAvatar";
import type { AgentStateItem } from "../types/office";

interface AgentSidebarProps {
  agent: AgentStateItem | null;
  activity: AgentStateItem["activity"];
  isOpen: boolean;
  onClose: () => void;
  onQuickAction: (agentId: string) => void;
  canOperate: boolean;
}

function formatTime(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });
}

export function AgentSidebar({
  agent,
  activity,
  isOpen,
  onClose,
  onQuickAction,
  canOperate,
}: AgentSidebarProps) {
  if (!isOpen || !agent) return null;

  const status = agent.status || "idle";
  const statusLabel = STATUS_LABELS[status] ?? status;
  const quickActions: Record<string, { label: string; target: string }> = {
    sara: { label: "Ver reportes listos", target: "reportes" },
    mateo: { label: "Ver vacantes y coincidencias", target: "aprobaciones" },
    valeria: { label: "Ver propuestas y variantes", target: "aprobaciones" },
    luciano: { label: "Abrir escritorio de Luciano", target: "escritorio-luciano" },
  };
  const action = quickActions[agent.agent_id];

  return (
    <aside className="fixed inset-0 z-40 flex justify-end bg-slate-950/60 lg:static lg:z-auto lg:bg-transparent" aria-label={`Panel de ${agent.display_name ?? agent.agent_id}`}>
      <button type="button" aria-label="Cerrar panel" onClick={onClose} className="absolute inset-0 lg:hidden" />
      <div className="relative flex h-full w-full max-w-sm flex-col gap-4 overflow-y-auto border-l border-slate-800 bg-slate-900 p-5 shadow-2xl lg:h-auto lg:rounded-2xl lg:shadow-none">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <AgentAvatar agentId={agent.agent_id} size="lg" status={status} />
            <div>
              <h2 className="text-lg font-semibold text-white">{agent.display_name ?? agent.agent_id}</h2>
              <p className="text-xs text-slate-400">{agent.role ?? "Agente de la oficina"}</p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white" aria-label="Cerrar">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3.5">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Estado actual</p>
          <p className="mt-1 text-sm font-medium text-slate-100">{statusLabel}</p>
          <p className="mt-2 text-xs leading-relaxed text-slate-300">
            {agent.current_task || "Listo en su puesto de trabajo"}
          </p>
        </div>

        <div>
          <div className="mb-2 flex items-center gap-2">
            <Clock3 className="h-4 w-4 text-slate-500" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Actividad reciente</h3>
          </div>
          {activity && activity.length > 0 ? (
            <ul className="space-y-2">
              {activity.map((entry, index) => (
                <li key={`${entry.at ?? index}-${entry.action}`} className="rounded-lg border border-slate-800 bg-slate-950/60 p-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-medium text-slate-200">{entry.action}</p>
                    <span className="text-[10px] text-slate-500">{formatTime(entry.at)}</span>
                  </div>
                  {entry.details && <p className="mt-1 text-[11px] leading-relaxed text-slate-400">{entry.details}</p>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="rounded-lg border border-dashed border-slate-700 p-3 text-xs text-slate-500">
              Sin actividad registrada en las últimas ejecuciones.
            </p>
          )}
        </div>

        {action && (
          <button
            type="button"
            onClick={() => onQuickAction(action.target)}
            className="mt-auto inline-flex items-center justify-between gap-2 rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-3.5 py-2.5 text-xs font-medium text-indigo-200 hover:bg-indigo-500/20"
          >
            {action.label}
            <ArrowUpRight className="h-4 w-4" />
          </button>
        )}
        {!canOperate && agent.agent_id === "luciano" && (
          <p className="text-[11px] text-slate-500">Iniciá sesión para usar su escritorio completo.</p>
        )}
      </div>
    </aside>
  );
}
