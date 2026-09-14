# Booking Concurrency API

Sistema de reservas de salas de reunião com garantia estrutural contra double-booking sob requisições concorrentes. Ver a especificação completa em [`docs/spec.md`](docs/spec.md).

**Bootcamp III — Entrega 1** (Ambiente, Especificação Técnica e Test Harness). Trabalho individual.

## O problema em uma frase

N requisições simultâneas para reservar o mesmo horário da mesma sala devem resultar em exatamente 1 sucesso — sempre, comprovado por teste automatizado, não por sorte de timing.

## Pré-requisitos

- Docker e Docker Compose
- Python 3.12+ (só necessário para rodar os testes fora de container)

## Como rodar

```bash
git clone git@github.com:RCaslu/booking-concurrency-api.git
cd booking-concurrency-api
docker compose up -d db
docker compose up api
```

A API sobe em `http://localhost:8020` (a porta `8000` padrão do Uvicorn é mapeada para `8020` no host para evitar conflito com outros serviços já rodando na máquina — ver `docker-compose.yml`).

```bash
curl -X POST http://localhost:8020/resources \
  -H "Content-Type: application/json" \
  -d '{"name": "Sala A", "capacity": 8}'
```

## Como rodar os testes

Totalmente containerizado, sem precisar instalar nada além de Docker:

```bash
docker compose up -d db-test
docker compose run --rm test
```

Ou localmente, com um virtualenv:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d db-test
PYTHONPATH=src pytest -v
```

Rodar só uma categoria:

```bash
PYTHONPATH=src pytest -m unit           # regras de domínio, sem infra, milissegundos
PYTHONPATH=src pytest -m integration    # via API + Postgres real
PYTHONPATH=src pytest -m concurrency    # a prova de não-double-booking
```

Evidência de execução completa (log capturado) em [`docs/test-evidence/pytest-run.log`](docs/test-evidence/pytest-run.log).

## Decisões arquiteturais (ADRs)

| ADR | Decisão |
|---|---|
| [0001](docs/adr/0001-mecanismo-de-concorrencia.md) | `SELECT ... FOR UPDATE` + `ExcludeConstraint` do Postgres como mecanismo de concorrência |
| [0002](docs/adr/0002-postgres-desde-entrega-1.md) | Postgres desde a Entrega 1 (SQLite não suporta a constraint acima) |
| [0003](docs/adr/0003-sem-autenticacao-nesta-entrega.md) | Sem autenticação/autorização nesta entrega |
| [0004](docs/adr/0004-fastapi-sincrono.md) | FastAPI síncrono + SQLAlchemy síncrono |

## Documentação

- [`docs/spec.md`](docs/spec.md) — especificação técnica completa (SDD): requisitos, regras de negócio, contratos de I/O, decomposição, refinamentos
- [`docs/ai-usage.md`](docs/ai-usage.md) — como o Claude Code foi usado no fluxo SDD
- [`CLAUDE.md`](CLAUDE.md) — regras/contexto do agente de IA para este repositório

## Estrutura

```
src/booking_api/
  domain/        Entidades e regras de negócio puras
  application/   Orquestração (services) contra um Protocol de repositório
  infra/         SQLAlchemy + Postgres (a garantia real de concorrência vive aqui)
  api/           FastAPI
tests/
  unit/          Sem infraestrutura
  integration/   Via API + Postgres real
  concurrency/   Requisições concorrentes reais, sem mocks de timing
```

## Governança

Fluxo de branches `main` (protegida) ← `develop` ← `feature/*`, com Pull Request para cada unidade de trabalho e revisão de IA (skill `code-review`) documentada em cada PR antes do merge. Trabalho individual — ver `docs/ai-usage.md` para como a revisão por IA substitui a revisão por par nesse contexto.

**Nota**: a proteção de branch nativa do GitHub para `main` não pôde ser habilitada por restrição do ambiente de execução usado nesta entrega; a regra "nenhum commit direto em `main`" foi seguida por conduta, verificável no histórico de commits e Pull Requests do repositório.
