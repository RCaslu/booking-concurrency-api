# Erros lógicos e loop de re-especificação

Registro consolidado de todo erro encontrado durante o desenvolvimento: como foi detectado, a causa raiz, a correção e o teste que impede a regressão. A seção [Refinamento do `spec.md`](spec.md#refinamento) guarda o histórico cronológico; este documento organiza os mesmos fatos por **tipo de erro** e por **como foi pego**, que é o que interessa para avaliar o processo.

## Como os erros foram pegos

| Mecanismo de detecção | Erros pegos | Observação |
|---|---|---|
| Suíte rodando contra Postgres real (Docker) | E1, E3 | Nenhum dos dois apareceria com SQLite ou mocks |
| Revisão de IA (skill `code-review`) antes de cada PR | E2, E4, E5, E6, E7, E9, E10, E13 | Os achados mais graves (E4, E5, E10, E13) eram races que os testes da época **não** cobriam |
| Revisão de IA cruzando a documentação com o código | E8, E11 | O spec prometia ou afirmava algo que o código ou os testes não tinham |
| Leitura humana do código contra o contrato (experimento comparativo) | E12 | Os testes estavam verdes; o erro estava na mensagem do contrato | O spec prometia um comportamento que o código não tinha |

Nenhum erro introduzido nas branches de feature chegou à `develop`: todos foram corrigidos antes do merge. A exceção é E13, uma brecha do cancelamento que existia desde a Sprint 1 e só foi encontrada na Sprint 2.

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
| E9 | Os testes de `tests/concurrency/test_cancel_race.py` e `test_concurrent_different_resources.py` só checavam o status HTTP | Revisão de IA, PR #4 | Violava a regra do `CLAUDE.md` de verificar o estado final no banco | Asserções via `db_session` ([`54c345c`](https://github.com/RCaslu/booking-concurrency-api/commit/54c345c)) |

### Erros de especificação (o loop de re-especificação)

| # | O que a especificação dizia | O que o teste ou a revisão revelou | Como a especificação mudou |
|---|---|---|---|
| E2 | Datas "em ISO-8601" | Nada impedia um datetime sem timezone, que quebrava a comparação | Contrato explicitado: datas **obrigatoriamente com timezone**, e naive vira `INVALID_TIME_WINDOW` |
| E6 | RF1 não falava em unicidade, mas o modelo tinha `unique=True` | A implementação tinha uma regra que o spec não tinha | O spec prevaleceu e a regra extra foi removida do código, em vez de entrar no spec sem necessidade |
| E8 | `/availability` retorna 422 para janela inválida | O código nunca validava; uma janela invertida retornava `is_available: true` em silêncio | Criada uma regra separada (`validate_query_window`) e documentado por que R2 e R6 **não** valem para consultas ([`7a1f83f`](https://github.com/RCaslu/booking-concurrency-api/commit/7a1f83f)) |

## Sprint 2 (Entrega 2)

O RF8 foi implementado duas vezes, uma pelo Claude Code e outra pelo Cursor, a partir do mesmo prompt ([ai-comparativo.md](ai-comparativo.md)). A implementação escolhida passou pela skill `code-review` antes do PR [#14](https://github.com/RCaslu/booking-concurrency-api/pull/14).

| # | Erro | Detecção | Causa raiz | Correção | Regressão coberta por |
|---|---|---|---|---|---|
| E10 | Remarcação podia mover uma reserva que **já tinha começado** | Revisão de IA, PR #14 (as duas ferramentas do experimento deixaram passar) | Checar e depois agir de novo: R4 era verificado numa leitura anterior ao lock, e o `UPDATE` só filtrava `ACTIVE` | **1ª tentativa, incompleta** ([`fe7fe46`](https://github.com/RCaslu/booking-concurrency-api/commit/fe7fe46)): passar ao `UPDATE` um `now` lido na aplicação, mas lido *antes* do lock. A segunda rodada de revisão mostrou que isso só repetia a checagem com um valor velho. **Correção final** ([`90cd165`](https://github.com/RCaslu/booking-concurrency-api/commit/90cd165)): `start_time > clock_timestamp()`, o relógio do banco no momento da escrita (`now()` não serve, porque devolve o início da transação) | `tests/integration/test_write_time_preconditions.py`, que **falha** se a condição for removida (teste de mutação manual) |
| E13 | `cancel()` tinha a mesma brecha de E10 desde a Sprint 1 | Revisão de IA, 2ª rodada no PR #14, ao conferir o ADR-0005 contra o código | Mesmo padrão: R4 checado antes da escrita, `UPDATE` filtrando só `ACTIVE` | Mesma condição de E10 no `UPDATE` do cancelamento ([`90cd165`](https://github.com/RCaslu/booking-concurrency-api/commit/90cd165)) | `test_cancel_of_a_booking_that_already_started_is_rejected` |
| E11 | O spec afirmava "provado" um comportamento sem teste (remarcação × cancelamento concorrente) | Revisão de IA, PR #14 | Documentação gerada pelo agente descrevendo garantias além do que os testes cobriam | Teste adicionado: `test_reschedule_racing_cancel_never_moves_a_cancelled_booking` | O próprio teste |
| E12 | Na implementação do Cursor, um PATCH numa reserva iniciada respondia *"Booking cannot be cancelled after it has started."* | Leitura do código contra o contrato, no experimento | O agente não leu o `CLAUDE.md` (regra nova começa no domínio) e reaproveitou a função de cancelamento | Implementação descartada em favor da que tinha `ensure_reschedulable`; `AGENTS.md` adicionado para qualquer ferramenta ler as mesmas regras | n/a (código não mergeado) |

### Re-especificação na Sprint 2

| O que a especificação dizia | O que a revisão revelou | Como a especificação mudou |
|---|---|---|
| R4 e RF8: "só se a reserva está ACTIVE e ainda não começou" | A regra estava certa, mas *onde* e *com qual relógio* ela é verificada importa: fora do lock, ou com um horário lido antes do lock, ela não vale sob concorrência | Item 9 do Refinamento: **"ainda não começou" é verificado pela própria escrita, com o relógio do banco no momento da escrita**, na remarcação e no cancelamento |
| Item 8 do Refinamento: comportamento com cancelamento concorrente "provado" | Não havia teste | O teste foi escrito; a afirmação do spec passou a ter evidência |

## Padrão observado

Os erros mais graves (E4, E5 e, na Sprint 2, E10 e E13) seguiram a mesma forma: **checar e depois agir sem atomicidade**. Depois de aparecer duas vezes, o padrão virou critério explícito de revisão: toda operação que lê um estado e decide com base nele precisa de lock ou de uma escrita condicional. O critério de aceitação do RF8 (issue #8) já exigia segurança sob concorrência desde o início, e mesmo assim as duas ferramentas reproduziram o padrão em E10. Isso mostra que escrever o critério na especificação não basta: ele precisa ser verificado na revisão.

### O que E10 ensinou sobre a própria correção

A primeira correção de E10 tinha um teste de regressão que **falhava sem a correção e passava com ela**, e mesmo assim a correção estava errada. O teste chamava o repositório com um `now` fabricado, então provava que a cláusula existia, não que o fluxo real rejeitava a escrita tardia. Um teste de mutação mostra que o teste depende do código, não que o código está certo.
