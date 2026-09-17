#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$DIR"

echo "=========================================================="
echo "  🚀 Iniciando Hermes Job Hunter 2.0 (Stack Completa)"
echo "=========================================================="

# 1. Libera portas se estiverem presas por processos antigos
fuser -k 8000/tcp 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true

# 2. Prepara ambiente virtual do backend
VENV_PATH="$DIR/.venv"
if [ ! -d "$VENV_PATH" ]; then
    echo "Criando ambiente virtual .venv..."
    python3 -m venv "$VENV_PATH"
    "$VENV_PATH/bin/pip" install --upgrade pip
    "$VENV_PATH/bin/pip" install -r "$DIR/backend/requirements.txt"
fi

# 3. Prepara dependências do frontend se necessário
if [ ! -d "$DIR/frontend/node_modules" ]; then
    echo "Instalando dependências do frontend..."
    cd "$DIR/frontend" && npm install && cd "$DIR"
fi

# 4. Variáveis de ambiente
export DATABASE_URL="${DATABASE_URL:-sqlite:///./hermes.db}"
export ENABLE_BUILTIN_SCHEDULER="${ENABLE_BUILTIN_SCHEDULER:-true}"
export DEFAULT_SEARCH_FREQUENCY_MINUTES="${DEFAULT_SEARCH_FREQUENCY_MINUTES:-60}"
export JOB_SOURCES="${JOB_SOURCES:-gupy,linkedin,remoteok,vagas,ciee,greenhouse,remotive,getonbrd,weworkremotely,jobicy}"

echo "• Banco de Dados: $DATABASE_URL"
echo "• Fontes Ativas:  $JOB_SOURCES"
echo "• Scheduler 24/7: $ENABLE_BUILTIN_SCHEDULER (${DEFAULT_SEARCH_FREQUENCY_MINUTES} min)"

# 5. Inicia o Backend em segundo plano
echo "• Iniciando Backend FastAPI (porta 8000)..."
cd "$DIR/backend"
"$VENV_PATH/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Aguarda o backend subir
sleep 2

# 6. Inicia o Frontend (Next.js na porta 3000)
echo "• Iniciando Frontend Web Dashboard (porta 3000)..."
cd "$DIR/frontend"
if [ -d "$DIR/frontend/.next" ]; then
    npm run start &
else
    npm run dev &
fi
FRONTEND_PID=$!

# Aguarda o frontend subir
sleep 2

# Função para encerrar ambos ao receber SIGINT/SIGTERM (Ctrl+C)
cleanup() {
    echo ""
    echo "Encerrando serviços do Hermes..."
    kill "$BACKEND_PID" 2>/dev/null || true
    kill "$FRONTEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
    wait "$FRONTEND_PID" 2>/dev/null || true
    echo "Serviços encerrados."
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

echo "=========================================================="
echo "  ✅ SISTEMA NO AR COM SUCESSO!"
echo "  🌐 Dashboard Web:  http://localhost:3000"
echo "  ⚡ Backend API:    http://localhost:8000"
echo "  📚 Documentação:   http://localhost:8000/docs"
echo "=========================================================="
echo "Pressione Ctrl+C para encerrar os serviços."

# Aguarda os processos
wait
