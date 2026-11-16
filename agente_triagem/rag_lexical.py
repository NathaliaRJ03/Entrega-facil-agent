"""Busca orientações sobre pedidos nos documentos locais usando BM25."""

import re
from functools import lru_cache
from pathlib import Path

from integrations.protecao_dados import mascarar_dados_sensiveis
from retriever.bm25 import BuscaBM25


PASTA_PROJETO = Path(__file__).resolve().parent.parent
PASTA_CONHECIMENTO = PASTA_PROJETO / "knowledge_base"


def dividir_markdown(texto: str) -> list[tuple[str, str]]:
    """Divide o Markdown em seções pelos títulos (#, ##, ###)."""
    secoes = re.split(r"\n(?=#{1,3} )", "\n" + texto)
    resultado = []
    for secao in secoes:
        secao = secao.strip()
        if not secao:
            continue
        titulo = secao.splitlines()[0].lstrip("# ").strip()
        resultado.append((titulo, secao))
    return resultado


def carregar_documentos() -> list[dict[str, str]]:
    """Carrega seções Markdown da base de conhecimento de pedidos."""
    documentos = []
    if not PASTA_CONHECIMENTO.exists():
        return documentos

    for arquivo in sorted(PASTA_CONHECIMENTO.glob("*.md")):
        texto = arquivo.read_text(encoding="utf-8-sig").strip()
        for titulo, secao in dividir_markdown(texto):
            documentos.append(
                {
                    "fonte": f"{arquivo.relative_to(PASTA_PROJETO)} > {titulo}",
                    "texto": secao,
                }
            )
    return documentos


@lru_cache(maxsize=1)
def criar_busca() -> BuscaBM25:
    """Cria o índice uma vez; reinicie o agente após editar os documentos."""
    return BuscaBM25(carregar_documentos())


def buscar_documentos_apoio(consulta: str) -> str:
    """Busca orientações documentadas sobre pedidos e atendimento.

    Args:
        consulta: Dúvida ou relato em texto livre para pesquisar nos documentos.
    """
    if not consulta or not consulta.strip():
        return "Escreva uma dúvida ou relato para pesquisar nos documentos."

    try:
        busca = criar_busca()
    except (OSError, ValueError, RuntimeError) as erro:
        return f"Não consegui carregar a base de conhecimento: {erro}"

    if not busca.documentos:
        return "A base está vazia. Adicione documentos de pedidos em knowledge_base/*.md."

    consulta_segura = mascarar_dados_sensiveis(consulta)
    resultados = busca.buscar(consulta_segura, limite=3)
    if not resultados:
        return "Não encontrei documentos com termos relevantes para essa consulta."

    respostas = ["Documentos de apoio encontrados:"]
    correcoes = resultados[0].get("termos_corrigidos", {})
    if correcoes:
        respostas.append(
            "Termos ajustados para a busca: "
            + ", ".join(f"{original} → {corrigido}" for original, corrigido in correcoes.items())
        )

    for numero, resultado in enumerate(resultados, start=1):
        texto = str(resultado["texto"])
        if len(texto) > 1000:
            texto = texto[:1000].rstrip() + "..."
        respostas.append(f"\n[{numero}] Fonte: {resultado['fonte']}\n{texto}")

    return "\n".join(respostas)
