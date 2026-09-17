#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$DIR"

echo "=========================================================="
echo "  Subindo Hermes Job Hunter 2.0 via Docker Compose (24/7)"
echo "=========================================================="

if [ ! -f "$DIR/.env" ]; then
    echo "Copiando .env.example para .env..."
    cp "$DIR/.env.example" "$DIR/.env"
fi

docker compose up -d --build

echo "=========================================================="
echo "  Serviços inicializados com sucesso!"
echo "  Dashboard Frontend: http://localhost:3000"
echo "  Backend API / Docs: http://localhost:8000/docs"
echo "  Para acompanhar os logs do agente:"
echo "    docker compose logs -f backend"
echo "=========================================================="
