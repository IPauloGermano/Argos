"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "../../../lib/api";

export default function JobDetail({ params }: { params: { id: string } }) {
  const [job, setJob] = useState<any>(null);
  const [isFavorite, setIsFavorite] = useState(false);
  const [feedback, setFeedback] = useState<"pos" | "neg" | null>(null);
  const [loading, setLoading] = useState(true);
  const [feedbackMsg, setFeedbackMsg] = useState("");

  useEffect(() => {
    Promise.all([
      api.get(`/api/jobs/${params.id}`).catch(() => null),
      api.getFavorites().catch(() => []),
      api.getFeedback(Number(params.id)).catch(() => null),
    ])
      .then(([jobData, favsData, fbData]) => {
        setJob(jobData);
        const isFav = (favsData || []).some((f: any) => f.job_id === Number(params.id));
        setIsFavorite(isFav);
        const fbObj = fbData?.feedback ?? fbData;
        if (fbObj && typeof fbObj.is_positive === "boolean") {
          setFeedback(fbObj.is_positive ? "pos" : "neg");
        }
      })
      .finally(() => setLoading(false));
  }, [params.id]);

  const toggleFavorite = async () => {
    const nextState = !isFavorite;
    setIsFavorite(nextState);
    try {
      if (nextState) {
        await api.addFavorite(Number(params.id));
        setFeedbackMsg("⭐ Vaga salva nos seus favoritos!");
      } else {
        await api.removeFavorite(Number(params.id));
        setFeedbackMsg("Vaga removida dos favoritos.");
      }
      setTimeout(() => setFeedbackMsg(""), 3000);
    } catch (e) {
      console.error(e);
      setIsFavorite(!nextState);
    }
  };

  const handleFeedback = async (isPos: boolean) => {
    const target = isPos ? "pos" : "neg";
    setFeedback(target);
    try {
      await api.sendFeedback(Number(params.id), isPos);
      setFeedbackMsg(
        isPos
          ? "👍 Obrigado! Suas recomendações futuras priorizarão vagas similares."
          : "👎 Entendido. Vamos diminuir vagas semelhantes nas próximas buscas."
      );
      setTimeout(() => setFeedbackMsg(""), 4000);
    } catch (e) {
      console.error(e);
    }
  };

  if (loading) {
    return (
      <div className="surface-panel text-center py-16 text-zinc-400 text-sm">
        <div className="inline-block animate-spin h-6 w-6 border-2 border-brand-500 border-t-transparent rounded-full mb-3" aria-hidden="true"></div>
        <p>Carregando detalhes da oportunidade...</p>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="surface-panel text-center py-16">
        <span className="text-3xl mb-2 block" aria-hidden="true">🔍</span>
        <p className="text-zinc-200 font-semibold text-base">Vaga não encontrada</p>
        <p className="text-xs text-zinc-400 mt-1 mb-4">Esta vaga pode ter sido encerrada ou removida.</p>
        <Link href="/jobs" className="btn-primary inline-flex text-xs py-2 px-4 min-h-[44px]">
          Voltar para o catálogo de vagas
        </Link>
      </div>
    );
  }

  const score = job.score;
  const isHighMatch = score != null && score >= 75;

  return (
    <div className="space-y-6">
      {/* Botão Voltar */}
      <div>
        <Link
          href="/jobs"
          className="text-xs text-zinc-400 hover:text-zinc-200 inline-flex items-center gap-1.5 py-1.5 transition-colors font-medium min-h-[36px]"
        >
          <span>←</span>
          <span>Voltar para todas as vagas</span>
        </Link>
      </div>

      {feedbackMsg && (
        <div className="p-3 rounded-lg bg-surface-elevated border border-brand-500/30 text-xs text-zinc-200 animate-fadeIn">
          {feedbackMsg}
        </div>
      )}

      {/* Header Principal da Vaga */}
      <div className="surface-panel p-5 sm:p-6 space-y-4 rounded-xl">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              {job.source && (
                <span className="uppercase tracking-wider text-xs text-zinc-300 bg-surface-elevated px-2.5 py-1 rounded border border-surface-border font-medium">
                  Via {job.source}
                </span>
              )}
              {job.work_mode && (
                <span className="badge-emerald text-xs">
                  {job.work_mode.toLowerCase() === "remote" || job.work_mode.toLowerCase() === "remoto"
                    ? "🌐 100% Remoto"
                    : job.work_mode.toLowerCase() === "hybrid" || job.work_mode.toLowerCase() === "hibrido"
                    ? "🏢 Híbrido"
                    : `📍 ${job.work_mode}`}
                </span>
              )}
              {job.employment_type && (
                <span className="badge-indigo text-xs">
                  💼 {job.employment_type.toUpperCase()}
                </span>
              )}
            </div>

            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
              {job.title}
            </h1>
            <p className="text-sm text-zinc-300 font-semibold mt-1">
              {job.company || "Empresa Confidencial"}{" "}
              <span className="text-zinc-500 font-normal">·</span>{" "}
              <span className="font-normal text-zinc-400">{job.location || "Brasil"}</span>
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {/* Botão de Favoritar */}
            <button
              type="button"
              onClick={toggleFavorite}
              className={`p-2.5 rounded-lg border transition-all min-h-[44px] min-w-[44px] flex items-center justify-center ${
                isFavorite
                  ? "bg-amber-500/20 border-amber-500/50 text-amber-300 shadow-sm"
                  : "bg-surface-elevated border-surface-border text-zinc-400 hover:text-amber-300"
              }`}
              title={isFavorite ? "Remover dos favoritos" : "Salvar nos favoritos"}
              aria-label={isFavorite ? "Remover dos favoritos" : "Salvar nos favoritos"}
            >
              <span className="text-base" aria-hidden="true">{isFavorite ? "⭐" : "☆"}</span>
            </button>

            {score != null && (
              <div
                className={`p-3 rounded-xl text-center border shrink-0 ${
                  isHighMatch
                    ? "bg-emerald-950/40 border-emerald-500/40 text-emerald-300"
                    : "bg-surface-elevated border-surface-border text-zinc-200"
                }`}
              >
                <span className="text-2xl sm:text-3xl font-bold block leading-none">{score}%</span>
                <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400 mt-1 block">
                  Match
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Linha de Sub-scores Explicativos */}
        {job.scores && Object.keys(job.scores).length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-3 border-t border-surface-border/70">
            {Object.entries(job.scores).map(([k, v]) => {
              const label =
                k === "role"
                  ? "Cargo & Título"
                  : k === "skills"
                  ? "Habilidades"
                  : k === "experience"
                  ? "Experiência"
                  : k === "location"
                  ? "Localização"
                  : k;
              return (
                <div key={k} className="p-2.5 rounded-lg bg-surface-elevated text-center">
                  <span className="text-xs text-zinc-400 uppercase tracking-wider block mb-0.5">
                    {label}
                  </span>
                  <span className="text-sm font-bold text-white">{String(v)}%</span>
                </div>
              );
            })}
          </div>
        )}

        {/* Barra de Ações: Candidatar-se na Fonte e Feedback */}
        <div className="pt-3 border-t border-surface-border flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          {job.url ? (
            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary w-full sm:w-auto text-center py-2.5 px-6 text-sm min-h-[44px] shadow-sm"
              aria-label={`Abrir página oficial de candidatura para ${job.title}`}
            >
              <span>🔗 Candidatar-se na Fonte Oficial</span>
              <span aria-hidden="true">↗</span>
            </a>
          ) : (
            <span className="text-xs text-zinc-500">Link direto não informado pela fonte</span>
          )}

          {/* Calibração de Relevância */}
          <div className="flex items-center gap-2 self-start sm:self-center">
            <span className="text-xs text-zinc-400">Esta vaga combina com você?</span>
            <button
              type="button"
              onClick={() => handleFeedback(true)}
              className={`py-1.5 px-3 rounded-lg border text-xs font-semibold transition-all min-h-[36px] flex items-center gap-1.5 ${
                feedback === "pos"
                  ? "bg-emerald-500/20 border-emerald-500 text-emerald-300"
                  : "bg-surface-elevated border-surface-border text-zinc-400 hover:text-zinc-200"
              }`}
              title="Vaga relevante (calibra algoritmo)"
            >
              <span>👍 Sim</span>
            </button>
            <button
              type="button"
              onClick={() => handleFeedback(false)}
              className={`py-1.5 px-3 rounded-lg border text-xs font-semibold transition-all min-h-[36px] flex items-center gap-1.5 ${
                feedback === "neg"
                  ? "bg-rose-500/20 border-rose-500 text-rose-300"
                  : "bg-surface-elevated border-surface-border text-zinc-400 hover:text-zinc-200"
              }`}
              title="Não relevante"
            >
              <span>👎 Não</span>
            </button>
          </div>
        </div>
      </div>

      {/* Motivos da Compatibilidade */}
      {job.reasoning && job.reasoning.length > 0 && (
        <div className="surface-panel p-5 space-y-2 rounded-xl">
          <h2 className="text-sm font-bold text-white flex items-center gap-2">
            <span aria-hidden="true">💡</span>
            <span>Por que esta vaga combina com seu perfil</span>
          </h2>
          <div className="space-y-2 pt-1">
            {job.reasoning.map((r: string, i: number) => (
              <p key={i} className="text-xs text-zinc-300 flex items-start gap-2 leading-relaxed">
                <span className="text-emerald-400 font-bold shrink-0 text-emerald-400" aria-hidden="true">✓</span>
                <span>{r}</span>
              </p>
            ))}
          </div>
        </div>
      )}

      {/* Histórico de Alterações da Vaga */}
      {job.changelog && job.changelog.length > 0 && (
        <div className="surface-panel p-5 space-y-2 rounded-xl">
          <h2 className="text-sm font-bold text-white flex items-center gap-2">
            <span aria-hidden="true">📝</span>
            <span>Alterações Detectadas nesta Oportunidade</span>
          </h2>
          <div className="space-y-2 pt-1">
            {job.changelog.map((chg: any, i: number) => (
              <div
                key={i}
                className="text-xs p-2.5 rounded bg-surface-elevated border border-surface-border"
              >
                <span className="font-semibold text-brand-300 block mb-0.5">
                  {chg.change_type}
                </span>
                <p className="text-zinc-400">
                  Campo <b>{chg.field_name}</b> alterado de{" "}
                  <span className="line-through text-rose-400">{chg.old_value}</span> para{" "}
                  <span className="text-emerald-400 font-semibold">{chg.new_value}</span>.
                </p>
                {chg.created_at && (
                  <span className="text-xs text-zinc-500 block mt-1">
                    Registrado em {new Date(chg.created_at).toLocaleString("pt-BR")}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Descrição Completa da Vaga */}
      <div className="surface-panel p-5 space-y-3 rounded-xl">
        <h2 className="text-sm font-bold text-white">Descrição Completa da Oportunidade</h2>
        <div className="text-xs sm:text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap font-sans bg-surface-elevated/40 p-4 rounded-lg border border-surface-border">
          {job.description}
        </div>

        {/* Segundo CTA ao final da leitura */}
        {job.url && (
          <div className="pt-3 border-t border-surface-border flex justify-end">
            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary text-xs py-2.5 px-5 min-h-[44px]"
            >
              <span>Candidatar-se na Fonte Oficial ↗</span>
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
