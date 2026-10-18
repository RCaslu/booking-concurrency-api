# ADR-0005: Como proteger as invariantes que não são R3

## Contexto

O ADR-0001 resolve a sobreposição (R3) com `FOR UPDATE` no recurso mais uma `ExcludeConstraint`. Três outras regras dependem de "ler um estado e decidir": a cota por solicitante (R7), o cancelamento (R4) e a remarcação (RF8 + R4). As três foram implementadas primeiro como **leitura e depois escrita**, e as três se mostraram burláveis sob concorrência (erros E4, E5 e E10 em [erros-e-reespecificacao.md](../erros-e-reespecificacao.md)).

## Decisão

Duas técnicas, escolhidas pelo **escopo do que precisa ser serializado**:

1. **A invariante cruza várias linhas e recursos (R7, cota por solicitante):** advisory lock transacional do Postgres, `pg_advisory_xact_lock(hashtext(requester_email))`. Serializa só as tentativas do mesmo solicitante e é liberado sozinho no commit ou no rollback.
2. **A invariante é sobre uma única linha (R4 no cancelamento e na remarcação):** a pré-condição vai **dentro da própria escrita**, com `UPDATE ... WHERE status = 'ACTIVE' AND start_time > now`. Quando `rowcount = 0`, o status é relido para escolher o erro certo.

## Alternativas descartadas

- **Lock de tabela ou lock global:** resolveria tudo, mas serializaria reservas de solicitantes e recursos diferentes, que não têm conflito nenhum. O teste `test_concurrent_different_resources` existe justamente para provar que isso não acontece.
- **Coluna contador de reservas ativas por solicitante + CHECK:** exigiria uma tabela nova e manter o contador sincronizado em toda escrita. É mais estado para errar do que um lock de poucas linhas.
- **`SERIALIZABLE` como nível de isolamento:** correto, mas transforma conflitos em erros de serialização que exigem retry na aplicação, com o mesmo problema de não determinismo do lock otimista (ADR-0001).
- **`SELECT ... FOR UPDATE` na linha da reserva antes de checar R4:** funciona, mas é uma ida a mais ao banco para o que um `WHERE` resolve na mesma instrução.

## Consequências

- Toda regra nova do tipo "só se o estado atual for X" passa a ser revisada com uma pergunta: *onde essa condição é verificada, antes do lock ou dentro da escrita?*
- Advisory locks são chaveados por hash: dois e-mails com o mesmo `hashtext` se serializariam sem necessidade. Isso é aceitável, porque só afeta o desempenho e nunca a correção.
