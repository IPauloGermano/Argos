#!/usr/bin/env bash

echo "Encerrando serviços do Hermes Job Hunter..."
fuser -k 8000/tcp 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "next start" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true

sleep 1
echo "✅ Todos os processos nas portas 8000 e 3000 foram encerrados."
