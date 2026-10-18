# Erros lógicos e loop de re-especificação

Registro consolidado de todo erro encontrado durante o desenvolvimento: como foi detectado, a causa raiz, a correção e o teste que impede a regressão. A seção [Refinamento do `spec.md`](spec.md#refinamento) guarda o histórico cronológico; este documento organiza os mesmos fatos por **tipo de erro** e por **como foi pego**, que é o que interessa para avaliar o processo.

## Como os erros foram pegos

| Mecanismo de detecção | Erros pegos | Observação |
|---|---|---|
| Suíte rodando contra Postgres real (Docker) | E1, E3 | Nenhum dos dois apareceria com SQLite ou mocks |
| Revisão de IA (skill `code-review`) antes de cada PR | E2, E4, E5, E6, E7, E8 | Os dois achados mais graves (E4, E5) eram races que os testes da época **não** cobriam |
| Revisão cruzando a documentação com o código | E8 | O spec prometia um comportamento que o código não tinha |

Nenhum erro chegou à `main`: todos foram corrigidos na própria branch de feature, antes do merge em `develop`.

## Sprint 1 (Entrega 1)

### Erros de código

| # | Erro | Detecção | Causa raiz | Correção | Regressão coberta por |
|---|---|---|---|---|---|
| E1 | `ExcludeConstraint` com `tsrange` sobre colunas `TIMESTAMPTZ`; o Postgres recusava criar a tabela | Suíte contra Postgres real | Tipo de range incompatível com o tipo da coluna, um erro que só o banco real acusa | `func.tstzrange(...)`; registrado no `CLAUDE.md` como "não repetir" | Toda a suíte de integração (a tabela não sobe sem isso) |
| E2 | Datetime *naive* em `validate_time_window` gerava `TypeError` (500) em vez de 422 | Revisão de IA, PR #1 | Comparação entre datetime naive e aware sem checagem prévia | Checagem de timezone como primeiro passo ([`022a7fc`](https://github.com/RCaslu/booking-concurrency-api/commit/022a7fc)) | `tests/unit/test_rules.py` (start/end naive) |
| E4 | Cota R7 burlável por requisições concorrentes do mesmo solicitante | Revisão de IA, PR #2 | TOCTOU: a contagem era lida antes da inserção, sem lock entre as duas operações | Advisory lock transacional por solicitante, `pg_advisory_xact_lock(hashtext(email))` ([`66495c0`](https://github.com/RCaslu/booking-concurrency-api/commit/66495c0)) | `tests/concurrency/test_quota_race.py`: 10 tentativas simultâneas, exatamente 3 sucessos |
| E5 | Dois `DELETE` concorrentes na mesma reserva retornavam 200 os dois | Revisão de IA, PR #3 | Leitura seguida de escrita sem lock nem condição | `UPDATE ... WHERE status = 'ACTIVE'` atômico ([`37bbdd4`](https://github.com/RCaslu/booking-concurrency-api/commit/37bbdd4)) | `tests/concurrency/test_cancel_race.py` |
| E6 | `unique=True` em `ResourceModel.name` sem tratamento: nome duplicado dava 500 | Revisão de IA, PR #3 | Constraint que nenhum requisito pedia | Constraint removida, já que RF1 não exige unicidade ([`37bbdd4`](https://github.com/RCaslu/booking-concurrency-api/commit/37bbdd4)) | n/a (a regra deixou de existir) |
| E7 | `requester_email` sem índice: full scan enquanto o advisory lock fica segurado | Revisão de IA, PR #3 | Índice esquecido numa coluna consultada dentro da seção crítica | Índice adicionado | n/a (desempenho) |

### Erros de teste (o teste provava a coisa errada)

| # | Erro | Detecção | Causa raiz | Correção |
|---|---|---|---|---|
| E3 | `test_concurrent_bookings_on_different_resources_all_succeed` dava 3/10 sucessos em vez de 10/10 | Suíte contra Postgres real | Todas as tentativas usavam o mesmo `requester_email` e esbarravam na cota R7 em vez de exercitar o lock por recurso | Um e-mail distinto por tentativa |
| E9 | `test_cancel_race` e `test_concurrent_different_resources` só checavam o status HTTP | Revisão de IA, PR #4 | Violava a regra do `CLAUDE.md` de verificar o estado final no banco | Asserções via `db_session` ([`54c345c`](https://github.com/RCaslu/booking-concurrency-api/commit/54c345c)) |

### Erros de especificação (o loop de re-especificação)

| # | O que a especificação dizia | O que o teste ou a revisão revelou | Como a especificação mudou |
|---|---|---|---|
| E2 | Datas "em ISO-8601" | Nada impedia um datetime sem timezone, que quebrava a comparação | Contrato explicitado: datas **obrigatoriamente com timezone**, e naive vira `INVALID_TIME_WINDOW` |
| E6 | RF1 não falava em unicidade, mas o modelo tinha `unique=True` | A implementação tinha uma regra que o spec não tinha | O spec prevaleceu e a regra extra foi removida do código, em vez de entrar no spec sem necessidade |
| E8 | `/availability` retorna 422 para janela inválida | O código nunca validava; uma janela invertida retornava `is_available: true` em silêncio | Criada uma regra separada (`validate_query_window`) e documentado por que R2 e R6 **não** valem para consultas ([`7a1f83f`](https://github.com/RCaslu/booking-concurrency-api/commit/7a1f83f)) |

## Sprint 2 (Entrega 2)

_Preenchido ao final da implementação de RF8 (issue #8)._

## Padrão observado

Os erros mais graves (E4, E5) seguiram a mesma forma: **checar e depois agir sem atomicidade**. Depois de aparecer duas vezes, o padrão virou critério explícito de revisão: toda operação que lê um estado e decide com base nele precisa de lock ou de uma escrita condicional. É por isso que o critério de aceitação de RF8 (issue #8) já começa exigindo segurança sob concorrência, em vez de descobrir isso na revisão.
