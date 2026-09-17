#!/usr/bin/env bash
# Instala e habilita o autostart do Hermes Job Hunter 2.0 via systemd --user.
# Uso: ./scripts/install-autostart.sh [--now]
#   sem args  -> instala + enable (inicia no próximo boot)
#   --now     -> além disso, troca o backend/frontend manuais pelo systemd agora
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
UNIT_DIR="$HOME/.config/systemd/user"
START_NOW=false
[ "${1:-}" = "--now" ] && START_NOW=true

mkdir -p "$UNIT_DIR"
cp "$DIR/scripts/systemd/hermes-jobhunter-backend.service" "$UNIT_DIR/"
cp "$DIR/scripts/systemd/hermes-jobhunter-frontend.service" "$UNIT_DIR/"

systemctl --user daemon-reload
systemctl --user enable hermes-jobhunter-backend.service hermes-jobhunter-frontend.service

# Garante que o user manager sobreviva ao logout/reboot sem sessão ativa
loginctl enable-linger "$USER" 2>/dev/null || sudo loginctl enable-linger "$USER" 2>/dev/null || true

echo "✅ Autostart instalado:"
systemctl --user is-enabled hermes-jobhunter-backend.service hermes-jobhunter-frontend.service

if [ "$START_NOW" = true ]; then
  echo "• Parando instâncias manuais (portas 8000/3000)..."
  "$DIR/scripts/stop.sh" || true
  sleep 2
  echo "• Iniciando via systemd..."
  systemctl --user restart hermes-jobhunter-backend.service
  systemctl --user restart hermes-jobhunter-frontend.service
  sleep 6
  "$DIR/scripts/status.sh" || true
  echo ""
  echo "Logs: journalctl --user -u hermes-jobhunter-backend -f"
  echo "      journalctl --user -u hermes-jobhunter-frontend -f"
else
  echo ""
  echo "Para migrar agora (trocar nohup -> systemd): $0 --now"
  echo "Para desfazer: ./scripts/uninstall-autostart.sh"
fi
