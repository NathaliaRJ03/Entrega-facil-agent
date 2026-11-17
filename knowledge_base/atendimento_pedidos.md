# Atendimento e consulta de pedidos

## Localizar o pedido

O formulário de reclamação informa o nome do cliente e o ID do pedido. A
consulta do histórico Gold usa o ID do pedido e confere o nome associado ao
registro. A resposta da consulta informa se o pedido foi confirmado. Se o ID
não existir, aparecer mais de um registro ou o nome não conferir, não afirme
dados do pedido; peça que a informação seja revisada.

## Situação e entrega

Use a consulta do pedido para responder sobre descrição, status do pedido,
status da entrega, data do pedido, previsão de entrega e data de entrega. A
reclamação do cliente pode mencionar atraso, demora, encomenda ou pedido não
recebido; essas palavras ajudam a localizar esta orientação, mas não comprovam
o status real do pedido.

## Confirmar atraso

O atraso é confirmado primeiro pelo campo `dias_atraso`, quando preenchido. Um
valor maior que zero indica atraso. Caso esse campo não esteja disponível, a
consulta compara a data de entrega com a data prevista. Se ainda não houver
data de entrega, compara a previsão com a data atual de São Paulo. Sem dados
suficientes, o atraso fica indeterminado.

## Cupom por atraso

Ofereça cupom somente quando a ferramenta confirmar `atraso_confirmado: sim`.
Use apenas o código, o benefício e a validade retornados por
oferecer_cupom_atraso, que aplica a tabela progressiva descrita em "Política de
compensação por atraso". Não invente código ou percentual.

## Registrar atendimento

Depois de responder, chame a ferramenta de registro com o ID da reclamação e,
somente se um cupom foi oferecido, o código desse cupom. O backend reconsulta o
pedido e calcula o status e o atraso; não envie esses valores como argumentos.
O CSV operacional guarda ID da reclamação, data do atendimento, ID do pedido,
status do pedido, confirmação de atraso e cupom oferecido. Não guarda o relato,
o nome, o e-mail nem o telefone do cliente.
