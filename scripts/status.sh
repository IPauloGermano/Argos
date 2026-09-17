#!/usr/bin/env bash

echo "=========================================================="
echo "  🔍 Verificando Status do Hermes Job Hunter 2.0"
echo "=========================================================="

BACKEND_UP=false
FRONTEND_UP=false

# Testa Backend
if curl -s -f http://localhost:8000/health > /dev/null 2>&1 || curl -s -f http://localhost:8000/api/health > /dev/null 2>&1; then
    BACKEND_UP=true
    BACKEND_INFO=$(curl -s http://localhost:8000/api/agent/status 2>/dev/null || echo "{}")
    echo "  [OK] ⚡ Backend FastAPI: ONLINE (http://localhost:8000)"
    echo "       📚 Docs / Swagger: http://localhost:8000/docs"
else
    echo "  [OFFLINE] ⚡ Backend FastAPI (porta 8000 não está respondendo)"
fi

# Testa Frontend
if curl -s -f http://localhost:3000 > /dev/null 2>&1; then
    FRONTEND_UP=true
    echo "  [OK] 🌐 Frontend Dashboard: ONLINE (http://localhost:3000)"
else
    echo "  [OFFLINE] 🌐 Frontend Dashboard (porta 3000 não está respondendo)"
fi

echo "=========================================================="
if [ "$BACKEND_UP" = true ] && [ "$FRONTEND_UP" = true ]; then
    echo "  🎉 Sistema 100% OPERACIONAL!"
    echo "  Acesse o painel no navegador: http://localhost:3000"
else
    echo "  ⚠️  Algum serviço está offline."
    echo "  Para iniciar: ./scripts/run_local.sh"
fi
echo "=========================================================="
