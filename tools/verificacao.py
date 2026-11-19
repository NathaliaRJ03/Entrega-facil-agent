"""Conferência, coluna por coluna, do que o cliente disse no Forms com a Gold.

Nome e ID do pedido corretos não bastam: o tipo de contestação e o relato
precisam bater com o que a Gold registra. Se não baterem, o agente não dá
solução nenhuma e encaminha para análise humana.

Resultado de cada coluna: "confere", "diverge" (contradiz a Gold) ou
"nao_verificavel" (a Gold não tem dado para decidir). O resultado geral é
"diverge" se alguma coluna divergir, "inconclusivo" se nenhuma divergir mas a
conferência essencial não puder ser feita, e "confere" nos demais casos.
Sinônimos e palavras diferentes são aceitos no relato; um relato sobre outro
assunto não.
"""

import re
from collections.abc import Callable
from datetime import date
from difflib import SequenceMatcher

from integrations.contratos import normalizar_coluna

# Palavras (radicais) que indicam cada tipo de problema no relato do cliente.
SINONIMOS_RELATO: dict[str, tuple[str, ...]] = {
    "atraso": (
        "atras", "demor", "tard", "prazo", "previs", "previst", "esper", "ainda nao chegou",
        "nao chegou", "nao chegaram", "nao foi entregue", "nao entreg", "passou da data",
        "passou do prazo", "dias", "semana", "cade", "onde esta", "nao recebi",
    ),
    "pedido_nao_enviado": (
        "nao enviad", "nao foi enviad", "nao enviaram", "nao enviou", "nao despach",
        "nao saiu", "nao postad", "nao foi postad", "parado", "sem envio", "nao mandaram",
        "nao chegou", "nao recebi", "aguardando envio", "nao embarc", "nao foi despach",
        "nao sai", "ainda nao", "envio", "enviar",
    ),
    "itens_faltando": (
        "falt", "incomplet", "veio sem", "nao veio", "nao vieram", "so veio", "so chegou",
        "apenas", "quantidade", "unidade", "item", "itens", "sem o ", "sem a ", "cade o",
        "veio so", "chegou so", "nao estava",
    ),
    "produto_errado": (
        "errad", "diferente", "trocad", "outro produto", "outra coisa", "nao e o que",
        "nao corresponde", "nao pedi", "nao foi o que", "tamanho", "cor ", "modelo",
        "enviaram outro", "veio outro", "equivocad", "nao era", "nao combina",
    ),
    "cancelamento_reembolso": (
        "cancel", "reembols", "estorn", "devol", "dinheiro de volta", "arrepend",
        "desist", "nao quero mais", "meu dinheiro", "ressarc", "reaver", "devolv",
    ),
    "cobranca_diferente": (
        "cobr", "valor", "pagu", "pago", "preco", "duplic", "a mais", "fatura", "cartao",
        "debit", "desconto", "taxa", "frete", "reais", "r$", "parcel", "diferente",
        "caro", "pix", "boleto",
    ),
    "pedido_nao_encontrado": (
        "nao encontr", "nao localiz", "sumiu", "nao acho", "nao aparece", "nao consta",
        "numero do pedido", "pedido", "rastre", "codigo", "nao consigo",
    ),
}

_ENTREGUE = ("entreg", "delivered", "concluid", "finalizad")
_ENVIADO = ("transit", "enviad", "despach", "a caminho", "saiu para", "postad", "expedid", "rota")
_NAO_ENVIADO = (
    "aguard", "pendent", "process", "separac", "prepar", "pagamento", "criado", "aprovad",
    "novo", "recebido", "faturad", "em analise", "nao enviad", "nao despach",
)
_CANCELADO = ("cancel",)


def _texto(valor: str) -> str:
    return " " + normalizar_coluna(valor or "").replace("_", " ") + " "


