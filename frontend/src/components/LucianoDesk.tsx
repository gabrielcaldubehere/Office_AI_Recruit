import { useState } from "react";
import { GraduationCap, Send } from "lucide-react";
import { runLucianoSessionApi } from "../services/api";
import type { LucianoSessionResponse, MentorMode } from "../types/office";

interface LucianoDeskProps {
  token: string | null;
  onRequireLogin: () => void;
}

const MODE_LABELS: { id: MentorMode; label: string }[] = [
  { id: "explain", label: "Conceptos / Código / Prompts" },
  { id: "quiz", label: "Examen Multiple Choice" },
  { id: "interview_prep", label: "Entrevistas & Pruebas" },
  { id: "client_negotiation", label: "Presupuestos & Cambios" },
];

export function LucianoDesk({ token, onRequireLogin }: LucianoDeskProps) {
  const [mode, setMode] = useState<MentorMode>("explain");
  const [topic, setTopic] = useState("");
  const [userContext, setUserContext] = useState("");
  const [numQuestions, setNumQuestions] = useState(5);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [result, setResult] = useState<LucianoSessionResponse | null>(null);
  const [selectedAnswers, setSelectedAnswers] = useState<Record<number, number>>({});

  const handleRun = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token) {
      onRequireLogin();
      return;
    }
    if (!topic.trim()) return;
    setLoading(true);
    setErrorMsg(null);
    setSelectedAnswers({});
    try {
      setResult(
        await runLucianoSessionApi(token, {
          mode,
          topic: topic.trim(),
          user_context: userContext.trim(),
          num_questions: numQuestions,
        }),
      );
    } catch (error) {
      setErrorMsg(error instanceof Error ? error.message : "Error al consultar con Luciano.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section id="escritorio-luciano" className="rounded-2xl border border-sky-500/25 bg-slate-900/90 p-5 shadow-lg">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <GraduationCap className="h-5 w-5 text-sky-400" />
          <div>
            <h3 className="text-base font-semibold">Escritorio de Luciano — Mentoría AI & Full Stack</h3>
            <p className="text-xs text-slate-400">
              Explicaciones, exámenes, entrevistas técnicas, presupuestos y defensa de cambios.
            </p>
          </div>
        </div>
        {!token && (
          <button
            type="button"
            onClick={onRequireLogin}
            className="rounded-xl bg-sky-600/20 px-3 py-1.5 text-xs font-medium text-sky-300 ring-1 ring-sky-500/40 hover:bg-sky-600/30"
          >
            Iniciá sesión para usar
          </button>
        )}
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {MODE_LABELS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            onClick={() => setMode(entry.id)}
            className={`rounded-xl px-3 py-1.5 text-xs font-medium transition ${
              mode === entry.id ? "bg-sky-600 text-white" : "bg-slate-800/80 text-slate-300 hover:bg-slate-800"
            }`}
          >
            {entry.label}
          </button>
        ))}
      </div>

      <form onSubmit={handleRun} className="space-y-3">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
          <input
            type="text"
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            placeholder="Ej: FastAPI + Supabase RLS, prompt JSON o defender un cambio de alcance..."
            className="rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-white outline-none focus:border-sky-500 md:col-span-3"
          />
          {mode === "quiz" ? (
            <select
              value={numQuestions}
              onChange={(event) => setNumQuestions(Number(event.target.value))}
              className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-sky-500"
            >
              {[3, 5, 8, 10].map((n) => (
                <option key={n} value={n}>{n} preguntas</option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              value={userContext}
              onChange={(event) => setUserContext(event.target.value)}
              placeholder="Contexto (opcional)"
              className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-sky-500"
            />
          )}
        </div>
        {mode === "quiz" && (
          <input
            type="text"
            value={userContext}
            onChange={(event) => setUserContext(event.target.value)}
            placeholder="Enfoque del examen (opcional)"
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2 text-sm text-white outline-none focus:border-sky-500"
          />
        )}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
            {loading ? "Luciano está preparando..." : "Iniciar sesión con Luciano"}
          </button>
        </div>
      </form>

      {errorMsg && (
        <p className="mt-3 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3.5 py-2 text-xs text-rose-300">{errorMsg}</p>
      )}

      {result?.session && (
        <div className="mt-5 space-y-4 rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
            <div>
              <h4 className="text-base font-semibold text-white">{result.session.title}</h4>
              <p className="text-xs text-slate-400">{result.session.summary}</p>
            </div>
            <span className="rounded-lg bg-slate-800 px-2.5 py-1 text-xs text-slate-300">
              {result.provider || "LLM"} · {result.tokens_used ?? 0} tokens
            </span>
          </div>
          <div className="whitespace-pre-line text-sm leading-relaxed text-slate-200">
            {result.session.explanation_or_guide}
          </div>
          {result.session.code_or_prompt_example && (
            <pre className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900 p-3.5 text-xs text-emerald-300">
              <code>{result.session.code_or_prompt_example}</code>
            </pre>
          )}
          {(result.session.quiz_questions?.length ?? 0) > 0 && (
            <div className="space-y-4 pt-2">
              <h5 className="text-sm font-semibold text-sky-300">Examen Multiple Choice</h5>
              {result.session.quiz_questions?.map((question, qIndex) => {
                const chosen = selectedAnswers[qIndex];
                const answered = chosen !== undefined;
                return (
                  <div key={qIndex} className="rounded-xl border border-slate-800 bg-slate-900/70 p-3.5">
                    <p className="mb-2.5 text-sm font-medium text-white">{qIndex + 1}. {question.question}</p>
                    <div className="space-y-1.5">
                      {question.options.map((option, oIndex) => {
                        let style = "border-slate-700 bg-slate-950 text-slate-200 hover:border-slate-500";
                        if (answered) {
                          if (question.correct_index === oIndex) style = "border-emerald-500 bg-emerald-500/15 text-emerald-200";
                          else if (chosen === oIndex) style = "border-rose-500 bg-rose-500/15 text-rose-200";
                        }
                        return (
                          <button
                            key={oIndex}
                            type="button"
                            onClick={() => setSelectedAnswers((prev) => ({ ...prev, [qIndex]: oIndex }))}
                            className={`w-full rounded-lg border px-3 py-2 text-left text-xs transition ${style}`}
                          >
                            {option}
                          </button>
                        );
                      })}
                    </div>
                    {answered && (
                      <p className="mt-2.5 rounded-lg bg-slate-950/90 p-2.5 text-xs text-slate-300">
                        <strong className="text-sky-300">Explicación:</strong> {question.explanation}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          {(result.session.communication_tips?.length ?? 0) > 0 && (
            <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-3">
              <p className="mb-1.5 text-xs font-semibold text-indigo-300">Claves para expresarte / negociar:</p>
              <ul className="list-disc space-y-1 pl-4 text-xs text-slate-300">
                {result.session.communication_tips?.map((tip, index) => <li key={index}>{tip}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
