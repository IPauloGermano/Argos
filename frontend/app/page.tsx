"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "../lib/api";
import AgentControl from "../components/AgentControl";
import JobCard from "../components/JobCard";
import Onboarding from "../components/Onboarding";

export default function Dashboard() {
  const [profile, setProfile] = useState<any>(null);
  const [dash, setDash] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [favorites, setFavorites] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [showOnboarding, setShowOnboarding] = useState(false);

  const refresh = async () => {
    try {
      const [profData, dashData, statusData, jobsData, favsData] = await Promise.all([
        api.get("/api/profile").catch(() => null),
        api.get("/api/agent/dashboard").catch(() => null),
        api.get("/api/agent/status").catch(() => null),
        api.get("/api/jobs?limit=6&status=active").catch(() => []),
        api.getFavorites().catch(() => []),
      ]);

      setProfile(profData);
      setDash(dashData);
      setStatus(statusData);
      setJobs(jobsData || []);
      setFavorites((favsData || []).map((f: any) => f.job_id));

      if (
        profData &&
        (!profData.roles || profData.roles.length === 0) &&
        !profData.headline
      ) {
        setShowOnboarding(true);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const targetRole =
    profile?.roles && profile.roles.length > 0
      ? profile.roles[0]
      : profile?.headline || "Desenvolvedor";

  const totalJobsCount = dash?.jobs_today ?? jobs.length;

  return (
    <div className="space-y-6">
      {/* Fluxo de Onboarding de Primeiro Acesso */}
      {showOnboarding ? (
        <Onboarding
          onComplete={() => {
            setShowOnboarding(false);
            refresh();
          }}
        />
      ) : (
        <>
          {/* Header & Resumo Central do Candidato (Sem gradientes artificiais) */}
          <section
            aria-labelledby="welcome-heading"
            className="surface-panel p-6 rounded-2xl border border-surface-border"
          >
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-xs font-semibold text-brand-400 uppercase tracking-wider">
                    Seu Assistente Pessoal
                  </span>
                  <span className="text-zinc-600" aria-hidden="true">·</span>
                  <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${
                    status?.is_executing_cycle
                      ? "text-brand-400"
                      : status?.running === false
                      ? "text-amber-400"
                      : "text-emerald-400"
                  }`}>
                    <span className={`h-2 w-2 rounded-full ${
                      status?.is_executing_cycle
                        ? "bg-brand-500 animate-pulse"
                        : status?.running === false
                        ? "bg-amber-500"
                        : "bg-emerald-500"
                    }`} aria-hidden="true"></span>
                    {status?.is_executing_cycle
                      ? "Buscando vagas agora..."
                      : status?.running === false
                      ? "Monitoramento pausado"
                      : "Monitoramento ativo"}
                  </span>
                </div>

                <h1
                  id="welcome-heading"
                  className="text-2xl sm:text-3xl font-bold text-white tracking-tight flex items-center gap-2 font-serif"
                >
                  <span>Olá!</span>
                  <span aria-hidden="true">👋</span>
                </h1>

                <p className="text-sm text-zinc-300 mt-1 max-w-xl leading-relaxed">
                  Estou procurando vagas de{" "}
                  <strong className="text-white font-semibold underline decoration-brand-500/60">
                    {targetRole}
                  </strong>{" "}
                  para você em tempo real.
                </p>
              </div>

              {/* Ações Rápidas */}
              <div className="flex flex-wrap items-center gap-2.5">
                <Link
                  href="/profile"
                  className="btn-ghost text-xs py-2.5 px-4 min-h-[44px]"
                  title="Alterar cargo, habilidades e preferências"
                >
                  <span>✏️ Ajustar preferências</span>
                </Link>
                <Link
                  href="/jobs"
                  className="btn-primary text-xs py-2.5 px-5 min-h-[44px]"
                >
                  <span>Ver catálogo ({totalJobsCount})</span>
                  <span aria-hidden="true">→</span>
                </Link>
              </div>
            </div>

            {/* Faixa Resumo com Tipografia Legível (Mínimo 12px) */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mt-6 pt-5 border-t border-surface-border">
              <div className="text-xs">
                <span className="text-zinc-400 block mb-1">Vagas compatíveis hoje</span>
                <span className="text-2xl sm:text-3xl font-bold text-white font-serif">
                  {totalJobsCount}
                </span>
              </div>
              <div className="text-xs">
                <span className="text-zinc-400 block mb-1">Altamente recomendadas</span>
                <span className="text-2xl sm:text-3xl font-bold text-emerald-400 font-serif">
                  {dash?.relevant ?? 0}
                </span>
              </div>
              <div className="text-xs col-span-2 sm:col-span-1">
                <span className="text-zinc-400 block mb-1">Maior compatibilidade</span>
                <span className="text-2xl sm:text-3xl font-bold text-brand-400 font-serif">
                  {dash?.best_score != null ? `${dash.best_score}%` : "—"}
                </span>
              </div>
            </div>
          </section>

          {/* Seção Imediata: Melhores Oportunidades Encontradas */}
          <section aria-labelledby="top-jobs-heading" className="space-y-3 pt-1">
            <div className="flex items-center justify-between">
              <div>
                <h2 id="top-jobs-heading" className="text-base sm:text-lg font-bold text-white font-serif">
                  Melhores Oportunidades para Você
                </h2>
                <p className="text-xs text-zinc-400">
                  Selecionadas e ordenadas pela maior afinidade técnica com o seu perfil
                </p>
              </div>
              <Link
                href="/jobs"
                className="text-xs font-semibold text-brand-400 hover:text-brand-300 inline-flex items-center gap-1 transition-colors min-h-[40px] py-1 px-2 rounded focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                <span>Ver catálogo completo ({totalJobsCount})</span>
                <span aria-hidden="true">→</span>
              </Link>
            </div>

            {loading ? (
              <div className="surface-panel text-center py-16 text-zinc-400 text-sm">
                <div
                  className="inline-block animate-spin h-6 w-6 border-2 border-brand-500 border-t-transparent rounded-full mb-3"
                  aria-hidden="true"
                ></div>
                <p>Buscando suas recomendações em tempo real...</p>
              </div>
            ) : jobs.length === 0 ? (
              <div className="surface-panel text-center py-14 border-dashed">
                <span className="text-3xl mb-2 block" aria-hidden="true">🔍</span>
                <p className="font-semibold text-zinc-200 text-base">
                  Ainda não encontramos vagas para este cargo
                </p>
                <p className="text-xs text-zinc-400 max-w-sm mx-auto mt-1 mb-5">
                  Clique no botão abaixo para disparar uma varredura nas plataformas conectadas.
                </p>
                <button
                  type="button"
                  className="btn-primary text-xs min-h-[44px] px-6"
                  onClick={refresh}
                >
                  Buscar Oportunidades Agora
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {jobs.slice(0, 6).map((j) => (
                  <JobCard
                    key={j.id}
                    job={j}
                    initialFavorite={favorites.includes(j.id)}
                    onFavoriteChange={(jobId, isFav) => {
                      if (isFav) {
                        setFavorites((prev) => [...prev, jobId]);
                      } else {
                        setFavorites((prev) => prev.filter((id) => id !== jobId));
                      }
                    }}
                  />
                ))}
              </div>
            )}
          </section>

          {/* Cockpit Amigável do Assistente */}
          <section aria-labelledby="assistant-control-heading" className="pt-2">
            <AgentControl status={status} refresh={refresh} />
          </section>
        </>
      )}
    </div>
  );
}
