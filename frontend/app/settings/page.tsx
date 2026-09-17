"use client";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";

export default function SettingsPage() {
  const [u, setU] = useState<any>(null);
  const [prefs, setPrefs] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get("/api/users/me"),
      api.get("/api/preferences")
    ]).then(([userData, prefData]) => {
      setU(userData);
      setPrefs(prefData);
    }).catch(console.error);
  }, []);

  if (!u || !prefs) {
    return (
      <div className="surface-panel text-center py-12 text-zinc-400 text-sm">
        Carregando configurações...
      </div>
    );
  }

  const save = async () => {
    setSaving(true);
    setMsg("");
    try {
      await Promise.all([
        api.put("/api/users/me", u),
        api.put("/api/preferences", {
          telegram_chat_id: prefs.telegram_chat_id,
          telegram_bot_token: prefs.telegram_bot_token,
          discord_webhook_url: prefs.discord_webhook_url,
          discord_enabled: prefs.discord_enabled,
          telegram_enabled: prefs.telegram_enabled,
        })
      ]);
      setMsg("✅ Configurações e canais salvos com sucesso!");
      setTimeout(() => setMsg(""), 3500);
    } catch (e) {
      setMsg(`❌ Erro ao salvar: ${String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">Canais & Configurações</h1>
          <p className="text-xs text-zinc-400 max-w-prose">Configure suas credenciais de entrega para alertas automáticos.</p>
        </div>
        <button className="btn-primary shrink-0" disabled={saving} onClick={save}>
          {saving ? "Salvando..." : "Salvar Configurações"}
        </button>
      </div>

      {msg && (
        <div className="p-3 rounded-lg bg-surface-elevated border border-surface-border text-xs text-zinc-200">
          {msg}
        </div>
      )}

      {/* Conta do Usuário */}
      <div className="surface-panel space-y-4">
        <h2 className="text-sm font-semibold text-white flex items-center gap-2">
          <span>👤</span>
          <span>Dados do Usuário</span>
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="section-label block mb-1">Nome Completo</label>
            <input
              className="input-field"
              value={u.name || ""}
              onChange={(e) => setU({ ...u, name: e.target.value })}
            />
          </div>
          <div>
            <label className="section-label block mb-1">E-mail de Destino</label>
            <input
              className="input-field"
              value={u.email || ""}
              onChange={(e) => setU({ ...u, email: e.target.value })}
            />
          </div>
        </div>
      </div>

      {/* Integração com Telegram */}
      <div className="surface-panel space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <span>💬</span>
            <span>Integração Telegram Bot</span>
          </h2>
          <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer">
            <input
              type="checkbox"
              className="rounded bg-surface-elevated border-surface-border text-brand-500 focus:ring-0"
              checked={!!prefs.telegram_enabled}
              onChange={(e) => setPrefs({ ...prefs, telegram_enabled: e.target.checked })}
            />
            <span>Habilitado</span>
          </label>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="section-label block mb-1">Telegram Chat ID</label>
            <input
              className="input-field"
              placeholder="Ex: 123456789"
              value={prefs.telegram_chat_id || u.telegram_chat_id || ""}
              onChange={(e) => {
                const val = e.target.value;
                setU({ ...u, telegram_chat_id: val });
                setPrefs({ ...prefs, telegram_chat_id: val });
              }}
            />
          </div>
          <div>
            <label className="section-label block mb-1">Bot Token (Opcional se definido no .env)</label>
            <input
              className="input-field"
              type="password"
              placeholder="123456:ABC-DEF..."
              value={prefs.telegram_bot_token || ""}
              onChange={(e) => setPrefs({ ...prefs, telegram_bot_token: e.target.value })}
            />
          </div>
        </div>
        <p className="text-xs text-zinc-400 mt-1 max-w-prose">
          Dica: Converse com o @BotFather no Telegram para criar seu bot e com o @userinfobot para pegar seu Chat ID.
        </p>
      </div>

      {/* Integração com Discord */}
      <div className="surface-panel space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <span>👾</span>
            <span>Integração Discord Webhook</span>
          </h2>
          <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer">
            <input
              type="checkbox"
              className="rounded bg-surface-elevated border-surface-border text-brand-500 focus:ring-0"
              checked={!!prefs.discord_enabled}
              onChange={(e) => setPrefs({ ...prefs, discord_enabled: e.target.checked })}
            />
            <span>Habilitado</span>
          </label>
        </div>

        <div>
          <label className="section-label block mb-1">Discord Webhook URL</label>
          <input
            className="input-field"
            placeholder="https://discord.com/api/webhooks/..."
            value={prefs.discord_webhook_url || ""}
            onChange={(e) => setPrefs({ ...prefs, discord_webhook_url: e.target.value })}
          />
          <span className="text-xs text-zinc-400 mt-1 block max-w-prose">
            Crie em: Configurações do seu Canal no Discord &gt; Integrações &gt; Webhooks.
          </span>
        </div>
      </div>
    </div>
  );
}
