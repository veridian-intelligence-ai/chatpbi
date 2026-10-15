# ─────────────────────────────────────────────
# API e login do app: Dockerfile
# Base: Python 3.12 slim
# ─────────────────────────────────────────────

FROM python:3.12-slim

# ─── Dependências do sistema ───
RUN apt-get update && apt-get install -y --no-install-recommends \
    unixodbc \
    unixodbc-dev \
    curl \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ─── Ambiente Python ───
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ─── Working directory ───
WORKDIR /app

# ─── Instalar dependências Python ───
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# ─── Copiar código ───
COPY api/ ./api/
COPY auth_server.py ./
COPY cors_config.py ./
COPY db_bootstrap.py ./
# Scripts de baseline do schema (db_bootstrap.py corre-os numa BD vazia).
COPY scripts/migrations/ ./scripts/migrations/

# ─── Configuração runtime ───
EXPOSE 8000

# ─── Comando default ───
# Corre uvicorn a partir da pasta api/, onde main.py espera encontrar
# os módulos irmãos (prompts, sql_tool, etc.) sem prefixo de package.
WORKDIR /app/api
# PORT vem do Railway; 8000 em local. O serviço auth usa a mesma imagem com
# outro start command (ver CLAUDE.md).
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
