# Análise crítica: ética, limites e segurança no uso de agentes de IA

Todo o código deste repositório foi escrito com agentes de IA: Claude Code nas Sprints 1 e 2, e Cursor no experimento comparativo ([ai-comparativo.md](ai-comparativo.md)). Por isso esta análise se apoia nos casos que **realmente aconteceram aqui**, com link para a evidência, e não em riscos hipotéticos.

## 1. Alucinação e código inseguro ou destrutivo

### O que aconteceu neste projeto

| Caso | Tipo de falha | Por que é perigoso | Como foi pego |
|---|---|---|---|
| `tsrange` sobre colunas `TIMESTAMPTZ` (E1) | API plausível, mas errada para o tipo da coluna | Num banco que aceitasse a conversão em silêncio, o range seria comparado sem timezone | Só o Postgres real acusou; um mock teria passado |
| Cota R7 burlável (E4) e cancelamento duplo (E5) | Código funcionalmente correto em teste sequencial, mas com race | É a classe de bug que o projeto existe para evitar, e mesmo assim o agente a produziu duas vezes | Revisão de IA dirigida, antes do merge |
| Docstring descrevendo um bug já corrigido (PR #4) | Documentação alucinada sobre o próprio código | Leva o próximo leitor, humano ou agente, a uma conclusão errada | Revisão de IA |
| Cursor ignorando o `CLAUDE.md` e vazando *"cannot be cancelled"* no PATCH | Contexto ignorado mesmo com instrução explícita no prompt | Erro de contrato que nenhum teste verde acusou | Leitura do código contra a especificação |
| Claude Code **e** Cursor checando R4 fora do lock (RF8) | Mesma sutileza de concorrência perdida pelas duas ferramentas | Testes verdes nas duas; a falha só aparece sob timing específico | Skill `code-review` no PR #14 |
| A correção de IA para o caso acima também estava errada (usava um horário lido antes do lock) | Correção incompleta com teste de regressão verde | O teste injetava o horário à mão e não exercitava o fluxo real | 2ª rodada do `code-review`, que também achou a mesma brecha no cancelamento, presente desde a Sprint 1 |

**Conclusão:** neste projeto, a falha típica do agente **não** foi o código que não roda. Foi o código que roda, passa nos testes e está sutilmente errado. Isso valeu inclusive para a *correção* de um bug apontado pela própria IA: a primeira versão do fix de R4 veio com um teste de regressão que falhava sem o fix e passava com ele, e ainda assim o fix estava incompleto. É exatamente o tipo de erro que um humano tende a aprovar quando vê tudo verde.

### Riscos destrutivos e como foram contidos

- **Permissões mínimas.** A execução headless do experimento usou uma allowlist de ferramentas. O agente podia editar, rodar testes e commitar, mas não fazer `push` nem rodar comandos arbitrários; três comandos foram bloqueados. Nunca foi usado `--dangerously-skip-permissions`.
- **Isolamento.** Cada agente do experimento trabalhou num `git worktree` próprio, sem acesso de escrita ao checkout principal.
- **Proteção da regra crítica.** O `CLAUDE.md` manda o agente **parar e perguntar** antes de enfraquecer a `ExcludeConstraint`, e a constraint fica no schema do banco justamente para que nem um bug de aplicação (humano ou gerado) consiga persistir uma sobreposição (RNF4).
- **Nada vai direto para `main`.** Toda mudança passa por branch, PR e CI.

## 2. Vazamento de dados, privacidade e confidencialidade

**O que foi exposto aos modelos:** todo o código-fonte, a especificação, os logs de teste e as mensagens de erro. No experimento, o mesmo código foi enviado a **dois provedores diferentes** (Anthropic pelo Claude Code; Cursor e xAI pelo Grok). Cada ferramenta acrescenta um provedor à lista de quem recebe o código, e cada um tem a sua política de retenção e de uso para treinamento, que depende do plano contratado e das configurações (por exemplo, o *Privacy Mode* do Cursor).

**Por que o risco foi baixo aqui:**
- É um projeto acadêmico e público. O código já é aberto.
- Não há dados pessoais reais. Os e-mails de solicitantes nos testes são fictícios (`@example.com`).
- As únicas credenciais no repositório (`booking`/`booking` no `docker-compose.yml`) são de um Postgres local descartável. `.env` e `.env.*` estão no `.gitignore`.

**O que mudaria num projeto real:**
- O agente lê o que estiver no disco, não só o que o desenvolvedor pretendia mostrar: `.env`, dumps de banco, logs com dados de clientes. O `.gitignore` não protege contra isso. É preciso configurar exclusões na própria ferramenta (lista de negação de leitura) e manter segredos fora do diretório de trabalho.
- Usar planos com retenção zero e sem treinamento sobre o código, e conferir isso no contrato, não na página de marketing.
- Saídas de ferramentas (logs, respostas HTTP) entram no contexto do modelo. Um log de produção colado para "ajudar a depurar" é um vazamento.

## 3. Propriedade intelectual e direitos autorais

- **Autoria.** A Lei de Direitos Autorais brasileira (Lei 9.610/98) considera autor a pessoa física criadora da obra, e o Escritório de Direitos Autorais dos EUA tem exigido contribuição humana para registrar uma obra. Na prática, trechos gerados por IA sem contribuição criativa humana relevante têm **proteção autoral incerta**. Neste projeto, a contribuição humana está na especificação, nas decisões de arquitetura (ADRs), na escolha entre as implementações do experimento e na revisão de cada PR, e é isso que sustenta a autoria do trabalho como um todo.
- **Termos dos provedores.** Em geral, os termos comerciais das ferramentas atribuem a saída ao usuário, mas não garantem que ela esteja livre de direitos de terceiros.
- **Contaminação por licença.** Um modelo pode reproduzir trechos de código de projetos com licença restritiva (por exemplo, GPL). O risco é baixo para código idiomático como o deste repositório, mas real em trechos longos e específicos.
- **Lacuna identificada neste repositório:** ele é público e **não tem arquivo `LICENSE`**. Sem licença, ninguém tem permissão legal de reutilizar o código, o que contradiz a intenção de um repositório público acadêmico. Fica registrado como pendência para o autor decidir (por exemplo, MIT).

## 4. A centralidade da homologação humana no fluxo SDD

O fluxo deste projeto não é "a IA gera e o humano aceita". É "o humano especifica, a IA implementa e o humano homologa contra a especificação".

**Decisões que foram humanas e não poderiam ter sido delegadas:**
- O domínio do problema e a decisão de usar Postgres desde a Entrega 1 (ADR-0002). O agente apresentou alternativas; a escolha foi humana.
- Remover a unicidade de nome de recurso (E6) em vez de adicionar tratamento: uma decisão sobre **o que o sistema deve fazer**, não sobre como.
- Escolher a implementação do RF8. As duas tinham testes verdes; a decisão veio da leitura do código contra o contrato.

**Por que testes automatizados não substituem a revisão:** em quase todos os casos da seção 1, a suíte inteira estava verde. Os testes provam o que alguém pensou em testar. A revisão encontra o que ninguém pensou. A especificação (SDD) é o que torna a revisão possível: sem um contrato escrito, não haveria contra o que comparar o código.

**Limitação reconhecida:** este é um trabalho individual. A "revisão por par" foi a combinação de autor + revisão de IA (skill `code-review`) documentada em cada PR. Isso pega muitos erros (sete dos nove da Sprint 1), mas não substitui um segundo humano: o revisor de IA e o gerador de IA tendem a compartilhar os mesmos pontos cegos, como mostrou o R4 fora do lock, perdido por **duas** ferramentas de **fornecedores diferentes**.
