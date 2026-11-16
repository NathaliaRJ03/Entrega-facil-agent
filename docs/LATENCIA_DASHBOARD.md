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

O registro não inclui nome, e-mail nem texto da reclamação. Se a planilha não
estiver configurada ou a gravação falhar, o agente continua respondendo; a falha
fica no log da aplicação.
