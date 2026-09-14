# ADR-0001 — Mecanismo de controle de concorrência

## Contexto

O núcleo do projeto é impedir double-booking sob requisições verdadeiramente concorrentes para o mesmo recurso/horário. Três abordagens foram avaliadas: lock em memória por recurso, lock otimista (version/ETag) com retry, e lock pessimista no banco (`SELECT ... FOR UPDATE`) combinado com uma constraint estrutural.

## Decisão

`SELECT ... FOR UPDATE` na linha do `Resource` dentro da transação de criação da reserva, serializando escritores concorrentes do mesmo recurso — mais uma `ExcludeConstraint` do Postgres na tabela `bookings` (`resource_id WITH =, tstzrange(start_time, end_time, '[)') WITH &&`, filtrada por `status = 'ACTIVE'`) como rede de segurança estrutural.

## Alternativas descartadas

- **Lock em memória (`threading.Lock`/`asyncio.Lock` por recurso)**: só funciona com processo único, sem múltiplos workers/réplicas — não é uma solução real de sistema distribuído, e não sobrevive a mais de um processo Uvicorn.
- **Lock otimista com retry**: viável, mas sob contenção alta em um slot popular gera número variável de retries, tornando o teste de concorrência mais difícil de manter 100% determinístico.

## Consequências

- A garantia de R3 não depende só do código Python estar correto — mesmo um bug que pulasse a checagem de overlap seria barrado pelo `IntegrityError` da constraint, mapeado para `OverlappingBookingError` (409).
- Testável de forma determinística: como o lock vive no banco (não em memória do processo Python), N requisições concorrentes reais são serializadas de forma consistente, sem depender de `sleep` ou timing da aplicação.
- Exige Postgres (ver ADR-0002) — `ExcludeConstraint` não existe em SQLite.
