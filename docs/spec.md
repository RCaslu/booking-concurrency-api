# SDD As-Built: Booking Concurrency API v1.0.0

Especificação técnica **definitiva**, descrevendo o sistema exatamente como foi entregue na release `v1.0.0`. Cada contrato, regra e componente abaixo foi conferido contra o código desta versão, e cada requisito aponta para os testes que o provam ([rastreabilidade](#rastreabilidade-requisito--teste)).

O documento nasceu como especificação de entrada do SDD (Entrega 1) e foi sendo ajustado conforme os testes e as revisões revelavam lacunas. Essas mudanças estão registradas, em ordem, na seção [Refinamento](#refinamento), no final.

## O problema

Sistema de reserva de salas de reunião que precisa garantir, sob requisições concorrentes, que **duas reservas nunca ocupem a mesma sala no mesmo intervalo de tempo**. É o clássico problema de double-booking de sistemas de agendamento (Google Calendar, Calendly). A garantia precisa ser estrutural, sem depender de sorte de timing, e comprovável por teste automatizado determinístico.

O domínio escolhido foi salas de reunião, e não vagas de estacionamento, porque o conceito de intervalo `[início, fim)` é fácil de explicar e gera casos de borda inequívocos: uma reunião que termina às 15h não conflita com outra que começa às 15h.

## Requisitos funcionais

| # | Requisito | Endpoint |
|---|---|---|
| RF1 | Cadastrar um recurso (sala) com nome, capacidade e localização | `POST /resources` |
| RF2 | Listar recursos e consultar um recurso específico | `GET /resources`, `GET /resources/{id}` |
| RF3 | Consultar disponibilidade de um recurso num intervalo de tempo | `GET /resources/{id}/availability` |
| RF4 | Criar uma reserva para um recurso, num intervalo de tempo, em nome de um solicitante | `POST /resources/{id}/bookings` |
| RF5 | Listar reservas de um recurso | `GET /resources/{id}/bookings` |
| RF6 | Consultar uma reserva específica | `GET /bookings/{id}` |
| RF7 | Cancelar uma reserva antes do seu início | `DELETE /bookings/{id}` |
| RF8 | Remarcar uma reserva antes do seu início para uma nova janela (mesmas pré-condições de R4; nova janela sujeita a R1, R2, R3 e R6; a própria reserva não conta como conflito) | `PATCH /bookings/{id}` |

## Requisitos não-funcionais

| # | Requisito | Como foi atendido |
|---|---|---|
| RNF1 | **Correção sob concorrência:** N requisições simultâneas para o mesmo recurso e horário resultam em exatamente 1 sucesso, sempre | `SELECT ... FOR UPDATE` no recurso + `ExcludeConstraint`; provado por testes com `threading.Barrier` contra Postgres real |
| RNF2 | Ambiente reproduzível via Docker | `docker compose up -d --build --wait api` sobe tudo; `docker compose run --rm --build test` roda o harness |
| RNF3 | Erros de negócio com código HTTP correto e corpo estruturado, nunca stack trace | Um único exception handler mapeia cada `DomainError` para HTTP (ver [Formato de erro](#formato-de-erro)) |
| RNF4 | A não-sobreposição vale mesmo com bug na aplicação | `EXCLUDE USING gist` na tabela `bookings`; testada diretamente, inserindo linhas sem passar pela aplicação |

## Regras de negócio

| # | Regra | Onde é verificada |
|---|---|---|
| R1 | `end_time` estritamente posterior a `start_time` | `validate_time_window` (domínio) + `CHECK ck_booking_end_after_start` (banco) |
| R2 | `start_time` não pode estar no passado | `validate_time_window` |
| R3 | **(núcleo)** Duas reservas `ACTIVE` do mesmo recurso não podem ter intervalos `[start, end)` sobrepostos | Checagem sob `FOR UPDATE` no repositório + `EXCLUDE no_overlapping_active_bookings` (banco) |
| R4 | Cancelar ou remarcar só se a reserva está `ACTIVE` e ainda não começou | `ensure_cancellable`/`ensure_reschedulable` (domínio) **e** na própria escrita: `UPDATE ... WHERE status = 'ACTIVE' AND start_time > clock_timestamp()` |
| R5 | O `resource_id` de uma reserva precisa existir | Service (404) + `FOREIGN KEY` |
| R6 | Duração entre 15 minutos e 4 horas (inclusive) | `validate_time_window` (`MIN_BOOKING_DURATION`, `MAX_BOOKING_DURATION`) |
| R7 | Máximo de 3 reservas `ACTIVE` por `requester_email` | `check_booking_quota` sob `pg_advisory_xact_lock(hashtext(email))` |

Regra de sobreposição (R3), formalmente: os intervalos `A=[a_start, a_end)` e `B=[b_start, b_end)` conflitam se e somente se `a_start < b_end AND a_end > b_start`. Está implementada em `overlaps()` (`domain/rules.py`) e, no banco, como `tstzrange(start_time, end_time, '[)') && ...`.

**Consulta de disponibilidade (RF3)** usa uma validação mais leve, `validate_query_window`: só exige timezone e `end > start`. R2 e R6 não se aplicam, porque consultar o passado ou uma janela longa é legítimo.

## Contratos de entrada/saída

Todas as datas em ISO-8601, **obrigatoriamente com timezone** (UTC recomendado). Um datetime *naive* é rejeitado com `INVALID_TIME_WINDOW`.

### `Resource`

| Campo | Tipo | Regras de entrada (`POST`) |
|---|---|---|
| `id` | uuid | gerado |
| `name` | string | obrigatório, de 1 a 120 caracteres; não precisa ser único |
| `capacity` | int | obrigatório, de 1 a 2.147.483.647 (limite do `integer` do Postgres) |
| `location` | string \| null | opcional, até 255 caracteres |
| `created_at` | datetime | gerado pelo banco |

### `Booking`

| Campo | Tipo | Regras de entrada |
|---|---|---|
| `id` | uuid | gerado |
| `resource_id` | uuid | vem da rota |
| `requester_email` | email | obrigatório no `POST`, validado como e-mail |
| `start_time`, `end_time` | datetime (com timezone) | obrigatórios; R1, R2 e R6 |
| `status` | `ACTIVE` \| `CANCELLED` | gerado |
| `created_at` | datetime | gerado pelo banco |
| `cancelled_at` | datetime \| null | preenchido no cancelamento |

### `Availability`

```json
{
  "resource_id": "uuid",
  "query_start": "datetime",
  "query_end": "datetime",
  "is_available": true,
  "conflicting_bookings": ["Booking (só ACTIVE que sobrepõem a janela)"]
}
```

### Endpoints

| Método | Rota | Sucesso | Erros |
|---|---|---|---|
| POST | `/resources` | 201 `Resource` | 422 (validação de payload) |
| GET | `/resources` | 200 `Resource[]`, ordenado por `created_at` | n/a |
| GET | `/resources/{id}` | 200 `Resource` | 404 `RESOURCE_NOT_FOUND` |
| GET | `/resources/{id}/availability?start=&end=` | 200 `Availability` | 404 `RESOURCE_NOT_FOUND`, 422 `INVALID_TIME_WINDOW` |
| POST | `/resources/{id}/bookings` | 201 `Booking` | 404 `RESOURCE_NOT_FOUND`, 422 `INVALID_TIME_WINDOW`, 409 `OVERLAPPING_BOOKING`, 409 `BOOKING_QUOTA_EXCEEDED` |
| GET | `/resources/{id}/bookings` | 200 `Booking[]` (todas, inclusive canceladas), ordenado por `start_time` | 404 `RESOURCE_NOT_FOUND` |
| GET | `/bookings/{id}` | 200 `Booking` | 404 `BOOKING_NOT_FOUND` |
| PATCH | `/bookings/{id}`, corpo `{start_time, end_time}` | 200 `Booking` atualizado | 404 `BOOKING_NOT_FOUND`, 422 `INVALID_TIME_WINDOW`, 409 `OVERLAPPING_BOOKING`, 409 `BOOKING_ALREADY_STARTED`, 409 `BOOKING_ALREADY_CANCELLED` |
| DELETE | `/bookings/{id}` | 200 `Booking` com `status=CANCELLED` | 404 `BOOKING_NOT_FOUND`, 409 `BOOKING_ALREADY_STARTED`, 409 `BOOKING_ALREADY_CANCELLED` |
| GET | `/health` | 200 `{"status": "ok"}` | n/a (usado pelo healthcheck do container) |

Em toda rota com `{id}`, um id que não é UUID responde 422 de validação.

**Ordem das verificações** na criação de reserva: janela (R1, R2, R6) → recurso existe (R5) → advisory lock do solicitante → cota (R7) → `FOR UPDATE` no recurso → sobreposição (R3) → `INSERT`. Na remarcação: janela → reserva existe → R4 → `FOR UPDATE` no recurso → sobreposição excluindo a própria reserva → `UPDATE` condicionado a R4.

### Formato de erro

Há **dois** formatos, e a diferença é intencional:

**Erro de regra de negócio** (todo `DomainError`), com `error_code` estável para o cliente tratar:

```json
{ "error_code": "OVERLAPPING_BOOKING", "message": "Resource is already booked for part of this time window.", "details": null }
```

**Erro de validação de payload** (tipo errado, campo ausente, e-mail inválido, `capacity` fora da faixa, `name` vazio, texto acima do limite, UUID inválido na rota): formato padrão do FastAPI, status 422:

```json
{ "detail": [ { "type": "greater_than", "loc": ["body", "capacity"], "msg": "Input should be greater than 0", "input": 0 } ] }
```

## Modelo de dados

Criado por `infra/bootstrap.py::init_db`, que habilita a extensão `btree_gist` e cria as tabelas.

**`resources`**: `id uuid PK`, `name varchar(120) NOT NULL`, `capacity int NOT NULL`, `location varchar(255)`, `created_at timestamptz DEFAULT now()`.

**`bookings`**: `id uuid PK`, `resource_id uuid NOT NULL FK → resources`, `requester_email varchar(255) NOT NULL` (indexado, por causa da cota R7), `start_time`/`end_time timestamptz NOT NULL`, `status varchar(20) NOT NULL`, `created_at timestamptz DEFAULT now()`, `cancelled_at timestamptz`.

| Constraint | Definição | Garante |
|---|---|---|
| `ck_booking_end_after_start` | `CHECK (end_time > start_time)` | R1 |
| `no_overlapping_active_bookings` | `EXCLUDE USING gist (resource_id WITH =, tstzrange(start_time, end_time, '[)') WITH &&) WHERE (status = 'ACTIVE')` | R3 / RNF4 |

## Componentes

```
src/booking_api/
  config.py                 Settings (DATABASE_URL via ambiente ou .env)
  domain/
    entities.py             Resource, Booking, BookingStatus
    rules.py                overlaps, validate_time_window, validate_query_window,
                            check_booking_quota, ensure_cancellable, ensure_reschedulable
    exceptions.py           DomainError e um subtipo por error_code
  application/
    ports.py                ResourceRepository, BookingRepository (Protocol)
    booking_service.py      BookingService: criação, cancelamento, remarcação, consultas
    resource_service.py     ResourceService
  infra/
    db.py                   engine e SessionLocal
    models.py               ResourceModel, BookingModel (+ constraints)
    repositories.py         SqlAlchemy*Repository: FOR UPDATE, advisory lock, UPDATEs condicionais
    bootstrap.py            init_db / drop_db
  api/
    main.py                 create_app, exception handler DomainError → HTTP, /health
    schemas.py              Pydantic: entrada e saída
    deps.py                 sessão por requisição e montagem dos services
    routers/resources.py    /resources...
    routers/bookings.py     /bookings/{id}
```

`domain/` não importa nada de SQLAlchemy nem FastAPI. `application/` depende só dos Protocols de `ports.py`. Só `infra/` sabe que existe um banco.

## Estratégia de concorrência

Ver [ADR-0001](adr/0001-mecanismo-de-concorrencia.md), [ADR-0002](adr/0002-postgres-desde-entrega-1.md) e [ADR-0005](adr/0005-invariantes-fora-de-r3.md).

| Invariante | Mecanismo |
|---|---|
| R3 (sobreposição), na criação e na remarcação | `SELECT ... FOR UPDATE` na linha do recurso serializa os escritores do mesmo recurso; a `ExcludeConstraint` é a rede final |
| R7 (cota) | `pg_advisory_xact_lock(hashtext(requester_email))` serializa só as tentativas do mesmo solicitante |
| R4 (cancelar/remarcar só antes do início) | Pré-condição dentro do `UPDATE`, com o relógio do banco no momento da escrita (`clock_timestamp()`) |

## Rastreabilidade requisito → teste

| Requisito | Testes |
|---|---|
| RF1 | `integration/test_api_resources.py::TestCreateResource` |
| RF2 | `integration/test_api_resources.py::TestListResources`, `TestGetResource` |
| RF3 | `integration/test_api_bookings.py::TestAvailability`, `unit/test_booking_service.py::TestCheckAvailability`, `unit/test_rules.py::TestValidateQueryWindow` |
| RF4 | `integration/test_api_bookings.py::TestCreateBooking`, `unit/test_booking_service.py::TestCreateBooking` |
| RF5 | `integration/test_api_resources.py::TestListBookingsForResource` |
| RF6 | `integration/test_api_bookings.py::TestGetBooking` |
| RF7 | `integration/test_api_bookings.py::TestCancelBooking`, `unit/test_booking_service.py::TestCancelBooking` |
| RF8 | `integration/test_api_bookings.py::TestRescheduleBooking`, `unit/test_booking_service.py::TestRescheduleBooking` |
| R1, R2, R6 | `unit/test_rules.py::TestValidateTimeWindow` |
| R3 | `unit/test_rules.py::TestOverlaps` + todos os testes de concorrência |
| R4 | `unit/test_rules.py::TestEnsureCancellable`, `TestEnsureReschedulable`, `integration/test_write_time_preconditions.py` |
| R5 | `integration/test_api_bookings.py::TestCreateBooking::test_create_booking_for_unknown_resource_returns_404`, `integration/test_api_resources.py::TestListBookingsForResource::test_unknown_resource_returns_404`, `unit/test_booking_service.py::TestCreateBooking::test_raises_when_resource_does_not_exist` |
| R7 | `unit/test_rules.py::TestCheckBookingQuota`, `concurrency/test_quota_race.py` |
| RNF1 | `concurrency/test_double_booking.py`, `test_concurrent_different_resources.py`, `test_cancel_race.py`, `test_reschedule_race.py`, `test_quota_race.py` |
| RNF2 | Não é um teste de unidade: o próprio harness roda em container (`docker compose run --rm --build test`), e o CI repete a suíte num ambiente limpo a cada PR |
| RNF3 | Asserções de `error_code` nos testes de integração; limites de campo em `TestCreateResource` |
| RNF4 | `integration/test_db_constraints.py::TestExcludeConstraintIsTheFinalGuarantee` |

## Limites conhecidos da v1.0.0

- **Sem autenticação** ([ADR-0003](adr/0003-sem-autenticacao-nesta-entrega.md)): qualquer chamador age em nome de qualquer `requester_email`.
- **Sem paginação** em `GET /resources` e `GET /resources/{id}/bookings`.
- **Schema criado por `create_all`, sem migrações versionadas:** uma mudança de schema exigiria introduzir Alembic.
- **Os ramos `except IntegrityError` dos repositórios** (a constraint barrando o que a checagem em Python deixou passar) não são exercitados pela suíte: o `FOR UPDATE` impede que o caso aconteça. A constraint em si é testada diretamente (RNF4).
- **O ramo de `cancel()` em que o `UPDATE` condicional perde a corrida** (`rowcount = 0` com status já `CANCELLED`) só é executado quando o timing do teste de concorrência leva a esse caminho. Na maioria das execuções, os `DELETE` perdedores são barrados antes, pela checagem de domínio. O resultado observável (exatamente um 200) é testado de forma determinística; a cobertura dessa linha específica varia entre execuções.

## Refinamento

Registro de ajustes feitos na especificação/implementação a partir de testes e revisão — não a versão idealizada, o que realmente aconteceu.

1. **`tsrange` → `tstzrange`** (durante a implementação da `ExcludeConstraint`): a primeira tentativa usou `tsrange()` (range de timestamp *sem* timezone), incompatível com as colunas `TIMESTAMPTZ` do schema — Postgres rejeitou a criação da tabela (`function tsrange(timestamp with time zone, ...) does not exist`). Só foi descoberto rodando a suíte contra um Postgres real via Docker, não seria pego por um teste com SQLite/mock. Corrigido para `tstzrange()`.

2. **Validação de timezone em `validate_time_window`** (achado pela revisão de IA no PR do domínio, ver `docs/ai-usage.md`): a função comparava datetimes sem checar se eram timezone-aware; um datetime *naive* chegando até ela gerava `TypeError` não tratado (500) em vez do `InvalidTimeWindowError` esperado (422). A especificação de contrato de I/O foi então explicitada ("obrigatoriamente com timezone") e a validação, adicionada como primeiro passo da função.

3. **Teste `test_concurrent_bookings_on_different_resources_all_succeed` usando o mesmo `requester_email` para todas as 10 reservas concorrentes**: o teste falhou inicialmente (3/10 sucessos em vez de 10/10) — não por bug na aplicação, mas porque todas as tentativas compartilhavam o mesmo solicitante, disparando a regra de cota (R7, máx. 3 reservas ativas por solicitante) em vez de exercitar o que o teste realmente queria provar (que o lock é por-recurso, não global). Corrigido usando um e-mail distinto por tentativa. Documentado aqui porque é exatamente o tipo de "refinamento por feedback de teste" que este processo deve capturar.

4. **Cota por solicitante (R7) não era atômica** (achado pela revisão de IA no PR da aplicação): a checagem de contagem rodava numa leitura separada, antes da inserção com lock de linha — duas requisições concorrentes do mesmo solicitante, para recursos diferentes, podiam furar o limite de 3. Corrigido com um advisory lock transacional do Postgres por solicitante (`lock_requester`), provado por `tests/concurrency/test_quota_race.py`.

5. **Cancelamento concorrente não era atômico** (achado pela revisão de IA no PR de infra): `cancel()` fazia leitura-depois-escrita sem lock nem condição — duas chamadas `DELETE` concorrentes pro mesmo booking podiam as duas retornar 200. Corrigido com um `UPDATE ... WHERE status = 'ACTIVE'` atômico, provado por `tests/concurrency/test_cancel_race.py`.

6. **Unicidade de nome de recurso removida**: `ResourceModel.name` tinha `unique=True` sem nenhum tratamento de erro correspondente — um nome duplicado gerava 500 não tratado. Como RF1 nunca exigiu unicidade, a constraint foi removida em vez de adicionar tratamento pra uma regra que não fazia parte da especificação original.

7. **`/availability` não validava a janela de tempo** (achado pela revisão de IA no PR de documentação, ao conferir a tabela de contratos contra a implementação real): a tabela de endpoints já prometia `422 INVALID_TIME_WINDOW` para essa rota, mas `check_availability()` nunca chamava validação alguma — um datetime naive quebraria com 500, e uma janela invertida (`end` antes de `start`) retornaria silenciosamente `is_available: true`. Corrigido com uma validação mais leve (`validate_query_window`, só forma do intervalo — timezone-aware e `end > start`), deliberadamente *sem* as regras R2 (não pode estar no passado) e R6 (duração 15min-4h), que fazem sentido pra uma reserva mas não pra uma consulta de disponibilidade.

8. **Remarcação (RF8) reaproveita o lock de criação em vez de um mecanismo novo**: `reschedule()` faz o mesmo `SELECT ... FOR UPDATE` no recurso que `create_active_booking()`, então remarcações e criações no mesmo recurso se serializam pelo mesmo lock, e a `ExcludeConstraint` continua sendo a rede final (um `UPDATE` que gere sobreposição viola a constraint igual a um `INSERT`). A checagem de conflito exclui a própria reserva (`id != booking_id`) — sem isso, mover uma reserva 30 minutos pra frente conflitaria com ela mesma. O `UPDATE` é condicional a `status = 'ACTIVE'`, no mesmo padrão do item 5: um cancelamento concorrente que comite primeiro faz a remarcação falhar com `BOOKING_ALREADY_CANCELLED` em vez de alterar a janela de uma reserva já cancelada. A pré-condição de negócio (ACTIVE e não iniciada) foi extraída para um helper compartilhado entre `ensure_cancellable` e o novo `ensure_reschedulable`. A cota (R7) não é rechecada: remarcar não muda o número de reservas ativas do solicitante. Provado por `tests/concurrency/test_reschedule_race.py` (N remarcações concorrentes para o mesmo horário, e uma remarcação concorrendo com N-1 criações — sempre exatamente 1 vencedor, verificado no banco).

9. **R4 era checado fora da seção crítica, na remarcação e no cancelamento** (achado pela revisão de IA no PR do RF8, e perdido pelas duas ferramentas do experimento comparativo, ver `docs/ai-comparativo.md`): `ensure_reschedulable`/`ensure_cancellable` rodam sobre uma leitura anterior ao lock, e os `UPDATE`s só filtravam `status = 'ACTIVE'`. Uma remarcação enfileirada atrás do lock do recurso podia mover uma reserva que já tinha começado, e o cancelamento tinha a mesma brecha desde a Sprint 1. A especificação de R4 passou a explicitar que **"ainda não começou" é verificado pela própria escrita, com o relógio do banco no momento da escrita**: os dois `UPDATE`s exigem `start_time > clock_timestamp()`, e `rowcount = 0` é resolvido para `BOOKING_ALREADY_CANCELLED` ou `BOOKING_ALREADY_STARTED`.

   A primeira correção passava para o `UPDATE` um `now` lido na aplicação *antes* do lock. A segunda rodada de revisão mostrou que isso só repetia a checagem com um valor velho. `now()` do Postgres também não serve, porque devolve o início da transação, que começa antes do lock; `clock_timestamp()` devolve a hora real de execução da instrução. Provado por `tests/integration/test_write_time_preconditions.py` (cada teste falha se a condição correspondente for removida). A mesma revisão apontou que o item 8 afirmava como "provado" o comportamento contra cancelamento concorrente sem teste nenhum; o teste foi adicionado (`test_reschedule_racing_cancel_never_moves_a_cancelled_booking`).

10. **Limites das colunas não faziam parte do contrato** (achado ao conferir o modelo de dados contra a API para este documento As-Built, e completado pela revisão de IA do PR): `name` é `varchar(120)`, `location` é `varchar(255)` e `capacity` é `integer` (até 2.147.483.647), mas o schema de entrada não tinha nenhum desses limites. Um valor acima chegava ao Postgres como `StringDataRightTruncation` ou `NumericValueOutOfRange` não tratado (500, violando RNF3). Além disso, `name` vazio era aceito, embora o contrato o declarasse obrigatório. O contrato de `Resource` passou a declarar todos esses limites, e o schema os valida (422).
