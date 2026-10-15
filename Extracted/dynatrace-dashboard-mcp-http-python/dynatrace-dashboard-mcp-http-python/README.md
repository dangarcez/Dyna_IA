# Dynatrace Dashboard Editor MCP — Python / HTTP

**Objetivo:** MCP local focado em criar/atualizar dashboards **Latest Dynatrace (Grail/DQL)** por HTTPS, sem `dtctl`. Convive com o MCP Dynatrace de consultas: use o servidor existente para DQL, descoberta de métricas e análise, e este servidor para **escrita de dashboards**.

> Não é para **Dashboards Classic**. Para Classic, a API e o esquema de tiles são outros.

## Instalação em 5 minutos (Windows)

1. Instale **Python 3.11 ou superior**, extraia o ZIP e abra a pasta no VS Code.
2. No terminal PowerShell desta pasta:
   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   Copy-Item .env.example .env
   notepad .env
   ```
3. Preencha `DT_ENV_URL=https://SEU-AMBIENTE.apps.dynatrace.com` e `DT_PLATFORM_TOKEN=...` no `.env`. **Nunca cole tokens no chat** nem versione `.env`.
4. No VS Code, `Ctrl+Shift+P` → `MCP: List Servers` → iniciar `dynatrace-dashboard-editor-http` (config em `.vscode/mcp.json`). Abra o Copilot em modo Agent e habilite as ferramentas deste servidor.
5. No Copilot: **“Use connection_status e list_dashboards do MCP editor HTTP. Não publique nada.”**

Para usar Linux/WSL/macOS, altere o Python em `.vscode/mcp.json` para `${workspaceFolder}/.venv/bin/python` e instale com `python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt`.

### Credenciais e permissões

**Platform Token** (mais simples): crie em *My platform tokens* no Dynatrace. Escopos de API: `document:documents:read` e `document:documents:write`. Além dos escopos, o usuário do token precisa ter permissão de leitura/escrita no documento (proprietário ou via compartilhamento). Use a URL da **plataforma** (`.apps.dynatrace.com`), não a URL clássica `.live.dynatrace.com`.

**OAuth Client Credentials** (opção corporativa): no `.env` deixe `DT_PLATFORM_TOKEN=` vazio e preencha `DT_OAUTH_CLIENT_ID`, `DT_OAUTH_CLIENT_SECRET` e `DT_OAUTH_SCOPES=document:documents:read document:documents:write`. O cliente pede um token ao `https://sso.dynatrace.com/sso/oauth2/token` automaticamente. Administrador pode precisar autorizar políticas e compartilhamento do documento para o usuário de serviço.

O MCP pode rodar em modo leitura, com `DT_ALLOW_WRITE=0` (padrão). Para publicar, **troque para `DT_ALLOW_WRITE=1` e reinicie o MCP**, e depois autorize a publicação do plano específico. Não desative TLS para contornar um proxy corporativo: configure as CAs e `HTTPS_PROXY` conforme sua organização.

## Como trabalhar com o Copilot

Ferramentas disponíveis:

| Ferramenta | Descrição |
|---|---|
| `connection_status` | Verifica token/permissão de listar documentos |
| `list_dashboards` / `get_dashboard` | Lista/lê dashboards e metadados |
| `list_dashboard_tiles` / `get_dashboard_tile` | Exibe IDs, layouts e visualização completa |
| `plan_create_dashboard` | Prepara criação a partir de documento JSON, ou dashboard vazio |
| `plan_add_tile` | Adiciona tile com ID e layout (ou atribui automaticamente) |
| `plan_patch_tile` | Modifica qualquer campo do tile (query, título, parâmetros) |
| `plan_update_tile_visualization` | Configura `visualization` e `visualizationSettings` com merge/replace |
| `plan_update_tile_layout` | Move/redimensiona tile (`x, y, w, h`) |
| `plan_delete_tile` | Remove um tile e seu layout |
| `plan_patch_dashboard_field` | Edição granular por JSON Pointer RFC6901 (inclui variáveis e settings) |
| `plan_replace_dashboard_content` | Substituição completa do JSON do dashboard |
| `review_change` / `discard_change` | Revisão/descarta prévia pendente |
| `publish_change` | Publica uma prévia com dupla confirmação |

As ferramentas `plan_*` **nunca fazem escrita remota**. Retornam `plan_id` e um **diff**. Planos ficam somente na memória do processo por **15 minutos**, e desaparecem se o servidor for reiniciado. **Não são acumulativos**: uma nova `plan_*` lê a última versão publicada, e publicar um plano invalida planos que tiveram a mesma versão de origem.

### Exemplo 1: criar dashboard

No Copilot:

