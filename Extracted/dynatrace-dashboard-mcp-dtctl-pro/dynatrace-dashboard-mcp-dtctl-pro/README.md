# Dynatrace Dashboard Editor — MCP Python / dtctl Pro

Servidor MCP para **GitHub Copilot + Latest Dynatrace**, com edição granular de dashboards em Python. Esta é a versão ampliada do antigo MCP Python baseado em `dtctl`, **não** substitui a versão HTTP: ambos são opções alternativas de transporte para modificar documentos.

**Comece por [SETUP-RAPIDO.md](SETUP-RAPIDO.md).**

## Dois MCPs juntos

- **MCP Dynatrace existente**: buscar logs, spans, métricas, contexto e DQL.
- **Este MCP (`dynatrace-dashboard-editor-dtctl`)**: preparar e publicar alterações controladas em dashboards (precisa do executável `dtctl`).

Ambos podem ficar ativos no mesmo VS Code. Prefira o MCP de consulta já instalado para explorar dados e este para trabalhar no documento do dashboard.

## Ferramentas disponíveis

| Ferramenta | Uso |
|---|---|
| `check_connection` | Verificar dtctl, contexto, token/OAuth e escrita local |
| `list_dashboards` | Lista os dashboards disponíveis |
| `get_dashboard` | Lê JSON integral por ID |
| `list_dashboard_tiles` | IDs, títulos, visualizações, DQL e layout |
| `get_dashboard_tile` | Lê tile individual incluindo settings completos |
| `run_dql` | Executar DQL opcionalmente, para validar dados |
| `plan_create_dashboard` | Novo dashboard |
| `plan_add_tile` | Criar gráfico ou bloco Markdown |
| `plan_upsert_tile` | Criar ou modificar parcialmente um tile |
| `plan_patch_tile` | Editar qualquer configuração de tile (merge/replace) |
| `plan_edit_tile_dql` | Alterar apenas DQL e querySettings |
| `plan_update_tile_visualization` | Alterar tipo, legendas, eixos, séries, unidades, cores e outras configurações da visualização |
| `plan_update_tile_layout` | Mover/redimensionar tiles |
| `plan_remove_tile` | Remover tile e layout |
| `plan_patch_dashboard_field` | Editar/remover valor específico via JSON Pointer |
| `plan_batch_dashboard_patches` | Alterar **até 25 campos de uma vez**, gerando só um plano e um diff |
| `plan_update_dashboard_settings` | Configurações gerais e timeframe |
| `plan_manage_variable` | Adicionar, substituir ou excluir variáveis |
| `plan_rename_dashboard` | Nome e descrição |
| `plan_replace_dashboard_content` | Substituição explícita de todo o content |
| `review_change` | Reexibir proposta e dry-run |
| `discard_change` | Descartar plano |
| `publish_change` | Publicar plano aprovado, após novo dry-run e backup |

## Exemplo: ocultar apenas a legenda

O Copilot pode usar `plan_update_tile_visualization`:

```json
{
  "dashboard_id": "ID_REAL_DO_DASHBOARD",
  "tile_id": "2",
  "settings_patch": {
    "legend": {"showLegend": false}
  },
  "mode": "merge"
}
```

A saída inclui `plan_id`, `diff`, `dtctl_dry_run` e marcação de `published: false`. `merge` mantém as outras opções da legenda. Para mudar de `lineChart` para `areaChart`, especifique `visualization="areaChart"` e `mode="replace"` (não se deve reutilizar configurações antigas que podem ser incompatíveis).

