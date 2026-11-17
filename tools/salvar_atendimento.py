"""Registra que uma reclamação real foi atendida, sem guardar o texto do cliente."""

import csv
from datetime import datetime, timezone

from integrations import latencia_sheets
from integrations.contratos import PASTA_SAIDA
from integrations.workspace import carregar_reclamacoes
from tools.tipos_reclamacao import classificar

ARQUIVO_ATENDIMENTOS = PASTA_SAIDA / "atendimentos.csv"
COLUNAS = (
    "id_reclamacao", "data_atendimento", "id_pedido", "tipo_contestacao",
    "status_pedido", "atraso_confirmado", "cupom_oferecido", "resultado",
    "categoria", "equipe_responsavel",
)


def _colunas_do_arquivo() -> list[str]:
    """Mantém o cabeçalho de um arquivo antigo para não desalinhar as colunas."""
    with ARQUIVO_ATENDIMENTOS.open(encoding="utf-8-sig", newline="") as arquivo:
        return next(csv.reader(arquivo), []) or list(COLUNAS)


def ids_ja_atendidos() -> set[str]:
    if not ARQUIVO_ATENDIMENTOS.exists():
        return set()
    with ARQUIVO_ATENDIMENTOS.open(encoding="utf-8-sig", newline="") as arquivo:
        return {
            linha.get("id_reclamacao", "").strip()
            for linha in csv.DictReader(arquivo)
            if linha.get("id_reclamacao", "").strip()
        }


def resultados_por_id() -> dict[str, str]:
    """ID da reclamação -> resultado registrado (atendido ou revisao_humana)."""
    if not ARQUIVO_ATENDIMENTOS.exists():
        return {}
    with ARQUIVO_ATENDIMENTOS.open(encoding="utf-8-sig", newline="") as arquivo:
        return {
            linha["id_reclamacao"].strip(): (linha.get("resultado") or "atendido").strip()
            for linha in csv.DictReader(arquivo)
            if (linha.get("id_reclamacao") or "").strip()
        }


def carregar_reclamacoes_pendentes() -> tuple[list[dict[str, str]], str, str]:
    """Lê apenas em memória e retorna pendências, origem e uma mensagem de erro."""
    try:
        reclamacoes, origem = carregar_reclamacoes()
    except (OSError, ValueError, KeyError):
        return [], "", "Não consegui carregar as reclamações. Solicite revisão manual."

    triados = ids_ja_atendidos()
    pendentes = [r for r in reclamacoes if r["id_reclamacao"] not in triados]
    return pendentes, origem, ""


def obter_proxima_reclamacao() -> tuple[dict[str, str] | None, str, str]:
    """Obtém a primeira pendência, sem expor as demais ao modelo."""
    pendentes, origem, erro = carregar_reclamacoes_pendentes()
    if erro:
        return None, origem, erro
    if not pendentes:
        return None, origem, ""
    return pendentes[0], origem, ""


