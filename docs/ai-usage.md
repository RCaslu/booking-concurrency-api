# Uso de agentes de IA no fluxo SDD

Ferramenta usada: **Claude Code** (Anthropic), com contexto de projeto em `CLAUDE.md` (raiz do repositório).

## Onde a IA foi usada

1. **Planejamento e especificação**: a arquitetura (domínio escolhido, modelo de dados, estratégia de concorrência, decomposição em módulos, contratos REST) foi desenhada com um agente de planejamento dedicado antes de qualquer código, e só depois transcrita para `docs/spec.md`. As decisões técnicas relevantes viraram ADRs (`docs/adr/`).

2. **Implementação incremental**: cada camada (`domain` → `application` → `infra`/`api`) foi implementada em sequência, com sua própria suíte de testes, seguindo a decomposição definida na especificação — nunca a aplicação inteira de uma vez.

3. **Revisão de código por IA em cada Pull Request**: antes de abrir cada PR para `develop`, a skill `code-review` foi rodada sobre o diff da branch. Achados relevantes, confirmados ou refutados, foram documentados na seção "AI Review" da descrição do PR correspondente. Dois achados reais foram corrigidos antes do merge:
   - **PR #1** (`feature/domain-model`): `validate_time_window()` não verificava timezone-awareness antes de comparar datetimes — um datetime *naive* geraria `TypeError` não tratado (500) em vez do erro de domínio esperado (422). Corrigido no mesmo PR.
   - **PR #2** (`feature/application-layer`): a checagem de cota por solicitante (R7) não era atômica em relação à inserção da reserva — duas requisições concorrentes do mesmo solicitante, para recursos diferentes, podiam furar o limite de 3 reservas ativas. Corrigido com um advisory lock transacional do Postgres por solicitante.

4. **Validação executada, não assumida**: toda alteração foi validada rodando a suíte de testes contra um Postgres real via Docker antes do commit — dois bugs reais só apareceram nessa validação (uso de `tsrange` em vez de `tstzrange`, e um teste de concorrência com um erro de setup que mascarava o que realmente estava sendo provado). Ambos registrados na seção "Refinamento" de `docs/spec.md`.

## O que a IA não decidiu sozinha

O domínio do problema (sistema de reservas com concorrência), a escolha de salas de reunião como recurso concreto, e a decisão de usar Postgres desde a Entrega 1 (em vez de uma alternativa mais simples) foram confirmados explicitamente antes da implementação começar — o agente apresentou opções com trade-offs, a decisão final foi humana.
