# Contratos de dados do atendimento de pedidos

O agente recebe reclamações do Forms, consulta a tabela Gold pelo ID do pedido e
registra metadados do atendimento. A engenharia de dados entrega os cabeçalhos
da Gold já traduzidos para português, usando os nomes canônicos abaixo. O código
também aceita variações portuguesas listadas nas tabelas.

## Regras gerais

- **Fontes únicas:** as reclamações vêm só das respostas do Google Forms (via
  Google Sheets) e os pedidos vêm só da tabela Gold no Databricks. Não há
  reserva em arquivo local nem amostra sintética: se uma fonte falhar, o agente
  não encontra o dado e encaminha para revisão humana.
- A comparação dos cabeçalhos ignora caixa, acentos e espaços.
- Datas devem usar `AAAA-MM-DD`, `AAAA-MM-DD HH:MM:SS`, `DD/MM/AAAA` ou
  `DD.MM.AAAA`.
- Colunas extras são ignoradas. Campos opcionais ausentes não são inferidos.

## Proteção dos relatos do Forms

- O formulário deve orientar a pessoa a não informar senhas, códigos de
  autenticação, dados completos de cartão ou dados bancários. Sugestão de
  aviso: "Não inclua senhas ou dados de pagamento no relato. Informe apenas o
  número do pedido e o problema ocorrido."
- O agente carrega uma reclamação por vez. No atendimento, nome, e-mail e
  telefone não são enviados ao modelo; o nome e o ID do pedido são usados apenas
  no backend para conferir a correspondência com a Gold.
- A lista de reclamações (`listar_reclamacoes_forms`) exibe nome, e-mail e ID
  do pedido em tabela. Nesses campos, só CPF, cartão e credenciais são
  mascarados. Relato e código da transação não aparecem na lista.
- Antes do envio ao modelo, o relato tem limite de 2.000 caracteres e são
  mascarados formatos reconhecíveis de CPF, CNPJ, e-mail, telefone, cartão,
  chave PIX no formato UUID, algumas credenciais e as ocorrências exatas do nome
  e do ID do pedido cadastrados. Relatos com frases comuns de prompt injection
  ficam retidos para revisão humana.
- O detector cobre padrões comuns e não identifica todo dado sensível ou toda
  tentativa de manipulação. A proteção principal é limitar as ferramentas e
  validar consultas, cupons e registros no backend.
- A redação protege o conteúdo enviado pelo agente ao modelo; ela não apaga nem
  altera a resposta original armazenada no Forms ou no Google Sheets.
- O identificador usado pelo agente deve conter de 1 a 80 letras ASCII,
  números, pontos, sublinhados ou hifens. Identificadores fora desse formato
  requerem revisão manual.

## 1. Reclamações do Google Forms

O Forms nativo continua sendo a entrada preferida. O agente lê a planilha de
respostas via `FORMS_CSV_URL` ou `FORMS_SHEET_ID`.

| Campo canônico | Obrigatório | Exemplos de título no Forms |
|---|---:|---|
| `relato` | sim | Descreva o que aconteceu, Descreva o problema, Reclamação |
| `id_pedido` | sim | ID do pedido, Número do pedido, Pedido |
| `nome_cliente` | sim | Nome, Nome completo, Nome do cliente |
| `id_reclamacao` | não | ID, Protocolo; se ausente, é criado como `FORM-0001` etc. |
| `data_envio` | não | Carimbo de data/hora (gerado pelo Forms) |
| `tipo_contestacao` | não | Tipo de contestação, Motivo |
| `data_compra` | não | Informe quando a compra foi realizada, Data da compra |
| `codigo_transacao` | não | Código da transação, ID da transação |
| `valor_pedido` | não | Valor do pedido, Valor da compra |

O nome é usado no backend para conferir o registro da Gold junto com o ID do
pedido. Ele não é incluído na resposta da ferramenta ao modelo nem gravado no
arquivo de atendimento. A pergunta "E-mail de contato" do Forms e outros campos
de contato são ignorados.

Como o agente usa os campos novos:

- `tipo_contestacao` é enviado ao modelo e gravado em `atendimentos.csv`. Só
  contestações de atraso ou entrega (ou sem tipo) podem receber cupom; os demais
  tipos (cobrança duplicada, valor diferente, item faltando) vão para revisão
  humana. A regra é aplicada no backend.
- `data_compra` e `valor_pedido` são enviados ao modelo como "informados pelo
  cliente", após validação. Data posterior ao envio ou valor fora do formato
  aparecem como `inconsistencias_no_formulario`.
- `codigo_transacao` não é enviado ao modelo: ele só recebe se o código foi
  informado (sim/não).

## 2. Rebeca (Engenharia de Dados): histórico Gold de pedidos

Tabela no Databricks (única fonte de pedidos): configure
`DATABRICKS_TABELA_GOLD_PEDIDOS` junto com `DATABRICKS_SERVER_HOSTNAME`,
`DATABRICKS_HTTP_PATH` e `DATABRICKS_TOKEN`. Teste com
`python scripts/testar_databricks.py <ID_PEDIDO>`.

