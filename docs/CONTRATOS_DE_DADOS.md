# Contratos de dados do atendimento de pedidos

O agente recebe reclamações do Forms, consulta a tabela Gold pelo ID do pedido e
registra metadados do atendimento. A engenharia de dados entrega os cabeçalhos
da Gold já traduzidos para português, usando os nomes canônicos abaixo. O código
também aceita variações portuguesas listadas nas tabelas.

## Regras gerais

- CSV em UTF-8, com cabeçalho na primeira linha. Vírgula e ponto e vírgula são
  aceitos.
- A comparação dos cabeçalhos ignora caixa, acentos e espaços.
- Datas devem usar `AAAA-MM-DD`, `AAAA-MM-DD HH:MM:SS`, `DD/MM/AAAA` ou
  `DD.MM.AAAA`.
- Coloque os arquivos em `data/entrada/`. Enquanto não chegarem, o agente usa
  `data/amostras/` e identifica a resposta como amostra sintética.
- Colunas extras são ignoradas. Campos opcionais ausentes não são inferidos.

## 1. Reclamações do Google Forms

O Forms nativo continua sendo a entrada preferida. O agente lê a planilha de
respostas via `FORMS_SHEET_ID` ou `FORMS_CSV_URL`. Também aceita o arquivo
`data/entrada/reclamacoes_forms.csv`.

| Campo canônico | Obrigatório | Exemplos de título no Forms |
|---|---:|---|
| `relato` | sim | Descreva o que aconteceu, Descreva o problema, Reclamação |
| `id_pedido` | sim | ID do pedido, Número do pedido, Pedido |
| `nome_cliente` | sim | Nome, Nome completo, Nome do cliente |
| `id_reclamacao` | não | ID, Protocolo; se ausente, é criado como `FORM-0001` etc. |
| `data_envio` | não | Carimbo de data/hora (gerado pelo Forms) |
| `produto` | não | Produto, Produto ou serviço |

O nome é usado no backend para conferir o registro da Gold junto com o ID do
pedido. Ele não é incluído na resposta da ferramenta ao modelo nem gravado no
arquivo de atendimento. E-mail e outros campos de contato são ignorados.

## 2. Rebeca (Engenharia de Dados): histórico Gold de pedidos

Arquivo local: `gold_pedidos.csv`. Tabela opcional no Databricks: configure
`DATABRICKS_TABELA_GOLD_PEDIDOS` junto com `DATABRICKS_SERVER_HOSTNAME`,
`DATABRICKS_HTTP_PATH` e `DATABRICKS_TOKEN`.

**Entregue uma linha por pedido**, com o identificador igual ao que o cliente
preenche no Forms. O agente interrompe a consulta de cupom se encontrar mais de
um registro para o mesmo ID.

| Campo canônico | Obrigatório | Variações portuguesas aceitas |
|---|---:|---|
| `id_pedido` | sim | ID do pedido, número do pedido, pedido |
| `nome_cliente` | sim | Nome, nome completo, nome do cliente |
| `status_pedido` | não | status do pedido, status |
| `data_pedido` | não | data do pedido |
| `data_prevista_entrega` | recomendado | previsão de entrega, data prevista de entrega, prazo de entrega |
| `data_entrega` | recomendado | data da entrega, entrega realizada em |
| `dias_atraso` | não | dias de atraso, atraso em dias |
| `status_entrega` | não | status da entrega |
| `descricao_pedido` | não | descrição do pedido, produto |

Rebeca deve entregar esses campos traduzidos e garantir que o mesmo
`id_pedido` e `nome_cliente` estejam no Forms e na Gold. O sistema consulta pelo
ID do pedido e compara o nome antes de retornar os dados; diferença de nome ou
mais de uma linha para o pedido bloqueia a consulta. A comparação ignora caixa,
acentos e pontuação. Se os valores de status continuarem em códigos SAP, inclua
também a descrição correspondente ou uma tabela de tradução.

O agente calcula atraso nesta ordem:

1. Se `dias_atraso` vier preenchido, valor maior que zero confirma atraso.
2. Caso contrário, compara `data_entrega` com `data_prevista_entrega`.
3. Se ainda não houver data de entrega, compara a previsão com a data atual de
   São Paulo.
4. Sem dados suficientes, o atraso fica indeterminado e nenhum cupom é oferecido.

No Databricks, a consulta lê os nomes das colunas e filtra pelo ID com parâmetro
SQL. Não carrega a Gold inteira para procurar o pedido em Python. Use
`databricks-sql-connector` versão 3.0.0 ou superior para parâmetros nativos.

## 3. Política de cupom

Configure `CUPOM_ATRASO_CODIGO` e `CUPOM_ATRASO_DESCONTO` com os valores aprovados
pela equipe. A ferramenta só retorna o cupom configurado quando confirma um
único pedido atrasado. Sem os dois valores, não há oferta automática: o agente
explica que a campanha precisa ser confirmada. O projeto não emite códigos
individuais nem verifica validade ou limite de uso; isso exige integração com o
sistema de cupons.

## Saída: `data/saida/atendimentos.csv`

Uma linha por reclamação atendida. O arquivo serve para remover a reclamação da
fila e manter auditoria operacional, sem gravar o texto da reclamação, nome ou
e-mail.

| Coluna | Descrição |
|---|---|
| `id_reclamacao` | ID da resposta do Forms (`FORM-000N` se não houver protocolo) |
| `data_atendimento` | Data e hora UTC em ISO 8601 |
| `id_pedido` | Pedido consultado, se informado |
| `status_pedido` | Status encontrado na Gold |
| `atraso_confirmado` | `sim`, `nao` ou `indeterminado` |
| `cupom_oferecido` | Código aprovado oferecido, ou vazio |
