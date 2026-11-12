## Procedimento PIX não compensado ou preso em processamento
Sintomas: Cliente realizou transferência PIX, valor saiu da conta mas não caiu no destino ou consta como pendente.
Ação N1: Verificar status da transação na fila de liquidação instantânea. Se passar de 15 minutos em processamento, abrir chamado urgente para Engenharia de Pagamentos (N2) anexando o ID da transação (E2E).
Prioridade: Alta.

## Procedimento Cobrança Duplicada no Cartão
Sintomas: Cliente relata duas cobranças iguais para a mesma compra no cartão de crédito ou débito.
Ação N1: Conferir se uma das transações está apenas como pré-autorização pendente. Se ambas estiverem liquidadas, orientar protocolo de contestação e encaminhar para fila de Estornos.
Prioridade: Média.

## Procedimento Falha de Liquidação para Lojista (Repasse)
Sintomas: Estabelecimento comercial reclama que as vendas do dia não foram liquidadas na conta bancária.
Ação N1: Validar lote de liquidação bancária (TED/PIX) e conferir se há bloqueio preventivo de risco. Escalar para time Financeiro/Liquidação.
Prioridade: Alta.