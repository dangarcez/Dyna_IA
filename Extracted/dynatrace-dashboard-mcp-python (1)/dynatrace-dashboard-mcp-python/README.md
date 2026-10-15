# MCP Dynatrace em Python — GitHub Copilot (VS Code)

Projeto educacional de servidor **MCP local por stdio**, em Python, para consultar, criar e atualizar **dashboards Latest Dynatrace** (Grail/DQL). Usa o [SDK oficial MCP para Python v2](https://py.sdk.modelcontextprotocol.io/) e delega autenticação e HTTP ao [`dtctl`](https://docs.dynatrace.com/docs/platform/dtctl). Não é um produto oficial da Dynatrace.

> **Escopo:** Não suporta **Dashboards Classic**, cujo formato de tiles (`visualConfig`) e API são diferentes. **Não foi conectado ao seu tenant**; valide permissões, DQL e visualizações antes de publicar.

## Conteúdo

- `server.py`: registra 8 ferramentas MCP usando `MCPServer`.
- `backend.py`: regras de validação, diffs, backup e comandos `dtctl` (sem execução de shell).
- `.vscode/mcp.json`: exemplo **Windows PowerShell** para o Copilot.
- `examples/dashboard-exemplo.json`: JSON para Latest Dynatrace.
- `examples/alterar-visualizacao.json`: argumentos para configurar uma visualização existente.
- `examples/trocar-tipo-visualizacao.json`: argumentos para trocar lineChart para areaChart.
- `tests/test_backend.py`: testes automatizados sem necessidade de ambiente Dynatrace.

## 1. Pré-requisitos

- Windows com **Python 3.11+**, VS Code e extensão GitHub Copilot Chat.
- `dtctl` instalado; Dynatrace SaaS Latest com acesso ao Document Service (leitura; escrita se for publicar).
- Login OAuth no `dtctl` configurado na **mesma máquina e conta de sistema operacional** que executa o VS Code. No caso de WSL/Dev Container/Remote, é no host remoto onde o MCP executa.
- Acesso a DQL/Grail se quiser usar `run_dql`. Consulte as permissões do Dynatrace da sua organização.

### 1.1 Localize o executável do dtctl no Windows

No terminal PowerShell do VS Code:

```powershell
(Get-Command dtctl).Source
# caso não esteja no PATH, encontre dtctl.exe pelo Explorador e use seu caminho completo
```

Exemplo de saída (apenas exemplo): `C:\Users\seuusuario\AppData\Local\Programs\dtctl\dtctl.exe`.

### 1.2 Configure acesso Dynatrace

```powershell
& "C:\CAMINHO\REAL\dtctl.exe" auth login --context meu-ambiente --environment "https://SEU-AMBIENTE.apps.dynatrace.com"
& "C:\CAMINHO\REAL\dtctl.exe" --context meu-ambiente doctor
& "C:\CAMINHO\REAL\dtctl.exe" --context meu-ambiente get dashboards -o json
```

Você **não precisa** armazenar um token no `mcp.json`: o `dtctl` gerencia as credenciais. Troque o domínio pelo endpoint correto do seu ambiente.

## 2. Crie ambiente Python e instale dependências

Extraia o ZIP, abra a **pasta raiz `dynatrace-dashboard-mcp-python`** no VS Code e execute o PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Se sua instalação padrão de Python já for 3.11+, você também pode usar `py -m venv .venv`.

## 3. Configure a conexão MCP no VS Code

Edite `.vscode/mcp.json` conforme seu ambiente (já incluído no projeto):

```json
{
  "servers": {
    "dynatrace-dashboard-python": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": ["${workspaceFolder}/server.py"],
      "env": {
        "DTCTL_CONTEXT": "meu-ambiente",
        "DTCTL_BIN": "C:/CAMINHO/REAL/dtctl.exe",
        "DTCTL_ALLOW_WRITE": "0"
      }
    }
  }
}
```

**Ajuste os campos `DTCTL_BIN` e `DTCTL_CONTEXT`.** O campo `DTCTL_BIN` resolve o problema anterior: **dtctl instalado mas fora do PATH**. No Windows, use barras `/` no caminho JSON, ou escape `\\`.

- `DTCTL_ALLOW_WRITE=0`: nenhuma ferramenta publica alterações, mesmo se `confirm=true`.
- `DTCTL_ALLOW_WRITE=1`: permite a operação quando a ferramenta receber `confirm=true`.
- Por segurança, **não inclua credenciais** no `mcp.json`; o arquivo pode ser versionado.
- Para usar em **outro projeto**, a entrada pode ficar no `.vscode/mcp.json` desse projeto, mas `command` e `args` devem apontar para caminhos **absolutos** da instalação do MCP Python.
- No **Linux/macOS**, `command` vira `${workspaceFolder}/.venv/bin/python`. Instale com `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
- Nas versões recentes do VS Code, `.mcp.json` (chave `mcpServers`) é a alternativa portátil recomendada; `.vscode/mcp.json` continua compatível.

## 4. Inicie e use no GitHub Copilot

1. No VS Code, abra a paleta: `Ctrl+Shift+P` → `MCP: List Servers`.
2. Selecione `dynatrace-dashboard-python` e clique em **Start** ou **Restart**.
3. No GitHub Copilot Chat, escolha o modo **Agent** e verifique se as ferramentas MCP estão disponíveis.
4. Pergunte: `Use check_connection para testar o dtctl. Depois liste meus dashboards com list_dashboards.`
5. Peça: `Use list_dashboard_tiles no dashboard ID .... Mostre os tile_ids e configurações de visualização.`
6. Peça: `Atualize a legenda do tile 2 do dashboard ID ... para ficar oculta, mantendo o resto, e mostre a prévia (confirm=false).`
7. **Só após revisar o diff e aceitar o conteúdo**, mude `DTCTL_ALLOW_WRITE` para `1`, reinicie o servidor, e peça uma chamada `confirm=true`.

Não inicie `python server.py` em um terminal esperando um prompt: por ser `stdio`, ele fica aguardando mensagens MCP. O VS Code é quem o inicia.

## 5. Ferramentas disponibilizadas

| Ferramenta | Ação |
|---|---|
| `check_connection` | Caminho do `dtctl`, versão e diagnóstico `doctor` |
| `list_dashboards` | Lista dashboards |
| `get_dashboard(dashboard_id)` | Retorna documento JSON integral |
| `list_dashboard_tiles(dashboard_id)` | Lista IDs, queries, layouts, `visualizationSettings` |
| `run_dql(dql)` | Executa DQL para validação |
| `create_dashboard(name,content?,confirm?)` | Cria dashboard (prévia por padrão) |
| `upsert_dashboard_tile(...)` | Adiciona/atualiza tile, query, layout, configurações |
| **`update_tile_visualization(...)`** | **Atualiza o tipo e as opções de visualização de um tile existente** |

### Ferramenta nova: update_tile_visualization

Exemplo de chamada MCP (arquivo: `examples/alterar-visualizacao.json`):

```json
{
  "dashboard_id": "SEU-DASHBOARD-ID",
  "tile_id": "2",
  "settings_patch": {
    "legend": { "showLegend": false },
    "axes": { "yAxis": { "showLabel": true, "label": "CPU (%)" } },
    "seriesConfig": { "curve": "linear", "pointsDisplay": "auto" }
  },
  "mode": "merge",
  "confirm": false
}
```

- `mode="merge"` atualiza só as chaves especificadas, preservando as demais; listas passadas são substituídas integralmente.
- `mode="replace"` substitui completamente `visualizationSettings`. **Obrigatório ao trocar `visualization`** (por exemplo de `lineChart` para `areaChart`), para evitar carregar opções incompatíveis do tipo anterior.
- Você também pode atualizar `title` e `query_settings_patch` quando necessário. O comando `upsert_dashboard_tile` aceita `visualization_settings` na criação ou edição.
- A ferramenta sempre baixa o JSON atual antes da alteração, gera diff, chama `dtctl apply --dry-run` e só publica com dupla autorização.
- Em publicações de dashboard existente, cria backup integral do documento anterior em `backups/` (não commitado no Git).

**Exemplos de tipos:** `lineChart`, `areaChart`, `barChart` (série temporal), `categoricalBarChart` (por categoria), `pieChart`, `donutChart`, `singleValue`, `table` etc. Os campos reais de `visualizationSettings` dependem do tipo; não coloque configurações de gráfico temporal num `table`.

Confira a [referência de tipos e campos](https://github.com/Dynatrace/dynatrace-for-ai/blob/main/skills/dt-app-dashboards/references/tiles.md) e a [referência de opções de visualização](https://github.com/Dynatrace/dynatrace-for-ai/blob/main/skills/dt-app-dashboards/assets/visualization-settings.reference.jsonc).

### Criar dashboard via MCP

Sem `content`, `create_dashboard` gera um dashboard com um tile Markdown de título. Para incluir gráficos, envie `content` com `version`, `variables`, `tiles` e `layouts` conforme `examples/dashboard-exemplo.json`; **não** inclua `id` no documento novo (o Dynatrace o gera).

Ao mudar queries DQL, faça `run_dql` antes de publicar. Queries que dependem de variáveis podem precisar de validação com valores reais. O exemplo de CPU usa uma métrica documentada, mas a existência dos dados e permissões depende do ambiente.

## 6. Segurança, funcionamento e limitações

- `DTCTL_ALLOW_WRITE=0` bloqueia publicação, mesmo se o agente enviar `confirm=true`.
- Operações com `confirm=false` sempre passam por `dtctl apply --dry-run` para validação/antevisão e fornecem diff de JSON; esse dry run ainda exige autenticação/permissões e pode falhar.
- Backup automático antes de publicar uma atualização, mas **não existe controle de concorrência forte**: evite editar o mesmo dashboard simultaneamente em duas sessões ou com outra pessoa no UI.
- O MCP usa `subprocess.run` **sem shell**, impedindo interpretação de caracteres especiais da DQL como comandos do sistema.
- `run_dql` pode ter custos Grail, e os resultados são expostos ao agente Copilot. Evite consultas de dados sensíveis e respeite a política da sua organização.
- Para **Dashboards Classic**, é necessário outro adaptador, baseado na Configuration API clássica (`/api/config/v1/dashboards`) e nas propriedades `visualConfig` dos tiles.
- Sem acesso ao seu tenant, só testamos a lógica local. A aceitação definitiva do JSON, parâmetros do CLI e permissões deve ser confirmada num dashboard de testes primeiro.

## 7. Referências oficiais

- [Dynatrace dtctl](https://docs.dynatrace.com/docs/platform/dtctl)
- [Schema JSON dos dashboards](https://docs.dynatrace.com/docs/analyze-explore-automate/dashboards-and-notebooks/document-api/document-structure-dashboards)
- [Criar e atualizar dashboard com dtctl](https://github.com/Dynatrace/dynatrace-for-ai/blob/main/skills/dt-app-dashboards/references/create-update.md)
- [SDK Python MCP v2](https://py.sdk.modelcontextprotocol.io/)
- [VS Code MCP](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
