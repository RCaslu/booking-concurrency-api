# ADR-0003 — Sem autenticação/autorização nesta entrega

## Contexto

O foco da Entrega 1 é o ambiente reprodutível, a especificação técnica e o test harness cobrindo a garantia central de concorrência — não o ciclo completo de um produto.

## Decisão

`requester_email` é usado como identificador simples de quem faz a reserva, sem JWT/OAuth/sessão. Qualquer chamador pode criar ou cancelar reservas em nome de qualquer e-mail.

## Consequências

- Fora do escopo desta entrega: autenticação, autorização (ex: só o próprio solicitante pode cancelar sua reserva) ficam para uma entrega futura.
- O modelo de dados já isola `requester_email` como campo próprio, o que facilita adicionar autenticação depois sem redesenhar o schema.
