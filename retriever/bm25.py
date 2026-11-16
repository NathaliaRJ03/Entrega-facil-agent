"""Indexa documentos e corrige erros ortográficos antes da busca BM25."""

from .preprocessing import corrigir_tokens, tokenizar

try:
    from rank_bm25 import BM25Okapi
except ImportError:
    BM25Okapi = None


class BuscaBM25:
    """Indexa documentos e devolve os mais relevantes para uma consulta."""

    def __init__(self, documentos: list[dict[str, str]]):
        self.documentos = []
        corpus = []
        for documento in documentos:
            texto = documento.get("texto", "").strip()
            tokens = tokenizar(texto)
            if tokens:
                self.documentos.append(documento)
                corpus.append(tokens)

        self.vocabulario = {token for documento in corpus for token in documento}
        self.indice = None

        if self.documentos and BM25Okapi is None:
            raise RuntimeError(
                "Falta a biblioteca rank-bm25. Instale com: pip install rank-bm25"
            )

        if self.documentos:
            self.indice = BM25Okapi(corpus)

    def buscar(self, consulta: str, limite: int = 3) -> list[dict[str, object]]:
        """Corrige termos desconhecidos e retorna documentos ordenados por BM25."""
        tokens_originais = tokenizar(consulta)
        tokens, correcoes = corrigir_tokens(tokens_originais, self.vocabulario)
        if not tokens or not self.indice or limite < 1:
            return []

        pontuacoes = self.indice.get_scores(tokens)
        posicoes = sorted(
            range(len(pontuacoes)),
            key=lambda posicao: pontuacoes[posicao],
            reverse=True,
        )

        resultados = []
        for posicao in posicoes:
            pontuacao = float(pontuacoes[posicao])
            if pontuacao <= 0:
                break

            documento = self.documentos[posicao]
            resultados.append(
                {
                    "fonte": documento["fonte"],
                    "texto": documento["texto"],
                    "pontuacao": pontuacao,
                    "termos_corrigidos": correcoes,
                }
            )
            if len(resultados) == limite:
                break

        return resultados
