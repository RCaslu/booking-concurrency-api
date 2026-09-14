# ADR-0004 — FastAPI síncrono + SQLAlchemy 2.0 síncrono (não async)

## Contexto

O projeto precisa raciocinar sobre concorrência *real* (múltiplas conexões de banco simultâneas, imitando múltiplos workers) de forma simples de implementar e testar.

## Decisão

Rotas `def` (síncronas) e SQLAlchemy 2.0 em modo síncrono, não `async def` com SQLAlchemy async (greenlet).

## Justificativa

Starlette já despacha rotas síncronas para um threadpool interno automaticamente — o teste de concorrência (`ThreadPoolExecutor` + `threading.Barrier`) exercita esse caminho de forma direta e previsível, sem a complexidade adicional de `async`/`await`/greenlet do SQLAlchemy async, que não traria benefício para o escopo atual (o gargalo real é o lock do Postgres, não I/O assíncrono da aplicação).

## Consequências

- Mais simples de raciocinar e depurar para quem está aprendendo o padrão.
- Uma migração futura para async (se necessária por volume de requisições) é possível, mas não é premissa desta entrega — YAGNI.
