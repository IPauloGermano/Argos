"use client";
import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import JobCard from "../../components/JobCard";

export default function JobsPage() {
  const [activeTab, setActiveTab] = useState<"all" | "new" | "favorites" | "ignored">("all");
  const [jobs, setJobs] = useState<any[]>([]);
  const [favorites, setFavorites] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [f, setF] = useState({
    search: "",
    min_score: "",
    seniority: "",
    work_mode: "",
    source: "",
    employment_type: "",
    location: "",
  });

  const [preferredCity, setPreferredCity] = useState<string>("");
  const [preferredCityDisplay, setPreferredCityDisplay] = useState<string>("");
  const [preferredTech, setPreferredTech] = useState<string>("");

  const loadAll = async (overrideParams?: any, targetTab?: "all" | "new" | "favorites" | "ignored") => {
    setLoading(true);
    const currentTab = targetTab || activeTab;
    const params = overrideParams || f;
    const q = new URLSearchParams();
    if (params.search) q.set("search", params.search);
    if (params.min_score) q.set("min_score", params.min_score);
    if (params.seniority) q.set("seniority", params.seniority);
    if (params.work_mode) q.set("work_mode", params.work_mode);
    if (params.source) q.set("source", params.source);
    if (params.employment_type) q.set("employment_type", params.employment_type);
    if (params.location) q.set("location", params.location);
    if (currentTab === "new") q.set("only_new", "true");
    if (currentTab === "ignored") q.set("exclude_dismissed", "false");
    q.set("limit", "200"); // teto da API: sem isso o backend devolve só 50

    try {
      const [jobsData, favsData] = await Promise.all([
        api.get(`/api/jobs?${q.toString()}`).catch(() => []),
        api.getFavorites().catch(() => []),
      ]);
      setJobs(jobsData || []);
      setFavorites(favsData || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const switchTab = (tab: "all" | "new" | "favorites" | "ignored") => {
    setActiveTab(tab);
    loadAll(f, tab);
  };

  useEffect(() => {
    loadAll();
    Promise.all([
      api.get("/api/preferences").catch(() => null),
      api.get("/api/profile").catch(() => null),
    ]).then(([prefs, profile]) => {
      if (prefs && Array.isArray(prefs.locations)) {
        const rawLoc = prefs.locations.find((l: string) => !["remoto", "remote", "brasil", "brazil"].includes(l.toLowerCase()));
        if (rawLoc) {
          const cleanCity = rawLoc.split(",")[0].split("-")[0].split("/")[0].trim();
          setPreferredCity(cleanCity);
          setPreferredCityDisplay(rawLoc);
        }
      }
      if (profile && Array.isArray(profile.skills) && profile.skills.length > 0) {
        setPreferredTech(profile.skills[0]);
      } else if (prefs && Array.isArray(prefs.preferred_keywords) && prefs.preferred_keywords.length > 0) {
        setPreferredTech(prefs.preferred_keywords[0]);
      }
    }).catch(() => {});
  }, []);

  const setQuickFilter = (key: string, value: string) => {
    const next = { ...f, [key]: f[key as keyof typeof f] === value ? "" : value };
    setF(next);
    loadAll(next);
  };

  const handleReset = () => {
    const reset = {
      search: "",
      min_score: "",
      seniority: "",
      work_mode: "",
      source: "",
      employment_type: "",
      location: "",
    };
    setF(reset);
    loadAll(reset);
  };

  const favoriteIds = favorites.map((fav: any) => fav.job_id);

  // Vagas a serem exibidas dependendo da aba ativa
  const displayedJobs =
    activeTab === "favorites"
      ? jobs.filter((j) => favoriteIds.includes(j.id))
      : activeTab === "ignored"
      ? jobs.filter((j) => j.is_dismissed)
      : jobs.filter((j) => !j.is_dismissed);

  return (
    <div className="space-y-5">
      {/* Cabeçalho da Página */}
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
          Catálogo de Oportunidades
        </h1>
        <p className="text-xs text-zinc-400 mt-0.5 max-w-prose">
          Oportunidades encontradas em tempo real pelas plataformas, validadas e ordenadas por compatibilidade.
        </p>
      </div>

      {/* Seletor de Abas: Todas as Vagas, Novas, Salvas e Ignoradas */}
      <div className="flex items-center gap-2 border-b border-surface-border pb-1 overflow-x-auto" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "all"}
          onClick={() => switchTab("all")}
          className={`px-4 py-2.5 text-xs sm:text-sm font-semibold border-b-2 transition-all inline-flex items-center gap-2 min-h-[44px] shrink-0 ${
            activeTab === "all"
              ? "border-brand-500 text-white font-bold"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          <span>💼 Todas as Oportunidades</span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-surface-elevated text-zinc-300">
            {activeTab === "all" ? displayedJobs.length : jobs.filter(j => !j.is_dismissed).length}
          </span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "new"}
          onClick={() => switchTab("new")}
          className={`px-4 py-2.5 text-xs sm:text-sm font-semibold border-b-2 transition-all inline-flex items-center gap-2 min-h-[44px] shrink-0 ${
            activeTab === "new"
              ? "border-sky-500 text-sky-300 font-bold"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          <span>✨ Apenas Novas (24h)</span>
          {activeTab === "new" && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-sky-950/80 text-sky-300 border border-sky-500/40">
              {displayedJobs.length}
            </span>
          )}
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "favorites"}
          onClick={() => switchTab("favorites")}
          className={`px-4 py-2.5 text-xs sm:text-sm font-semibold border-b-2 transition-all inline-flex items-center gap-2 min-h-[44px] shrink-0 ${
            activeTab === "favorites"
              ? "border-amber-500 text-amber-300 font-bold"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          <span>⭐ Vagas Salvas</span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-surface-elevated text-amber-400">
            {favorites.length}
          </span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "ignored"}
          onClick={() => switchTab("ignored")}
          className={`px-4 py-2.5 text-xs sm:text-sm font-semibold border-b-2 transition-all inline-flex items-center gap-2 min-h-[44px] shrink-0 ${
            activeTab === "ignored"
              ? "border-rose-500 text-rose-300 font-bold"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          <span>🚫 Ignoradas</span>
          {activeTab === "ignored" && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-rose-950/80 text-rose-300 border border-rose-500/40">
              {displayedJobs.length}
            </span>
          )}
        </button>
      </div>

      {/* Barra de Filtros e Busca (Apenas nas abas ativas de catálogo) */}
      {(activeTab === "all" || activeTab === "new") && (
        <div className="surface-panel p-4 space-y-3">
          {/* Campo de Busca Livre */}
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="relative flex-1">
              <span className="absolute left-3 top-2.5 text-zinc-400 text-sm" aria-hidden="true">
                🔍
              </span>
              <input
                className="input-field pl-9 text-sm"
                placeholder="Buscar por cargo, tecnologia, local ou empresa (ex: Python, Remoto, Backend)..."
                value={f.search}
                onChange={(e) => setF({ ...f, search: e.target.value })}
                onKeyDown={(e) => e.key === "Enter" && loadAll()}
              />
            </div>

            <button
              type="button"
              className="btn-primary shrink-0 text-xs py-2 px-5 min-h-[44px]"
              onClick={() => loadAll()}
            >
              Buscar
            </button>

            {(f.search || f.min_score || f.seniority || f.work_mode || f.source || f.employment_type || f.location) && (
              <button
                type="button"
                className="btn-ghost shrink-0 text-xs py-2 px-3.5 min-h-[44px]"
                onClick={handleReset}
              >
                Limpar Filtros
              </button>
            )}
          </div>

          {/* Chips de Filtro Rápido Baseados no Perfil */}
          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <span className="text-xs text-zinc-400 font-medium mr-1">Filtros rápidos:</span>
            {preferredCity && (
              <button
                type="button"
                onClick={() => setQuickFilter("location", preferredCity)}
                className={`text-xs px-3 py-1.5 rounded-full border transition-all min-h-[32px] ${
                  f.location === preferredCity
                    ? "bg-brand-500 text-zinc-950 font-bold border-brand-400"
                    : "bg-surface-elevated text-zinc-300 border-surface-border hover:border-zinc-500"
                }`}
              >
                📍 {preferredCityDisplay || preferredCity}
              </button>
            )}
            {preferredTech && (
              <button
                type="button"
                onClick={() => setQuickFilter("search", preferredTech)}
                className={`text-xs px-3 py-1.5 rounded-full border transition-all min-h-[32px] ${
                  f.search === preferredTech
                    ? "bg-brand-500 text-zinc-950 font-bold border-brand-400"
                    : "bg-surface-elevated text-zinc-300 border-surface-border hover:border-zinc-500"
                }`}
              >
                ⚡ {preferredTech}
              </button>
            )}
            <button
              type="button"
              onClick={() => setQuickFilter("work_mode", "remote")}
              className={`text-xs px-3 py-1.5 rounded-full border transition-all min-h-[32px] ${
                f.work_mode === "remote"
                  ? "bg-brand-500 text-zinc-950 font-bold border-brand-400"
                  : "bg-surface-elevated text-zinc-300 border-surface-border hover:border-zinc-500"
              }`}
            >
              🌐 100% Remoto
            </button>
            <button
              type="button"
              onClick={() => setQuickFilter("min_score", "75")}
              className={`text-xs px-3 py-1.5 rounded-full border transition-all min-h-[32px] ${
                f.min_score === "75"
                  ? "bg-brand-500 text-zinc-950 font-bold border-brand-400"
                  : "bg-surface-elevated text-zinc-300 border-surface-border hover:border-zinc-500"
              }`}
            >
              ⭐ Match ≥ 75%
            </button>
            <button
              type="button"
              onClick={() => setQuickFilter("seniority", "junior")}
              className={`text-xs px-3 py-1.5 rounded-full border transition-all min-h-[32px] ${
                f.seniority === "junior"
                  ? "bg-brand-500 text-zinc-950 font-bold border-brand-400"
                  : "bg-surface-elevated text-zinc-300 border-surface-border hover:border-zinc-500"
              }`}
            >
              🌱 Júnior
            </button>
            <button
              type="button"
              onClick={() => setQuickFilter("seniority", "estagio")}
              className={`text-xs px-3 py-1.5 rounded-full border transition-all min-h-[32px] ${
                f.seniority === "estagio"
                  ? "bg-brand-500 text-zinc-950 font-bold border-brand-400"
                  : "bg-surface-elevated text-zinc-300 border-surface-border hover:border-zinc-500"
              }`}
            >
              🎓 Estágio
            </button>
          </div>

          {/* Seletores Complementares */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-surface-border/60">
            <select
              aria-label="Filtrar por senioridade"
              className="input-field text-xs py-2"
              value={f.seniority}
              onChange={(e) => {
                const next = { ...f, seniority: e.target.value };
                setF(next);
                loadAll(next);
              }}
            >
              <option value="">Todas Senioridades</option>
              <option value="estagio">Estágio</option>
              <option value="junior">Júnior</option>
              <option value="mid">Pleno</option>
              <option value="senior">Sênior</option>
            </select>

            <select
              aria-label="Filtrar por modalidade"
              className="input-field text-xs py-2"
              value={f.work_mode}
              onChange={(e) => {
                const next = { ...f, work_mode: e.target.value };
                setF(next);
                loadAll(next);
              }}
            >
              <option value="">Todas Modalidades</option>
              <option value="remote">Remoto</option>
              <option value="hybrid">Híbrido</option>
              <option value="onsite">Presencial</option>
            </select>

            <select
              aria-label="Filtrar por plataforma"
              className="input-field text-xs py-2"
              value={f.source}
              onChange={(e) => {
                const next = { ...f, source: e.target.value };
                setF(next);
                loadAll(next);
              }}
            >
              <option value="">Todas Plataformas</option>
              <option value="linkedin">LinkedIn</option>
              <option value="getonbrd">Get on Board (Chile/LatAm)</option>
              <option value="weworkremotely">We Work Remotely (EUA/Global)</option>
              <option value="jobicy">Jobicy (EUA/Remoto)</option>
              <option value="remoteok">Remote OK</option>
              <option value="remotive">Remotive</option>
              <option value="gupy">Gupy</option>
              <option value="greenhouse">Greenhouse</option>
              <option value="indeed">Indeed</option>
              <option value="vagas">Vagas.com</option>
              <option value="ciee">CIEE</option>
            </select>

            <select
              aria-label="Filtrar por nota mínima"
              className="input-field text-xs py-2"
              value={f.min_score}
              onChange={(e) => {
                const next = { ...f, min_score: e.target.value };
                setF(next);
                loadAll(next);
              }}
            >
              <option value="">Compatibilidade</option>
              <option value="60">≥ 60%</option>
              <option value="75">≥ 75% (Recomendadas)</option>
              <option value="85">≥ 85% (Alta aderência)</option>
            </select>
          </div>
        </div>
      )}

      {/* Contador de Resultados */}
      <div className="flex items-center justify-between text-xs text-zinc-400 px-1">
        <span>
          {loading ? "Filtrando..." : `${displayedJobs.length} oportunidade(s) ${activeTab === "favorites" ? "salva(s)" : "encontrada(s)"}`}
        </span>
        {displayedJobs.length > 0 && (
          <span className="text-xs text-zinc-400">
            Ordenadas por maior compatibilidade com seu perfil
          </span>
        )}
      </div>

      {/* Listagem de Cards */}
      {loading ? (
        <div className="surface-panel text-center py-16 text-zinc-400 text-sm">
          <div className="inline-block animate-spin h-6 w-6 border-2 border-brand-500 border-t-transparent rounded-full mb-3" aria-hidden="true"></div>
          <p>Carregando catálogo de vagas...</p>
        </div>
      ) : displayedJobs.length === 0 ? (
        <div className="surface-panel text-center py-16 border-dashed">
          <span className="text-3xl mb-2 block" aria-hidden="true">
            {activeTab === "favorites" ? "⭐" : activeTab === "new" ? "✨" : activeTab === "ignored" ? "🚫" : "🔍"}
          </span>
          <p className="font-semibold text-zinc-200">
            {activeTab === "favorites"
              ? "Você ainda não salvou nenhuma vaga"
              : activeTab === "new"
              ? "Nenhuma nova vaga catalogada nas últimas 24 horas"
              : activeTab === "ignored"
              ? "Você não possui nenhuma vaga ignorada"
              : "Nenhuma vaga corresponde aos filtros selecionados"}
          </p>
          <p className="text-xs text-zinc-400 max-w-sm mx-auto mt-1 mb-4">
            {activeTab === "favorites"
              ? "Clique no ícone de estrela nas vagas do catálogo para salvá-las aqui e consultá-las facilmente."
              : activeTab === "new"
              ? "O Hermes continua varrendo as fontes 24/7. Novas oportunidades descobertas aparecerão aqui automaticamente."
              : activeTab === "ignored"
              ? "Vagas que você ignorar com o botão '✕' aparecerão aqui caso deseje revisá-las ou restaurá-las."
              : "Tente ajustar ou limpar os filtros de busca para ver mais oportunidades."}
          </p>
          {activeTab !== "all" ? (
            <button
              type="button"
              className="btn-primary text-xs min-h-[42px] px-4"
              onClick={() => switchTab("all")}
            >
              Explorar Todas as Vagas
            </button>
          ) : (
            <button
              type="button"
              className="btn-primary text-xs min-h-[42px] px-4"
              onClick={handleReset}
            >
              Limpar Filtros e Ver Tudo
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          {displayedJobs.map((j) => (
            <JobCard
              key={j.id}
              job={j}
              initialFavorite={favoriteIds.includes(j.id)}
              onFavoriteChange={(jobId, isFav) => {
                if (isFav) {
                  setFavorites((prev) => [...prev, { job_id: jobId }]);
                } else {
                  setFavorites((prev) => prev.filter((fav: any) => fav.job_id !== jobId));
                }
              }}
              initialDismissed={j.is_dismissed}
              onDismissChange={(jobId, isDismissed) => {
                setJobs((prev) =>
                  prev.map((item) => (item.id === jobId ? { ...item, is_dismissed: isDismissed } : item))
                );
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
