Leia CLAUDE.md e docs/spec.md antes de começar e siga as regras deles.

Tarefa: implementar RF8 — remarcar uma reserva existente via PATCH /bookings/{id}, com corpo {"start_time": ..., "end_time": ...}.

Regras:
- Só pode remarcar reserva ACTIVE que ainda não começou (mesma regra de R4).
- A nova janela passa pelas mesmas validações de criação (R1, R2, R6).
- A nova janela não pode sobrepor outra reserva ACTIVE do mesmo recurso (a própria reserva sendo remarcada não conta como conflito).
- Tem que ser seguro sob concorrência: duas remarcações simultâneas para horários conflitantes, ou uma remarcação concorrendo com uma criação, nunca podem resultar em sobreposição.
- Respostas: 200 com o Booking atualizado; 404 BOOKING_NOT_FOUND; 422 INVALID_TIME_WINDOW; 409 OVERLAPPING_BOOKING, BOOKING_ALREADY_STARTED ou BOOKING_ALREADY_CANCELLED.

Entregáveis:
- Atualizar docs/spec.md (RF8, tabela de endpoints e um item novo na seção Refinamento).
- Testes unit, integration e concurrency seguindo as convenções do CLAUDE.md.
- Rodar a suíte completa (docker compose up -d db-test, depois PYTHONPATH=src pytest -v) e deixar tudo passando.
- Commitar na branch atual. Não fazer push.
