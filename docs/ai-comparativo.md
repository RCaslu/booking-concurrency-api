# Análise comparativa: Claude Code × Cursor

Comparação feita com um **experimento controlado**, não com impressões gerais: as duas ferramentas receberam a mesma tarefa real do projeto, partindo do mesmo commit, e os dois resultados passaram pelos mesmos critérios objetivos (issue #9).

## Método

| Item | Valor |
|---|---|
| Tarefa | RF8: remarcar uma reserva (`PATCH /bookings/{id}`) com segurança sob concorrência. Escolhida por tocar a regra mais crítica do projeto (R3, `ExcludeConstraint` + `FOR UPDATE`), onde um agente que alucina ou "simplifica" demais quebra a garantia central |
| Prompt | Idêntico para as duas, sem edição: [`experimento-rf8/prompt.md`](experimento-rf8/prompt.md) |
| Ponto de partida | Commit `df87b58` de `develop`, cada ferramenta num `git worktree` isolado |
| Claude Code | Sessão headless nova (`claude -p`), sem o contexto da conversa de planejamento, modelo Claude Opus 5.5, ferramentas limitadas por allowlist |
| Cursor | Modo Agent, modelo Grok 4.7 (high), operado pelo autor sem intervir |
| Avaliação (igual para as duas) | Suíte completa em container (`docker compose run --rm test`), testes de concorrência repetidos 5×, diff de `infra/models.py`, aderência ao `CLAUDE.md` e leitura do código |

Branches publicadas com o resultado bruto de cada uma: [`experiment/claude-rf8`](https://github.com/RCaslu/booking-concurrency-api/tree/experiment/claude-rf8) e [`experiment/cursor-rf8`](https://github.com/RCaslu/booking-concurrency-api/tree/experiment/cursor-rf8).

## Resultados medidos

| Critério | Claude Code | Cursor |
|---|---|---|
| Tempo até o commit | 3 min 3 s | 6 min 52 s |
| Intervenção humana necessária | 0 | 0 |
| Suíte completa em container | 87 passed | 90 passed |
| Testes novos | 18 | 21 |
| Concorrência repetida 5× | 5/5 sem falha intermitente | 5/5 sem falha intermitente |
| `ExcludeConstraint` (`tstzrange`) intocada | Sim | Sim |
| Reusa o `SELECT ... FOR UPDATE` do recurso | Sim | Sim, e também trava a linha da reserva |
| Testes de concorrência com `Barrier` e estado verificado via `db_session` | Sim | Sim |
| Leu o `CLAUDE.md` | Sim (carregado automaticamente) | **Não**, mesmo com o prompt pedindo explicitamente |
| Regra nova começando em `domain/rules.py` (convenção do `CLAUDE.md`) | Sim (`ensure_reschedulable` + testes de domínio) | Não; reaproveitou `ensure_cancellable` |
| Defeito de contrato | Nenhum encontrado na avaliação | PATCH numa reserva já iniciada responde *"Booking cannot be cancelled after it has started."* |
| Entrada nova no Refinamento do `spec.md` | Sim | Sim (explica bem o porquê de `id != booking_id`) |
| Relato final honesto sobre o que não fez | Sim (avisou que não rodou `code-review` e que usou outro Python) | Não se aplica |
| Custo da execução | US$ 1,03 (reportado pela CLI) | Não exposto por execução no plano usado |

### Defeito compartilhado pelas duas

As duas implementações verificam R4 ("a reserva ainda não começou") **antes** de tomar o lock, e o `UPDATE` não verifica de novo. Isso abre uma janela pequena de checagem-e-ação, o mesmo padrão dos erros E4 e E5 da Sprint 1 ([erros-e-reespecificacao.md](erros-e-reespecificacao.md)). Nenhuma das duas ferramentas percebeu sozinha. Ver o tratamento na seção "AI Review" do PR do RF8.

## Leitura qualitativa

**Claude Code**
- *Pontos fortes:* lê o arquivo de contexto do projeto nativamente, e isso apareceu no resultado: seguiu a convenção de camadas e a regra de testes de concorrência sem ser lembrado. Trabalha bem sem supervisão (headless), o que permite rodar em CI ou em lote. O relatório final separou o que fez do que não fez.
- *Limitações:* custo por execução visível e não desprezível. Sem interface de diff lado a lado, a revisão acontece no git/PR. A allowlist bloqueou três comandos; o agente contornou sozinho, o que é bom para a autonomia mas pede atenção em quem configura as permissões.

**Cursor**
- *Pontos fortes:* integração com o editor (diff visual e aceite por trecho) e mais testes de integração. A explicação no `spec.md` ficou especialmente clara. Travar também a linha da reserva é uma defesa extra razoável.
- *Limitações:* ignorou o `CLAUDE.md`. O Cursor procura as regras em `.cursor/rules` e `AGENTS.md`, então um arquivo de contexto escrito para uma ferramenta **não é portável** para outra. A consequência foi concreta: sem a convenção "regra nova começa no domínio", ele reaproveitou uma função de cancelamento e vazou a mensagem errada para o contrato da API.

## Impacto real na qualidade

1. **O arquivo de contexto pesa mais que o modelo.** A diferença de qualidade mais visível entre as duas implementações veio do agente que leu as regras do projeto e do que não leu, e não da capacidade bruta de cada modelo. Ação tomada: o repositório passa a ter um `AGENTS.md` apontando para as mesmas regras, para qualquer ferramenta.
2. **As duas acertaram a parte difícil e erraram a mesma sutileza.** Os locks e a constraint ficaram corretos, mas a checagem de tempo continuou fora da seção crítica. Para esta classe de bug, a revisão humana e a revisão por IA dirigida continuam necessárias, e testes verdes não bastam.
3. **"Testes passando" não diferenciou as duas.** 87 contra 90, ambas verdes. O que as diferenciou foi ler o código contra a especificação e o contrato.

## Limites deste experimento

- Uma única tarefa (n = 1). Serve como evidência, não como estatística.
- A comparação é entre **ferramenta + modelo** (Claude Code com Opus 5.5 contra Cursor com Grok 4.7). Não isola o efeito da ferramenta do efeito do modelo.
- O Claude Code rodou headless; o Cursor rodou interativo. O tempo de parede do Cursor inclui a renderização da interface.
- Codex CLI e Antigravity não foram avaliados. Como não há uso real deles, ficam fora da matriz, em vez de entrar com opiniões de segunda mão.
