import re
import unicodedata


LIMITE_RELATO = 2000

_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_ID_PEDIDO = re.compile(r"(?i)\bPED[-_][A-Z0-9][A-Z0-9_-]{2,}\b")
_CNPJ = re.compile(r"(?<!\d)(?:\d{2}[.\s]?\d{3}[.\s]?\d{3}/?\s?\d{4}-?\s?\d{2})(?!\d)")
_CPF = re.compile(r"(?<!\d)(?:\d{3}[.\s]?\d{3}[.\s]?\d{3}-?\s?\d{2})(?!\d)")
_TELEFONE = re.compile(
    r"(?<!\d)(?:\+?55[\s.-]*)?\(?\d{2}\)?[\s.-]*9?\d{4}[\s.-]?\d{4}(?!\d)"
)
_UUID = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
)
_CARTAO = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_CREDENCIAL = re.compile(
    r"(?i)\b(senha|password|passcode|token\s+de\s+acesso|access\s+token|"
    r"api[\s_-]?key|chave\s+privada|secret\s+key|credencial)\b"
    r"\s*(?::|=|\b[eé]\b|\bis\b)\s*[^\r\n,;]{1,200}"
)
_TOKEN = re.compile(
    r"(?i)\b(?:bearer\s+\S+|(?:gh[pousr]_|github_pat_|sk_live_|sk_test_|"
    r"xox[baprs]-)[A-Za-z0-9_-]{12,})\b"
)


def _normalizar_para_deteccao(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.casefold())
    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) not in {"Mn", "Cf"}
    )
    return " ".join(texto.split())


_PADROES_INJECAO = tuple(
    re.compile(padrao, re.IGNORECASE)
    for padrao in (
        r"\b(?:ignore|desconsidere|desconsidera|disregard)\b.{0,100}\b"
        r"(?:instrucoes|instructions|regras|rules|mensagens anteriores|prompt|politica|policy)\b",
        r"\b(?:revele|mostre|imprima|repita|exiba|exporte|reveal|show|print|"
        r"repeat|display|export|output|disclose)\b.{0,100}\b(?:prompt|instrucoes internas|"
        r"mensagem do sistema|system prompt|developer prompt)\b",
        r"\b(?:aja|finja|act|pretend)\b.{0,40}\b(?:como|as|ser)\b.{0,40}\b"
        r"(?:sistema|admin|administrador|developer)\b",
        r"\b(?:mostre|liste|exiba|exporte|show|list|display|export)\b.{0,80}\b"
        r"(?:todos os pedidos|todos os clientes|todos os dados|all orders|all customers|all data)\b",
    )
)


def contem_prompt_injection(texto: str) -> bool:
    normalizado = _normalizar_para_deteccao(str(texto or "")[:LIMITE_RELATO])
    return any(padrao.search(normalizado) for padrao in _PADROES_INJECAO)


def _luhn_valido(numero: str) -> bool:
    soma = 0
    paridade = len(numero) % 2
    for indice, caractere in enumerate(numero):
        digito = int(caractere)
        if indice % 2 == paridade:
            digito *= 2
            if digito > 9:
                digito -= 9
        soma += digito
    return soma % 10 == 0


def _mascarar_cartao(candidato: re.Match[str]) -> str:
    digitos = re.sub(r"\D", "", candidato.group())
    if 13 <= len(digitos) <= 19 and _luhn_valido(digitos):
        return "[CARTÃO REMOVIDO]"
    return candidato.group()


def mascarar_dados_sensiveis(
    texto: str,
    valores_privados: tuple[tuple[str, str], ...] = (),
) -> str:
    """Remove padrões comuns de PII e credenciais antes do texto chegar ao modelo."""
    valor = unicodedata.normalize("NFKC", str(texto or ""))
    valor = "".join(
        caractere
        for caractere in valor
        if unicodedata.category(caractere) != "Cf"
        and (unicodedata.category(caractere) != "Cc" or caractere in "\n\t\r")
    )

    truncado = len(valor) > LIMITE_RELATO
    valor = valor[:LIMITE_RELATO]

    for valor_privado, marcador in valores_privados:
        partes = unicodedata.normalize("NFKC", str(valor_privado or "")).split()
        if len(" ".join(partes)) >= 3:
            trecho = r"\s+".join(re.escape(parte) for parte in partes)
            padrao = re.compile(rf"(?<!\w){trecho}(?!\w)", re.IGNORECASE)
            valor = padrao.sub(marcador, valor)

    valor = _CREDENCIAL.sub(lambda m: f"{m.group(1)}: [CREDENCIAL REMOVIDA]", valor)
    valor = _TOKEN.sub("[TOKEN REMOVIDO]", valor)
    valor = _EMAIL.sub("[E-MAIL REMOVIDO]", valor)
    valor = _ID_PEDIDO.sub("[ID PEDIDO REMOVIDO]", valor)
    valor = _CNPJ.sub("[CNPJ REMOVIDO]", valor)
    valor = _CPF.sub("[CPF REMOVIDO]", valor)
    valor = _TELEFONE.sub("[TELEFONE REMOVIDO]", valor)
    valor = _UUID.sub("[CHAVE PIX REMOVIDA]", valor)
    valor = _CARTAO.sub(_mascarar_cartao, valor)

    if truncado:
        valor = valor.rstrip() + " [RELATO TRUNCADO]"
    return valor
