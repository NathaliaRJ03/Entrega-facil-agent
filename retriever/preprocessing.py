"""Normaliza consultas e corrige erros simples antes da busca BM25."""

import re
import unicodedata


def normalizar(texto: str) -> str:
    """Converte para minúsculas e remove acentos."""
    texto = unicodedata.normalize("NFD", (texto or "").casefold())
    return "".join(
        letra for letra in texto if unicodedata.category(letra) != "Mn"
    )


def tokenizar(texto: str) -> list[str]:
    """Separa o texto normalizado em palavras e números."""
    texto = normalizar(texto)
    return re.findall(r"[a-z0-9]+", texto)


def distancia_levenshtein(esquerda: str, direita: str, limite: int | None = None) -> int:
    """Calcula quantas inserções, remoções ou substituições separam as palavras."""
    if esquerda == direita:
        return 0
    if limite is not None and abs(len(esquerda) - len(direita)) > limite:
        return limite + 1

    anterior = list(range(len(direita) + 1))
    for indice_esquerda, letra_esquerda in enumerate(esquerda, start=1):
        atual = [indice_esquerda]
        for indice_direita, letra_direita in enumerate(direita, start=1):
            custo = 0 if letra_esquerda == letra_direita else 1
            atual.append(min(
                anterior[indice_direita] + 1,
                atual[indice_direita - 1] + 1,
                anterior[indice_direita - 1] + custo,
            ))
        anterior = atual

    distancia = anterior[-1]
    return min(distancia, limite + 1) if limite is not None else distancia


def corrigir_tokens(
    tokens: list[str], vocabulario: set[str]
) -> tuple[list[str], dict[str, str]]:
    """Corrige apenas palavras desconhecidas com uma opção próxima e única.

    Palavras curtas, números e termos ambíguos são mantidos como foram escritos.
    """
    corrigidos = []
    mapa_correcoes: dict[str, str] = {}

    for token in tokens:
        if token in vocabulario or not token.isalpha() or len(token) < 4:
            corrigidos.append(token)
            continue

        limite = 1 if len(token) <= 7 else 2
        candidatos = []
        for palavra in vocabulario:
            if abs(len(token) - len(palavra)) > limite:
                continue
            distancia = distancia_levenshtein(token, palavra, limite)
            if distancia <= limite:
                candidatos.append((distancia, palavra))

        if not candidatos:
            corrigidos.append(token)
            continue

        menor_distancia = min(distancia for distancia, _ in candidatos)
        melhores = {
            palavra for distancia, palavra in candidatos
            if distancia == menor_distancia
        }
        if len(melhores) != 1:
            corrigidos.append(token)
            continue

        palavra = melhores.pop()
        corrigidos.append(palavra)
        mapa_correcoes[token] = palavra

    return corrigidos, mapa_correcoes
