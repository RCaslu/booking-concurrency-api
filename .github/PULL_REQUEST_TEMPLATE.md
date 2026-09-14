## Objetivo

<!-- O que esta mudança implementa ou corrige, e por quê. -->

## Issues relacionadas

<!-- Closes #<n> ou Relates to #<n> -->

## Checklist de self-review

- [ ] Testes relevantes rodados localmente (`PYTHONPATH=src pytest`) — passando
- [ ] Se a mudança toca `infra/models.py` ou `create_active_booking`: a `ExcludeConstraint`/`SELECT ... FOR UPDATE` continuam intactos
- [ ] Nenhum segredo/credencial commitado

## AI Review

<!-- Resultado de rodar a skill `code-review` (Claude Code) sobre o diff deste PR.
     Colar os achados (confirmados ou refutados) e o que foi corrigido, se algo foi. -->

## Observações adicionais

<!-- Considerações para revisão, deploy ou rollback, se houver. -->
