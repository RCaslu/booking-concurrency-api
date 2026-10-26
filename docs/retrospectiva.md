# Retrospectiva do projeto

Avaliação final das três sprints (Entregas 1 a 3). Trabalho individual, então as lições de "governança em equipe" vêm de manter sozinho um fluxo de equipe (branches, PRs, revisão, CI) e de ver onde esse fluxo protegeu o projeto e onde não bastou.

## Em números

| | Sprint 1 | Sprint 2 | Sprint 3 | Total |
|---|---|---|---|---|
| Testes automatizados | 69 | 91 | 100 | **100, todos passando** |
| Cobertura de código | n/a | n/a | 98% | **98%** |
| Erros encontrados antes do merge ([relatório](erros-e-reespecificacao.md)) | 9 | 4 | 2 | **15** |
| ...encontrados pela revisão de IA (skill `code-review`) | 7 | 3 | 0 | 10 |
| ...encontrados por outros meios (banco real, leitura humana, cobertura, conferência do spec) | 2 | 1 | 2 | 5 |
| Itens de Refinamento no spec | 7 | 2 | 1 | 10 |

## Eficácia dos agentes de IA no fluxo SDD

**Onde funcionou muito bem**
- **Gerar código a partir do spec.** Com `docs/spec.md` e `CLAUDE.md` como contexto, cada camada saiu com testes na primeira passada. No experimento da Sprint 2, uma sessão headless do Claude Code implementou o RF8 completo (domínio, service, repositório, rota, spec e 18 testes, incluindo concorrência) em cerca de 3 minutos, sem intervenção.
- **Revisar.** A revisão de IA foi o mecanismo que mais encontrou erros (10 de 15), e os mais graves: races de checar e depois agir que a suíte não cobria (E4, E5, E10, E13).
- **Conferir documentação contra código.** Pedir ao revisor para checar cada afirmação dos documentos contra o código achou contratos não cumpridos (E8), garantias afirmadas sem teste (E11) e nove imprecisões nos relatórios da Entrega 2.

**Onde falhou**
- **O mesmo padrão de bug, repetido.** O agente produziu código de checar e depois agir três vezes, mesmo com a regra de concorrência escrita no contexto. Duas ferramentas de fornecedores diferentes erraram a mesma sutileza no RF8.
- **Correções erradas com testes verdes.** A primeira correção do E10 veio com um teste de regressão que falhava sem ela e passava com ela, e ainda assim a correção estava incompleta.
- **Contexto que não é lido.** O Cursor ignorou o `CLAUDE.md`. Um arquivo de regras só vale para a ferramenta que o lê.

## Ganho de produtividade

O ganho real foi na **parte mecânica**: estrutura em camadas, testes de integração repetitivos, documentação e diagramas saíram rápido. O tempo economizado ali foi gasto em outro lugar, e esse é o resultado mais honesto do projeto: **revisar ficou mais caro, não mais barato.** Código gerado em minutos ainda exigiu ler o diff contra o spec, rodar contra o banco real, testar concorrência de verdade e uma segunda rodada de revisão quando a primeira correção estava errada.

Mesmo assim, o saldo foi claramente positivo. Um projeto com garantia de concorrência provada por teste, 100 testes, 98% de cobertura, 5 ADRs e 15 erros documentados não caberia no prazo sem os agentes. Mas só se sustentou porque a verificação foi tratada como parte do trabalho, não como etapa opcional.

## Principais dificuldades superadas

1. **Provar concorrência, e não só testá-la.** Um teste de concorrência que passa por sorte de timing é pior que nenhum. A solução foi `threading.Barrier` + `ThreadPoolExecutor` contra Postgres real, sempre verificando o estado final no banco e nunca só o status HTTP (regra do `CLAUDE.md`, nascida do E9).
2. **Saber *onde* uma regra é verificada.** R4 estava certo no domínio e errado sob concorrência. Foram necessárias duas tentativas para chegar ao relógio do banco no momento da escrita (`clock_timestamp()`) — ver ADR-0005.
3. **Manter a documentação verdadeira.** Documentos gerados com ajuda de IA tendem a afirmar mais do que o código faz. A partir da Sprint 2, toda documentação passou pela mesma revisão que o código.

## Lições sobre governança

- **O fluxo `feature/*` → PR → CI → `develop` → `main` valeu mesmo sozinho.** Todos os 15 erros foram pegos e corrigidos numa branch de feature, antes do merge. O único erro que já estava na `main` (E13, presente desde a Sprint 1) também foi encontrado e corrigido por esse fluxo.
- **A seção "AI Review" em cada PR transformou revisão em registro.** Ela documenta também os achados *não* corrigidos e o porquê, o que tornou visíveis decisões que, de outro modo, ficariam só na cabeça do autor.
- **Issues e milestones por sprint deram rastreabilidade de ponta a ponta:** requisito → issue → branch → PR com revisão → teste → release.
- **O limite do trabalho individual:** a revisão por IA não substitui um segundo humano. O revisor e o gerador de IA compartilham pontos cegos (o R4 fora do lock passou por duas ferramentas). Numa equipe, a primeira mudança seria exigir aprovação humana em todo PR, além da revisão de IA.

## O que faria diferente

- Escreveria a pergunta *"onde essa pré-condição é verificada, antes do lock ou dentro da escrita?"* no spec desde a Entrega 1.
- Ligaria o relatório de cobertura desde o primeiro dia: o RF5 ficou duas sprints sem nenhum teste, escondido atrás de uma suíte grande e verde.
- Manteria um `AGENTS.md` desde o início, para que qualquer ferramenta leia as mesmas regras.
