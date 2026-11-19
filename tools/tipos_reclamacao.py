"""Tipos de reclamação do Forms e a atitude do agente para cada um.

A classificação é feita aqui, a partir do campo "Tipo de contestação" do Forms,
e nunca pelo modelo. Só o tipo "atraso" pode gerar cupom, e somente quando a
tabela Gold confirmar o atraso. Tipos vazios ou desconhecidos vão para revisão
humana.
"""

from dataclasses import dataclass

from integrations.contratos import normalizar_coluna


@dataclass(frozen=True)
class TipoReclamacao:
    chave: str
    nome: str
    marcadores: tuple[str, ...]
    equipe: str
    acao: str
    permite_cupom: bool = False


# A ordem importa: o primeiro tipo cujo marcador aparece no texto vence.
TIPOS: tuple[TipoReclamacao, ...] = (
    TipoReclamacao(
        chave="pedido_nao_encontrado",
        nome="Pedido não encontrado",
        marcadores=("nao_encontr", "nao_localiz", "sumiu"),
        equipe="Atendimento",
        acao=(
            "Chame consultar_pedido. Se o pedido for confirmado na Gold, informe ao "
            "cliente só a situação e a previsão, exatamente como vieram da ferramenta, "
            "e chame registrar_atendimento. Se o pedido não for encontrado (ou o nome "
            "não conferir), diga ao cliente que não localizou o pedido, que o caso foi "
            "encaminhado a um analista e que ele retornará em breve com o número do "
            "pedido. Depois chame encaminhar_para_revisao_humana. Sem cupom."
        ),
    ),
    TipoReclamacao(
        chave="pedido_nao_enviado",
        nome="Pedido não enviado",
        marcadores=("nao_enviad", "nao_foi_enviad", "nao_despach", "nao_saiu", "nao_postad"),
        equipe="Logística",
        acao=(
            "Chame consultar_pedido só para confirmar o pedido. Diga ao cliente que a "
            "solicitação dele foi enviada para análise do setor responsável (Logística), "
            "sem prometer prazo, e chame registrar_atendimento. Não ofereça cupom: o "
            "cliente não reclamou de atraso."
        ),
    ),
    TipoReclamacao(
        chave="cobranca_diferente",
        nome="Cobrança diferente",
        marcadores=("cobranc", "cobrad", "valor", "duplicad", "pagamento", "preco"),
        equipe="Financeiro",
        acao=(
            "Chame consultar_pedido só para confirmar o pedido. A Gold não tem valores "
            "pagos: não confirme, não calcule e não prometa valores. Trate como um "
            "pedido de cancelamento ou reembolso: diga ao cliente que, como não consegue "
            "validar a solicitação por aqui, ela está sendo encaminhada ao Financeiro "
            "para análise. Se codigo_transacao_informado for 'não', peça também o "
            "comprovante de pagamento. Chame registrar_atendimento. Sem cupom."
        ),
    ),
    TipoReclamacao(
        chave="cancelamento_reembolso",
        nome="Cancelamento ou reembolso",
        marcadores=("cancel", "reembols", "estorn", "devoluc", "devolv", "arrepend"),
        equipe="Financeiro",
        acao=(
            "Chame consultar_pedido só para confirmar o pedido. Diga ao cliente que, como "
            "não consegue validar a solicitação por aqui, ela está sendo encaminhada ao "
            "Financeiro para análise. Não confirme cancelamento nem reembolso e não "
            "prometa prazo nem valor. Chame registrar_atendimento. Sem cupom."
        ),
    ),
    TipoReclamacao(
        chave="itens_faltando",
        nome="Itens faltando",
        marcadores=("faltand", "faltou", "falta", "incomplet", "veio_sem"),
        equipe="Logística",
        acao=(
            "Chame consultar_pedido só para confirmar o pedido. Diga ao cliente que a "
            "equipe vai informar as etapas para a devolução do pedido, sem prometer "
            "prazo, e que o caso foi encaminhado à Logística. Chame "
            "registrar_atendimento. Sem cupom."
        ),
    ),
    TipoReclamacao(
        chave="produto_errado",
        nome="Produto errado",
        marcadores=("errad", "trocad", "outro_produto", "nao_corresponde"),
        equipe="Trocas e Devoluções",
        acao=(
            "Chame consultar_pedido para ver o(s) produto(s) registrados na Gold. Peça "
            "uma foto do produto recebido e da etiqueta, pergunte se o cliente prefere "
            "troca ou reembolso e diga que o caso foi encaminhado à equipe de Trocas e "
            "Devoluções. Chame registrar_atendimento. Sem cupom."
        ),
    ),
    TipoReclamacao(
        chave="atraso",
        nome="Atraso na entrega",
        marcadores=("atras", "demor"),
        equipe="Atendimento",
        permite_cupom=True,
        acao=(
            "Chame consultar_pedido. Se atraso_confirmado for 'sim', chame "
            "oferecer_cupom_atraso e use só o cupom devolvido. Se for 'não', explique "
            "com as datas da Gold que o pedido foi entregue no prazo, sem cupom, e chame "
            "registrar_atendimento. Se for 'indeterminado', diga que a entrega ainda não "
            "consta na base, sem cupom, e chame encaminhar_para_revisao_humana."
        ),
    ),
)

OUTRO = TipoReclamacao(
    chave="outro",
    nome="Tipo não reconhecido",
    marcadores=(),
    equipe="Revisão humana",
    acao=(
        "O tipo de contestação não foi reconhecido. Não ofereça cupom. Diga ao "
        "cliente que o caso foi encaminhado para análise da equipe e chame "
        "encaminhar_para_revisao_humana."
    ),
)


def classificar(tipo_contestacao: str) -> TipoReclamacao:
    """Classifica o texto do Forms. Vazio ou desconhecido -> OUTRO."""
    texto = normalizar_coluna(tipo_contestacao or "")
    if not texto:
        return OUTRO
    for tipo in TIPOS:
        if any(marcador in texto for marcador in tipo.marcadores):
            return tipo
    return OUTRO
