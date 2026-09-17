#!/usr/bin/env bash
# Remove o autostart do Hermes Job Hunter 2.0 (systemd --user).
set -e
systemctl --user disable --now hermes-jobhunter-frontend.service 2>/dev/null || true
systemctl --user disable --now hermes-jobhunter-backend.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/hermes-jobhunter-backend.service"
rm -f "$HOME/.config/systemd/user/hermes-jobhunter-frontend.service"
systemctl --user daemon-reload
echo "✅ Autostart removido. (linger mantido de propósito; desligue com: loginctl disable-linger $USER)"
