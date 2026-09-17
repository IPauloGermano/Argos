"use client";
import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";

export default function NotificationsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [prefs, setPrefs] = useState<any>(null);
  const [user, setUser] = useState<any>(null);
  const [testResult, setTestResult] = useState("");
  const [testing, setTesting] = useState(false);
  const [savingChannels, setSavingChannels] = useState(false);
  const [channelMsg, setChannelMsg] = useState("");

  const loadAll = async () => {
    try {
      const [notifs, prefData, userData] = await Promise.all([
        api.get("/api/notifications").catch(() => []),
        api.get("/api/preferences").catch(() => null),
        api.get("/api/users/me").catch(() => null),
      ]);
      setItems(notifs || []);
      setPrefs(prefData);
      setUser(userData);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const triggerTest = async (channel: string) => {
    setTesting(true);
    setTestResult("");
    try {
      const res = await api.post("/api/notifications/test", { channel });
      setTestResult(`✅ ${res.message || "Alerta de teste enviado com sucesso!"}`);
      const notifs = await api.get("/api/notifications");
      setItems(notifs || []);
      setTimeout(() => setTestResult(""), 5000);
    } catch (e) {
      setTestResult(`❌ Falha no teste: ${String(e)}`);
    } finally {
      setTesting(false);
    }
  };

  const saveChannels = async () => {
    setSavingChannels(true);
    setChannelMsg("");
    try {
      await api.put("/api/preferences", {
        telegram_enabled: prefs?.telegram_enabled,
        telegram_chat_id: prefs?.telegram_chat_id,
        telegram_bot_token: prefs?.telegram_bot_token,
        discord_enabled: prefs?.discord_enabled,
        discord_webhook_url: prefs?.discord_webhook_url,
      });
      setChannelMsg("✅ Canais salvos com sucesso!");
      setTimeout(() => setChannelMsg(""), 4000);
    } catch (e) {
      setChannelMsg(`❌ Erro ao salvar canais: ${String(e)}`);
    } finally {
      setSavingChannels(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Cabeçalho */}
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
          Alertas & Canais de Notificação
        </h1>
        <p className="text-xs text-zinc-400 mt-0.5 max-w-prose">
          Receba notificações em tempo real sempre que uma oportunidade de alta compatibilidade for encontrada.
        </p>
      </div>

      {testResult && (
        <div className="p-3 rounded-lg bg-surface-elevated border border-brand-500/30 text-xs text-zinc-200 animate-fadeIn">
          {testResult}
        </div>
      )}

      {channelMsg && (
        <div className="p-3 rounded-lg bg-surface-elevated border border-emerald-500/30 text-xs text-emerald-300 animate-fadeIn">
          {channelMsg}
        </div>
      )}

      {/* Painel de Configuração dos Canais (Telegram & Discord) */}
      <div className="space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-surface-border">
          <div className="flex items-center gap-2">
            <span className="text-xl">🔔</span>
            <h2 className="text-sm font-semibold text-white">
              Onde Você Deseja Receber os Alertas
            </h2>
          </div>

          <button
            type="button"
            className="btn-primary text-xs py-1.5 px-3 min-h-[36px]"
            disabled={savingChannels}
            onClick={saveChannels}
          >
            {savingChannels ? "Salvando..." : "Salvar Canais"}
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Card Telegram */}
          <div className="surface-panel p-5 rounded-xl space-y-3 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-lg">💬</span>
                  <span className="text-xs font-bold text-white">Telegram Bot</span>
                </div>
                <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded bg-surface-elevated border-surface-border text-brand-500 focus:ring-0"
                    checked={!!prefs?.telegram_enabled}
                    onChange={(e) =>
                      setPrefs({ ...prefs, telegram_enabled: e.target.checked })
                    }
                  />
                  <span>Ativo</span>
                </label>
              </div>

              <div className="space-y-2">
                <div>
                  <label htmlFor="telegram-chat-id" className="text-xs font-semibold text-zinc-300 block mb-1 uppercase">
                    Seu Chat ID do Telegram
                  </label>
                  <input
                    id="telegram-chat-id"
                    type="text"
                    placeholder="Ex: 123456789"
                    value={prefs?.telegram_chat_id || ""}
                    onChange={(e) =>
                      setPrefs({ ...prefs, telegram_chat_id: e.target.value })
                    }
                    className="input-field text-xs py-2"
                  />
                  <span className="text-xs text-zinc-400 mt-1 block">
                    Dica: envie qualquer mensagem para @userinfobot no Telegram para descobrir seu Chat ID.
                  </span>
                </div>
              </div>
            </div>

            <div className="pt-2 border-t border-surface-border flex items-center justify-between">
              <span className="text-xs text-zinc-400">Teste de envio</span>
              <button
                type="button"
                className="btn-ghost text-xs py-1.5 px-3 min-h-[40px]"
                disabled={testing || !prefs?.telegram_chat_id}
                onClick={() => triggerTest("telegram")}
              >
                <span>💬 Disparar Mensagem de Teste</span>
              </button>
            </div>
          </div>

          {/* Card Discord */}
          <div className="surface-panel p-5 rounded-xl space-y-3 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-lg">👾</span>
                  <span className="text-xs font-bold text-white">Discord Webhook</span>
                </div>
                <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded bg-surface-elevated border-surface-border text-brand-500 focus:ring-0"
                    checked={!!prefs?.discord_enabled}
                    onChange={(e) =>
                      setPrefs({ ...prefs, discord_enabled: e.target.checked })
                    }
                  />
                  <span>Ativo</span>
                </label>
              </div>

              <div>
                <label htmlFor="discord-url" className="text-xs font-semibold text-zinc-300 block mb-1 uppercase">
                  URL do Webhook do Canal
                </label>
                <input
                  id="discord-url"
                  type="text"
                  placeholder="https://discord.com/api/webhooks/..."
                  value={prefs?.discord_webhook_url || ""}
                  onChange={(e) =>
                    setPrefs({ ...prefs, discord_webhook_url: e.target.value })
                  }
                  className="input-field text-xs py-2"
                />
                <span className="text-xs text-zinc-400 mt-1 block">
                  Crie em: Configurações do seu Canal no Discord &gt; Integrações &gt; Webhooks.
                </span>
              </div>
            </div>

            <div className="pt-2 border-t border-surface-border flex items-center justify-between">
              <span className="text-xs text-zinc-400">Teste de envio</span>
              <button
                type="button"
                className="btn-ghost text-xs py-1.5 px-3 min-h-[40px]"
                disabled={testing || !prefs?.discord_webhook_url}
                onClick={() => triggerTest("discord")}
              >
                <span>👾 Disparar Mensagem de Teste</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Histórico das Notificações Enviadas */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm sm:text-base font-semibold text-white">
            Histórico de Alertas Recentes ({items.length})
          </h2>
          <button
            type="button"
            onClick={loadAll}
            className="text-xs text-brand-400 hover:text-brand-300"
          >
            Atualizar lista
          </button>
        </div>

        {items.length === 0 ? (
          <div className="surface-panel text-center py-12 border-dashed">
            <span className="text-3xl mb-2 block" aria-hidden="true">🔔</span>
            <p className="font-semibold text-zinc-200">
              Nenhuma notificação enviada ainda
            </p>
            <p className="text-xs text-zinc-400 mt-1 max-w-sm mx-auto">
              Quando o assistente encontrar oportunidades que atinjam sua nota mínima de compatibilidade, os alertas enviados ficarão registrados aqui.
            </p>
          </div>
        ) : (
          <div className="space-y-2.5">
            {items.map((n) => {
              const isSent = n.status === "sent";
              const channelIcon =
                n.channel === "telegram" ? "💬" : n.channel === "discord" ? "👾" : "✉️";

              return (
                <div
                  key={n.id}
                  className="surface-panel flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 py-3 px-4 rounded-xl"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-lg shrink-0">{channelIcon}</span>
                    <div>
                      <h3 className="text-sm font-semibold text-white">
                        {n.job_title || `Oportunidade #${n.job_id}`}
                      </h3>
                      <p className="text-xs text-zinc-400">
                        {n.company || "Empresa Confidencial"} · Canal:{" "}
                        <span className="font-medium text-zinc-300 capitalize">{n.channel}</span>
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 self-end sm:self-center shrink-0">
                    {n.sent_at && (
                      <span className="text-xs text-zinc-400">
                        {new Date(n.sent_at).toLocaleString("pt-BR")}
                      </span>
                    )}
                    {isSent ? (
                      <span className="badge-emerald text-xs py-0.5 px-2">
                        ✓ Enviada
                      </span>
                    ) : (
                      <span
                        className="bg-rose-950/60 border border-rose-500/30 text-rose-300 text-xs px-2.5 py-0.5 rounded-full"
                        title={n.error}
                      >
                        ✕ Falha no envio
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
