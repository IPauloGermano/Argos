#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$DIR/backend"

echo "=========================================================="
echo "  Executando Suíte de Testes Automatizados do Hermes"
echo "=========================================================="

DATABASE_URL="sqlite:///./test.db" "$DIR/.venv/bin/python" -m pytest -v
rm -f "$DIR/backend/test.db"
