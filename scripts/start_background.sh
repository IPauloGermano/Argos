#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$DIR"

echo "=========================================================="
echo "  🚀 Iniciando Hermes Job Hunter em SEGUNDO PLANO (Daemon)"
echo "=========================================================="

# Libera portas antigas
fuser -k 8000/tcp 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true

# Configura ambiente
VENV_PATH="$DIR/.venv"
if [ ! -d "$VENV_PATH" ]; then
    echo "Configurando ambiente virtual..."
    python3 -m venv "$VENV_PATH"
    "$VENV_PATH/bin/pip" install -r "$DIR/backend/requirements.txt"
fi

export DATABASE_URL="${DATABASE_URL:-sqlite:///./hermes.db}"
export ENABLE_BUILTIN_SCHEDULER="${ENABLE_BUILTIN_SCHEDULER:-true}"
export DEFAULT_SEARCH_FREQUENCY_MINUTES="${DEFAULT_SEARCH_FREQUENCY_MINUTES:-60}"
export JOB_SOURCES="${JOB_SOURCES:-gupy,linkedin,indeed,vagas,ciee,greenhouse,remotive}"

# Inicia Backend em segundo plano com setsid e nohup
echo "• Iniciando Backend (porta 8000)..."
cd "$DIR/backend"
setsid nohup "$VENV_PATH/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000 < /dev/null > "$DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$DIR/.backend.pid"
disown $BACKEND_PID 2>/dev/null || true

# Inicia Frontend em segundo plano com setsid e nohup
echo "• Iniciando Frontend (porta 3000)..."
cd "$DIR/frontend"
if [ -d "$DIR/frontend/.next" ]; then
    setsid nohup npm run start < /dev/null > "$DIR/frontend.log" 2>&1 &
else
    setsid nohup npm run dev < /dev/null > "$DIR/frontend.log" 2>&1 &
fi
FRONTEND_PID=$!
echo $FRONTEND_PID > "$DIR/.frontend.pid"
disown $FRONTEND_PID 2>/dev/null || true

cd "$DIR"
echo "Aguardando inicialização..."
sleep 3

# Valida status
./scripts/status.sh
echo ""
echo "Logs disponíveis em:"
echo "  • Backend:  $DIR/backend.log"
echo "  • Frontend: $DIR/frontend.log"
echo ""
echo "Para parar os serviços a qualquer momento:"
echo "  ./scripts/stop.sh"
echo "=========================================================="
