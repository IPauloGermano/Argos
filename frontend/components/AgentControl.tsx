"use client";
import React, { useState, useEffect } from "react";
import { api } from "../lib/api";

function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return (
      d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) +
      " (" +
      d.toLocaleDateString("pt-BR") +
      ")"
    );
  } catch {
    return iso;
  }
}

export default function AgentControl({
  status,
  refresh,
}: {
  status: any;
  refresh: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [searchStep, setSearchStep] = useState<number>(0);
  const [resultMsg, setResultMsg] = useState("");
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);

  const isExecuting = busy || status?.is_executing_cycle;

  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (busy) {
      timer = setInterval(() => {
        setSearchStep((prev) => (prev < 3 ? prev + 1 : prev));
      }, 3000);
    } else {
      setSearchStep(0);
    }
    return () => clearInterval(timer);
  }, [busy]);

  const handleRunSearch = async () => {
    setBusy(true);
    setResultMsg("");
    setSearchStep(1);

    try {
      await api.post("/api/agent/run");
      await refresh();

      const lastStats = status?.last_stats;
      const newCount = lastStats?.new || 0;

      if (newCount > 0) {
        setResultMsg(`✨ Varredura concluída! ${newCount} nova(s) vaga(s) encontrada(s) e adicionada(s) ao seu radar.`);
      } else {
        setResultMsg(`✓ Varredura concluída! Catálogo atualizado com as oportunidades mais recentes.`);
      }

      setTimeout(() => setResultMsg(""), 6000);
    } catch (e) {
      setResultMsg(`❌ Erro ao buscar vagas: ${String(e)}`);
    } finally {
      setBusy(false);
      setSearchStep(0);
    }
  };

  const togglePause = async () => {
    try {
      if (status?.running) {
        await api.post("/api/agent/pause");
      } else {
        await api.post("/api/agent/start");
      }
      refresh();
    } catch (e) {
      alert(String(e));
    }
  };

  const isRunning = status?.running;
  const sources = status?.sources || ["gupy", "linkedin", "remoteok", "vagas", "ciee", "greenhouse", "remotive", "getonbrd", "weworkremotely", "jobicy"];

  return (
    <div className="surface-panel p-5 rounded-xl transition-all border border-surface-border">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-lg bg-surface-elevated border border-surface-border flex items-center justify-center text-lg shrink-0 text-amber-400">
            ✦
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm sm:text-base font-bold text-white">
                Monitoramento Automático
              </h2>
              {isRunning ? (
                <span className="badge-match text-xs py-0.5 px-2.5">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true"></span>
                  Ligado 24h
                </span>
              ) : (
                <span className="badge-amber text-xs py-0.5 px-2.5">
                  <span className="h-2 w-2 rounded-full bg-amber-500" aria-hidden="true"></span>
                  Pausado
                </span>
              )}
            </div>
            <p className="text-xs text-zinc-400 mt-1">
              O assistente procura novas vagas a cada {status?.frequency_minutes ? Math.round(status.frequency_minutes / 60) || 1 : 1} hora(s).
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5 self-start sm:self-center shrink-0">
          <button
            type="button"
            className="btn-primary text-xs py-2 px-4 min-h-[44px]"
            disabled={isExecuting}
            onClick={handleRunSearch}
            aria-label="Buscar novas vagas agora"
          >
            {isExecuting ? (
              <span className="inline-flex items-center gap-2">
                <span className="animate-spin h-3.5 w-3.5 border-2 border-stone-950 border-t-transparent rounded-full" aria-hidden="true"></span>
                <span>Buscando...</span>
              </span>
            ) : (
              <span>⚡ Buscar Novas Vagas Agora</span>
            )}
          </button>

          <button
            type="button"
            className="btn-ghost text-xs py-2 px-3.5 min-h-[44px]"
            onClick={togglePause}
            title={isRunning ? "Pausar busca automática periódica" : "Retomar busca automática"}
          >
            {isRunning ? "⏸️ Pausar" : "▶️ Retomar"}
          </button>
        </div>
      </div>

      {/* Indicador de Progresso Honesto Durante a Busca */}
      {isExecuting && (
        <div className="mt-4 p-4 rounded-lg bg-surface-elevated border border-brand-500/30 text-xs space-y-2">
          <div className="flex items-center gap-2 text-brand-400 font-semibold">
            <span>🔎</span>
            <span>Consultando plataformas de vagas em tempo real...</span>
          </div>
          <p className="text-xs text-zinc-400">
            Varrendo LinkedIn, Gupy, Greenhouse e outros portais. Esse processo leva alguns segundos.
          </p>
          <div className="w-full bg-surface-base h-2 rounded-full overflow-hidden border border-surface-border">
            <div
              className="bg-brand-500 h-full transition-all duration-500"
              style={{
                width: searchStep === 1 ? "35%" : searchStep === 2 ? "70%" : searchStep >= 3 ? "90%" : "15%",
              }}
            ></div>
          </div>
        </div>
      )}

      {/* Mensagem de Conclusão */}
      {resultMsg && (
        <div className="mt-3.5 p-3 rounded-lg bg-surface-elevated border border-emerald-500/30 text-xs text-emerald-300">
          {resultMsg}
        </div>
      )}

      {/* Detalhes Técnicos Secundários (Colapsável) */}
      <div className="mt-4 pt-3 border-t border-surface-border">
        <button
          type="button"
          onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
          className="text-xs text-zinc-400 hover:text-zinc-200 inline-flex items-center gap-1.5 font-medium transition-colors min-h-[36px]"
        >
          <span>{showTechnicalDetails ? "▼ Ocultar detalhes das plataformas" : "▶ Ver plataformas monitoradas & histórico"}</span>
        </button>

        {showTechnicalDetails && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3 pt-2 text-xs">
            <div>
              <span className="text-zinc-400 block mb-1">Última verificação</span>
              <span className="font-medium text-zinc-200">
                {formatTimestamp(status?.last_search)}
              </span>
            </div>
            <div>
              <span className="text-zinc-400 block mb-1">Próxima agendada</span>
              <span className="font-medium text-zinc-200">
                {formatTimestamp(status?.next_search)}
              </span>
            </div>
            <div>
              <span className="text-zinc-400 block mb-1">Plataformas ativas ({sources.length})</span>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {sources.map((s: string) => (
                  <span
                    key={s}
                    className="px-2.5 py-0.5 rounded bg-surface-elevated text-xs text-zinc-300 border border-surface-border uppercase font-medium"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
