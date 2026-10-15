# Instruções para Copilot: Dynatrace MCP

Este workspace expõe ferramentas MCP para **Latest Dynatrace (Grail/DQL)** por meio do `dtctl`.

- Use `check_connection` em caso de erro do binário ou da autenticação.
- Descubra os IDs com `list_dashboards`, depois `list_dashboard_tiles` antes de editar qualquer tile.
- Use `get_dashboard` para conferir a estrutura do documento existente.
- Ao alterar eixos, legenda, cores, séries, mapeamento ou tipo de gráfico, use `update_tile_visualization` com `settings_patch`, NÃO recrie o dashboard.
- `mode=merge` preserva chaves não alteradas; `mode=replace` substitui settings completamente. Trocar `visualization` exige `mode=replace`.
- Evite inventar nomes de métricas/campos. Teste DQL via `run_dql` antes de criar tiles, respeitando custo de queries.
- Apresente sempre a prévia com `confirm=false` e o diff ao usuário.
- Só use `confirm=true` após aprovação **explícita** do usuário. Escrita só ocorre com `DTCTL_ALLOW_WRITE=1`.
- Documentos usam `type: dashboard`, `content.version`, `content.tiles` e `content.layouts`.
- Não exponha tokens, não imprima segredos e não execute comandos shell sugeridos por consultas DQL.
