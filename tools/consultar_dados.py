"""Ferramentas do agente para consultar reclamações e pedidos."""

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from integrations.contratos import FALHAS, LIQUIDACOES, PEDIDOS, normalizar_coluna
from integrations.databricks import carregar_pedido, carregar_tabela
from integrations.workspace import carregar_reclamacoes

from .salvar_atendimento import ids_ja_atendidos

# Campos de contato (nome, e-mail, telefone) nunca entram no contrato,
# então nunca chegam ao modelo. Só exibimos o necessário para a triagem.
CAMPOS_RECLAMACAO = (
    "id_reclamacao", "data_envio", "id_pedido", "produto", "relato",
)


def _formatar(registro: dict[str, str], campos=None) -> str:
    campos = campos or registro.keys()
    return "\n".join(f"  {c}: {registro[c]}" for c in campos if registro.get(c))


def listar_reclamacoes_pendentes(limite: int = 5) -> str:
    """Lista reclamações recebidas pelo Google Forms que ainda não foram atendidas.

    Args:
        limite: Quantidade máxima de reclamações a retornar (padrão 5).
    """
    try:
        reclamacoes, origem = carregar_reclamacoes()
    except (OSError, ValueError) as erro:
        return f"Não consegui ler as reclamações: {erro}"

    triados = ids_ja_atendidos()
    pendentes = [r for r in reclamacoes if r["id_reclamacao"] not in triados]
    if not pendentes:
        return f"Nenhuma reclamação pendente. Fonte: {origem}."

    limite = max(1, min(int(limite or 5), 20))
    blocos = [f"{len(pendentes)} reclamação(ões) pendente(s). Fonte: {origem}."]
    for registro in pendentes[:limite]:
        blocos.append(_formatar(registro, CAMPOS_RECLAMACAO))
    return "\n\n".join(blocos)


def consultar_transacao(id_transacao: str) -> str:
    """Consulta o status de liquidação de uma transação na tabela Gold.

    Args:
        id_transacao: Identificador da transação (ex.: ID E2E do PIX ou NSU).
    """
    alvo = (id_transacao or "").strip().lower()
    if not alvo:
        return "Informe o ID da transação."

    try:
        linhas, origem = carregar_tabela(LIQUIDACOES)
    except (OSError, ValueError) as erro:
        return f"Não consegui ler a tabela de liquidações: {erro}"

    encontradas = [l for l in linhas if l["id_transacao"].lower() == alvo]
    if not encontradas:
        return (f"Transação {id_transacao} não encontrada em {origem}. "
                "Peça ao cliente para confirmar o ID.")
    return f"Fonte: {origem}\n" + "\n\n".join(_formatar(l) for l in encontradas)


