"use client";
import React, { useState } from "react";
import ChipInput from "./ChipInput";
import { api } from "../lib/api";

interface OnboardingProps {
  onComplete: () => void;
}

const COMMON_ROLES = [
  "Desenvolvedor Backend",
  "Desenvolvedor Frontend",
  "Engenheiro de Software",
  "Analista de Dados",
  "Desenvolvedor Fullstack",
  "Estágio em Desenvolvimento",
  "Desenvolvedor Python",
  "QA / Engenheiro de Testes",
];

export default function Onboarding({ onComplete }: OnboardingProps) {
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [roles, setRoles] = useState<string[]>(["Desenvolvedor Backend"]);
  const [workModes, setWorkModes] = useState<string[]>(["remote"]);
  const [location, setLocation] = useState<string>("Brasil");
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");

  const toggleWorkMode = (mode: string) => {
    if (workModes.includes(mode)) {
      if (workModes.length > 1) {
        setWorkModes(workModes.filter((m) => m !== mode));
      }
    } else {
      setWorkModes([...workModes, mode]);
    }
  };

  const handleResumeUpload = async (file: File) => {
    setUploading(true);
    setStatusMsg("Analisando seu currículo e extraindo suas habilidades...");
    try {
      await api.uploadResume(file);
      setStatusMsg("Currículo processado com sucesso!");
      await finalize();
    } catch (e) {
      console.error(e);
      setStatusMsg("Não foi possível processar o arquivo agora. Você pode continuar sem ele.");
      setUploading(false);
    }
  };

  const finalize = async () => {
    setSaving(true);
    setStep(4);
    try {
      // 1. Atualiza preferências de busca
      await api.put("/api/preferences", {
        desired_roles: roles.length > 0 ? roles : ["Desenvolvedor Backend"],
        work_modes: workModes,
        locations: [location || "Brasil"],
      });

      // 2. Atualiza perfil
      await api.put("/api/profile", {
        roles: roles.length > 0 ? roles : ["Desenvolvedor Backend"],
        headline: roles[0] || "Profissional de Tecnologia",
      });

      // 3. Dispara a primeira busca automática do assistente em background
      try {
        await api.post("/api/agent/run");
      } catch {
        // pipeline assíncrono
      }

      setTimeout(() => {
        onComplete();
      }, 1600);
    } catch (e) {
      console.error(e);
      onComplete();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="surface-panel p-6 sm:p-8 max-w-2xl mx-auto my-6 border-brand-500/30 shadow-2xl relative overflow-hidden">
      {/* Indicador de Passos */}
      {step !== 4 && (
        <div className="flex items-center justify-between mb-8 pb-4 border-b border-surface-border">
          <div>
            <h2 className="text-base font-bold text-white">Configuração Inicial Rápida</h2>
            <p className="text-xs text-zinc-400 mt-0.5">
              Personalize o Hermes em menos de 1 minuto para receber as vagas certas
            </p>
          </div>

          <div className="flex items-center gap-1.5" role="status" aria-label={`Passo ${step} de 3`}>
            {[1, 2, 3].map((s) => (
              <div
                key={s}
                className={`h-2 rounded-full transition-all ${
                  s === step
                    ? "w-8 bg-brand-500"
                    : s < step
                    ? "w-3 bg-emerald-500"
                    : "w-3 bg-zinc-800"
                }`}
              />
            ))}
          </div>
        </div>
      )}

      {/* Etapa 1: Qual cargo você está procurando? */}
      {step === 1 && (
        <div className="space-y-5">
          <div>
            <span className="text-xs font-semibold text-brand-400 uppercase tracking-wider block">Etapa 1 de 3</span>
            <h3 className="text-lg font-bold text-white mt-1">
              Qual cargo você está procurando?
            </h3>
            <p className="text-xs text-zinc-400 mt-1">
              Adicione os títulos de vagas que mais combinam com seu objetivo. Você pode adicionar múltiplos cargos.
            </p>
          </div>

          <ChipInput
            id="onboarding-roles-input"
            values={roles}
            onChange={setRoles}
            placeholder="Ex: Desenvolvedor Backend, Engenheiro de Software..."
            suggestions={COMMON_ROLES}
            hint="Dica: Clique nas opções sugeridas ou digite e aperte Enter."
          />

          <div className="pt-4 flex items-center justify-between border-t border-surface-border">
            <span className="text-xs text-zinc-400">
              {roles.length} cargo(s) selecionado(s)
            </span>
            <button
              type="button"
              className="btn-primary min-h-[44px] px-6"
              disabled={roles.length === 0}
              onClick={() => setStep(2)}
            >
              <span>Continuar</span>
              <span aria-hidden="true">→</span>
            </button>
          </div>
        </div>
      )}

      {/* Etapa 2: Onde você quer trabalhar? */}
      {step === 2 && (
        <div className="space-y-5">
          <div>
            <span className="text-xs font-semibold text-brand-400 uppercase tracking-wider block">Etapa 2 de 3</span>
            <h3 className="text-lg font-bold text-white mt-1">
              Onde você quer trabalhar?
            </h3>
            <p className="text-xs text-zinc-400 mt-1">
              Selecione as modalidades aceitáveis e a sua localização preferencial.
            </p>
          </div>

          <div className="space-y-3">
            <label className="text-xs font-semibold text-zinc-300 block uppercase tracking-wider">
              Modalidade de Trabalho
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
              {[
                { id: "remote", label: "🌐 Remoto", desc: "100% à distância" },
                { id: "hybrid", label: "🏢 Híbrido", desc: "Alguns dias presencial" },
                { id: "onsite", label: "📍 Presencial", desc: "No escritório físico" },
              ].map((m) => {
                const active = workModes.includes(m.id);
                return (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => toggleWorkMode(m.id)}
                    className={`p-3 rounded-xl border text-left transition-all min-h-[64px] ${
                      active
                        ? "bg-brand-500/15 border-brand-500 text-white shadow-sm ring-1 ring-brand-500/50"
                        : "bg-surface-elevated border-surface-border text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    <span className="text-sm font-semibold block">{m.label}</span>
                    <span className="text-xs text-zinc-400 mt-0.5 block">{m.desc}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label htmlFor="onboarding-location" className="text-xs font-semibold text-zinc-300 block mb-1.5 uppercase tracking-wider">
              Localização de Preferência
            </label>
            <input
              id="onboarding-location"
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Ex: Remoto, São Paulo, Curitiba, Belo Horizonte..."
              className="input-field"
            />
          </div>

          <div className="pt-4 flex items-center justify-between border-t border-surface-border">
            <button
              type="button"
              className="btn-ghost text-xs min-h-[44px]"
              onClick={() => setStep(1)}
            >
              ← Voltar
            </button>
            <button
              type="button"
              className="btn-primary min-h-[44px] px-6"
              onClick={() => setStep(3)}
            >
              <span>Continuar</span>
              <span aria-hidden="true">→</span>
            </button>
          </div>
        </div>
      )}

      {/* Etapa 3: Quer usar seu currículo para melhorar as recomendações? */}
      {step === 3 && (
        <div className="space-y-5">
          <div>
            <span className="text-xs font-semibold text-brand-400 uppercase tracking-wider block">Etapa 3 de 3</span>
            <h3 className="text-lg font-bold text-white mt-1">
              Quer usar seu currículo para recomendações mais precisas?
            </h3>
            <p className="text-xs text-zinc-400 mt-1">
              O Hermes analisa suas tecnologias e histórico para calcular a compatibilidade exata com cada vaga. (Opcional)
            </p>
          </div>

          {/* Área de Upload Amigável */}
          <div className="p-8 rounded-xl border-2 border-dashed border-surface-border hover:border-brand-500/50 bg-surface-elevated/40 text-center transition-all">
            <span className="text-3xl mb-3 block" aria-hidden="true">📄</span>
            <p className="text-sm font-semibold text-zinc-200">
              Envie seu currículo em PDF, DOCX ou TXT
            </p>
            <p className="text-xs text-zinc-400 mt-1 mb-5">
              Seus dados permanecem salvos em segurança no seu banco de dados local.
            </p>

            <label className="btn-primary cursor-pointer inline-flex items-center gap-2 min-h-[44px] px-5">
              <span>{uploading ? "Processando arquivo..." : "📁 Enviar Currículo (PDF / DOCX / TXT)"}</span>
              <input
                type="file"
                accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                disabled={uploading || saving}
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleResumeUpload(file);
                }}
              />
            </label>
          </div>

          {statusMsg && (
            <p className="text-xs text-center text-brand-300">
              {statusMsg}
            </p>
          )}

          <div className="pt-4 flex items-center justify-between border-t border-surface-border">
            <button
              type="button"
              className="btn-ghost text-xs min-h-[44px]"
              disabled={uploading || saving}
              onClick={() => setStep(2)}
            >
              ← Voltar
            </button>

            <button
              type="button"
              className="btn-ghost text-xs min-h-[44px] px-4 font-medium text-zinc-300 hover:text-white"
              disabled={uploading || saving}
              onClick={finalize}
            >
              Continuar sem currículo por enquanto →
            </button>
          </div>
        </div>
      )}

      {/* Etapa 4: Conclusão Calma (Sem bounce/easing espalhafatoso) */}
      {step === 4 && (
        <div className="py-10 text-center space-y-4">
          <span className="text-4xl block text-amber-400" aria-hidden="true">✦</span>
          <h3 className="text-xl font-bold text-white">
            Perfeito! Agora o Hermes vai procurar oportunidades para você.
          </h3>
          <p className="text-xs text-zinc-300 max-w-md mx-auto leading-relaxed">
            Configuração concluída com sucesso. Estamos varrendo as plataformas em tempo real e montando seu painel personalizado.
          </p>
          <div className="inline-block animate-spin h-5 w-5 border-2 border-brand-500 border-t-transparent rounded-full mt-2" aria-hidden="true"></div>
        </div>
      )}
    </div>
  );
}
