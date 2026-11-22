/**
 * Envia ao cliente um e-mail de confirmação assim que ele responde o Forms.
 *
 * Onde colar: no FORMULÁRIO (não na planilha), menu ⋮ > Editor de scripts.
 * Cole este arquivo, ajuste as constantes e crie o acionador:
 *   Acionadores (relógio) > Adicionar acionador >
 *   função: aoEnviarFormulario | origem: Do formulário | evento: Ao enviar formulário.
 * Na primeira vez, autorize o envio de e-mail pela sua conta.
 *
 * O e-mail sai da conta dona do script. Contas gratuitas enviam até ~100
 * e-mails por dia (Workspace: ~1500).
 */

// Títulos das perguntas do Google Forms.
const PERGUNTA_EMAIL = 'E-mail';
const PERGUNTA_NOME = 'Nome';
const PERGUNTA_PEDIDO = 'ID do pedido';

const NOME_REMETENTE = 'Atendimento Entrega Fácil';
const ASSUNTO = 'Recebemos a sua reclamação';

function aoEnviarFormulario(e) {
  const respostas = [];
  e.response.getItemResponses().forEach(function (item) {
    respostas.push({
      titulo: normalizar(item.getItem().getTitle()),
      valor: String(item.getResponse() || '').trim(),
    });
  });
  // Acha a resposta cujo título começa com o texto procurado (ignora caixa,
  // acentos e pontuação final como "ID do pedido:").
  function resposta(titulo) {
    const alvo = normalizar(titulo);
    const achada = respostas.filter(function (r) { return r.titulo.indexOf(alvo) === 0; })[0];
    return achada ? achada.valor : '';
  }

  // Prefere a pergunta de e-mail; se o Forms coleta e-mails, usa o do respondente.
  const email = resposta(PERGUNTA_EMAIL) || e.response.getRespondentEmail() || '';
  if (!/^[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+$/.test(email)) {
    console.warn('Resposta ' + e.response.getId() + ' sem e-mail válido; nada enviado.');
    return;
  }

  const primeiroNome = resposta(PERGUNTA_NOME).split(/\s+/)[0];
  const pedido = resposta(PERGUNTA_PEDIDO);

  // Não repete o relato nem outros dados do cliente; só confirma o recebimento.
  const corpo = [
    'Olá' + (primeiroNome ? ', ' + primeiroNome : '') + '!',
    '',
    'A Entrega Fácil recebeu a sua reclamação' + (pedido ? ' sobre o pedido ' + pedido : '') + '.',
    'Nossa equipe vai analisar o caso e retornar o contato em breve.',
    '',
    'Se precisar complementar alguma informação, é só responder a este e-mail.',
    '',
    'Atenciosamente,',
    'Equipe Entrega Fácil',
  ].join('\n');

  try {
    MailApp.sendEmail({ to: email, subject: ASSUNTO, body: corpo, name: NOME_REMETENTE });
  } catch (erro) {
    // Falha de e-mail não pode impedir o registro da reclamação.
    console.error('Falha ao enviar confirmação da resposta ' + e.response.getId() + ': ' + erro);
  }
}

function normalizar(texto) {
  return String(texto || '')
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

/**
 * Diagnóstico: selecione esta função no editor e clique em Executar.
 * Mostra no log (Execuções) a conta que o script usa para enviar e-mails.
 * Deve aparecer entregafacil08@gmail.com.
 */
function verificarRemetente() {
  console.log('Conta que envia: ' + Session.getEffectiveUser().getEmail());
}