def situacao_do_pedido(pedido: dict[str, str], parse_data: Callable) -> str:
    """'entregue', 'enviado', 'nao_enviado', 'nao_entregue', 'cancelado' ou 'desconhecido'.

    Usa só a Gold. A data real de entrega é a prova de entrega; "Concluído" sem
    data (atraso_status "Em aberto") não significa entregue.
    """
    status_pedido = _texto(pedido.get("status_pedido", ""))
    status_entrega = _texto(pedido.get("status_entrega", ""))
    status = status_pedido + status_entrega
    if any(m in status for m in _CANCELADO):
        return "cancelado"
    if parse_data(pedido.get("data_entrega", "")):
        return "entregue"
    if any(m in status_pedido for m in _NAO_ENVIADO):
        return "nao_enviado"
    if "em aberto" in status_entrega:
        return "nao_entregue"
    if any(m in status for m in _ENTREGUE) and "nao entreg" not in status:
        return "entregue"
    if any(m in status for m in _ENVIADO):
        return "enviado"
    return "desconhecido"


# Motivo registrado na Gold -> tipos de contestação do Forms compatíveis com ele.
_MOTIVOS_GOLD: tuple[tuple[tuple[str, ...], frozenset[str]], ...] = (
    (("atras",), frozenset({"atraso"})),
    (("nao entreg",), frozenset({"atraso", "pedido_nao_enviado", "pedido_nao_encontrado"})),
    (("nao enviad",), frozenset({"pedido_nao_enviado"})),
    (("falt", "incomplet"), frozenset({"itens_faltando"})),
    (("cancel", "recus", "reembols", "estorn"), frozenset({"cancelamento_reembolso", "cobranca_diferente"})),
    (("errad", "trocad"), frozenset({"produto_errado"})),
    (("cobr", "duplic"), frozenset({"cobranca_diferente"})),
)


def tipos_compativeis_com_motivo_gold(motivos: str) -> set[str] | None:
    """Tipos do Forms compatíveis com os motivos da Gold; None se a Gold não registra motivo."""
    compativeis: set[str] = set()
    registrou = False
    for motivo in (m for m in (motivos or "").split(";") if m.strip()):
        texto = _texto(motivo)
        if "sem reclamacao" in texto or "nao informado" in texto:
            continue
        registrou = True
        for marcadores, tipos in _MOTIVOS_GOLD:
            if any(m in texto for m in marcadores):
                compativeis |= tipos
    return compativeis if registrou else None


def tipos_do_relato(relato: str) -> set[str]:
    """Tipos de problema que o relato descreve, aceitando sinônimos."""
    texto = _texto(relato)
    palavras_relato = texto.split()
    return {
        chave
        for chave, palavras in SINONIMOS_RELATO.items()
        if any(_aparece(p, texto, palavras_relato) for p in palavras)
    }


def _aparece(radical: str, texto: str, palavras_relato: list[str]) -> bool:
    """Radical no texto, tolerando pequenos erros de digitação em palavras longas."""
    if radical in texto:
        return True
    r = radical.strip()
    if " " in r or len(r) < 5:
        return False
    return any(
        w[:2] == r[:2] and SequenceMatcher(None, w[: len(r)], r).ratio() >= 0.8
        for w in palavras_relato
        if len(w) >= len(r)
    )


_PARTICULAS = {"de", "da", "do", "das", "dos", "e"}


def _tokens_nome(nome: str) -> list[str]:
    return [t for t in normalizar_coluna(nome or "").split("_") if t and t not in _PARTICULAS]


def _proximo(a: str, b: str) -> bool:
    return a == b or SequenceMatcher(None, a, b).ratio() >= 0.88


def nomes_equivalentes(nome_forms: str, nome_gold: str) -> bool:
    """Mesmo nome mesmo com acento, caixa, ordem, nome do meio ou erro de digitação.

    "Maria Silva" confere com "Maria de Souza Silva"; "Mariaa Silva" também.
    Um nome só ("Maria") nunca confere com um nome composto.
    """
    a, b = _tokens_nome(nome_forms), _tokens_nome(nome_gold)
    if not a or not b:
        return False
    curto, longo = (a, b) if len(a) <= len(b) else (b, a)
    if len(curto) < 2 and len(longo) > 1:
        return False
    return all(any(_proximo(t, u) for u in longo) for t in curto)


