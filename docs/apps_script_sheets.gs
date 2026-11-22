/**
 * Recebe as linhas do agente (latência e tickets) e grava na planilha.
 *
 * Onde colar: na planilha, Extensões > Apps Script. Substitua todo o conteúdo
 * por este arquivo, troque o TOKEN pelo valor de SHEETS_WEBHOOK_TOKEN do .env
 * e implante como App da Web.
 */
const TOKEN = 'COLE_AQUI_O_SHEETS_WEBHOOK_TOKEN_DO_ENV';
// ID da planilha (o trecho entre /d/ e /edit no link dela). Necessário quando o
// script não foi criado por Extensões > Apps Script dentro da própria planilha.
const PLANILHA_ID = '';

function doPost(e) {
  let dados;
  try {
    dados = JSON.parse(e.postData.contents);
  } catch (erro) {
    return responder({ ok: false, erro: 'corpo inválido' });
  }
  if (dados.token !== TOKEN) {
    return responder({ ok: false, erro: 'token inválido' });
  }
  if (!dados.aba || !Array.isArray(dados.cabecalhos) || !Array.isArray(dados.linha)) {
    return responder({ ok: false, erro: 'faltam aba, cabecalhos ou linha' });
  }

  // Evita que duas gravações ao mesmo tempo escrevam o cabeçalho duas vezes.
  const trava = LockService.getScriptLock();
  trava.waitLock(10000);
  try {
    const planilha = PLANILHA_ID
      ? SpreadsheetApp.openById(PLANILHA_ID)
      : SpreadsheetApp.getActiveSpreadsheet();
    if (!planilha) {
      return responder({ ok: false, erro: 'preencha PLANILHA_ID no Apps Script' });
    }
    const aba = planilha.getSheetByName(dados.aba) || planilha.insertSheet(dados.aba);

    if (aba.getLastRow() === 0) {
      aba.appendRow(dados.cabecalhos);
    } else {
      const atuais = aba.getRange(1, 1, 1, dados.cabecalhos.length).getValues()[0];
      if (atuais.join('|') !== dados.cabecalhos.join('|')) {
        return responder({
          ok: false,
          erro: 'a aba ' + dados.aba + ' precisa ter os cabeçalhos ' + dados.cabecalhos.join(', '),
        });
      }
    }

    aba.appendRow(dados.linha);
    return responder({ ok: true });
  } finally {
    trava.releaseLock();
  }
}

function responder(objeto) {
  return ContentService
    .createTextOutput(JSON.stringify(objeto))
    .setMimeType(ContentService.MimeType.JSON);
}