> Use o MCP Dynatrace existente para descobrir DQL de CPU/erros. Com o MCP editor HTTP, chame `plan_create_dashboard` com um JSON válido de dashboard (ou primeiro um dashboard vazio). Mostre o diff e não publique até eu confirmar.

Use `examples/dashboard-exemplo.json` como referência estrutural; **valide a DQL e a visualização no seu ambiente**. Depois de revisar:

> Autorizo publicar somente o plano `PLAN_ID` pelo MCP editor HTTP.

O Copilot chama `publish_change(plan_id="...", confirm=True)` e `DT_ALLOW_WRITE=1` deve estar ativo.

### Exemplo 2: alterar somente aparência de um tile

> No dashboard ID `...`, liste os tiles; no tile `2`, oculte a legenda e altere o nome do eixo Y para “CPU (%)”. Preserve tudo que não for mencionado; apresente prévia sem publicar.

Ferramenta e parâmetros (conceituais):

```json
{
  "dashboard_id": "ID_DO_DASHBOARD",
  "tile_id": "2",
  "settings_patch": {
    "legend": {"showLegend": false},
    "axes": {"yAxis": {"label": "CPU (%)", "showLabel": true}}
  },
  "mode": "merge"
}
```

Para alterar **lineChart → areaChart**, use `visualization="areaChart", mode="replace", settings_patch={}`. `replace` descarta visualizaçãoSettings anteriores; com `merge` apenas os campos informados são alterados, preservando os demais.

### Exemplo 3: edição ultra-granular

Use `plan_patch_dashboard_field` com `json_pointer="/tiles/2/visualizationSettings/axes/yAxis/label"`, `value="Latência (ms)"`, `operation="set"`. Ou `json_pointer="/settings/defaultTimeframe/enabled"`, `value=true`. Para remover uma propriedade existente, `operation="remove"`.

### Exemplo 4: mover um painel

Use `plan_update_tile_layout(dashboard_id="...", tile_id="2", layout_patch={"x":12,"w":12})`.

## Segurança e consistência

- Somente **HTTPS**, com validação TLS, sem comandos de sistema ou execução de DQL no servidor de escrita.
- Token somente em `.env` (não versionado). Auth é Bearer e funciona por Platform Token ou OAuth client credentials.
- `publish_change` exige `DT_ALLOW_WRITE=1`, `confirm=True`, `plan_id` existente e controle otimista pela versão de metadata fornecida pelo Dynatrace.
- Uma nova leitura confirma que versão e conteúdo não mudaram desde a prévia. O **HTTP PUT substitui o conteúdo do documento**, mas a edição é feita sobre uma cópia do JSON original para preservar outros tiles.
- Antes de atualizar um documento, grava backup JSON **local** em `backups/`. O diretório também é excluído de Git. Guarde-o em lugar aprovado pela política de segurança (pode conter DQL e informação de ambiente). Se o backup falhar, a escrita é bloqueada.
- A função de validação local é **estrutural**, não valida a semântica completa do esquema Dynatrace; o dashboard pode exigir campos extras em tipos de visualização específicos. Compare com um tile real que já renderiza e valide no Dynatrace.
- O servidor não tem ferramenta para apagar o documento inteiro nem alterar compartilhamentos.

## Testar sem chamar o tenant

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q .
```

Os testes usam **HTTP simulado**. Sem acesso ao seu tenant, não há garantia de teste ponta a ponta: use primeiro um dashboard descartável no seu ambiente.

## Integração coexistente

Mantenha seu MCP Dynatrace de consulta como já está. Adicione **somente** este novo servidor no seu workspace ou configuração global (mesmo `mcp.json` pode ter vários servidores em `servers`). O projeto fornece uma `.vscode/mcp.json` dedicada para o workspace dele. Se você quiser usar o editor em qualquer workspace, copie a entrada `dynatrace-dashboard-editor-http` para a configuração de MCP do seu usuário e troque `${workspaceFolder}` por **caminhos absolutos para a pasta deste projeto**, pois workspaceFolder mudará conforme o repositório aberto. Isso evita conflito com outros MCPs.

## Documentação oficial

- Document service: https://docs.dynatrace.com/docs/analyze-explore-automate/dashboards-and-notebooks/document-api
- Esquema JSON e layout: https://docs.dynatrace.com/docs/analyze-explore-automate/dashboards-and-notebooks/document-api/document-structure-dashboards
- Developer document API: https://developer.dynatrace.com/develop/sdks/client-document/v1/
- Platform Token: https://docs.dynatrace.com/docs/manage/identity-access-management/access-tokens-and-oauth-clients/platform-tokens
- VS Code MCP: https://code.visualstudio.com/docs/agents/reference/mcp-configuration
- MCP Python v2: https://py.sdk.modelcontextprotocol.io/get-started/installation/
