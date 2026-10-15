"""
Configuração CORS partilhada pelos dois serviços do app (auth_server + api/main).

Lê origens da variável de ambiente ALLOWED_ORIGINS (lista separada por
vírgulas).

Fail-fast se ALLOWED_ORIGINS não estiver definida — evita servir sem CORS
ou cair em wildcard inadvertidamente.

Pré-requisito: o módulo que importa este ficheiro deve fazer load_dotenv()
antes (load_dotenv() para main.py, load_dotenv("auth.env") para auth_server.py).
"""

import os
from typing import List


def get_allowed_origins() -> List[str]:
    """Constrói whitelist CORS a partir da variável ALLOWED_ORIGINS."""
    raw_origins = os.getenv("ALLOWED_ORIGINS", "").strip()

    if not raw_origins:
        raise RuntimeError(
            "ALLOWED_ORIGINS não configurada. "
            "Define a variável com a lista de origens permitidas, separadas por vírgula. "
            "Exemplo: ALLOWED_ORIGINS=https://meu-app.vercel.app,http://localhost:8080"
        )

    origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    if not origins:
        raise RuntimeError("ALLOWED_ORIGINS está definida mas não tem origens válidas após parsing.")

    print(f"[cors] Origens permitidas: {origins}")
    return origins
