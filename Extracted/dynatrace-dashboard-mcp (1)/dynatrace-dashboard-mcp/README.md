# Dynatrace Dashboard MCP local (GitHub Copilot + VS Code)

Projeto de exemplo em JavaScript para gerenciar dashboards **Latest Dynatrace (SaaS)** a partir do GitHub Copilot. O servidor usa **MCP por stdio** e delega autenticação/chamadas remotas ao **dtctl**. Não é um componente oficial da Dynatrace.

## Pré-requisitos

- VS Code com GitHub Copilot Chat (modo Agent), Node.js >= 20, npm.
- Dynatrace **SaaS Latest**, acesso para leitura/gravação de dashboards, permissões `document:documents:read` e `document:documents:write` (além das permissões DQL para `run_dql`).
- `dtctl` instalado e autenticado na **mesma máquina/processo em que o MCP rodará**.

## 1. Instale e autentique o dtctl

Instalação: consulte https://docs.dynatrace.com/docs/platform/dtctl

macOS/Linux com Homebrew: `brew install dynatrace-oss/tap/dtctl`

Windows PowerShell: `irm https://raw.githubusercontent.com/dynatrace-oss/dtctl/main/install.ps1 | iex` (revise o script antes de executar).

```sh
dtctl auth login --context meu-ambiente --environment "https://abc12345.apps.dynatrace.com"
dtctl doctor
dtctl get dashboards -o json
dtctl query 'fetch logs | limit 1'
```

A autenticação via OAuth abre o browser e armazena credenciais no cofre do sistema operacional. Se usar vários contextos, defina `DTCTL_CONTEXT=meu-ambiente` no processo MCP ou selecione contexto com `dtctl config use-context meu-ambiente` conforme sua versão.

## 2. Instale o MCP

Dentro desta pasta:

```sh
npm install
npm run check
```

Abra **esta pasta como workspace** no VS Code. O arquivo `.vscode/mcp.json` já está configurado; ele inicia o servidor automaticamente pelo VS Code quando você o habilitar.

> Se for usar em outro projeto, copie a entrada MCP para o `.vscode/mcp.json` dele e substitua `"${workspaceFolder}/src/index.js"` pelo caminho absoluto deste `src/index.js`.

> Em versões novas do VS Code, `.mcp.json` no workspace com `mcpServers` é o formato portátil recomendado; `.vscode/mcp.json` continua compatível.

## 3. Teste no Copilot

1. Abra a paleta de comandos e execute **MCP: List Servers** (ou abra `.vscode/mcp.json` e inicie o servidor).
2. No Chat do Copilot, escolha modo **Agent**.
3. Experimente: `Liste meus dashboards do Dynatrace usando list_dashboards`.
4. Experimente: `Gere um dashboard de hosts com gráficos de CPU e memória. Valide as DQLs com run_dql. Mostre a prévia, sem publicar.`
5. Depois de conferir a prévia, aprove explicitamente para que o Copilot chame a ferramenta com `confirm=true`.

## Ferramentas disponíveis

| Nome | Ação | Modifica ambiente? |
| --- | --- | --- |
| `list_dashboards` | Retorna lista de dashboards | Não |
| `get_dashboard` | Retorna JSON completo de um dashboard | Não |
| `run_dql` | Executa DQL para explorar/validar dados | Não (mas pode ter custo) |
| `create_dashboard` | Cria dashboard a partir de JSON de conteúdo | Apenas com `confirm=true` |
| `upsert_dashboard_tile` | Adiciona ou altera tile após ler JSON atual | Apenas com `confirm=true` |

**A prévia usa `dtctl apply --dry-run`.** Nunca aceite `confirm=true` sem verificar o que o agente quer modificar. Confirmação programática não substitui o controle de permissões do VS Code ou da organização.

## Exemplo do JSON de dashboard

Consulte `example-dashboard.json`. A estrutura contém `version: 21`, `variables`, `tiles` e `layouts`. Esse arquivo demonstra o formato do conteúdo; as DQLs devem ser testadas no seu próprio ambiente antes da publicação.

## Segurança e limitações

- Nunca inclua senhas, tokens nem chaves no repositório. Prefira o OAuth do `dtctl`.
- A ferramenta `upsert_dashboard_tile` preserva os campos existentes porque **busca o documento atual antes de modificar**, mas não faz *optimistic locking* entre a leitura e a gravação. Evite edição concorrente, especialmente em produção.
- O MCP está limitado a dashboards da versão **Latest Dynatrace**. Para **Dashboards Classic**, use a Configuration API `api/config/v1/dashboards`, que possui esquema e autenticação diferentes.
- Este é um MVP; não oferece exclusão, compartilhamento nem operações gerais com variáveis. Para produção, acrescente auditoria, testes e política de aprovação.
- `dtctl` emite erros/diagnósticos; o MCP os encaminha ao Copilot. Verifique sua política de dados antes de consultar logs sensíveis.
- Não há testes reais com seu Dynatrace neste pacote; valide as ferramentas no seu tenant.

## Referências

- Dynatrace dtctl: https://docs.dynatrace.com/docs/platform/dtctl
- Dynatrace dashboard JSON: https://docs.dynatrace.com/docs/analyze-explore-automate/dashboards-and-notebooks/document-api/document-structure-dashboards
- Dynatrace Document API: https://docs.dynatrace.com/docs/analyze-explore-automate/dashboards-and-notebooks/document-api
- VS Code MCP: https://code.visualstudio.com/docs/agent-customization/mcp-servers
- MCP TypeScript SDK v2: https://github.com/modelcontextprotocol/typescript-sdk
