"""Tabela progressiva de cupons por atraso: fonte única para oferta e registro.

Para mudar códigos, percentuais ou validade, edite FAIXAS. A orientação de
comportamento do agente fica em knowledge_base_orien/politica_cupons_atraso.md.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FaixaCupom:
    nome: str
    dias_min: int
    dias_max: int | None
    codigo: str
    beneficio: str
    validade_dias: int
    alternativa: str = ""
    observacao: str = ""
    # Como o agente responde nesta faixa. {codigo} e {validade} são preenchidos aqui.
    modelo_resposta: str = ""

    def codigos(self) -> set[str]:
        return {self.codigo, self.alternativa} - {""}

    def resposta_modelo(self) -> str:
        return self.modelo_resposta.format(codigo=self.codigo, validade=self.validade_dias)


# A partir desta posição de FAIXAS (EF-GARANTIA10), o cliente muito irritado não sobe mais.
INDICE_AJUSTE_IRRITADO = 2

FAIXAS = (
    FaixaCupom(
        "1 dia", 1, 1, "EF-FRETE", "frete grátis na próxima compra", 30,
        modelo_resposta=(
            "Olá! Sentimos muito pelo atraso no seu pedido. Como forma de compensação, "
            "liberamos para você o cupom {codigo}, com frete grátis na sua próxima "
            "compra, válido por {validade} dias. Se precisar de qualquer outra ajuda "
            "com o pedido, estou por aqui."
        ),
    ),
    FaixaCupom(
        "2 dias", 2, 2, "EF-CORTESIA5", "5% de desconto na próxima compra", 30,
        modelo_resposta=(
            "Olá! Sentimos muito pelo atraso no seu pedido. Como forma de compensação, "
            "liberamos para você o cupom {codigo}, com 5% de desconto na sua próxima "
            "compra, válido por {validade} dias. Se precisar de qualquer outra ajuda "
            "com o pedido, estou por aqui."
        ),
    ),
    FaixaCupom(
        "3 a 4 dias", 3, 4, "EF-GARANTIA10", "10% de desconto na próxima compra", 30,
        modelo_resposta=(
            "Olá! Sentimos muito pelo atraso no seu pedido, e agradecemos a sua "
            "paciência. Como forma de compensação, liberamos para você o cupom "
            "{codigo}, com 10% de desconto na sua próxima compra, válido por "
            "{validade} dias. Se precisar de qualquer outra ajuda com o pedido, "
            "estou por aqui."
        ),
    ),
    FaixaCupom(
        "5 a 7 dias", 5, 7, "EF-COMPROMISSO15", "15% de desconto na próxima compra", 45,
        modelo_resposta=(
            "Olá! Lamentamos o atraso no seu pedido e agradecemos a sua paciência. "
            "Como forma de compensação, liberamos para você o cupom {codigo}, com "
            "15% de desconto na sua próxima compra, válido por {validade} dias. Se "
            "precisar de qualquer outra ajuda com o pedido, estou por aqui."
        ),
    ),
    FaixaCupom(
        "8 a 14 dias", 8, 14, "EF-PRIORIDADE20",
        "20% de desconto + prioridade no atendimento e no envio dos próximos pedidos", 45,
        modelo_resposta=(
            "Lamentamos muito pela demora, esse não é o padrão de serviço que queremos "
            "entregar. Para compensar, liberamos o cupom {codigo}, com 20% de "
            "desconto válido por {validade} dias, além de prioridade no atendimento e "
            "no envio dos seus próximos pedidos. Se precisar de qualquer outra ajuda "
            "com o pedido, estou por aqui."
        ),
    ),
    FaixaCupom(
        "15 dias ou mais", 15, None, "EF-PREMIUM25", "25% de desconto", 60,
        observacao=(
            "O cliente também pode preferir o cancelamento com reembolso integral; "
            "isso é feito pela revisão humana, não pelo agente."
        ),
        modelo_resposta=(
            "Entendo a sua insatisfação e peço desculpas pela situação. Para o seu "
            "caso, posso oferecer o cupom {codigo}, com 25% de desconto válido por "
            "{validade} dias. Se preferir o reembolso, encaminho a sua solicitação "
            "para a nossa equipe, que fará a análise e retornará o mais rápido possível."
        ),
    ),
)


def _indice_da_faixa(dias: int) -> int | None:
    for indice, faixa in enumerate(FAIXAS):
        if dias >= faixa.dias_min and (faixa.dias_max is None or dias <= faixa.dias_max):
            return indice
    return None


def faixa_aplicavel(dias: int, cliente_muito_irritado: bool = False) -> FaixaCupom | None:
    """Faixa pelo atraso. Cliente muito irritado com 1 ou 2 dias sobe para EF-GARANTIA10 (10%)."""
    indice = _indice_da_faixa(dias)
    if indice is None:
        return None
    if cliente_muito_irritado and indice < INDICE_AJUSTE_IRRITADO:
        indice = INDICE_AJUSTE_IRRITADO
    return FAIXAS[indice]


def codigos_aceitos(dias: int) -> set[str]:
    """Códigos que podem ser registrados para esse atraso (inclui o ajuste de cliente irritado)."""
    aceitos: set[str] = set()
    for irritado in (False, True):
        faixa = faixa_aplicavel(dias, irritado)
        if faixa is not None:
            aceitos |= faixa.codigos()
    return aceitos
