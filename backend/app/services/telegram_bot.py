from __future__ import annotations
import html
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_
from app.models.entities import (
    User, CandidateProfile, SearchPreferences, Job, JobMatch, Notification, CircuitBreakerRecord
)
from app.services.favorites import add_favorite, remove_favorite, list_favorites
from app.services.feedback import record_feedback
from app.services.reports import generate_weekly_report, format_weekly_report_telegram
from app.services.scheduler import get_scheduler_status, pause_scheduler, resume_scheduler


def escape_html(text: str) -> str:
    """Escapa caracteres HTML para formatação segura no Telegram."""
    if not text:
        return ""
    return html.escape(str(text))


def truncate(text: str, max_len: int = 4000) -> str:
    """Garante que a mensagem não exceda o limite de 4096 caracteres do Telegram."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 15] + "... [truncado]"


class TelegramBotService:
    """
    Motor completo de atendimento interativo do Bot Telegram do Hermes.
    Processa comandos, mensagens em linguagem natural, botões inline e callbacks.
    """

    @staticmethod
    def get_or_create_user(db: Session, telegram_chat_id: str, from_user: Optional[dict] = None) -> User:
        """Garante a existência do usuário associado ao chat_id do Telegram."""
        user = db.scalar(select(User).where(User.telegram_chat_id == str(telegram_chat_id)))
        if not user:
            # Tenta associar ao usuário default existente se não tiver telegram_chat_id
            user = db.scalar(select(User).where(User.id == 1))
            if user and not user.telegram_chat_id:
                user.telegram_chat_id = str(telegram_chat_id)
                db.commit()
                db.refresh(user)
                return user

            # Cria novo usuário se não existir
            name = "Usuário Telegram"
            if from_user:
                first = from_user.get("first_name", "")
                last = from_user.get("last_name", "")
                name = f"{first} {last}".strip() or name

            email = f"telegram_{telegram_chat_id}@hermes.local"
            user = User(
                name=name,
                email=email,
                telegram_chat_id=str(telegram_chat_id)
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            # Cria perfil e preferências vazios para o novo usuário
            prof = CandidateProfile(user_id=user.id, headline="Profissional em Busca de Oportunidades")
            prefs = SearchPreferences(
                user_id=user.id,
                telegram_chat_id=str(telegram_chat_id),
                telegram_enabled=True,
                desired_roles=["Desenvolvedor Backend", "Desenvolvedor Python"],
                seniority_levels=["estagio", "junior"],
                work_modes=["remote", "hybrid"]
            )
            db.add(prof)
            db.add(prefs)
            db.commit()

        return user

    @classmethod
    def handle_update(cls, update: dict, db: Session) -> dict:
        """
        Ponto de entrada para processamento de qualquer evento/update do Telegram.
        Retorna dicionário contendo action, chat_id, text, reply_markup, callback_query_id.
        """
        # 1. Tratamento de Callback Query (clique em botão inline)
        if "callback_query" in update:
            cb = update["callback_query"]
            chat_id = str(cb.get("message", {}).get("chat", {}).get("id") or cb.get("from", {}).get("id"))
            data = cb.get("data", "")
            user = cls.get_or_create_user(db, chat_id, cb.get("from"))
            return cls.handle_callback(db, user, chat_id, data, cb.get("id"))

        # 2. Tratamento de Mensagem de Texto
        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = (message.get("text") or "").strip()
        from_user = message.get("from")

        if not chat_id:
            return {"action": "ignored", "reason": "no_chat_id"}

        user = cls.get_or_create_user(db, chat_id, from_user)

        # Roteamento de comandos (/command)
        if text.startswith("/"):
            parts = text.split()
            cmd = parts[0].lower().split("@")[0]  # remove menção ao bot se houver
            args = parts[1:]
            return cls.handle_command(db, user, chat_id, cmd, args)

        # Roteamento de mensagens de texto livres / conversacionais
        return cls.handle_conversational_text(db, user, chat_id, text)

    @classmethod
    def handle_command(cls, db: Session, user: User, chat_id: str, cmd: str, args: list[str]) -> dict:
        """Processa comandos específicos iniciados por '/'."""
        user = user or cls.get_or_create_user(db, chat_id)
        if cmd == "/start":
            msg = (
                f"👋 <b>Olá, {escape_html(user.name)}! Seja bem-vindo ao Hermes Job Hunter 2.0.</b>\n\n"
                "⚡ Sou seu assistente autônomo de busca e monitoramento contínuo de vagas 24/7.\n"
                "Varro constantemente portais como LinkedIn, Gupy, Remotive, Vagas, CIEE e Greenhouse "
                "para encontrar as oportunidades mais compatíveis com o seu perfil.\n\n"
                "🎯 <b>Comandos Principais:</b>\n"
                "• /vagas — Ver as melhores oportunidades recomendadas para você\n"
                "• /perfil — Ver o resumo do seu perfil profissional cadastrado\n"
                "• /filtros — Consultar suas preferências de busca e modalidades\n"
                "• /favoritos — Ver as vagas que você favoritou\n"
                "• /status — Status da automação 24/7 e telemetria\n"
                "• /relatorio — Relatório semanal dos últimos 7 dias com Top 10\n"
                "• /ajuda — Lista completa de todos os comandos"
            )
            keyboard = [
                [{"text": "💼 Ver Vagas", "callback_data": "cmd:vagas"}, {"text": "👤 Meu Perfil", "callback_data": "cmd:perfil"}],
                [{"text": "⚙️ Filtros", "callback_data": "cmd:filtros"}, {"text": "⭐ Favoritos", "callback_data": "cmd:favoritos"}],
                [{"text": "📊 Relatório 7 Dias", "callback_data": "cmd:relatorio"}, {"text": "🤖 Status", "callback_data": "cmd:status"}]
            ]
            return {"action": "sendMessage", "chat_id": chat_id, "text": msg, "reply_markup": {"inline_keyboard": keyboard}}

        elif cmd in ("/help", "/ajuda"):
            msg = (
                "📖 <b>Guia de Comandos do Hermes Job Hunter</b>\n\n"
                "<b>Gestão de Vagas:</b>\n"
                "• /vagas — Top vagas com maior score de compatibilidade\n"
                "• /novas — Vagas descobertas nas últimas 24 horas\n"
                "• /favoritos — Lista de oportunidades favoritadas por você\n"
                "• /relatorio — Relatório consolidado dos últimos 7 dias\n\n"
                "<b>Perfil e Preferências:</b>\n"
                "• /perfil — Exibe seu perfil atual e tecnologias mapeadas\n"
                "• /perfis — Informações sobre seus perfis cadastrados\n"
                "• /filtros — Exibe seus critérios de filtragem ativos\n"
                "• /reset — Reinicia preferências para os padrões\n\n"
                "<b>Automação 24/7 & Conectores:</b>\n"
                "• /status — Estado do scheduler 24/7 e métricas gerais\n"
                "• /fontes — Lista portais monitorados e status de conectividade\n"
                "• /pausar — Pausa temporariamente a busca autônoma\n"
                "• /retomar — Retoma a busca autônoma contínua\n"
                "• /teste — Diagnóstico rápido de integridade do sistema"
            )
            return {"action": "sendMessage", "chat_id": chat_id, "text": msg}

        elif cmd == "/perfil":
            prof = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
            if not prof:
                return {"action": "sendMessage", "chat_id": chat_id, "text": "⚠️ Nenhum perfil encontrado para o seu usuário."}

            skills_str = ", ".join(prof.skills[:12]) if prof.skills else "Nenhuma skill listada"
            roles_str = ", ".join(prof.roles[:4]) if prof.roles else "Desenvolvedor"
            langs_str = ", ".join(prof.languages) if prof.languages else "Português"

            msg = (
                f"👤 <b>Perfil do Candidato: {escape_html(user.name)}</b>\n\n"
                f"📌 <b>Headline:</b> {escape_html(prof.headline or 'Desenvolvedor')}\n"
                f"🎓 <b>Senioridade:</b> {prof.seniority.upper()} | <b>Experiência:</b> {prof.years_experience} ano(s)\n"
                f"💼 <b>Cargos Alvo:</b> {escape_html(roles_str)}\n"
                f"🛠️ <b>Tecnologias ({len(prof.skills or [])}):</b>\n<code>{escape_html(skills_str)}</code>\n"
                f"🌐 <b>Idiomas:</b> {escape_html(langs_str)}\n\n"
                f"📝 <b>Resumo:</b>\n<i>{escape_html((prof.summary or '')[:300])}...</i>"
            )
            return {"action": "sendMessage", "chat_id": chat_id, "text": msg}

        elif cmd == "/perfis":
            prof = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
            msg = (
                f"📋 <b>Perfis Configurados</b>\n\n"
                f"• Perfil Ativo (Padrão): <b>{escape_html(user.name)}</b>\n"
                f"  Headline: {escape_html(prof.headline if prof else 'N/A')}\n"
                f"  Senioridade: {(prof.seniority if prof else 'junior').upper()}\n\n"
                "<i>O Hermes opera com perfil único vinculado à sua conta local.</i>"
            )
            return {"action": "sendMessage", "chat_id": chat_id, "text": msg}

        elif cmd == "/filtros":
            prefs = db.scalar(select(SearchPreferences).where(SearchPreferences.user_id == user.id))
            if not prefs:
                return {"action": "sendMessage", "chat_id": chat_id, "text": "⚠️ Nenhuma preferência configurada."}

            roles = ", ".join(prefs.desired_roles or []) or "Aberto"
            modes = ", ".join(prefs.work_modes or []) or "Todos"
            locs = ", ".join(prefs.locations or []) or "Brasil / Remoto"
            sen = ", ".join(prefs.seniority_levels or []) or "Todas"
            ex_comp = ", ".join(prefs.excluded_companies or []) or "Nenhuma"
            ex_kw = ", ".join(prefs.excluded_keywords or []) or "Nenhuma"

            msg = (
                "⚙️ <b>Filtros de Busca Ativos</b>\n\n"
                f"🎯 <b>Cargos Desejados:</b> {escape_html(roles)}\n"
                f"📍 <b>Modalidades:</b> {escape_html(modes)}\n"
                f"🌍 <b>Localizações:</b> {escape_html(locs)}\n"
                f"📶 <b>Senioridades:</b> {escape_html(sen)}\n"
                f"⭐ <b>Score Mínimo p/ Alerta:</b> ≥ {prefs.minimum_match_score}%\n"
                f"⏱️ <b>Frequência de Busca:</b> A cada {prefs.search_frequency_minutes} min\n"
                f"🚫 <b>Empresas Ignoradas:</b> {escape_html(ex_comp)}\n"
                f"🚫 <b>Palavras Proibidas:</b> {escape_html(ex_kw)}"
            )
            return {"action": "sendMessage", "chat_id": chat_id, "text": msg}

        elif cmd == "/vagas":
            # Retorna as melhores vagas ordenadas por compatibilidade
            matches = db.execute(
                select(Job, JobMatch)
                .join(JobMatch, JobMatch.job_id == Job.id)
                .where(Job.status == "active")
                .order_by(JobMatch.score.desc())
                .limit(5)
            ).all()

            if not matches:
                return {"action": "sendMessage", "chat_id": chat_id, "text": "💼 Nenhuma vaga cadastrada ou compatível no momento. Use /status para checar o assistente."}

            messages = []
            for job, match in matches:
                score = match.score if match else 0
                pub_date = job.published_at.strftime("%d/%m/%Y") if job.published_at else "Recente"
                reason_bullets = "\n".join(f"• {escape_html(r)}" for r in (match.reasoning or [])[:3])

                text_card = (
                    f"💼 <b>{escape_html(job.title)}</b> (<b>{score}% Match</b>)\n"
                    f"🏢 {escape_html(job.company)} | 📍 {escape_html(job.location)} ({job.work_mode})\n"
                    f"📅 Publicada em: {pub_date} | Fonte: {job.source.upper()}\n\n"
                    f"💡 <b>Motivos da Relevância:</b>\n{reason_bullets}\n"
                )

                keyboard = [
                    [{"text": "🔗 Acessar Vaga", "url": job.url}],
                    [
                        {"text": "⭐ Favoritar", "callback_data": f"fav:{job.id}"},
                        {"text": "🚫 Ignorar", "callback_data": f"ignore:{job.id}"}
                    ],
                    [
                        {"text": "👍 Relevante", "callback_data": f"fb_pos:{job.id}"},
                        {"text": "👎 Não Relevante", "callback_data": f"fb_neg:{job.id}"}
                    ]
                ]
                messages.append({
                    "action": "sendMessage",
                    "chat_id": chat_id,
                    "text": text_card,
                    "reply_markup": {"inline_keyboard": keyboard}
                })

            # Retorna a primeira mensagem com o total de vagas encontradas sem referência circular
            return {
                "action": "sendMessage",
                "chat_id": chat_id,
                "text": messages[0]["text"],
                "reply_markup": messages[0]["reply_markup"],
                "total_count": len(messages),
                "additional_messages": [m["text"] for m in messages[1:]]
            }

        elif cmd == "/novas":
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            jobs = db.execute(
                select(Job, JobMatch)
                .outerjoin(JobMatch, JobMatch.job_id == Job.id)
                .where(Job.status == "active", (Job.discovered_at >= cutoff) | (Job.published_at >= cutoff))
                .order_by(JobMatch.score.desc().nullslast(), Job.id.desc())
                .limit(5)
            ).all()

            if not jobs:
                return {"action": "sendMessage", "chat_id": chat_id, "text": "✨ Nenhuma nova vaga catalogada nas últimas 24 horas. O monitoramento contínuo continua rodando!"}

            msg_lines = ["✨ <b>Vagas Descobertas nas Últimas 24 Horas:</b>\n"]
            for idx, (j, m) in enumerate(jobs, 1):
                sc = m.score if m else 0
                msg_lines.append(
                    f"<b>{idx}. {escape_html(j.title)}</b> (Score: {sc}%)\n"
                    f"   🏢 {escape_html(j.company)} | 📍 {escape_html(j.location)}\n"
                    f"   🔗 <a href='{j.url}'>Ver Oportunidade</a>\n"
                )
            return {"action": "sendMessage", "chat_id": chat_id, "text": "\n".join(msg_lines)}

        elif cmd == "/favoritos":
            favs = list_favorites(db, user.id)
            if not favs:
                return {"action": "sendMessage", "chat_id": chat_id, "text": "⭐ Você ainda não favoritou nenhuma vaga.\nUse o botão <b>⭐ Favoritar</b> ao consultar vagas com /vagas."}

            msg_lines = ["⭐ <b>Suas Vagas Favoritas:</b>\n"]
            keyboards = []
            for idx, f in enumerate(favs[:8], 1):
                msg_lines.append(
                    f"<b>{idx}. {escape_html(f['title'])}</b>\n"
                    f"   🏢 {escape_html(f['company'])} | 📍 {escape_html(f['location'])}\n"
                    f"   🔗 <a href='{f['url']}'>Acessar</a>\n"
                )
                keyboards.append([{"text": f"❌ Remover #{idx}: {f['title'][:20]}...", "callback_data": f"unfav:{f['job_id']}"}])

            return {
                "action": "sendMessage",
                "chat_id": chat_id,
                "text": "\n".join(msg_lines),
                "reply_markup": {"inline_keyboard": keyboards}
            }

        elif cmd == "/status":
            sched = get_scheduler_status()
            total_jobs = db.scalar(select(func.count(Job.id))) or 0
            active_jobs = db.scalar(select(func.count(Job.id)).where(Job.status == "active")) or 0
            best_score = db.scalar(select(func.max(JobMatch.score))) or 0

            status_str = "🟢 Ativo e Monitorando 24/7" if sched["running"] and not sched["is_paused"] else "🟡 Pausado"
            next_run = sched.get("next_search") or "Em instantes"

            msg = (
                "🤖 <b>Status do Hermes Job Hunter 2.0</b>\n\n"
                f"• <b>Estado:</b> {status_str}\n"
                f"• <b>Próxima busca programada:</b> <code>{next_run}</code>\n"
                f"• <b>Frequência de varredura:</b> A cada {sched.get('frequency_minutes', 60)} min\n"
                f"• <b>Total de vagas no catálogo:</b> <b>{total_jobs}</b>\n"
                f"• <b>Vagas ativas e verificadas:</b> <b>{active_jobs}</b>\n"
                f"• <b>Maior grau de compatibilidade:</b> <b>{best_score}%</b>\n"
            )
            return {"action": "sendMessage", "chat_id": chat_id, "text": msg}

        elif cmd == "/fontes":
            cbs = db.scalars(select(CircuitBreakerRecord)).all()
            cb_map = {cb.source_name: cb.state for cb in cbs}
            all_sources = ["linkedin", "gupy", "remotive", "greenhouse", "vagas", "ciee", "indeed"]

            lines = ["🌐 <b>Fontes de Oportunidades Conectadas:</b>\n"]
            for src in all_sources:
                st = cb_map.get(src, "CLOSED")
                badge = "🟢 Ativo" if st == "CLOSED" else ("🔴 Circuit Breaker Aberto" if st == "OPEN" else "🟡 Testando")
                lines.append(f"• <b>{src.capitalize()}:</b> {badge}")

            return {"action": "sendMessage", "chat_id": chat_id, "text": "\n".join(lines)}

        elif cmd == "/pausar":
            pause_scheduler()
            return {"action": "sendMessage", "chat_id": chat_id, "text": "⏸️ <b>Busca contínua pausada.</b> O assistente não fará varreduras automáticas até que você envie /retomar."}

        elif cmd == "/retomar":
            resume_scheduler()
            return {"action": "sendMessage", "chat_id": chat_id, "text": "▶️ <b>Busca contínua retomada com sucesso!</b> O assistente voltou a monitorar o mercado 24/7."}

        elif cmd == "/relatorio":
            report_data = generate_weekly_report(db, user.id, top_limit=10)
            formatted_text = format_weekly_report_telegram(report_data)
            return {"action": "sendMessage", "chat_id": chat_id, "text": formatted_text}

        elif cmd == "/reset":
            prefs = db.scalar(select(SearchPreferences).where(SearchPreferences.user_id == user.id))
            if prefs:
                prefs.excluded_companies = []
                prefs.excluded_keywords = []
                prefs.excluded_jobs = []
                prefs.minimum_match_score = 70
                db.commit()
            return {"action": "sendMessage", "chat_id": chat_id, "text": "🔄 <b>Filtros reiniciados com sucesso!</b> As listas de exclusão foram limpas e o score mínimo voltou para 70%."}

        elif cmd == "/teste":
            total_jobs = db.scalar(select(func.count(Job.id))) or 0
            return {
                "action": "sendMessage",
                "chat_id": chat_id,
                "text": f"✅ <b>Teste de Diagnóstico: OK!</b>\n• Banco de dados: Conectado ({total_jobs} vagas)\n• Telegram Bot: Operacional e responsivo\n• Usuário: {escape_html(user.name)}"
            }

        else:
            return {
                "action": "sendMessage",
                "chat_id": chat_id,
                "text": f"❓ Comando <code>{escape_html(cmd)}</code> não reconhecido.\nEnvie /ajuda para consultar todos os comandos disponíveis."
            }

    @classmethod
    def handle_conversational_text(cls, db: Session, user: User, chat_id: str, text: str) -> dict:
        """Trata mensagens de texto livres sem entrar em estado inconsistente."""
        user = user or cls.get_or_create_user(db, chat_id)
        lower = text.lower().strip()

        # Saudações comuns
        greetings = ("oi", "ola", "olá", "opa", "bom dia", "boa tarde", "boa noite", "e ai", "e aí", "hello")
        if any(lower.startswith(g) or g in lower.split() or g in lower for g in greetings):
            msg = (
                f"Olá, <b>{escape_html(user.name)}</b>! Como posso ajudar você hoje?\n\n"
                "• Envie /vagas para ver vagas recomendadas\n"
                "• Envie /perfil para conferir seu perfil\n"
                "• Envie /relatorio para ver o balanço semanal de vagas\n"
                "• Envie /ajuda para ver todos os comandos"
            )
            return {"action": "sendMessage", "chat_id": chat_id, "text": msg}

        # Intenção de busca por estágio
        if "estagio" in lower or "estágio" in lower:
            msg = (
                "🎓 <b>Identifiquei seu interesse em vagas de Estágio!</b>\n\n"
                "O Hermes está configurado para priorizar oportunidades de nível inicial.\n"
                "Envie /vagas para conferir as recomendações atuais ou /filtros para checar seus critérios."
            )
            return {"action": "sendMessage", "chat_id": chat_id, "text": msg}

        # Termo de tecnologia comum
        if lower in ("python", "django", "sql", "docker", "fastapi", "backend"):
            jobs_count = db.scalar(
                select(func.count(Job.id)).where(Job.title.ilike(f"%{lower}%"))
            ) or 0
            msg = (
                f"🔍 <b>Encontrei {jobs_count} vaga(s) com o termo '{escape_html(text)}' no catálogo!</b>\n\n"
                "Envie /vagas para listar as mais compatíveis com o seu perfil geral."
            )
            return {"action": "sendMessage", "chat_id": chat_id, "text": msg}

        # Consulta dinâmica de localização registrada nas preferências
        user_locs = (user.preferences.locations or []) if (user and hasattr(user, "preferences") and user.preferences) else []
        matched_loc = next((loc for loc in user_locs if loc and (loc.lower() in lower or lower in loc.lower())), None)
        if matched_loc:
            msg = (
                f"📍 <b>A localização '{escape_html(matched_loc)}' está registrada nas suas preferências de busca.</b>\n\n"
                "O assistente prioriza oportunidades locais presenciais/híbridas para sua região e posições 100% remotas."
            )
            return {"action": "sendMessage", "chat_id": chat_id, "text": msg}

        # Texto não reconhecido / aleatório (ex: "asdfgh")
        msg = (
            "🤖 Recebi sua mensagem, mas não compreendi como uma ação direta.\n\n"
            "• Para ver oportunidades, envie /vagas\n"
            "• Para ver seu perfil, envie /perfil\n"
            "• Para consultar a lista completa de comandos, envie /ajuda"
        )
        return {"action": "sendMessage", "chat_id": chat_id, "text": msg}

    @classmethod
    def handle_callback(cls, db: Session, user: User, chat_id: str, data: str, callback_id: Optional[str] = None) -> dict:
        """Processa cliques em botões inline do Telegram."""
        if data.startswith("cmd:"):
            cmd = "/" + data[4:]
            return cls.handle_command(db, user, chat_id, cmd, [])

        if data.startswith("fav:"):
            job_id = int(data.split(":")[1])
            add_favorite(db, user.id, job_id)
            job = db.get(Job, job_id)
            title = job.title if job else "Vaga"
            return {
                "action": "answerCallbackQuery",
                "callback_query_id": callback_id,
                "text": f"⭐ Vaga '{title[:30]}' adicionada aos seus favoritos!",
                "show_alert": False,
                "follow_up_message": f"⭐ A vaga <b>{escape_html(title)}</b> foi salva nos seus /favoritos!"
            }

        if data.startswith("unfav:"):
            job_id = int(data.split(":")[1])
            remove_favorite(db, user.id, job_id)
            return {
                "action": "answerCallbackQuery",
                "callback_query_id": callback_id,
                "text": "❌ Vaga removida dos seus favoritos.",
                "show_alert": False,
                "follow_up_message": "❌ Vaga removida dos favoritos com sucesso. Consulte /favoritos para a lista atualizada."
            }

        if data.startswith("ignore:"):
            job_id = int(data.split(":")[1])
            job = db.get(Job, job_id)
            prefs = db.scalar(select(SearchPreferences).where(SearchPreferences.user_id == user.id))
            if prefs and job:
                ex_jobs = list(prefs.excluded_jobs or [])
                if job.id not in ex_jobs:
                    ex_jobs.append(job.id)
                    prefs.excluded_jobs = ex_jobs
                    db.commit()

            return {
                "action": "answerCallbackQuery",
                "callback_query_id": callback_id,
                "text": f"🚫 Vaga '{job.title[:30] if job else ''}' ignorada.",
                "show_alert": False,
                "follow_up_message": f"🚫 A oportunidade foi ocultada das suas recomendações futuras."
            }

        if data.startswith("fb_pos:"):
            job_id = int(data.split(":")[1])
            record_feedback(db, user_id=user.id, job_id=job_id, is_positive=True)
            return {
                "action": "answerCallbackQuery",
                "callback_query_id": callback_id,
                "text": "👍 Obrigado pelo feedback! Vamos calibrar futuras recomendações.",
                "show_alert": False
            }

        if data.startswith("fb_neg:"):
            job_id = int(data.split(":")[1])
            record_feedback(db, user_id=user.id, job_id=job_id, is_positive=False)
            return {
                "action": "answerCallbackQuery",
                "callback_query_id": callback_id,
                "text": "👎 Feedback registrado. Essa vaga terá menos relevância.",
                "show_alert": False
            }

        return {
            "action": "answerCallbackQuery",
            "callback_query_id": callback_id,
            "text": "Ação recebida.",
            "show_alert": False
        }
