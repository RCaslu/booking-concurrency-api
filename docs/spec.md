## SDD — Booking Concurrency API

Especificação técnica do problema, requisitos, regras de negócio e contratos de entrada/saída. Este documento é o ponto de partida (Spec-Driven Development): a implementação em `src/` é derivada dele, e ajustes feitos durante o desenvolvimento (a partir de testes ou revisão) são registrados na seção Refinamento, no final.

## O problema

Sistema de reserva de salas de reunião que precisa garantir, sob requisições concorrentes, que **duas reservas nunca ocupem a mesma sala no mesmo intervalo de tempo** — o clássico problema de double-booking de sistemas de agendamento (Google Calendar, Calendly). A garantia precisa ser estrutural (não depender de sorte de timing) e comprovável por teste automatizado determinístico.

Domínio escolhido — salas de reunião, não vagas de estacionamento — porque o conceito de intervalo `[início, fim)` é fácil de explicar e naturalmente gera casos de borda inequívocos (uma reunião que termina às 15h não conflita com outra que começa às 15h).

## Requisitos funcionais

| # | Requisito |
|---|---|
| RF1 | Cadastrar um recurso (sala) com nome, capacidade e localização |
| RF2 | Listar recursos e consultar um recurso específico |
| RF3 | Consultar disponibilidade de um recurso num intervalo de tempo |
| RF4 | Criar uma reserva para um recurso, num intervalo de tempo, em nome de um solicitante |
| RF5 | Listar reservas de um recurso |
| RF6 | Consultar uma reserva específica |
| RF7 | Cancelar uma reserva antes do seu início |

## Requisitos não-funcionais

| # | Requisito |
|---|---|
| RNF1 | **Correção sob concorrência**: N requisições simultâneas para o mesmo recurso/horário devem resultar em exatamente 1 sucesso, sempre — comprovado por teste automatizado, não por inspeção manual |
| RNF2 | Ambiente reproduzível via Docker (`docker compose up`) — sem "funciona na minha máquina" |
| RNF3 | Erros de negócio devem retornar códigos HTTP corretos e um corpo de erro estruturado (`error_code`, `message`), nunca um stack trace |
| RNF4 | A regra de não-sobreposição deve ser garantida mesmo que a camada de aplicação tenha um bug — a garantia final vive no schema do banco, não só no código Python |

## Regras de negócio

| # | Regra | Categoria |
|---|---|---|
| R1 | `end_time` deve ser estritamente posterior a `start_time` | Validação |
| R2 | `start_time` não pode estar no passado | Validação |
| R3 | **(núcleo)** Duas reservas `ACTIVE` do mesmo recurso não podem ter intervalos `[start, end)` sobrepostos | Concorrência |
| R4 | Cancelamento só é permitido se a reserva está `ACTIVE` e ainda não começou (`now < start_time`) | Negócio |
| R5 | `resource_id` referenciado numa reserva precisa existir | Referencial |
| R6 | Duração da reserva entre 15 minutos e 4 horas | Negócio |
| R7 | Máximo de 3 reservas `ACTIVE` simultâneas por `requester_email` | Negócio |

Regra de sobreposição (R3), formalmente: dados os intervalos `A=[a_start, a_end)` e `B=[b_start, b_end)`, eles conflitam se e somente se `a_start < b_end AND a_end > b_start`. Implementada em `overlaps()` (`src/booking_api/domain/rules.py`).

## Contratos de entrada/saída

Todas as datas em ISO-8601, **obrigatoriamente com timezone** (UTC recomendado) — um datetime *naive* é rejeitado como `INVALID_TIME_WINDOW` (ver Refinamento).

### `Resource`

```json
{
  "id": "uuid",
  "name": "string",
  "capacity": "int > 0",
  "location": "string | null",
  "created_at": "datetime"
}
```

### `Booking`

```json
{
  "id": "uuid",
  "resource_id": "uuid",
  "requester_email": "email",
  "start_time": "datetime (tz-aware)",
  "end_time": "datetime (tz-aware)",
  "status": "ACTIVE | CANCELLED",
  "created_at": "datetime",
  "cancelled_at": "datetime | null"
}
```

### Endpoints

| Método | Rota | Sucesso | Erros |
|---|---|---|---|
| POST | `/resources` | 201 `Resource` | 422 (payload inválido) |
| GET | `/resources` | 200 `Resource[]` | — |
| GET | `/resources/{id}` | 200 `Resource` | 404 `RESOURCE_NOT_FOUND` |
| GET | `/resources/{id}/availability?start&end` | 200 `Availability` | 404, 422 `INVALID_TIME_WINDOW` |
| POST | `/resources/{id}/bookings` | 201 `Booking` | 404 `RESOURCE_NOT_FOUND`, 422 `INVALID_TIME_WINDOW`, 409 `OVERLAPPING_BOOKING`, 409 `BOOKING_QUOTA_EXCEEDED` |
| GET | `/resources/{id}/bookings` | 200 `Booking[]` | 404 |
| GET | `/bookings/{id}` | 200 `Booking` | 404 `BOOKING_NOT_FOUND` |
| DELETE | `/bookings/{id}` | 200 `Booking` (status=CANCELLED) | 404, 409 `BOOKING_ALREADY_STARTED`, 409 `BOOKING_ALREADY_CANCELLED` |

