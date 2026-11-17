"""Testa a conexão com o Databricks e a leitura da tabela Gold de pedidos.

Uso: python scripts/testar_databricks.py [ID_PEDIDO]
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from integrations.contratos import PEDIDOS  # noqa: E402
from integrations.databricks import _ler_pedido_databricks  # noqa: E402

faltando = [
    v
    for v in (
        "DATABRICKS_SERVER_HOSTNAME",
        "DATABRICKS_HTTP_PATH",
        "DATABRICKS_TOKEN",
        "DATABRICKS_TABELA_GOLD_PEDIDOS",
    )
    if not os.getenv(v, "").strip()
]
if faltando:
    sys.exit(f"Variáveis faltando no .env: {', '.join(faltando)}")

contrato = PEDIDOS
tabela = os.environ["DATABRICKS_TABELA_GOLD_PEDIDOS"].strip()
id_pedido = sys.argv[1] if len(sys.argv) > 1 else "PED-1001"

print(f"Consultando {tabela} pelo pedido {id_pedido}...")
linhas = _ler_pedido_databricks(contrato, tabela, id_pedido)
print(f"Conexão OK. {len(linhas)} linha(s) encontrada(s).")
for linha in contrato.padronizar(linhas, tabela):
    print(linha)
