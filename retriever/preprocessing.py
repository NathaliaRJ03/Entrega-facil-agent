"""Prepara o texto e expande sinônimos antes da busca BM25."""

import re
import unicodedata


# Cada chave é um conceito. Os valores são outras formas de descrevê-lo.
SINONIMOS = {
    "pix": (
        "transferencia instantanea",
        "liquidacao instantanea",
        "liquidacao",
        "pagamento instantaneo",
    ),
    "duplicidade": (
        "duas vezes",
        "cobranca duplicada",
        "cobrada duas vezes",
        "pagamento duplicado",
        "cobrado em dobro",
        "cobraram em dobro",
        "lancamento duplicado",
    ),
}

# Estorno é uma ação relacionada à duplicidade, não um sinônimo exato.
TERMOS_RELACIONADOS = {
    "duplicidade": ("estorno",),
}


def normalizar(texto: str) -> str:
    """Deixa o texto em minúsculas e remove acentos."""
    texto = unicodedata.normalize("NFD", texto.lower())
    return "".join(letra for letra in texto if unicodedata.category(letra) != "Mn")


def tokenizar(texto: str) -> list[str]:
    """Separa palavras e acrescenta os sinônimos dos conceitos encontrados."""
    texto = normalizar(texto)
    texto = re.sub(r"[^\w\s]", " ", texto)
    tokens = re.findall(r"\w+", texto, flags=re.UNICODE)
    palavras_adicionadas = set(tokens)

    for conceito, sinonimos in SINONIMOS.items():
        formas = (conceito, *sinonimos)
        encontrou_conceito = any(
            re.search(rf"\b{re.escape(forma)}\b", texto)
            for forma in formas
        )
        if not encontrou_conceito:
            continue

        formas_relacionadas = (*formas, *TERMOS_RELACIONADOS.get(conceito, ()))
        for forma in formas_relacionadas:
            for palavra in re.findall(r"\w+", forma):
                if palavra not in palavras_adicionadas:
                    tokens.append(palavra)
                    palavras_adicionadas.add(palavra)

    # Mantém repetições do texto original para preservar a frequência do BM25.
    return tokens