### Formato de erro

```json
{ "error_code": "OVERLAPPING_BOOKING", "message": "string", "details": null }
```

## Decomposição em componentes testáveis

```
domain/       Entidades e regras puras (R1-R7). Zero I/O, zero dependência externa.
application/  BookingService/ResourceService — orquestram domain + um Protocol de
              repositório (ports.py), sem depender de SQLAlchemy concretamente.
infra/        Implementação real dos repositórios (Postgres/SQLAlchemy) e a
              garantia estrutural de R3 (EXCLUDE constraint).
api/          FastAPI — schemas, rotas, tradução de exceções de domínio para HTTP.
```

Cada camada é testável isoladamente: `domain/` sem nenhuma infraestrutura (`tests/unit/test_rules.py`), `application/` com um repositório fake em memória (`tests/unit/test_booking_service.py`), `infra/`+`api/` com Postgres real via Docker (`tests/integration/`, `tests/concurrency/`).

## Estratégia de concorrência

Ver [ADR-0001](adr/0001-mecanismo-de-concorrencia.md) e [ADR-0002](adr/0002-postgres-desde-entrega-1.md). Resumo: `SELECT ... FOR UPDATE` no recurso serializa escritores concorrentes do mesmo recurso; uma `ExcludeConstraint` do Postgres na tabela `bookings` é a garantia estrutural final, independente de qualquer bug de aplicação.

## Refinamento

Registro de ajustes feitos na especificação/implementação a partir de testes e revisão — não a versão idealizada, o que realmente aconteceu.

1. **`tsrange` → `tstzrange`** (durante a implementação da `ExcludeConstraint`): a primeira tentativa usou `tsrange()` (range de timestamp *sem* timezone), incompatível com as colunas `TIMESTAMPTZ` do schema — Postgres rejeitou a criação da tabela (`function tsrange(timestamp with time zone, ...) does not exist`). Só foi descoberto rodando a suíte contra um Postgres real via Docker, não seria pego por um teste com SQLite/mock. Corrigido para `tstzrange()`.

2. **Validação de timezone em `validate_time_window`** (achado pela revisão de IA no PR do domínio, ver `docs/ai-usage.md`): a função comparava datetimes sem checar se eram timezone-aware; um datetime *naive* chegando até ela gerava `TypeError` não tratado (500) em vez do `InvalidTimeWindowError` esperado (422). A especificação de contrato de I/O foi então explicitada ("obrigatoriamente com timezone") e a validação, adicionada como primeiro passo da função.

3. **Teste `test_concurrent_bookings_on_different_resources_all_succeed` usando o mesmo `requester_email` para todas as 10 reservas concorrentes**: o teste falhou inicialmente (3/10 sucessos em vez de 10/10) — não por bug na aplicação, mas porque todas as tentativas compartilhavam o mesmo solicitante, disparando a regra de cota (R7, máx. 3 reservas ativas por solicitante) em vez de exercitar o que o teste realmente queria provar (que o lock é por-recurso, não global). Corrigido usando um e-mail distinto por tentativa. Documentado aqui porque é exatamente o tipo de "refinamento por feedback de teste" que este processo deve capturar.

4. **Cota por solicitante (R7) não era atômica** (achado pela revisão de IA no PR da aplicação): a checagem de contagem rodava numa leitura separada, antes da inserção com lock de linha — duas requisições concorrentes do mesmo solicitante, para recursos diferentes, podiam furar o limite de 3. Corrigido com um advisory lock transacional do Postgres por solicitante (`lock_requester`), provado por `tests/concurrency/test_quota_race.py`.

5. **Cancelamento concorrente não era atômico** (achado pela revisão de IA no PR de infra): `cancel()` fazia leitura-depois-escrita sem lock nem condição — duas chamadas `DELETE` concorrentes pro mesmo booking podiam as duas retornar 200. Corrigido com um `UPDATE ... WHERE status = 'ACTIVE'` atômico, provado por `tests/concurrency/test_cancel_race.py`.

6. **Unicidade de nome de recurso removida**: `ResourceModel.name` tinha `unique=True` sem nenhum tratamento de erro correspondente — um nome duplicado gerava 500 não tratado. Como RF1 nunca exigiu unicidade, a constraint foi removida em vez de adicionar tratamento pra uma regra que não fazia parte da especificação original.

7. **`/availability` não validava a janela de tempo** (achado pela revisão de IA no PR de documentação, ao conferir a tabela de contratos contra a implementação real): a tabela de endpoints já prometia `422 INVALID_TIME_WINDOW` para essa rota, mas `check_availability()` nunca chamava validação alguma — um datetime naive quebraria com 500, e uma janela invertida (`end` antes de `start`) retornaria silenciosamente `is_available: true`. Corrigido com uma validação mais leve (`validate_query_window`, só forma do intervalo — timezone-aware e `end > start`), deliberadamente *sem* as regras R2 (não pode estar no passado) e R6 (duração 15min-4h), que fazem sentido pra uma reserva mas não pra uma consulta de disponibilidade.
