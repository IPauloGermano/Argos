FROM python:3.12-slim

WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    # Dependencias de sistema do Chromium (CloakBrowser)
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# CloakBrowser é dependência OPCIONAL (fallback anti-bot do Indeed).
# Falha na instalação do Chromium não deve quebrar o build: o runtime
# detecta via cloak_available() e usa HTTP puro. Log explícito, sem mascarar.
RUN pip install --no-cache-dir -r requirements.txt \
    && (python -m cloakbrowser install && echo "[build] cloakbrowser chromium ok" || echo "[build] WARNING: cloakbrowser chromium indisponível (opcional, continuando sem browser fallback)")

COPY app ./app
# Alembic precisa estar na imagem: lifespan executa `upgrade head` no Postgres.
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

ENV PYTHONUNBUFFERED=1

# Hardening: executa como usuário não-root
RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /code
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
