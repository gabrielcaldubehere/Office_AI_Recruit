import { useState } from "react";
import { ExternalLink, Filter, LoaderCircle, Play } from "lucide-react";
import { collectSourcesApi } from "../services/api";
import type { SourceCollectResult } from "../types/office";

interface SourcePanelProps {
  token: string;
  onNotice: (message: string) => void;
  onEvaluated: () => void;
}

export function SourcePanel({ token, onNotice, onEvaluated }: SourcePanelProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<SourceCollectResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const collect = async (
    key: string,
    platform: "upwork" | "freelancer" | "remoteok" | "wwr" | "all",
    itemType: "client" | "job",
    evaluate: boolean,
  ) => {
    setBusy(key);
    setError(null);
    try {
      const response = await collectSourcesApi(token, {
        platform,
        item_type: itemType,
        upwork_limit: 10,
        freelancer_limit: 10,
        evaluate,
        market: itemType === "job" ? "GLOBAL_EN" : "LATAM_ES",
        min_fit_score: 60,
        max_items_per_batch: 25,
      });
      setResult(response);
      if (evaluate) onEvaluated();
      onNotice(
        `${response.platform}: ${response.fetched} fuentes, ${response.prefiltered_out} descartadas sin tokens` +
          (evaluate && response.batch
            ? `; ${response.batch.saved_for_approval} guardados para aprobación.`
            : ". Sin llamadas al LLM."),
      );
    } catch (collectError) {
      setError(collectError instanceof Error ? collectError.message : "No se pudo consultar la fuente.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <section id="fuentes" className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-white">Fuentes de empleo y clientes</h2>
          <p className="text-xs text-slate-400">
            Upwork, Freelancer, RemoteOK y We Work Remotely con pre-filtro local: antigüedad mayor a 15 días, senioridad y stack ajeno se descartan antes de gastar tokens.
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[11px] text-emerald-200">
          <Filter className="h-3.5 w-3.5" /> Sin tokens en el pre-filtro
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => void collect("upwork-clients", "upwork", "client", false)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-[11px] text-slate-200 hover:bg-slate-700 disabled:opacity-50"
        >
          <Play className="h-3.5 w-3.5" /> Vista previa Upwork
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => void collect("freelancer-clients", "freelancer", "client", false)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-[11px] text-slate-200 hover:bg-slate-700 disabled:opacity-50"
        >
          <Play className="h-3.5 w-3.5" /> Vista previa Freelancer
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => void collect("remoteok-jobs", "remoteok", "job", false)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-[11px] text-slate-200 hover:bg-slate-700 disabled:opacity-50"
        >
          <Play className="h-3.5 w-3.5" /> Vista previa RemoteOK
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => void collect("wwr-jobs", "wwr", "job", false)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-[11px] text-slate-200 hover:bg-slate-700 disabled:opacity-50"
        >
          <Play className="h-3.5 w-3.5" /> Vista previa We Work Remotely
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => void collect("all-jobs-evaluate", "all", "job", true)}
          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-[11px] font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          {busy === "all-jobs-evaluate" ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
          Evaluar empleos con Sara
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => void collect("all-clients-evaluate", "all", "client", true)}
          className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-2 text-[11px] font-medium text-white hover:bg-amber-500 disabled:opacity-50"
        >
          {busy === "all-clients-evaluate" ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
          Evaluar clientes con Valeria
        </button>
      </div>

      {error && (
        <p className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-200">
          {error}
        </p>
      )}

      {result && (
        <div className="mt-4 space-y-2">
          <p className="text-[11px] text-slate-400">
            {result.platform} · {result.fetched} ítems · {result.prefiltered_out} pre-filtrados sin LLM
          </p>
          {(result.notes ?? []).map((note, index) => (
            <p
              key={index}
              className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-2.5 py-1.5 text-[10px] text-amber-200"
            >
              {note}
            </p>
          ))}
          {result.items.slice(0, 8).map((item, index) => (
            <div key={`${item.source_url}-${index}`} className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
              <p className="text-xs font-medium text-slate-200">
                {item.title || item.company_or_client_name || "Oportunidad detectada"}
              </p>
              <p className="mt-0.5 text-[10px] text-slate-500">
                Fuente: {item.source_platform} · Empresa/cliente: {item.company_or_client_name}
              </p>
              {item.source_url && (
                <a
                  href={item.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-flex items-center gap-1 text-[10px] text-sky-300 hover:text-sky-200"
                >
                  <ExternalLink className="h-3 w-3" /> Ver publicación original
                </a>
              )}
            </div>
          ))}
          {result.items.length === 0 && (
            <p className="rounded-lg border border-dashed border-slate-700 p-4 text-center text-[11px] text-slate-500">
              No hay ítems que pasen el pre-filtro en esta corrida. No se gastaron tokens.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