def _numero(texto: str) -> float | None:
    limpo = re.sub(r"[^\d,.-]", "", str(texto or ""))
    if not limpo:
        return None
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return None


_STOP_PRODUTO = {"para", "com", "sem", "pedido", "produto", "item", "itens", "meu", "minha", "que", "uma", "dos", "das"}


def _palavras_produto(texto: str) -> set[str]:
    return {
        p[:5] for p in _texto(texto).split()
        if len(p) >= 4 and p not in _STOP_PRODUTO
    }


def conferir(
    reclamacao: dict[str, str],
    pedido: dict[str, str],
    chave_tipo: str,
    atraso: str,
    parse_data: Callable[[str], date | None],
) -> dict:
    """Confronta Forms x Gold e devolve {'resultado', 'colunas', 'motivos'}."""
    colunas: list[dict[str, str]] = []

    def registrar(coluna: str, situacao: str, motivo: str = "") -> None:
        colunas.append({"coluna": coluna, "situacao": situacao, "motivo": motivo})

    # 1 e 2. Identidade: o ID achou o pedido e o nome já foi conferido no backend.
    registrar("id_pedido", "confere")
    registrar("nome_cliente", "confere")

    # 2b. E-mail de contato: pode ser outro e-mail legítimo, então não bloqueia.
    email_forms = (reclamacao.get("email_contato") or "").strip().lower()
    email_gold = (pedido.get("email_cliente") or "").strip().lower()
    if email_forms and email_gold:
        if email_forms == email_gold:
            registrar("email_contato", "confere")
        else:
            registrar("email_contato", "nao_verificavel", "e-mail de contato diferente do cadastro")
    else:
        registrar("email_contato", "nao_verificavel", "a Gold não tem e-mail")

    # 2c. Valor informado x valor do pedido na Gold (se a Gold tiver a coluna).
    valor_forms = _numero(reclamacao.get("valor_pedido", ""))
    valor_gold = _numero(pedido.get("valor_total_pedido") or pedido.get("valor_pedido", ""))
    if valor_forms is not None and valor_gold is not None and chave_tipo != "cobranca_diferente":
        if abs(valor_forms - valor_gold) <= max(0.01, 0.01 * valor_gold):
            registrar("valor_pedido", "confere")
        else:
            registrar("valor_pedido", "diverge", "o valor informado não bate com o valor do pedido")
    else:
        registrar("valor_pedido", "nao_verificavel", "sem valor para comparar na Gold ou em disputa")

    # 3. Data da compra informada x data do pedido na Gold (tolera 1 dia de fuso).
    compra_forms = parse_data(reclamacao.get("data_compra", ""))
    compra_gold = parse_data(pedido.get("data_pedido", ""))
    if compra_forms and compra_gold:
        if abs((compra_forms - compra_gold).days) <= 1:
            registrar("data_compra", "confere")
        else:
            registrar("data_compra", "diverge", "a data da compra informada não bate com o registro do pedido")
    else:
        registrar("data_compra", "nao_verificavel")

    # 4. Tipo de contestação x o que a Gold registra (motivo, situação, quantidades).
    situacao = situacao_do_pedido(pedido, parse_data)
    incompativel = "o tipo de contestação não é compatível com a situação do pedido na Gold"
    compativeis = tipos_compativeis_com_motivo_gold(pedido.get("motivos_do_pedido") or pedido.get("motivo_reclamacao", ""))
    qtd_itens = _numero(pedido.get("qtd_itens_total", ""))
    qtd_enviada = _numero(pedido.get("qtd_enviada_total", ""))
    faltou_item = qtd_itens is not None and qtd_enviada is not None and qtd_enviada < qtd_itens

    if chave_tipo == "atraso" and atraso == "não":
        registrar("tipo_contestacao", "diverge", "a Gold mostra o pedido entregue no prazo")
    elif compativeis is not None and chave_tipo in SINONIMOS_RELATO and chave_tipo != "pedido_nao_encontrado":
        if chave_tipo in compativeis:
            registrar("tipo_contestacao", "confere")
        else:
            registrar("tipo_contestacao", "diverge", "a Gold registra outro motivo de reclamação para este pedido")
    elif chave_tipo == "atraso":
        registrar("tipo_contestacao", "confere" if atraso == "sim" else "nao_verificavel",
                  "" if atraso == "sim" else "a Gold ainda não tem a entrega para confirmar o atraso")
    elif chave_tipo == "pedido_nao_enviado":
        if situacao in ("nao_enviado", "cancelado"):
            registrar("tipo_contestacao", "confere")
        elif situacao in ("enviado", "entregue"):
            registrar("tipo_contestacao", "diverge", "a Gold mostra o pedido já enviado ou entregue")
        else:
            registrar("tipo_contestacao", "nao_verificavel", "a Gold não mostra se o pedido saiu")
    elif chave_tipo == "itens_faltando":
        if faltou_item:
            registrar("tipo_contestacao", "confere")
        elif qtd_itens is not None and qtd_enviada is not None:
            registrar("tipo_contestacao", "diverge", "a Gold mostra todos os itens enviados")
        elif situacao == "entregue":
            registrar("tipo_contestacao", "confere")
        elif situacao in ("nao_enviado", "enviado", "nao_entregue", "cancelado"):
            registrar("tipo_contestacao", "diverge", incompativel + " (o pedido não consta como entregue)")
        else:
            registrar("tipo_contestacao", "nao_verificavel", "sem quantidades na Gold")
    elif chave_tipo == "produto_errado":
        if situacao == "entregue":
            registrar("tipo_contestacao", "confere")
        elif situacao in ("nao_enviado", "enviado", "nao_entregue", "cancelado"):
            registrar("tipo_contestacao", "diverge", incompativel + " (o pedido não consta como entregue)")
        else:
            registrar("tipo_contestacao", "nao_verificavel", "status do pedido sem correspondência")
    elif chave_tipo in ("cancelamento_reembolso", "cobranca_diferente"):
        # A Gold não tem valores pagos nem pedidos de reembolso: o Financeiro decide.
        registrar("tipo_contestacao", "confere", "a análise é do Financeiro")
    elif chave_tipo == "pedido_nao_encontrado":
        registrar("tipo_contestacao", "confere")
    else:
        registrar("tipo_contestacao", "nao_verificavel", "tipo não reconhecido")

    # 5. Relato x tipo de contestação (sinônimos valem; outro assunto, não).
    relato = (reclamacao.get("relato") or "").strip()
    if len(relato) < 5:
        registrar("relato", "nao_verificavel", "relato vazio ou curto demais")
    else:
        descritos = tipos_do_relato(relato)
        if not chave_tipo or chave_tipo not in SINONIMOS_RELATO:
            registrar("relato", "nao_verificavel")
        elif chave_tipo in descritos:
            registrar("relato", "confere")
        else:
            registrar("relato", "diverge", "o relato não descreve o tipo de contestação escolhido")

    # 6. Produto citado no relato x produto(s) do pedido na Gold (só informativo).
    produtos = pedido.get("produtos_do_pedido") or pedido.get("descricao_pedido") or ""
    if _palavras_produto(relato) & _palavras_produto(produtos):
        registrar("relato_x_produto", "confere")
    else:
        registrar("relato_x_produto", "nao_verificavel", "o relato não cita o produto")

    # 7. Código da transação: a Gold não tem esse dado.
    registrar("codigo_transacao", "nao_verificavel", "a Gold não tem código de transação")

    divergentes = [c["motivo"] for c in colunas if c["situacao"] == "diverge"]
    essencial_aberto = any(
        c["situacao"] == "nao_verificavel" and c["coluna"] in ("tipo_contestacao", "relato")
        for c in colunas
    )
    if divergentes:
        resultado = "diverge"
    elif essencial_aberto:
        resultado = "inconclusivo"
    else:
        resultado = "confere"
    return {"resultado": resultado, "colunas": colunas, "motivos": divergentes}
