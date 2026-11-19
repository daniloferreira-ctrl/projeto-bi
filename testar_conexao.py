"""Testa a conexão com o Postgres e mostra o erro real (com acentos)."""
import os
from pathlib import Path

arq = Path(__file__).parent / ".env"
if arq.exists():
    for linha in arq.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.strip().startswith("#"):
            k, v = linha.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

cfg = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", "5432"),
    dbname=os.getenv("DB_NAME", "backoffice_local"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASS", ""),
)
print("Tentando conectar em:", {k: v for k, v in cfg.items() if k != "password"},
      "| senha preenchida:", "sim" if cfg["password"] else "NÃO")

import psycopg2
try:
    with psycopg2.connect(**cfg) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM cm_sync.vw_contratos")
        print("OK! Conectou. Linhas em vw_contratos:", cur.fetchone()[0])
except UnicodeDecodeError as e:
    print("ERRO DO BANCO:", e.object.decode("cp1252", errors="replace"))
except Exception as e:
    print("ERRO:", e)