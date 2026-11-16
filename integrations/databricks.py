"""Lê tabelas Gold da Rebeca a partir de CSV ou Databricks.

Dois modos:
- Arquivo (padrão, risco zero): a Rebeca exporta a Gold para data/entrada/ com
  o nome definido no contrato (para pedidos: gold_pedidos.csv).
- Databricks SQL: defina DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH,
  DATABRICKS_TOKEN e a variável da tabela (ex.: DATABRICKS_TABELA_GOLD_PEDIDOS=
  workspace.gold.pedidos). A consulta de pedido filtra pelo ID no Databricks.
"""

import os
import re

from .contratos import Contrato, ler_csv


def _variavel_tabela(contrato: Contrato) -> str:
    return f"DATABRICKS_TABELA_{contrato.nome.upper()}"


def _nome_tabela_sql(tabela: str) -> str:
    """Valida o nome configurado e cita cada parte como identificador SQL."""
    partes = tabela.split(".")
    if not 1 <= len(partes) <= 3 or any(
        not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", parte) for parte in partes
    ):
        raise ValueError(f"Nome de tabela inválido: {tabela!r}")
    return ".".join(f"`{parte}`" for parte in partes)


def _ler_pedido_databricks(contrato: Contrato, tabela: str, id_pedido: str) -> list[dict]:
    """Busca somente o pedido solicitado, usando parâmetro SQL para o valor."""
    from databricks import sql  # dependência opcional

    tabela_sql = _nome_tabela_sql(tabela)
    with sql.connect(
        server_hostname=os.environ["DATABRICKS_SERVER_HOSTNAME"],
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_TOKEN"],
    ) as conexao, conexao.cursor() as cursor:
        # LIMIT 0 lê o esquema e localiza a coluna traduzida de ID do pedido.
        cursor.execute(f"SELECT * FROM {tabela_sql} LIMIT 0")
        colunas = [descricao[0] for descricao in (cursor.description or [])]
        coluna_id = contrato.resolver_coluna("id_pedido", colunas)
        if coluna_id is None:
            raise ValueError(
                f"A tabela {tabela} não tem uma coluna reconhecida como id_pedido. "
                f"Colunas encontradas: {colunas}"
            )

        colunas_necessarias = []
        for canonica in contrato.colunas:
            original = contrato.resolver_coluna(canonica, colunas)
            if original is not None and original not in colunas_necessarias:
                colunas_necessarias.append(original)
        selecao_sql = ", ".join(
            f"`{coluna.replace('`', '``')}`" for coluna in colunas_necessarias
        )
        identificador_sql = f"`{coluna_id.replace('`', '``')}`"
        cursor.execute(
            f"SELECT {selecao_sql} FROM {tabela_sql} "
            f"WHERE {identificador_sql} = ? LIMIT 10",
            parameters=[id_pedido],
        )
        colunas = [descricao[0] for descricao in (cursor.description or [])]
        return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]


def carregar_pedido(contrato: Contrato, id_pedido: str) -> tuple[list[dict[str, str]], str]:
    """Busca um pedido pelo ID no Databricks ou no CSV local/amostra."""
    aviso = ""
    tabela = os.getenv(_variavel_tabela(contrato), "").strip()
    if tabela and os.getenv("DATABRICKS_TOKEN"):
        try:
            linhas = contrato.padronizar(
                _ler_pedido_databricks(contrato, tabela, id_pedido), tabela
            )
            return linhas, f"Databricks ({tabela})"
        except Exception as erro:  # noqa: BLE001 - permite fallback CSV na demo
            aviso = f" [falha ao consultar Databricks: {erro}]"

    caminho, eh_amostra = contrato.localizar_arquivo()
    if caminho is None:
        return [], f"tabela {contrato.nome} ainda não entregue" + aviso

    linhas = contrato.padronizar(ler_csv(caminho), caminho.name)
    alvo = (id_pedido or "").strip().casefold()
    encontradas = [linha for linha in linhas if linha["id_pedido"].casefold() == alvo]
    origem = ("AMOSTRA SINTÉTICA " if eh_amostra else "") + f"arquivo {caminho.name}"
    return encontradas, origem + aviso
