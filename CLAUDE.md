# Project: booking-concurrency-api

Sistema de reservas de salas de reunião com garantia estrutural contra double-booking sob concorrência. Ver `docs/spec.md` para a especificação completa (SDD).

## Stack

- Python 3.12, FastAPI (síncrono), SQLAlchemy 2.0 (síncrono), Postgres 16
- pytest (unit / integration / concurrency), Docker Compose

## Regra inegociável deste projeto

**A garantia de não-sobreposição (R3) vive no banco, não só no Python.** Qualquer mudança em `infra/models.py` ou `infra/repositories.py::create_active_booking` precisa manter a `ExcludeConstraint` (`tstzrange`, não `tsrange` — as colunas são `TIMESTAMPTZ`) e o `SELECT ... FOR UPDATE` no recurso. Se uma mudança parecer exigir remover ou enfraquecer essa constraint, pare e pergunte — não é um refactor trivial.

## Estrutura (Clean Architecture leve)

```
domain/        Entidades + regras puras (rules.py). Zero import de SQLAlchemy/FastAPI.
application/   Services orquestram domain + Protocol de repositório (ports.py).
infra/         SQLAlchemy real — única camada que sabe que existe um banco.
api/           FastAPI — schemas, rotas, tradução de exceção de domínio para HTTP.
```

Uma mudança de regra de negócio deveria, na maioria das vezes, começar em `domain/rules.py` + `tests/unit/test_rules.py` — não direto no router ou no repositório.

## Convenções de teste

- `pytest.mark.unit` — sem banco, sem FastAPI. Deve rodar em milissegundos.
- `pytest.mark.integration` — via `TestClient` + Postgres real (`tests/conftest.py`, fixture `client`).
- `pytest.mark.concurrency` — usa `threading.Barrier` + `ThreadPoolExecutor` contra Postgres real. **Nunca** `asyncio.gather`/`time.sleep` para simular concorrência — não é determinístico e mascara races reais.
- Todo teste de concorrência precisa verificar o estado final direto no banco (via `db_session`), não só o código HTTP retornado.

## Fluxo de trabalho deste repositório

`main` (protegida) ← `develop` ← `feature/*`. Nenhum commit direto em `main`. Cada branch de feature abre PR para `develop` com uma seção "AI Review" na descrição — rodar a skill `code-review` no diff antes do PR e documentar achados (corrigidos ou não) ali.

## O que já foi tentado e não funcionou (não repetir)

- `func.tsrange(...)` na `ExcludeConstraint` — Postgres rejeita porque as colunas são `TIMESTAMPTZ`, não `TIMESTAMP`. Usar `func.tstzrange(...)`.
- Fixture `clean_tables` com `autouse=True` no `conftest.py` raiz — força até os testes `unit/` (que não deveriam tocar banco) a tentarem conectar no Postgres de teste. A limpeza de tabelas só deve ser puxada por fixtures que já dependem de banco (`client`, `db_session`), nunca autouse global.
