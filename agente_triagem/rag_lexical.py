"""Busca exemplos e documentos internos usando BM25."""
import re
import json
from functools import lru_cache
from pathlib import Path

from integrations.contratos import HISTORICO_CFPB, ler_csv
from retriever.bm25 import BuscaBM25


PASTA_PROJETO = Path(__file__).resolve().parent.parent
LIMITE_CFPB = 20_000 
ARQUIVO_EXEMPLOS = PASTA_PROJETO / "data" / "exemplos_reclamacoes.json"
PASTA_CONHECIMENTO = PASTA_PROJETO / "knowledge_base"

CAMPOS_EXEMPLO = (
    "relato",
    "descricao",
    "reclamacao",
    "narrativa",
    "complaint_what_happened",
    "consumer_complaint_narrative",
    "consumer complaint narrative",
    "tipo",
    "categoria",
    "problema",
    "issue",
    "subproblema",
    "sub_issue",
    "sub-issue",
    "produto",
    "subproduto",
    "sub_product",
    "sub-product",
    "product",
    "prioridade",
    "proximo_passo",
    "company_response",
    "company public response",
)


def carregar_exemplos() -> list[dict[str, str]]:
    """Lê os exemplos estruturados de data/exemplos_reclamacoes.json."""
    if not ARQUIVO_EXEMPLOS.exists():
        return []

    conteudo = ARQUIVO_EXEMPLOS.read_text(encoding="utf-8-sig").strip()
    if not conteudo:
        return []

    exemplos = json.loads(conteudo)
    if not isinstance(exemplos, list):
        raise ValueError("O arquivo de exemplos precisa conter uma lista JSON.")

    documentos = []
    for numero, exemplo in enumerate(exemplos, start=1):
        if not isinstance(exemplo, dict):
            continue

        campos = {str(chave).lower(): valor for chave, valor in exemplo.items()}
        partes = []
        for nome in CAMPOS_EXEMPLO:
            valor = campos.get(nome.lower())
            if isinstance(valor, (str, int, float)) and str(valor).strip():
                partes.append(str(valor).strip())

        if partes:
            documentos.append(
                {
                    "fonte": f"data/exemplos_reclamacoes.json (caso {numero})",
                    "texto": " ".join(partes),
                }
            )

    return documentos


def carregar_cfpb() -> list[dict[str, str]]:
    """Lê a amostra tratada do CFPB entregue pela Eng. de Dados (opcional)."""
    caminho, _ = HISTORICO_CFPB.localizar_arquivo()
    if caminho is None:
        return []

    registros = HISTORICO_CFPB.padronizar(ler_csv(caminho), caminho.name)
    documentos = []
    for numero, registro in enumerate(registros[:LIMITE_CFPB], start=1):
        if not registro["relato"]:
            continue
        identificador = registro["id_reclamacao"] or str(numero)
        partes = (registro["produto"], registro["subproduto"], registro["problema"],
                  registro["subproblema"], registro["relato"],
                  registro["resposta_empresa"])
        documentos.append({
            "fonte": f"{caminho.name} (reclamação {identificador})",
            "texto": " ".join(p for p in partes if p),
        })
    return documentos


@lru_cache(maxsize=1)
def criar_busca() -> BuscaBM25:
    """Cria o índice uma vez; reinicie o agente após editar os arquivos de dados."""
    return BuscaBM25(carregar_documentos())


def buscar_casos_semelhantes(consulta: str) -> str:
    """Busca exemplos, regras e procedimentos relacionados à reclamação.

    Args:
        consulta: Texto da reclamação que será pesquisado na base local.
    """
    if not consulta or not consulta.strip():
        return "Escreva uma reclamação para eu pesquisar."

    try:
        busca = criar_busca()
    except (OSError, ValueError, RuntimeError) as erro:
        return f"Não consegui carregar a base de conhecimento: {erro}"

    if not busca.documentos:
        return (
            "A base está vazia. Adicione exemplos em "
            "data/exemplos_reclamacoes.json ou conteúdo em knowledge_base/*.md."
        )

    resultados = busca.buscar(consulta, limite=3)
    if not resultados:
        return "Não encontrei referências com palavras em comum com essa reclamação."

    respostas = ["Referências encontradas na base local:"]
    for numero, resultado in enumerate(resultados, start=1):
        texto = resultado["texto"]
        if len(texto) > 1000:
            texto = texto[:1000].rstrip() + "..."

        respostas.append(
            f"\n[{numero}] Fonte: {resultado['fonte']}\n{texto}"
        )

    return "\n".join(respostas)


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
    """Exemplos + histórico CFPB + seções dos Markdown da base de conhecimento."""
    documentos = carregar_exemplos() + carregar_cfpb()
    if not PASTA_CONHECIMENTO.exists():
        return documentos

    for arquivo in sorted(PASTA_CONHECIMENTO.glob("*.md")):
        texto = arquivo.read_text(encoding="utf-8-sig").strip()
        for titulo, secao in dividir_markdown(texto):
            documentos.append({
                "fonte": f"{arquivo.relative_to(PASTA_PROJETO)} > {titulo}",
                "texto": secao,
            })
    return documentos
