"use client";
import React, { useState } from "react";
import Link from "next/link";
import type { Job } from "../types";
import { api } from "../lib/api";

interface JobCardProps {
  job: Job;
  initialFavorite?: boolean;
  onFavoriteChange?: (jobId: number, isFav: boolean) => void;
  initialDismissed?: boolean;
  onDismissChange?: (jobId: number, isDismissed: boolean) => void;
}

export default function JobCard({
  job,
  initialFavorite = false,
  onFavoriteChange,
  initialDismissed = false,
  onDismissChange,
}: JobCardProps) {
  const [isFavorite, setIsFavorite] = useState(initialFavorite);
  const [isDismissed, setIsDismissed] = useState(job.is_dismissed || initialDismissed || false);
  const [dismissLoading, setDismissLoading] = useState(false);
  const [feedback, setFeedback] = useState<"pos" | "neg" | null>(null);
  const [feedbackLoading, setFeedbackLoading] = useState(false);

  const score = job.score;
  const isHighMatch = score != null && score >= 75;

  const isNew = job.discovered_at
    ? (Date.now() - new Date(job.discovered_at).getTime()) < 24 * 60 * 60 * 1000
    : false;

  const workMode = (job.work_mode || "").toLowerCase();
  const modeLabel =
    workMode === "remote" || workMode === "remoto"
      ? "🌐 Remoto"
      : workMode === "hybrid" || workMode === "hibrido"
      ? "🏢 Híbrido"
      : job.work_mode
      ? `📍 ${job.work_mode}`
      : null;

  const bestReason =
    job.reasoning && job.reasoning.length > 0 ? job.reasoning[0] : null;

  const handleToggleDismiss = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (dismissLoading) return;
    const nextState = !isDismissed;
    setIsDismissed(nextState);
    if (onDismissChange) onDismissChange(job.id, nextState);

    setDismissLoading(true);
    try {
      if (nextState) {
        await api.dismissJob(job.id);
      } else {
        await api.undismissJob(job.id);
      }
    } catch (err) {
      console.error("Erro ao alternar status de ignorada:", err);
      setIsDismissed(!nextState);
      if (onDismissChange) onDismissChange(job.id, !nextState);
    } finally {
      setDismissLoading(false);
    }
  };

  const handleToggleFavorite = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const nextState = !isFavorite;
    setIsFavorite(nextState);
    if (onFavoriteChange) onFavoriteChange(job.id, nextState);

    try {
      if (nextState) {
        await api.addFavorite(job.id);
      } else {
        await api.removeFavorite(job.id);
      }
    } catch (err) {
      console.error("Erro ao favoritar:", err);
      setIsFavorite(!nextState);
      if (onFavoriteChange) onFavoriteChange(job.id, !nextState);
    }
  };

  const handleFeedback = async (e: React.MouseEvent, isPos: boolean) => {
    e.preventDefault();
    e.stopPropagation();
    if (feedbackLoading) return;
    const target = isPos ? "pos" : "neg";
    if (feedback === target) return;

    setFeedbackLoading(true);
    setFeedback(target);
    try {
      await api.sendFeedback(job.id, isPos);
    } catch (err) {
      console.error("Erro ao enviar feedback:", err);
    } finally {
      setFeedbackLoading(false);
    }
  };

  return (
    <article
      aria-labelledby={`job-title-${job.id}`}
      className="surface-panel-hover flex flex-col justify-between p-5 rounded-xl transition-all border border-surface-border relative"
    >
      <div>
        {/* Cabeçalho da Oportunidade: Título, Compatibilidade e Salvar */}
        <div className="flex items-start justify-between gap-3 mb-2.5">
          <div className="min-w-0 flex-1">
            <Link
              href={`/jobs/${job.id}`}
              className="hover:text-brand-400 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 rounded block"
            >
              <h2
                id={`job-title-${job.id}`}
                className="font-bold text-base sm:text-lg text-white leading-snug break-words"
              >
                {job.title}
              </h2>
            </Link>

            <p className="text-xs text-zinc-300 mt-1 font-medium flex flex-wrap items-center gap-2">
              <span className="text-white font-semibold">{job.company || "Empresa Confidencial"}</span>
              <span className="text-zinc-500" aria-hidden="true">·</span>
              <span>{job.location || "Brasil"}</span>
              {modeLabel && (
                <>
                  <span className="text-zinc-500" aria-hidden="true">·</span>
                  <span className="text-zinc-300">{modeLabel}</span>
                </>
              )}
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {/* Botão de Favoritar (Teclável e Acessível) */}
            <button
              type="button"
              onClick={handleToggleFavorite}
              className={`p-2 rounded-lg border transition-all min-h-[44px] min-w-[44px] flex items-center justify-center ${
                isFavorite
                  ? "bg-amber-500/20 border-amber-500/60 text-amber-300 shadow-sm"
                  : "bg-surface-elevated border-surface-border text-zinc-400 hover:text-amber-300 hover:bg-surface-subtle"
              }`}
              title={isFavorite ? "Remover dos favoritos" : "Salvar nos favoritos"}
              aria-label={isFavorite ? `Remover ${job.title} dos favoritos` : `Favoritar vaga ${job.title}`}
            >
              <span className="text-sm" aria-hidden="true">{isFavorite ? "⭐" : "☆"}</span>
            </button>

            {/* Botão de Ignorar / Ocultar */}
            <button
              type="button"
              onClick={handleToggleDismiss}
              disabled={dismissLoading}
              className={`p-2 rounded-lg border transition-all min-h-[44px] min-w-[44px] flex items-center justify-center ${
                isDismissed
                  ? "bg-rose-500/20 border-rose-500/60 text-rose-300 shadow-sm"
                  : "bg-surface-elevated border-surface-border text-zinc-400 hover:text-rose-400 hover:bg-surface-subtle"
              }`}
              title={isDismissed ? "Restaurar vaga (não ignorar)" : "Ignorar vaga (não recomendar novamente)"}
              aria-label={isDismissed ? `Restaurar vaga ${job.title}` : `Ignorar vaga ${job.title}`}
            >
              <span className="text-xs font-bold" aria-hidden="true">{isDismissed ? "🚫" : "✕"}</span>
            </button>

            {/* Destaque Límpido de Compatibilidade */}
            {score != null && (
              <div
                className={`px-3 py-1 rounded-full text-xs font-bold inline-flex items-center gap-1.5 shrink-0 ${
                  isHighMatch
                    ? "badge-match"
                    : "badge-neutral"
                }`}
                title={`Compatibilidade calculada: ${score}%`}
              >
                <span aria-hidden="true">{isHighMatch ? "✦" : "·"}</span>
                <span>{score}% match</span>
              </div>
            )}
          </div>
        </div>

        {/* Linha de Metadados: Salário, Selo Nova e Origem */}
        <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400 my-2.5">
          {isNew && (
            <span className="font-semibold text-sky-300 bg-sky-950/60 px-2 py-0.5 rounded border border-sky-500/40 inline-flex items-center gap-1">
              ✨ Nova
            </span>
          )}

          {isDismissed && (
            <span className="font-semibold text-rose-300 bg-rose-950/60 px-2 py-0.5 rounded border border-rose-500/40 inline-flex items-center gap-1">
              🚫 Ignorada
            </span>
          )}

          {job.salary_max && (
            <span className="font-semibold text-emerald-400 bg-emerald-950/40 px-2.5 py-1 rounded border border-emerald-500/30">
              💰 {job.currency || "R$"} {Number(job.salary_min || 0).toLocaleString("pt-BR")} - {Number(job.salary_max).toLocaleString("pt-BR")}
            </span>
          )}

          {job.source && (
            <span className="text-xs text-zinc-300 bg-surface-elevated px-2.5 py-0.5 rounded border border-surface-border uppercase font-medium tracking-wide">
              {job.source}
            </span>
          )}

          {job.published_at && (
            <span className="text-zinc-400 text-xs ml-auto">
              {new Date(job.published_at).toLocaleDateString("pt-BR")}
            </span>
          )}
        </div>

        {/* Justificativa Humana da Compatibilidade (Estilo editorial sem aninhamento de card) */}
        {bestReason && (
          <div className="border-l-2 border-brand-500/60 pl-3 py-1 text-xs text-zinc-300 my-2.5 flex items-start gap-2 leading-relaxed">
            <span className="text-brand-400 font-bold shrink-0 mt-0.5" aria-hidden="true">✓</span>
            <p className="break-words">
              <strong className="text-zinc-100 font-medium">Por que combina: </strong>
              {bestReason}
            </p>
          </div>
        )}

        {/* Resumo da Descrição */}
        <p className="text-xs text-zinc-400 line-clamp-2 leading-relaxed break-words overflow-hidden">
          {job.description}
        </p>
      </div>

      {/* Rodapé: Ações Principais e Calibração */}
      <div className="flex flex-wrap sm:flex-nowrap items-center justify-between gap-3 mt-4 pt-3.5 border-t border-surface-border">
        <div className="flex items-center gap-2.5">
          <Link
            href={`/jobs/${job.id}`}
            className="text-xs text-zinc-300 hover:text-white font-medium py-2 transition-colors inline-flex items-center gap-1 focus-visible:ring-1 focus-visible:ring-brand-500 rounded px-1"
          >
            <span>Ver análise completa</span>
            <span aria-hidden="true">→</span>
          </Link>

          <span className="text-zinc-700 text-xs" aria-hidden="true">|</span>

          {/* Calibração por Feedback */}
          <div className="flex items-center gap-1" role="group" aria-label="Avaliar aderência desta oportunidade">
            <button
              type="button"
              onClick={(e) => handleFeedback(e, true)}
              className={`p-1.5 rounded text-xs transition-colors min-h-[36px] min-w-[36px] flex items-center justify-center ${
                feedback === "pos"
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                  : "text-zinc-400 hover:text-emerald-400 hover:bg-surface-elevated"
              }`}
              title="Vaga relevante (calibra recomendações futuras)"
              aria-label="Vaga relevante para o meu perfil"
            >
              👍
            </button>
            <button
              type="button"
              onClick={(e) => handleFeedback(e, false)}
              className={`p-1.5 rounded text-xs transition-colors min-h-[36px] min-w-[36px] flex items-center justify-center ${
                feedback === "neg"
                  ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                  : "text-zinc-400 hover:text-rose-400 hover:bg-surface-elevated"
              }`}
              title="Não relevante (reduz vagas semelhantes)"
              aria-label="Vaga não relevante para o meu perfil"
            >
              👎
            </button>
          </div>
        </div>

        {/* CTA Primário Soberano: Candidatura Oficial */}
        {job.url ? (
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary text-xs w-full sm:w-auto text-center"
            aria-label={`Candidatar-se na fonte para a vaga ${job.title} na empresa ${job.company}`}
          >
            <span>Candidatar-se na fonte</span>
            <span aria-hidden="true">↗</span>
          </a>
        ) : (
          <Link
            href={`/jobs/${job.id}`}
            className="btn-primary text-xs w-full sm:w-auto"
          >
            Ver detalhes da vaga
          </Link>
        )}
      </div>
    </article>
  );
}
