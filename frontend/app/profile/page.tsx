"use client";
import React, { useEffect, useState } from "react";
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

const FREQUENCY_OPTIONS = [
  { minutes: 60, label: "A cada 1 hora (Recomendado)" },
  { minutes: 240, label: "A cada 4 horas" },
  { minutes: 1440, label: "1 vez ao dia" },
];

const SUGGESTED_SKILLS = [
  "Python", "FastAPI", "PostgreSQL", "Docker", "Git", "Node.js", "React", "TypeScript", "AWS", "SQL"
];

const SUGGESTED_ROLES = [
  "Desenvolvedor Backend", "Desenvolvedor Frontend", "Engenheiro de Software", "Desenvolvedor Fullstack", "Analista de Dados"
];

export default function ProfilePage() {
  const [activeTab, setActiveTab] = useState<"profile" | "preferences">("profile");
  const [p, setP] = useState<any>(null);
  const [prefs, setPrefs] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get("/api/profile").catch(() => null),
      api.get("/api/preferences").catch(() => null),
    ]).then(([profileData, prefData]) => {
      setP(profileData);
      setPrefs(prefData);
    });
  }, []);

  if (!p || !prefs) {
    return (
      <div className="surface-panel text-center py-16 text-zinc-400 text-sm">
        <div className="inline-block animate-spin h-6 w-6 border-2 border-brand-500 border-t-transparent rounded-full mb-3"></div>
        <p>Carregando seus dados...</p>
      </div>
    );
  }

  const setProfileField = (k: string, v: any) => setP({ ...p, [k]: v });
  const setPrefField = (k: string, v: any) => setPrefs({ ...prefs, [k]: v });

  const togglePreferenceItem = (field: "seniority_levels" | "work_modes", val: string) => {
    const list = Array.isArray(prefs[field]) ? [...prefs[field]] : [];
    if (list.includes(val)) {
      if (list.length > 1) {
        setPrefField(field, list.filter((item) => item !== val));
      }
    } else {
      setPrefField(field, [...list, val]);
    }
  };

  const saveAll = async () => {
    setSaving(true);
    setMsg("");
    try {
      // 1. Salva perfil
      const profilePayload = {
        headline: p.headline,
        summary: p.summary,
        years_experience: Number(p.years_experience) || 0,
        seniority: p.seniority,
        skills: Array.isArray(p.skills) ? p.skills : [],
        roles: Array.isArray(p.roles) ? p.roles : [],
        languages: Array.isArray(p.languages) ? p.languages : [],
      };

      // 2. Salva preferências de busca
      const prefPayload = {
        desired_roles: Array.isArray(prefs.desired_roles) ? prefs.desired_roles : p.roles,
        mandatory_keywords: Array.isArray(prefs.mandatory_keywords) ? prefs.mandatory_keywords : [],
        preferred_keywords: Array.isArray(prefs.preferred_keywords) ? prefs.preferred_keywords : [],
        excluded_keywords: Array.isArray(prefs.excluded_keywords) ? prefs.excluded_keywords : [],
        excluded_companies: Array.isArray(prefs.excluded_companies) ? prefs.excluded_companies : [],
        seniority_levels: prefs.seniority_levels || ["junior", "mid", "senior"],
        work_modes: prefs.work_modes || ["remote"],
        minimum_salary: (prefs.minimum_salary ?? prefs.min_salary) ? Number(prefs.minimum_salary ?? prefs.min_salary) : null,
        min_salary: (prefs.minimum_salary ?? prefs.min_salary) ? Number(prefs.minimum_salary ?? prefs.min_salary) : null,
        minimum_match_score: Number(prefs.minimum_match_score) || 70,
        search_frequency_minutes: Number(prefs.search_frequency_minutes) || 60,
      };

      const [resP, resPrefs] = await Promise.all([
        api.put("/api/profile", profilePayload),
        api.put("/api/preferences", prefPayload),
      ]);

      setP(resP);
      setPrefs(resPrefs);
      setMsg("✅ Perfil e critérios de busca salvos com sucesso!");
      setTimeout(() => setMsg(""), 4000);
    } catch (e) {
      setMsg(`❌ Erro ao salvar: ${String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const handleUploadResume = async (file: File) => {
    setUploading(true);
    setMsg("⏳ Analisando currículo com inteligência artificial...");
    try {
      const res = await api.uploadResume(file);
      setP(res);
      setMsg("✅ Currículo processado com sucesso! Seus dados e habilidades foram atualizados.");
      setTimeout(() => setMsg(""), 5000);
    } catch (e) {
      setMsg(`❌ Erro no processamento do arquivo: ${String(e)}`);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Cabeçalho da Página */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
            Meu Perfil & Preferências de Vagas
          </h1>
          <p className="text-xs text-zinc-400 max-w-prose">
            Configure seu perfil e critérios para que o Hermes selecione oportunidades sob medida para você.
          </p>
        </div>

        <button
          type="button"
          className="btn-primary shrink-0 text-xs py-2 px-4 min-h-[40px]"
          disabled={saving}
          onClick={saveAll}
        >
          {saving ? "Salvando alterações..." : "💾 Salvar Alterações"}
        </button>
      </div>

      {msg && (
        <div className="p-3 rounded-lg bg-surface-elevated border border-surface-border text-xs text-zinc-200 animate-fadeIn">
          {msg}
        </div>
      )}

      {/* Seletor de Abas Internas */}
      <div className="flex items-center gap-2 border-b border-surface-border pb-1">
        <button
          type="button"
          onClick={() => setActiveTab("profile")}
          className={`px-4 py-2 text-xs sm:text-sm font-semibold border-b-2 transition-all ${
            activeTab === "profile"
              ? "border-brand-500 text-white font-bold"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          👤 1. Quem Sou Eu (Currículo & Skills)
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("preferences")}
          className={`px-4 py-2 text-xs sm:text-sm font-semibold border-b-2 transition-all ${
            activeTab === "preferences"
              ? "border-brand-500 text-white font-bold"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          🎯 2. O Que Procuro (Cargos & Filtros)
        </button>
      </div>

      {/* ABA 1: PERFIL & CURRÍCULO */}
      {activeTab === "profile" && (
        <div className="space-y-6 animate-fadeIn">
          {/* Card de Upload de PDF */}
          <div className="surface-panel border-dashed p-5 space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                  <span>📄</span>
                  <span>Extrair Informações do Currículo (PDF, DOCX, TXT)</span>
                </h2>
                <p className="text-xs text-zinc-400 mt-1 max-w-prose leading-relaxed">
                  Envie seu currículo em PDF, DOCX ou TXT para preenchimento automático.
                </p>
              </div>

              <label className="btn-ghost cursor-pointer shrink-0 text-xs py-2 px-3.5 min-h-[42px] inline-flex items-center">
                <span>{uploading ? "Lendo arquivo..." : "📁 Enviar Currículo"}</span>
                <input
                  type="file"
                  accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                  disabled={uploading}
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleUploadResume(file);
                  }}
                />
              </label>
            </div>
          </div>

          {/* Dados do Perfil */}
          <div className="space-y-5">
            <div>
              <label htmlFor="headline-input" className="text-xs font-semibold text-zinc-300 block mb-1.5">
                Título Profissional / Headline
              </label>
              <input
                id="headline-input"
                className="input-field"
                placeholder="Ex: Desenvolvedor Backend Python | Engenheiro de Software"
                value={p.headline || ""}
                onChange={(e) => setProfileField("headline", e.target.value)}
              />
            </div>

            <div>
              <label htmlFor="summary-input" className="text-xs font-semibold text-zinc-300 block mb-1.5">
                Resumo Profissional
              </label>
              <textarea
                id="summary-input"
                className="input-field leading-relaxed"
                rows={3}
                placeholder="Breve resumo da sua trajetória e tecnologias que domina..."
                value={p.summary || ""}
                onChange={(e) => setProfileField("summary", e.target.value)}
              />
            </div>

            {/* Componente de Chips para Skills */}
            <ChipInput
              id="skills-input"
              label="Habilidades & Tecnologias que Você Domina"
              values={Array.isArray(p.skills) ? p.skills : []}
              onChange={(newSkills) => setProfileField("skills", newSkills)}
              placeholder="Digite uma tecnologia (ex: Python, Docker) e pressione Enter..."
              suggestions={SUGGESTED_SKILLS}
              hint="Tecnologias comparadas com as vagas para calcular compatibilidade."
            />

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
              <div>
                <label htmlFor="experience-input" className="text-xs font-semibold text-zinc-300 block mb-1.5">
                  Anos de Experiência
                </label>
                <input
                  id="experience-input"
                  type="number"
                  min={0}
                  className="input-field"
                  value={p.years_experience ?? 0}
                  onChange={(e) => setProfileField("years_experience", Number(e.target.value))}
                />
              </div>

              {/* Seletor Amigável de Senioridade Atual */}
              <div>
                <span className="text-xs font-semibold text-zinc-300 block mb-1.5">
                  Sua Senioridade Atual
                </span>
                <div className="grid grid-cols-3 gap-1.5">
                  {["junior", "mid", "senior"].map((lvl) => {
                    const active = (p.seniority || "").toLowerCase() === lvl;
                    const label = lvl === "junior" ? "Júnior" : lvl === "mid" ? "Pleno" : "Sênior";
                    return (
                      <button
                        key={lvl}
                        type="button"
                        onClick={() => setProfileField("seniority", lvl)}
                        className={`py-2 px-2.5 rounded-lg text-xs font-semibold transition-all text-center ${
                          active
                            ? "bg-brand-500 text-zinc-950 font-bold shadow-sm"
                            : "bg-surface-base text-zinc-400 hover:text-zinc-200"
                        }`}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Chips de Idiomas */}
            <ChipInput
              id="languages-input"
              label="Idiomas"
              values={Array.isArray(p.languages) ? p.languages : []}
              onChange={(newLanguages) => setProfileField("languages", newLanguages)}
              placeholder="Ex: Português, Inglês..."
              suggestions={["Português", "Inglês", "Espanhol"]}
            />
          </div>
        </div>
      )}

      {/* ABA 2: O QUE PROCURO (CRITÉRIOS DE BUSCA) */}
      {activeTab === "preferences" && (
        <div className="space-y-6 animate-fadeIn">
          <div className="space-y-5">
            {/* Chips de Cargos Desejados */}
            <ChipInput
              id="desired-roles-input"
              label="Cargos Desejados para Monitoramento"
              values={Array.isArray(prefs.desired_roles) ? prefs.desired_roles : p.roles || []}
              onChange={(newRoles) => {
                setPrefField("desired_roles", newRoles);
                setProfileField("roles", newRoles);
              }}
              placeholder="Ex: Backend Developer, Desenvolvedor Python..."
              suggestions={SUGGESTED_ROLES}
              hint="O assistente varre as plataformas buscando oportunidades com estes títulos."
            />

            {/* Seletor Visual de Modalidade */}
            <div>
              <span className="text-xs font-semibold text-zinc-300 block mb-2">
                Modalidades Aceitáveis
              </span>
              <div className="grid grid-cols-3 gap-2.5">
                {WORK_MODE_OPTIONS.map((m) => {
                  const active = (prefs.work_modes || []).includes(m.id);
                  return (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => togglePreferenceItem("work_modes", m.id)}
                      className={`py-2.5 px-3 rounded-xl text-xs font-semibold border transition-all text-center ${
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

            {/* Seletor Visual de Senioridade das Vagas */}
            <div>
              <span className="text-xs font-semibold text-zinc-300 block mb-2">
                Níveis de Vagas de seu Interesse
              </span>
              <div className="flex flex-wrap gap-2">
                {SENIORITY_OPTIONS.map((s) => {
                  const active = (prefs.seniority_levels || []).includes(s.id);
                  return (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => togglePreferenceItem("seniority_levels", s.id)}
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

            {/* Chips de Palavras-chave Obrigatórias e Excluídas */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
              <ChipInput
                id="mandatory-input"
                label="Palavras-chave Obrigatórias"
                values={Array.isArray(prefs.mandatory_keywords) ? prefs.mandatory_keywords : []}
                onChange={(vals) => setPrefField("mandatory_keywords", vals)}
                placeholder="Ex: Python, Django..."
                hint="Vagas sem estas palavras serão descartadas automaticamente."
              />

              <ChipInput
                id="excluded-input"
                label="Termos a Descartar (Exclusão)"
                values={Array.isArray(prefs.excluded_keywords) ? prefs.excluded_keywords : []}
                onChange={(vals) => setPrefField("excluded_keywords", vals)}
                placeholder="Ex: PHP, Java, Presencial..."
                hint="Vagas contendo estes termos não serão adicionadas."
              />
            </div>

            {/* Chips de Empresas a Bloquear */}
            <ChipInput
              id="excluded-companies-input"
              label="Empresas que Deseja Ignorar"
              values={Array.isArray(prefs.excluded_companies) ? prefs.excluded_companies : []}
              onChange={(vals) => setPrefField("excluded_companies", vals)}
              placeholder="Ex: Empresa X, Consultoria Y..."
              hint="Oportunidades destas empresas não aparecerão nas suas recomendações."
            />

            {/* Slider Amigável de Compatibilidade Mínima */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label htmlFor="score-slider" className="text-xs font-semibold text-zinc-300">
                  Nota Mínima de Compatibilidade para Alertas
                </label>
                <span className="text-xs font-bold text-emerald-400">
                  ≥ {prefs.minimum_match_score || 70}%
                </span>
              </div>
              <input
                id="score-slider"
                type="range"
                min={40}
                max={95}
                step={5}
                value={prefs.minimum_match_score || 70}
                onChange={(e) => setPrefField("minimum_match_score", Number(e.target.value))}
                className="w-full accent-brand-500 cursor-pointer"
              />
              <p className="text-xs text-zinc-400 mt-1.5 max-w-prose">
                Apenas vagas com nota igual ou superior a esta gerarão alertas automáticos no Telegram/Discord.
              </p>
            </div>

            {/* Seletor Amigável de Frequência */}
            <div>
              <span className="text-xs font-semibold text-zinc-300 block mb-2">
                Frequência de Busca Automática
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                {FREQUENCY_OPTIONS.map((opt) => {
                  const active = (prefs.search_frequency_minutes || 60) === opt.minutes;
                  return (
                    <button
                      key={opt.minutes}
                      type="button"
                      onClick={() => setPrefField("search_frequency_minutes", opt.minutes)}
                      className={`p-2.5 rounded-lg text-xs font-semibold border text-center transition-all ${
                        active
                          ? "bg-brand-500/15 border-brand-500 text-white shadow-sm"
                          : "bg-surface-elevated border-surface-border text-zinc-400 hover:text-zinc-200"
                      }`}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Botão de Salvar no Rodapé */}
      <div className="flex items-center justify-between pt-2">
        <span className="text-xs text-zinc-400">
          Suas alterações são aplicadas imediatamente às próximas buscas.
        </span>
        <button
          type="button"
          className="btn-primary text-xs py-2.5 px-5 min-h-[42px]"
          disabled={saving}
          onClick={saveAll}
        >
          {saving ? "Salvando..." : "Salvar Alterações"}
        </button>
      </div>
    </div>
  );
}
