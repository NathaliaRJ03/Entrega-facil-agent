"""Contratos de dados: o que cada pessoa da equipe entrega para o agente.

Cada contrato define as colunas canônicas que o agente usa e os nomes
alternativos aceitos (ex.: o título da pergunta no Google Forms). Assim a
equipe pode entregar o arquivo com o cabeçalho que for mais natural, desde
que ele bata com algum apelido. Ver docs/CONTRATOS_DE_DADOS.md.

Ordem de busca dos arquivos:
1. data/entrada/<arquivo>   -> dados reais da equipe (fora do Git, LGPD)
2. data/amostras/<arquivo>  -> amostra sintética para o agente rodar sem eles
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

PASTA_PROJETO = Path(__file__).resolve().parent.parent
PASTA_ENTRADA = PASTA_PROJETO / "data" / "entrada"
PASTA_AMOSTRAS = PASTA_PROJETO / "data" / "amostras"
PASTA_SAIDA = PASTA_PROJETO / "data" / "saida"


def normalizar_coluna(nome: str) -> str:
    """'Valor da transação (R$)' -> 'valor_da_transacao_r'."""
    nome = unicodedata.normalize("NFD", str(nome).strip().lower())
    nome = "".join(c for c in nome if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", nome).strip("_")


@dataclass(frozen=True)
class Contrato:
    nome: str
    responsavel: str
    arquivo: str
    colunas: dict[str, tuple[str, ...]]
    obrigatorias: tuple[str, ...] = field(default=())

    def resolver_coluna(self, canonica: str, nomes: list[str]) -> str | None:
        """Localiza o cabeçalho original correspondente a uma coluna canônica."""
        recebidas = {normalizar_coluna(nome): nome for nome in nomes}
        for opcao in (canonica, *self.colunas.get(canonica, ())):
            original = recebidas.get(normalizar_coluna(opcao))
            if original is not None:
                return original
        return None

    def localizar_arquivo(self) -> tuple[Path | None, bool]:
        """Retorna (caminho, eh_amostra). Prefere os dados reais da equipe."""
        real = PASTA_ENTRADA / self.arquivo
        if real.exists():
            return real, False
        amostra = PASTA_AMOSTRAS / self.arquivo
        if amostra.exists():
            return amostra, True
        return None, False

    def padronizar(self, linhas: list[dict], origem: str) -> list[dict[str, str]]:
        """Renomeia as colunas para os nomes canônicos e valida as obrigatórias."""
        if not linhas:
            return []

        mapa: dict[str, str] = {}
        nomes = list(linhas[0].keys())
        for canonica in self.colunas:
            original = self.resolver_coluna(canonica, nomes)
            if original is not None:
                mapa[canonica] = original

        faltando = [c for c in self.obrigatorias if c not in mapa]
        if faltando:
            raise ValueError(
                f"{origem}: faltam as colunas {faltando} do contrato "
                f"'{self.nome}' (responsável: {self.responsavel}). "
                f"Colunas recebidas: {list(linhas[0].keys())}"
            )

        padronizadas = []
        for linha in linhas:
            registro = {c: "" for c in self.colunas}
            for canonica, original in mapa.items():
                valor = linha.get(original)
                registro[canonica] = "" if valor is None else str(valor).strip()
            padronizadas.append(registro)
        return padronizadas


def ler_csv(caminho: Path) -> list[dict[str, str]]:
    """Lê CSV com vírgula ou ponto e vírgula (Excel em português usa ';')."""
    return ler_csv_texto(caminho.read_text(encoding="utf-8-sig"))


def ler_csv_texto(texto: str) -> list[dict[str, str]]:
    """Mesmo que ler_csv, mas a partir do conteúdo (ex.: baixado de uma URL)."""
    texto = texto.lstrip("﻿")
    try:
        dialeto = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t")
    except csv.Error:
        dialeto = csv.excel
    return list(csv.DictReader(io.StringIO(texto, newline=""), dialect=dialeto))


# --- Victor (NOC): respostas do Google Forms de reclamações -----------------
RECLAMACOES = Contrato(
    nome="reclamacoes_forms",
    responsavel="Victor (NOC)",
    arquivo="reclamacoes_forms.csv",
    colunas={
        "id_reclamacao": ("id", "protocolo", "numero_protocolo"),
        "id_pedido": ("id do pedido", "pedido", "número do pedido", "numero do pedido"),
        "nome_cliente": ("nome", "nome completo", "nome do cliente"),
        "data_envio": ("carimbo de data/hora", "timestamp", "data_hora", "data"),
        "produto": ("qual produto", "produto ou serviço", "servico", "produto_servico"),
        "tipo_contestacao": ("tipo de contestação", "tipo", "motivo"),
        "relato": ("descreva oque aconteceu", "descreva o que aconteceu",
                   "descreva o problema", "descrição", "descricao", "reclamação",
                   "reclamacao", "mensagem"),
        "valor": ("valor contestado", "valor da transação", "valor da transação (r$)",
                  "valor (r$)"),
        "data_transacao": ("informe quando a operação foi realizada",
                           "data da transação", "data da operação"),
        "id_transacao": ("id da transação", "código da transação", "codigo_transacao",
                         "e2e", "id_e2e"),
    },
    obrigatorias=("relato", "id_pedido", "nome_cliente"),
)

# --- Rebeca (Eng. de Dados): histórico Gold sintético de pedidos -------------
# Os cabeçalhos entregues pela engenharia de dados já devem estar traduzidos.
PEDIDOS = Contrato(
    nome="gold_pedidos",
    responsavel="Rebeca (Eng. de Dados)",
    arquivo="gold_pedidos.csv",
    colunas={
        "id_pedido": ("id do pedido", "número do pedido", "numero do pedido", "pedido"),
        "nome_cliente": ("nome", "nome completo", "nome do cliente"),
        "status_pedido": ("status do pedido", "status"),
        "data_pedido": ("data do pedido",),
        "data_prevista_entrega": (
            "previsão de entrega", "previsao de entrega", "data prevista de entrega",
            "prazo de entrega",
        ),
        "data_entrega": (
            "data de entrega", "data da entrega", "entrega realizada em",
        ),
        "dias_atraso": ("dias de atraso", "atraso em dias"),
        "status_entrega": ("status da entrega",),
        "descricao_pedido": ("descrição do pedido", "descricao do pedido", "produto"),
    },
    obrigatorias=("id_pedido", "nome_cliente"),
)

# --- Rebeca (Eng. Dados): tabela Gold de liquidações -------------------------
LIQUIDACOES = Contrato(
    nome="gold_liquidacoes",
    responsavel="Rebeca (Eng. de Dados)",
    arquivo="gold_liquidacoes.csv",
    colunas={
        "id_transacao": ("transaction_id", "id_e2e", "e2e"),
        "data_transacao": ("transaction_date", "dt_transacao"),
        "produto": ("metodo_pagamento", "payment_method", "canal"),
        "valor": ("amount", "valor_transacao"),
        "status_liquidacao": ("status", "settlement_status"),
        "codigo_erro": ("error_code", "cod_erro"),
        "data_liquidacao": ("settlement_date", "dt_liquidacao"),
        "latencia_liquidacao_seg": ("latencia_seg", "settlement_latency_sec"),
    },
    obrigatorias=("id_transacao", "status_liquidacao"),
)

# --- Rebeca (Eng. Dados): tabela Gold de falhas/incidentes -------------------
FALHAS = Contrato(
    nome="gold_falhas",
    responsavel="Rebeca (Eng. de Dados)",
    arquivo="gold_falhas.csv",
    colunas={
        "id_incidente": ("incident_id", "id_falha"),
        "servico": ("produto", "service", "componente"),
        "inicio": ("data_inicio", "started_at", "inicio_falha"),
        "fim": ("data_fim", "resolved_at", "fim_falha"),
        "codigo_erro": ("error_code", "cod_erro"),
        "severidade": ("severity", "criticidade"),
        "transacoes_afetadas": ("qtd_transacoes_afetadas", "affected_transactions"),
        "descricao": ("description", "resumo"),
    },
    obrigatorias=("id_incidente", "servico", "inicio"),
)

# --- Rebeca (Eng. Dados): amostra do CFPB tratada (alimenta o RAG) -----------
HISTORICO_CFPB = Contrato(
    nome="cfpb_reclamacoes",
    responsavel="Rebeca (Eng. de Dados)",
    arquivo="cfpb_reclamacoes.csv",
    colunas={
        "id_reclamacao": ("complaint_id", "complaint id"),
        "produto": ("product",),
        "subproduto": ("sub_product", "sub-product"),
        "problema": ("issue",),
        "subproblema": ("sub_issue", "sub-issue"),
        "relato": ("consumer_complaint_narrative", "consumer complaint narrative",
                   "narrativa"),
        "resposta_empresa": ("company_response_to_consumer",
                             "company response to consumer"),
    },
    obrigatorias=("relato",),
)
