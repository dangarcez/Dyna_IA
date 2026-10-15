# Dynatrace Dashboard MCP — instruções ao Copilot

- Para cada dashboard, comece com `list_dashboards` e (se atualizar) `get_dashboard`.
- Não invente nomes de campos ou métricas DQL: descubra campos e valide as consultas via `run_dql` com limites de volume.
- Prefira tiles `data` com `title`, `query`, `visualization`, `visualizationSettings` e `querySettings`.
- Não inclua filtros rígidos de tempo em consultas de tiles, exceto quando solicitado; use o timeframe do dashboard.
- Para criar, use `create_dashboard` com `version: 21`, `variables: []`, `tiles` e `layouts` coerentes.
- Para editar, use `upsert_dashboard_tile` a fim de preservar o que o usuário já configurou. Para cores, unidades, colunas de tabela etc., passe `visualizationSettings` (mesclado por padrão; arrays como `colorRules` são substituídos inteiros). Não use `dtctl` diretamente para contornar o MCP.
- Sempre execute primeiro com `confirm=false` e mostre a prévia ao usuário. Só envie `confirm=true` após aprovação explícita, especialmente em produção.
- Evite custos desnecessários com DQL muito ampla, `fetch logs` sem filtros ou consultas frequentes.
