"""Lê a tabela Gold de pedidos no Databricks (única fonte de pedidos).

Defina DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN e a
variável da tabela (ex.: DATABRICKS_TABELA_GOLD_PEDIDOS=catalogo.schema.tabela).
A consulta filtra pelo ID do pedido no próprio Databricks.
"""

import os
import re

from .contratos import Contrato


LIMITE_LINHAS_POR_PEDIDO = 50
_TIPOS_INTEIROS = {"tinyint", "smallint", "int", "integer", "bigint", "long"}


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
        descricoes = cursor.description or []
        colunas = [descricao[0] for descricao in descricoes]
        coluna_id = contrato.resolver_coluna("id_pedido", colunas)
        if coluna_id is None:
            raise ValueError(
                f"A tabela {tabela} não tem uma coluna reconhecida como id_pedido. "
                f"Colunas encontradas: {colunas}"
            )

        # O cliente digita "5000100"; a Gold pode guardar 5000100 (número) ou
        # "0005000100" (texto). IDs só com dígitos são comparados como número.
        tipo_id = str(dict((d[0], d[1]) for d in descricoes).get(coluna_id, "")).lower()
        valor_id = id_pedido.strip()
        identificador_sql = f"`{coluna_id.replace('`', '``')}`"
        numerico = re.fullmatch(r"\d{1,18}", valor_id) is not None
        if tipo_id in _TIPOS_INTEIROS:
            if not numerico:
                return []  # evita erro de conversão no SQL (que cairia no CSV)
            filtro, parametros = f"{identificador_sql} = ?", [int(valor_id)]
        elif numerico:
            filtro = (
                f"({identificador_sql} = ? OR "
                f"try_cast({identificador_sql} AS BIGINT) = ?)"
            )
            parametros = [valor_id, int(valor_id)]
        else:
            filtro, parametros = f"{identificador_sql} = ?", [valor_id]

        colunas_necessarias = []
        for canonica in contrato.colunas:
            original = contrato.resolver_coluna(canonica, colunas)
            if original is not None and original not in colunas_necessarias:
                colunas_necessarias.append(original)
        selecao_sql = ", ".join(
            f"`{coluna.replace('`', '``')}`" for coluna in colunas_necessarias
        )
        # Uma linha por remessa: traz todas (até o limite) para o agente
        # consolidar o pedido. Acima do limite, a consulta é bloqueada.
        cursor.execute(
            f"SELECT {selecao_sql} FROM {tabela_sql} "
            f"WHERE {filtro} LIMIT {LIMITE_LINHAS_POR_PEDIDO + 1}",
            parameters=parametros,
        )
        colunas = [descricao[0] for descricao in (cursor.description or [])]
        return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]


def carregar_pedido(contrato: Contrato, id_pedido: str) -> tuple[list[dict[str, str]], str]:
    """Busca um pedido pelo ID somente na tabela Gold do Databricks.

    Não há fonte reserva: sem Databricks configurado ou com falha na consulta,
    retorna lista vazia. O agente nunca usa CSV local nem amostra sintética.
    """
    tabela = os.getenv(_variavel_tabela(contrato), "").strip()
    if not (tabela and os.getenv("DATABRICKS_TOKEN")):
        return [], "Databricks não configurado (Gold indisponível)"
    try:
        linhas = contrato.padronizar(
            _ler_pedido_databricks(contrato, tabela, id_pedido), tabela
        )
    except Exception as erro:  # noqa: BLE001 - sem reserva: falha = sem dados
        return [], f"Databricks ({tabela}) [falha ao consultar: {erro}]"
    return linhas, f"Databricks ({tabela})"
