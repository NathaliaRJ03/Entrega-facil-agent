"""Registra a triagem feita pelo agente em data/saida/triagens.csv.

Esse arquivo é a ENTREGA do agente para a equipe: a Rebeca ingere na camada
Bronze e a Maria Eduarda usa no dashboard. Contrato em docs/CONTRATOS_DE_DADOS.md.
"""

import csv
import uuid
from datetime import datetime, timezone

from integrations.contratos import PASTA_SAIDA, normalizar_coluna

ARQUIVO_TRIAGENS = PASTA_SAIDA / "triagens.csv"
COLUNAS = (
    "id_triagem", "data_triagem", "id_reclamacao", "id_transacao",
    "tipo_ocorrencia", "prioridade", "encaminhar_humano",
    "justificativa", "proximo_passo", "fontes",
)
PRIORIDADES = {"baixa": "Baixa", "media": "Média", "alta": "Alta"}


def ids_ja_triados() -> set[str]:
    if not ARQUIVO_TRIAGENS.exists():
        return set()
    with ARQUIVO_TRIAGENS.open(encoding="utf-8-sig", newline="") as arquivo:
        return {linha["id_reclamacao"] for linha in csv.DictReader(arquivo)}


def salvar_triagem(
    id_reclamacao: str,
    tipo_ocorrencia: str,
    prioridade: str,
    justificativa: str,
    proximo_passo: str,
    fontes: str,
    encaminhar_humano: bool,
    id_transacao: str = "",
) -> str:
    """Salva o resultado da triagem de uma reclamação.

    Args:
        id_reclamacao: ID da reclamação (ex.: FORM-0003).
        tipo_ocorrencia: Ex.: Falha de Liquidação, Cobrança Indevida, Suspeita de Fraude.
        prioridade: Baixa, Média ou Alta.
        justificativa: Motivo da classificação, em uma ou duas frases.
        proximo_passo: Ação recomendada para a equipe N1.
        fontes: Documentos/tabelas consultados (ex.: runbook_n1.md; gold_falhas INC-002).
        encaminhar_humano: True se o caso precisa de análise humana.
        id_transacao: ID da transação, se conhecido.
    """
    prioridade_ok = PRIORIDADES.get(normalizar_coluna(prioridade))
    if not prioridade_ok:
        return "Prioridade inválida. Use Baixa, Média ou Alta."
    if not (id_reclamacao or "").strip():
        return "Informe o id_reclamacao."
    if id_reclamacao in ids_ja_triados():
        return f"A reclamação {id_reclamacao} já foi triada. Nada foi salvo."

    registro = {
        "id_triagem": uuid.uuid4().hex[:12],
        "data_triagem": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "id_reclamacao": id_reclamacao.strip(),
        "id_transacao": (id_transacao or "").strip(),
        "tipo_ocorrencia": tipo_ocorrencia.strip(),
        "prioridade": prioridade_ok,
        "encaminhar_humano": "sim" if encaminhar_humano else "nao",
        "justificativa": justificativa.strip(),
        "proximo_passo": proximo_passo.strip(),
        "fontes": fontes.strip(),
    }

    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    novo = not ARQUIVO_TRIAGENS.exists()
    with ARQUIVO_TRIAGENS.open("a", encoding="utf-8-sig" if novo else "utf-8",
                               newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS)
        if novo:
            escritor.writeheader()
        escritor.writerow(registro)

    return f"Triagem {registro['id_triagem']} salva para {id_reclamacao}."
