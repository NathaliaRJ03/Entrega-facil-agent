# Latência do agente para o dashboard

O agente mede o tempo entre o início e o fim de cada invocação do Google ADK.
Essa duração inclui as chamadas ao modelo e às ferramentas usadas durante a
resposta. O cronômetro usa `perf_counter_ns`, e os horários são gravados em UTC.

Quando o agente termina, uma linha é enviada em segundo plano para o Google
Sheets. A escrita ocorre fora do caminho da resposta para não esperar a rede da
planilha antes de responder ao usuário.

## Configuração

Defina no `.env`:

```dotenv
GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
LATENCIA_SHEETS_ID=ID_DA_PLANILHA
LATENCIA_SHEETS_ABA=latencia_agente
```

Para preencher `LATENCIA_SHEETS_ID`, copie somente o trecho entre `/d/` e
`/edit` do link da planilha. Por exemplo, em
`https://docs.google.com/spreadsheets/d/1AbCxyz987/edit`, o ID é
`1AbCxyz987`. `LATENCIA_SHEETS_ABA` é o nome da guia dentro da planilha; pode
manter `latencia_agente`.

Compartilhe a planilha com o e-mail da conta de serviço indicado no arquivo de
credenciais e dê permissão de **Editor**. Se a aba `latencia_agente` não existir,
o projeto a cria na primeira gravação.

### Alternativa sem Google Cloud: Apps Script

Se não for possível criar a conta de serviço, a própria planilha recebe as
linhas por um app da web do Apps Script:

1. Na planilha, abra **Extensões > Apps Script**, apague o conteúdo e cole
   `docs/apps_script_sheets.gs`.
2. Troque o valor de `TOKEN` pelo `SHEETS_WEBHOOK_TOKEN` do `.env` e salve.
3. **Implantar > Nova implantação**, tipo **App da Web**, executar como
   **Eu**, acesso **Qualquer pessoa**. Autorize quando pedir.
4. Copie o link que termina em `/exec` para `SHEETS_WEBHOOK_URL` no `.env`.

Com `SHEETS_WEBHOOK_URL` preenchido, o agente usa esse caminho no lugar da conta
de serviço. "Qualquer pessoa" só permite chamar o link; sem o token, o script
recusa a gravação. Ao alterar o script, publique uma nova versão em
**Implantar > Gerenciar implantações** para a mudança valer.

## Colunas enviadas

| Coluna | Significado |
|---|---|
| `id_invocacao` | Identificador único desta execução no ADK |
| `agente` | Nome do agente que respondeu |
| `inicio_utc` | Horário em que começou o processamento |
| `fim_utc` | Horário em que terminou a geração da resposta, em UTC |
| `horario_resposta` | Horário local de São Paulo em que a resposta terminou |
| `latencia_ms` | Duração total em milissegundos |
| `status` | `sucesso` quando a execução concluiu |

## Tickets encerrados

Na mesma planilha, a aba `tickets_atendimento` (ou o nome em
`TICKETS_SHEETS_ABA`) recebe uma linha cada vez que uma reclamação sai da fila,
seja atendida ou encaminhada para revisão humana. A aba é criada na primeira
gravação.

| Coluna | Significado |
|---|---|
| `ID_TICKET` | ID da reclamação do Forms (ex.: `FORM-0007`) |
| `TIMESTAMP_ABERTURA` | Carimbo de data/hora da resposta no Forms |
| `TIMESTAMP_RESOLUCAO` | Quando o agente encerrou o ticket |
| `STATUS_TICKET` | `atendido` ou `revisao_humana` |

Os dois horários vão no fuso de São Paulo com o deslocamento explícito
(ex.: `2026-11-12T15:05:00-03:00`). O Forms grava hora local e o registro do
atendimento é UTC; sem essa conversão, o tempo de resolução sairia 3 horas
errado. O arquivo `data/saida/atendimentos.csv` continua sendo a fonte da
verdade; o Sheets é só o dashboard.

O registro não inclui nome, e-mail nem texto da reclamação. Se a planilha não
estiver configurada ou a gravação falhar, o agente continua respondendo; a falha
fica no log da aplicação.