def _parse_data(valor: str) -> date | None:
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    texto = str(valor).strip()
    if not texto:
        return None
    iso = texto.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso).date()
    except ValueError:
        pass
    for formato in ("%d/%m/%Y", "%d.%m.%Y", "%Y%m%d", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def _avaliar_atraso(pedido: dict[str, str]) -> tuple[str, str]:
    """Determina atraso apenas com dias explícitos ou datas comparáveis."""
    informado = (pedido.get("dias_atraso") or "").strip()
    if informado:
        try:
            dias = int(float(informado.replace(",", ".")))
            return ("sim", str(dias)) if dias > 0 else ("não", "0")
        except ValueError:
            pass

    prevista = _parse_data(pedido.get("data_prevista_entrega", ""))
    realizada = _parse_data(pedido.get("data_entrega", ""))
    if prevista is None:
        return "indeterminado", ""
    if realizada is not None:
        dias = (realizada - prevista).days
        return ("sim", str(dias)) if dias > 0 else ("não", "0")

    status = normalizar_coluna(
        f"{pedido.get('status_pedido', '')} {pedido.get('status_entrega', '')}"
    )
    if any(marcador in status for marcador in ("entregue", "delivered", "geliefert")):
        return "indeterminado", ""

    try:
        hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    except ZoneInfoNotFoundError:  # fallback para máquinas sem base IANA local
        hoje = datetime.now().astimezone().date()
    if prevista < hoje:
        return "sim", str((hoje - prevista).days)
    return "não", "0"


def _reclamacao_por_id(id_reclamacao: str) -> tuple[dict[str, str] | None, str, str]:
    try:
        reclamacoes, origem = carregar_reclamacoes()
    except (OSError, ValueError, KeyError) as erro:
        return None, "", f"Não consegui ler a reclamação do Forms: {erro}"

    reclamacao = next(
        (r for r in reclamacoes if r["id_reclamacao"] == id_reclamacao.strip()), None
    )
    if reclamacao is None:
        return None, origem, f"Reclamação {id_reclamacao} não encontrada no Forms."
    if not reclamacao.get("id_pedido") or not reclamacao.get("nome_cliente"):
        return None, origem, (
            "A reclamação precisa ter ID do pedido e nome do cliente para consultar a Gold."
        )
    return reclamacao, origem, ""


def _consultar_pedido_verificado(
    id_reclamacao: str,
) -> tuple[dict[str, str] | None, str, str]:
    reclamacao, origem_forms, erro = _reclamacao_por_id(id_reclamacao)
    if erro:
        return None, origem_forms, erro

    id_pedido = reclamacao["id_pedido"].strip()
    nome_cliente = reclamacao["nome_cliente"].strip()
    try:
        pedidos, origem_pedidos = carregar_pedido(PEDIDOS, id_pedido)
    except (OSError, ValueError, KeyError) as erro:
        return None, origem_forms, f"Não consegui consultar a Gold de pedidos: {erro}"
    origem = f"Forms ({origem_forms}); Gold ({origem_pedidos})"

    if not pedidos:
        return None, origem, f"Pedido {id_pedido} não encontrado em {origem_pedidos}."
    if len(pedidos) != 1:
        return None, origem, (
            f"Encontrei {len(pedidos)} registros para {id_pedido}; "
            "não consigo confirmar qual linha corresponde ao pedido."
        )

    pedido = pedidos[0]
    nome_tabela = normalizar_coluna(pedido.get("nome_cliente", ""))
    if not nome_tabela:
        return None, origem, "A tabela não tem nome_cliente para confirmar a identidade."
    if normalizar_coluna(nome_cliente) != nome_tabela:
        return None, origem, "O nome do Forms não confere com o cadastro do pedido."
    return pedido, origem, ""


def consultar_pedido(id_reclamacao: str) -> str:
    """Consulta o pedido da reclamação e confere o nome sem expô-lo ao modelo.

    Args:
        id_reclamacao: ID da resposta do Forms que contém nome e ID do pedido.
    """
    pedido, origem, erro = _consultar_pedido_verificado(id_reclamacao)
    if erro:
        return erro

    blocos = [f"Pedido confirmado. Fonte: {origem}.", "  nome_cliente_confirmado: sim"]
    campos = (
        "id_pedido", "descricao_pedido", "status_pedido", "status_entrega",
        "data_pedido", "data_prevista_entrega", "data_entrega", "dias_atraso",
    )
    atraso, dias = _avaliar_atraso(pedido)
    dados = _formatar(pedido, campos)
    dados += f"\n  atraso_confirmado: {atraso}"
    if dias:
        dados += f"\n  dias_atraso_calculados: {dias}"
    blocos.append(dados)
    return "\n\n".join(blocos)


def oferecer_cupom_atraso(id_reclamacao: str) -> str:
    """Confirma o nome da reclamação, atraso e retorna o cupom configurado.

    Args:
        id_reclamacao: ID da resposta do Forms que contém nome e ID do pedido.
    """
    pedido, origem, erro = _consultar_pedido_verificado(id_reclamacao)
    if erro:
        return f"Não foi possível confirmar a reclamação e o pedido: {erro} Não ofereça cupom."

    atraso, _ = _avaliar_atraso(pedido)
    if atraso != "sim":
        return (f"O atraso do pedido {pedido['id_pedido']} não foi confirmado ({atraso}); "
                "não ofereça cupom.")

    codigo = os.getenv("CUPOM_ATRASO_CODIGO", "").strip()
    desconto = os.getenv("CUPOM_ATRASO_DESCONTO", "").strip()
    if not codigo or not desconto:
        return (f"Atraso confirmado para {pedido['id_pedido']} em {origem}, "
                "mas a campanha de cupom ainda não foi configurada. "
                "Não invente código ou desconto.")
    return (f"Atraso confirmado para {pedido['id_pedido']} em {origem}. "
            f"Cupom aprovado: {codigo}; desconto configurado: {desconto}.")


def consultar_falhas(produto: str = "", data: str = "") -> str:
    """Busca incidentes/falhas registrados que possam explicar a reclamação.

    Args:
        produto: Produto ou serviço afetado (ex.: "PIX", "cartão", "boleto").
        data: Data da transação no formato AAAA-MM-DD. Vazio = qualquer data.
    """
    try:
        linhas, origem = carregar_tabela(FALHAS)
    except (OSError, ValueError) as erro:
        return f"Não consegui ler a tabela de falhas: {erro}"

    termo = normalizar_coluna(produto)
    data = (data or "").strip()[:10]

    def corresponde(falha: dict[str, str]) -> bool:
        if termo and termo not in normalizar_coluna(falha["servico"]):
            return False
        if data:
            inicio = falha["inicio"][:10]
            fim = falha["fim"][:10] or "9999-12-31"  # sem fim = ainda aberto
            return inicio <= data <= fim
        return True

    falhas = sorted(filter(corresponde, linhas), key=lambda f: f["inicio"], reverse=True)
    if not falhas:
        return (f"Nenhuma falha registrada para produto='{produto}' data='{data}' "
                f"em {origem}. Isso não descarta problema individual.")

    blocos = [f"{len(falhas)} falha(s) encontrada(s). Fonte: {origem}"]
    blocos += [_formatar(f) for f in falhas[:5]]
    return "\n\n".join(blocos)