**Outras configurações**: legend, axes, dataMapping, seriesConfig, coloring, thresholds, unitsOverrides e opções de tabela dependem do tipo de visualização. Não invente campos: primeiro leia um tile similar ou consulte [a referência de configurações do Dynatrace](https://github.com/Dynatrace/dynatrace-for-ai/blob/main/skills/dt-app-dashboards/assets/visualization-settings.reference.jsonc). `dtctl --dry-run` pode detectar problemas, mas não garante que o gráfico renderizará com os dados da DQL.

## Exemplo: múltiplas alterações num único plano

Para alterar título e legenda de um mesmo tile e movê-lo, `plan_batch_dashboard_patches`:

```json
{
  "dashboard_id": "ID_REAL_DO_DASHBOARD",
  "patches": [
    {"path": "/tiles/2/title", "operation": "set", "value": "Latência P95"},
    {"path": "/tiles/2/visualizationSettings/legend/showLegend", "operation": "set", "value": false},
    {"path": "/layouts/2/w", "operation": "set", "value": 24}
  ]
}
```

JSON Pointer é **relativo a `content`**: os caminhos começam em `/tiles`, `/layouts`, `/variables`, `/settings` ou `/annotations`. Não use `/content/...`. Use `~1` para `/` em nomes de propriedades e `~0` para `~`.

## Ciclo de aprovação

1. Leia o documento atual com `get_dashboard` / `get_dashboard_tile`.
2. Crie uma **prévia**, usando uma ferramenta `plan_*`. Ela prepara alterações apenas em memória, valida estrutura JSON e executa `dtctl apply -f temp.json --dry-run --no-hooks`. **Ainda não publica.**
3. Exiba ao usuário o diff e dry-run. Cada plano expira após 15 minutos ou após reiniciar o servidor.
4. Com aprovação humana explícita e `DTCTL_ALLOW_WRITE=1`, chame `publish_change(plan_id, confirm=true)`.
5. Antes da publicação, o servidor consulta o dashboard novamente, compara hash do documento, grava um backup JSON local, repete o dry-run e executa `dtctl apply -f temp.json --no-hooks`.
6. Faça leitura posterior com `get_dashboard` para verificar o conteúdo persistido.

**Limites de segurança:** as verificações mitigam sobrescritas concorrentes, mas **não implementam lock transacional**; outra pessoa pode modificar o dashboard entre a última leitura e a chamada `apply`. Como a API recebe o documento completo, não é uma operação PATCH no servidor. O uso de `--no-hooks` evita efeitos de hooks locais, porém também deixa de executar hooks de validação corporativos. O ambiente Dynatrace aplica suas permissões e políticas próprias.

## Troubleshooting

**dtctl fora do PATH** — use `(Get-Command dtctl).Source` no PowerShell e informe o executável em `DTCTL_BIN` no `mcp.json`.

**dtctl presente no terminal, mas ausente no MCP** — o processo VS Code pode usar PATH distinto. Prefira caminho absoluto para `DTCTL_BIN`. Em WSL/Dev Container use o binário do ambiente onde o servidor Python roda.

**403 / acesso negado** — verifique permissões de documento e safety level do contexto (`dtctl auth status`, `dtctl config describe-context meu-ambiente`).

**Erro de JSON ao ler** — revise `dtctl get dashboard ID -o json --plain --no-agent`. O programa espera documento `{"id":"...","type":"dashboard","name":"...","content":{...}}`.

**Erro no dry-run** — confira `dtctl apply --help`, a versão do `dtctl`, permissões e opções aceitas. Validações mais detalhadas dependem do tenant e das visualizações selecionadas.

**MCP não inicia** — confirme o caminho do Python da `.venv`, que o SDK foi instalado (`python -m pip show mcp`) e verifique logs em `MCP: List Servers`.

## Testes e limitações

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

- **37 testes** de lógica local, diffs, backups, validações e simulação de comandos CLI aprovados neste ambiente de preparação.
- Não foi possível baixar o pacote `mcp` e nem executar o `dtctl` contra um Dynatrace real nesta sessão; o servidor MCP e a aplicação efetiva no tenant **precisam de teste de integração na sua máquina**.
- Não oferece suporte a **Classic Dashboards**. Eles usam outra API/modelo de dados.
- O código não implementa chamadas HTTP nem armazena tokens; a autenticação fica sob responsabilidade do `dtctl`.

## Referências

- [dtctl CLI (documentação Dynatrace)](https://docs.dynatrace.com/docs/platform/dtctl)
- [dtctl Quick start](https://dynatrace-oss.github.io/dtctl/docs/quick-start/)
- [Dashboards document structure (Dynatrace)](https://docs.dynatrace.com/docs/analyze-explore-automate/dashboards-and-notebooks/document-api/document-structure-dashboards)
- [MCP Python SDK 2](https://py.sdk.modelcontextprotocol.io/whats-new/)
