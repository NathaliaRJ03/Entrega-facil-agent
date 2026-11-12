## Erro ERR_504_GATEWAY_TIMEOUT
Descrição: Tempo limite excedido na comunicação com o arranjo de pagamento ou banco emissor.
Impacto: Transação fica com status indeterminado para o cliente, podendo gerar tentativa duplicada.
Diagnóstico N1: Solicitar comprovante e horário exato da tentativa antes de orientar nova transação.

## Erro ERR_LIQ_422_CONTA_INVALIDA
Descrição: Rejeição na liquidação financeira por divergência de titularidade ou dados bancários do recebedor.
Impacto: Valor retido em conta transitória da PagFácil aguardando regularização cadastral.
Diagnóstico N1: Pedir confirmação de agência, conta e CPF/CNPJ do titular para reprocessamento.