def registrar_atendimento(
    id_reclamacao: str,
    cupom_oferecido: str = "",
) -> str:
    """Marca uma reclamação do Forms como atendida para não reaparecer na fila.

    Reconsulta os dados no backend; não confia em status, atraso ou pedido enviados
    pelo modelo. Registra somente metadados operacionais, sem relato ou contato.
    """
    reclamacao = str(id_reclamacao or "").strip()
    if not reclamacao:
        return "Informe o ID da reclamação para registrar o atendimento."

    proxima, _, erro = obter_proxima_reclamacao()
    if erro:
        return erro
    if proxima is None:
        return "Nenhuma reclamação pendente para registrar."
    if reclamacao != proxima["id_reclamacao"]:
        return "Só é possível registrar a reclamação pendente atualmente selecionada."

    # Importação local evita ciclo: consultar_dados também usa ids_ja_atendidos.
    from tools.consultar_dados import (
        LIMITE_TIPO,
        _avaliar_atraso,
        _consultar_pedido_verificado,
        contestacao_de_atraso,
    )

    pedido, _, erro = _consultar_pedido_verificado(reclamacao)
    if erro:
        return f"O pedido não foi confirmado; atendimento não registrado. {erro}"

    from tools.politica_cupons import codigos_aceitos

    atraso_calculado, dias = _avaliar_atraso(pedido)
    atraso = "nao" if atraso_calculado == "não" else atraso_calculado
    tipo = (proxima.get("tipo_contestacao") or "").strip()[:LIMITE_TIPO]
    categoria = classificar(tipo)
    if categoria.chave == "outro":
        return ("O tipo de contestação não foi reconhecido; use "
                "encaminhar_para_revisao_humana.")
    cupom = (cupom_oferecido or "").strip()
    if cupom and (
        atraso != "sim"
        or not contestacao_de_atraso(tipo)
        or cupom not in codigos_aceitos(int(dias or 0))
    ):
        return "O cupom não corresponde à faixa de atraso confirmada ou o atraso não foi confirmado."

    registro = {
        "id_reclamacao": reclamacao,
        "data_atendimento": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "id_pedido": (pedido.get("id_pedido") or "").strip(),
        "tipo_contestacao": tipo,
        "status_pedido": (pedido.get("status_pedido") or "").strip(),
        "atraso_confirmado": atraso,
        "cupom_oferecido": cupom,
        "resultado": "atendido",
        "categoria": categoria.nome,
        "equipe_responsavel": categoria.equipe,
    }

    _gravar(registro, abertura=proxima.get("data_envio", ""))
    return f"Atendimento registrado para {reclamacao}."


def encaminhar_para_revisao_humana(id_reclamacao: str) -> str:
    """Tira da fila uma reclamação que não pôde ser atendida automaticamente.

    Use quando a reclamação foi retida, o pedido não foi encontrado, o nome não
    confere ou há inconsistências no formulário. Assim a fila avança para a
    próxima resposta do Forms. Não grava relato, nome nem o ID não confirmado.

    Args:
        id_reclamacao: ID da reclamação pendente atual.
    """
    reclamacao = str(id_reclamacao or "").strip()
    proxima, _, erro = obter_proxima_reclamacao()
    if erro:
        return erro
    if proxima is None:
        return "Nenhuma reclamação pendente."
    if reclamacao != proxima["id_reclamacao"]:
        return "Só é possível encaminhar a reclamação pendente atualmente selecionada."

    from tools.consultar_dados import LIMITE_TIPO, reclamacao_tem_injecao

    retida = reclamacao_tem_injecao(proxima)
    _gravar({
        "id_reclamacao": reclamacao,
        "data_atendimento": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tipo_contestacao": "" if retida else
            (proxima.get("tipo_contestacao") or "").strip()[:LIMITE_TIPO],
        "resultado": "revisao_humana",
        "categoria": "" if retida else
            classificar(proxima.get("tipo_contestacao") or "").nome,
        "equipe_responsavel": "Revisão humana",
    }, abertura=proxima.get("data_envio", ""))
    return f"Reclamação {reclamacao} encaminhada para revisão humana e removida da fila."


def _gravar(registro: dict[str, str], abertura: str = "") -> None:
    """Grava o encerramento no CSV local e envia o ticket ao Sheets.

    Todo ticket passa por aqui uma única vez (atendido ou revisão humana), pois
    depois de gravado ele sai da fila. O CSV é a fonte da verdade; o Sheets é só
    o dashboard e roda em segundo plano, sem bloquear nem derrubar o agente.
    """
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    novo = not ARQUIVO_ATENDIMENTOS.exists()
    colunas = list(COLUNAS) if novo else _colunas_do_arquivo()
    with ARQUIVO_ATENDIMENTOS.open(
        "a", encoding="utf-8-sig" if novo else "utf-8", newline=""
    ) as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=colunas, extrasaction="ignore")
        if novo:
            escritor.writeheader()
        escritor.writerow(registro)

    latencia_sheets.agendar_ticket(
        id_ticket=registro["id_reclamacao"],
        abertura=abertura,
        resolucao=registro["data_atendimento"],
        status=registro["resultado"],
    )
