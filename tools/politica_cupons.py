"""Tabela progressiva de cupons por atraso: fonte única para oferta e registro.

Para mudar códigos, percentuais ou validade, edite FAIXAS. A orientação de
comportamento do agente fica em knowledge_base/politica_cupons_atraso.md.
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

    def codigos(self) -> set[str]:
        return {self.codigo, self.alternativa} - {""}


FAIXAS = (
    FaixaCupom(
        "1 a 3 dias", 1, 3, "DESCULPA5", "5% de desconto na próxima compra", 30,
        alternativa="FRETEZERO",
        observacao="Alternativa equivalente: frete grátis na próxima compra (FRETEZERO).",
    ),
    FaixaCupom("4 a 7 dias", 4, 7, "ATRASO10", "10% de desconto em todo o site/app", 30),
    FaixaCupom(
        "8 a 14 dias", 8, 14, "PRIORIDADE15",
        "15% de desconto + prioridade de envio no próximo pedido", 45,
    ),
    FaixaCupom(
        "15 dias ou mais", 15, None, "ESPECIAL20", "20% de desconto", 60,
        observacao=(
            "O cliente também pode preferir o cancelamento com reembolso integral; "
            "isso é feito pela revisão humana, não pelo agente."
        ),
    ),
)


def _indice_da_faixa(dias: int) -> int | None:
    for indice, faixa in enumerate(FAIXAS):
        if dias >= faixa.dias_min and (faixa.dias_max is None or dias <= faixa.dias_max):
            return indice
    return None


def faixa_aplicavel(dias: int, cliente_muito_irritado: bool = False) -> FaixaCupom | None:
    """Faixa pelo atraso. Cliente muito irritado na 1ª faixa sobe para a 2ª (10%)."""
    indice = _indice_da_faixa(dias)
    if indice is None:
        return None
    if cliente_muito_irritado and indice == 0:
        indice = 1
    return FAIXAS[indice]


def codigos_aceitos(dias: int) -> set[str]:
    """Códigos que podem ser registrados para esse atraso (inclui o ajuste da 1ª faixa)."""
    aceitos: set[str] = set()
    for irritado in (False, True):
        faixa = faixa_aplicavel(dias, irritado)
        if faixa is not None:
            aceitos |= faixa.codigos()
    return aceitos