A tabela pode ter **uma linha por remessa** (até 50 por pedido). O agente junta
as remessas do mesmo ID e usa a mais atrasada; se as remessas tiverem nomes de
cliente diferentes, a consulta é bloqueada. O ID é aceito com ou sem zeros à
esquerda (`5000100` encontra `0005000100`).

| Campo canônico | Obrigatório | Variações portuguesas aceitas |
|---|---:|---|
| `id_pedido` | sim | ID do pedido, número do pedido, pedido |
| `nome_cliente` | sim | Nome, nome completo, nome do cliente |
| `status_pedido` | não | status do pedido, status, situacao_pedido |
| `data_pedido` | não | data do pedido |
| `data_prevista_entrega` | recomendado | previsão de entrega, data prevista de entrega, prazo de entrega, data_planejada_entrega |
| `data_entrega` | recomendado | data da entrega, entrega realizada em, data_real_entrega |
| `dias_atraso` | não | dias de atraso, atraso em dias (positivo = atrasado) |
| `status_entrega` | não | status da entrega, atraso_status |
| `descricao_pedido` | não | descrição do pedido, produto, descricao_produto |

A coluna `atraso` da Gold atual **não** é usada: nela, atraso é negativo e
adiantamento é positivo, o inverso de `dias_atraso`. O agente calcula pelas
datas, que dão o mesmo número com o sinal correto.

Rebeca deve entregar esses campos traduzidos e garantir que o mesmo
`id_pedido` e `nome_cliente` estejam no Forms e na Gold. O sistema consulta pelo
ID do pedido e compara o nome antes de retornar os dados; diferença de nome
bloqueia a consulta. A comparação ignora caixa,
acentos e pontuação. Se os valores de status continuarem em códigos SAP, inclua
também a descrição correspondente ou uma tabela de tradução.

O agente calcula atraso nesta ordem:

1. Se `dias_atraso` vier preenchido, valor maior que zero confirma atraso.
2. Caso contrário, compara `data_entrega` com `data_prevista_entrega`.
3. Sem as duas datas (por exemplo, remessa ainda não entregue), o atraso fica
   indeterminado e nenhum cupom é oferecido. O agente não estima atraso
   comparando a previsão com a data de hoje.

No Databricks, a consulta lê os nomes das colunas e filtra pelo ID com parâmetro
SQL. Não carrega a Gold inteira para procurar o pedido em Python. Use
`databricks-sql-connector` versão 3.0.0 ou superior para parâmetros nativos.

## 3. Tipos de reclamação e atitude do agente

O campo "Tipo de contestação" do Forms define a categoria, no backend
(`tools/tipos_reclamacao.py`), por palavras-chave. O modelo não escolhe a
categoria. **Só "Atraso na entrega" pode gerar cupom**, e somente quando a Gold
confirma o atraso pelas datas. Tipo vazio ou desconhecido vai para revisão
humana.

| Categoria | Equipe | Atitude | Cupom |
|---|---|---|---|
| Atraso na entrega | Atendimento | Confirma o atraso na Gold; se confirmado, oferece o cupom da faixa; se sem data de entrega, revisão humana | Só com atraso confirmado |
| Produto errado | Trocas e Devoluções | Mostra o produto da Gold, pede foto, pergunta troca ou reembolso | Não |
| Cancelamento ou reembolso | Financeiro | Diz que não consegue validar a solicitação e a encaminha para análise | Não |
| Cobrança diferente | Financeiro | Igual ao cancelamento ou reembolso; a Gold não tem valores; pede comprovante se não houver código da transação | Não |
| Pedido não encontrado | Atendimento | Gold achou: informa situação e previsão. Não achou: um analista retorna em breve com o número do pedido (revisão humana) | Não |
| Pedido não enviado | Logística | Diz que a solicitação foi enviada para análise do setor responsável | Não |
| Itens faltando | Logística | Diz que a equipe vai informar as etapas para a devolução do pedido | Não |

O registro do atendimento grava `categoria` e `equipe_responsavel`.

## 4. Política de cupom

A política segue uma tabela progressiva por dias de atraso, definida em
`tools/politica_cupons.py` (códigos, benefícios e validade) e explicada ao
agente em `knowledge_base/politica_cupons_atraso.md`:

| Atraso | Código | Benefício | Validade |
|---|---|---|---|
| 1 a 3 dias | DESCULPA5 ou FRETEZERO | 5% OFF ou frete grátis | 30 dias |
| 4 a 7 dias | ATRASO10 | 10% OFF | 30 dias |
| 8 a 14 dias | PRIORIDADE15 | 15% OFF + prioridade de envio | 45 dias |
| 15 dias ou mais | ESPECIAL20 | 20% OFF (ou cancelamento com reembolso, via revisão humana) | 60 dias |

A ferramenta só retorna o cupom quando confirma um único pedido atrasado, e o
registro só aceita o código da faixa calculada. Cliente muito irritado na
primeira faixa pode subir para ATRASO10. O projeto não emite códigos
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
