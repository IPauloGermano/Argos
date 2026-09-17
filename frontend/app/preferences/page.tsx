"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "../../lib/api";
import ChipInput from "../../components/ChipInput";

const SENIORITY_OPTIONS = [
  { id: "estagio", label: "🎓 Estágio" },
  { id: "trainee", label: "🚀 Trainee" },
  { id: "junior", label: "🌱 Júnior" },
  { id: "mid", label: "⚡ Pleno" },
  { id: "senior", label: "⭐ Sênior" },
];

const WORK_MODE_OPTIONS = [
  { id: "remote", label: "🌐 100% Remoto" },
  { id: "hybrid", label: "🏢 Híbrido" },
  { id: "onsite", label: "📍 Presencial" },
];

export default function PreferencesPage() {
  const [p, setP] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/api/preferences").then(setP).catch(console.error);
  }, []);

  if (!p) {
    return (
      <div className="surface-panel text-center py-16 text-zinc-400 text-sm">
        <div className="inline-block animate-spin h-6 w-6 border-2 border-brand-500 border-t-transparent rounded-full mb-3"></div>
        <p>Carregando preferências de busca...</p>
      </div>
    );
  }

  const set = (k: string, v: any) => setP({ ...p, [k]: v });

  const toggleArrayItem = (field: string, val: string) => {
    const list = Array.isArray(p[field]) ? [...p[field]] : [];
    if (list.includes(val)) {
      if (list.length > 1) {
        set(field, list.filter((item) => item !== val));
      }
    } else {
      set(field, [...list, val]);
    }
  };

  const save = async () => {
    setSaving(true);
    setMsg("");
    try {
      const res = await api.put("/api/preferences", p);
      setP(res);
      setMsg("✅ Preferências salvas com sucesso!");
      setTimeout(() => setMsg(""), 4000);
    } catch (e) {
      setMsg(`❌ Erro ao salvar: ${String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Cabeçalho */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
              Filtros Avançados & Regras
            </h1>
            <span className="text-xs bg-surface-elevated text-zinc-400 px-2 py-0.5 rounded border border-surface-border">
              Configurações detalhadas
            </span>
          </div>
          <p className="text-xs text-zinc-400 mt-0.5">
            Refine com precisão os termos de busca, exclusões e plataformas monitoradas.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link href="/profile" className="btn-ghost text-xs py-2 px-3">
            ← Ver Meu Perfil
          </Link>
          <button
            type="button"
            className="btn-primary text-xs py-2 px-4 min-h-[38px]"
            disabled={saving}
            onClick={save}
          >
            {saving ? "Salvando..." : "Salvar Alterações"}
          </button>
        </div>
      </div>

      {msg && (
        <div className="p-3 rounded-lg bg-surface-elevated border border-surface-border text-xs text-zinc-200 animate-fadeIn">
          {msg}
        </div>
      )}

      {/* Seção 1: Cargos e Palavras-chave */}
      <div className="surface-panel p-5 space-y-4">
        <h2 className="text-sm font-semibold text-white flex items-center gap-2">
          <span>🎯</span>
          <span>Cargos e Palavras-chave</span>
        </h2>

        <ChipInput
          id="desired-roles"
          label="Cargos Desejados"
          values={Array.isArray(p.desired_roles) ? p.desired_roles : []}
          onChange={(vals) => set("desired_roles", vals)}
          placeholder="Ex: Backend Developer, Desenvolvedor..."
          suggestions={["Desenvolvedor Backend", "Desenvolvedor Frontend", "Engenheiro de Software"]}
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <ChipInput
            id="mandatory-keywords"
            label="Palavras-chave Obrigatórias"
            values={Array.isArray(p.mandatory_keywords) ? p.mandatory_keywords : []}
            onChange={(vals) => set("mandatory_keywords", vals)}
            placeholder="Ex: Python, FastAPI..."
            hint="Vagas sem estas palavras são eliminadas."
          />

          <ChipInput
            id="preferred-keywords"
            label="Palavras-chave Preferidas (Bônus)"
            values={Array.isArray(p.preferred_keywords) ? p.preferred_keywords : []}
            onChange={(vals) => set("preferred_keywords", vals)}
            placeholder="Ex: Docker, AWS, PostgreSQL..."
            hint="Aumentam a nota de compatibilidade."
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <ChipInput
            id="excluded-keywords"
            label="Palavras-chave Excluídas"
            values={Array.isArray(p.excluded_keywords) ? p.excluded_keywords : []}
            onChange={(vals) => set("excluded_keywords", vals)}
            placeholder="Ex: PHP, Java..."
            hint="Descarta vagas com estes termos."
          />

          <ChipInput
            id="excluded-companies"
            label="Empresas Descartadas"
            values={Array.isArray(p.excluded_companies) ? p.excluded_companies : []}
            onChange={(vals) => set("excluded_companies", vals)}
            placeholder="Ex: Nome da empresa..."
            hint="Empresas que você não deseja receber alertas."
          />
        </div>
      </div>

      {/* Seção 2: Modalidade e Localização */}
      <div className="surface-panel p-5 space-y-4">
        <h2 className="text-sm font-semibold text-white flex items-center gap-2">
          <span>📍</span>
          <span>Modalidade & Localização</span>
        </h2>

        <div>
          <span className="text-xs font-semibold text-zinc-300 block mb-2 uppercase tracking-wider">
            Modalidade de Trabalho
          </span>
          <div className="grid grid-cols-3 gap-2.5">
            {WORK_MODE_OPTIONS.map((m) => {
              const active = (p.work_modes || []).includes(m.id);
              return (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => toggleArrayItem("work_modes", m.id)}
                  className={`py-2.5 px-3 rounded-xl text-xs font-semibold border text-center transition-all ${
                    active
                      ? "bg-brand-500/15 border-brand-500 text-white shadow-sm"
                      : "bg-surface-elevated border-surface-border text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {m.label}
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <span className="text-xs font-semibold text-zinc-300 block mb-2 uppercase tracking-wider">
            Senioridade Aceitável
          </span>
          <div className="flex flex-wrap gap-2">
            {SENIORITY_OPTIONS.map((s) => {
              const active = (p.seniority_levels || []).includes(s.id);
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => toggleArrayItem("seniority_levels", s.id)}
                  className={`py-2 px-3 rounded-lg text-xs font-semibold border transition-all ${
                    active
                      ? "bg-brand-500/15 border-brand-500 text-white shadow-sm"
                      : "bg-surface-elevated border-surface-border text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {s.label}
                </button>
              );
            })}
          </div>
        </div>

        <ChipInput
          id="locations-input"
          label="Cidades / Regiões"
          values={Array.isArray(p.locations) ? p.locations : []}
          onChange={(vals) => set("locations", vals)}
          placeholder="Ex: Brasil, Remoto, São Paulo..."
        />
      </div>

      {/* Seção 3: Nota Mínima & Idade Máxima */}
      <div className="surface-panel p-5 space-y-4">
        <h2 className="text-sm font-semibold text-white flex items-center gap-2">
          <span>⚙️</span>
          <span>Calibragem do Agente</span>
        </h2>

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label htmlFor="score-range" className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
              Nota Mínima de Compatibilidade
            </label>
            <span className="text-xs font-bold text-emerald-400">
              ≥ {p.minimum_match_score || 70}%
            </span>
          </div>
          <input
            id="score-range"
            type="range"
            min={40}
            max={95}
            step={5}
            value={p.minimum_match_score || 70}
            onChange={(e) => set("minimum_match_score", Number(e.target.value))}
            className="w-full accent-brand-500 cursor-pointer"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="min-salary" className="text-xs font-semibold text-zinc-300 block mb-1.5 uppercase tracking-wider">
              Salário Mínimo Pretendido (R$)
            </label>
            <input
              id="min-salary"
              type="number"
              min={0}
              step={500}
              placeholder="Ex: 5000"
              value={p.min_salary || ""}
              onChange={(e) => set("min_salary", e.target.value ? Number(e.target.value) : null)}
              className="input-field"
            />
          </div>

          <div>
            <label htmlFor="max-age" className="text-xs font-semibold text-zinc-300 block mb-1.5 uppercase tracking-wider">
              Idade Máxima da Vaga (Dias)
            </label>
            <input
              id="max-age"
              type="number"
              min={7}
              max={180}
              value={p.max_job_age_days || 60}
              onChange={(e) => set("max_job_age_days", Number(e.target.value))}
              className="input-field"
            />
          </div>
        </div>
      </div>

      <div className="flex justify-end pt-2">
        <button
          type="button"
          className="btn-primary text-xs py-2.5 px-6 min-h-[42px]"
          disabled={saving}
          onClick={save}
        >
          {saving ? "Salvando..." : "Salvar Alterações"}
        </button>
      </div>
    </div>
  );
}
