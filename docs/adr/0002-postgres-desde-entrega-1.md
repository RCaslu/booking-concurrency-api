# ADR-0002 — Postgres desde a Entrega 1 (não SQLite)

## Contexto

O teste de concorrência (núcleo do projeto) precisa ser determinístico: N requisições simultâneas para o mesmo slot devem produzir exatamente 1 sucesso, sempre, em qualquer execução.

## Decisão

Usar Postgres (via Docker) desde o início, em vez de SQLite para simplificar o setup local.

## Justificativa

SQLite não suporta `ExcludeConstraint`/GiST (a garantia estrutural do ADR-0001) e serializa todo acesso por um lock de arquivo de processo único — sob concorrência real ele tende a lançar `database is locked` de forma não determinística, o oposto do que um teste de concorrência confiável precisa. O custo aceito é mais uma dependência de infraestrutura, mitigado pelo `docker-compose.yml` que sobe banco de desenvolvimento e banco de teste prontos para uso (`docker compose up -d db db-test`).

## Consequências

- Reprodutibilidade depende de Docker estar disponível — documentado como pré-requisito no README.
- `tests/conftest.py` aponta para um banco de teste dedicado (`TEST_DATABASE_URL`), isolado do banco de desenvolvimento.
