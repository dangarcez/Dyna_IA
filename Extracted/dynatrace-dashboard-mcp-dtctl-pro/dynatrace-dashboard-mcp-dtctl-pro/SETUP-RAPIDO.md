# Setup rápido — Dynatrace Dashboard MCP Python + dtctl

> Para **Latest Dynatrace (Grail/DQL)**. O servidor MCP usa `stdio`, e o acesso ao tenant é feito pelo executável `dtctl` (não há chamadas HTTPS programadas neste MCP).

## 1. Requisitos

- VS Code com GitHub Copilot em modo Agent e suporte a MCP.
- Python 3.11+.
- `dtctl` instalado e autenticado em um contexto que tenha acesso aos dashboards que deseja editar.

No PowerShell, confira:

```powershell
Get-Command dtctl | Select-Object -ExpandProperty Source

dtctl --help
dtctl get dashboards -o json --plain
```

Se não aparecer o executável, instale `dtctl` via documentação do projeto ou use a **versão HTTP** do MCP que não depende dele.

Caso precise criar contexto OAuth:

```powershell
dtctl auth login --context meu-ambiente --environment "https://SEU-ID.apps.dynatrace.com"
dtctl auth status
dtctl get dashboards --context meu-ambiente -o json
```

## 2. Criar ambiente Python

Extraia o ZIP, abra **a pasta do projeto** no VS Code e execute no terminal PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Use outra versão instalada com `py -0p` se você não tiver o Python 3.11, desde que seja 3.11+.

## 3. Configurar .vscode/mcp.json

O arquivo já está no projeto. Ajuste `DTCTL_CONTEXT` e `DTCTL_BIN`, apontando para o caminho real do `dtctl.exe` descoberto em (1):

```json
{
  "servers": {
    "dynatrace-dashboard-editor-dtctl": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": ["${workspaceFolder}/server.py"],
      "env": {
        "DTCTL_CONTEXT": "meu-ambiente",
        "DTCTL_BIN": "C:/caminho/real/dtctl.exe",
        "DTCTL_ALLOW_WRITE": "0"
      }
    }
  }
}
```

As barras `/` funcionam no caminho Windows dentro de JSON. Se `dtctl` já estiver no PATH acessível ao VS Code, pode usar `"DTCTL_BIN": "dtctl"`.

Para Linux/macOS, ajuste `command` para `${workspaceFolder}/.venv/bin/python` e `DTCTL_BIN` para o binário correspondente.

## 4. Ligar ao GitHub Copilot

1. `Ctrl+Shift+P` → **MCP: List Servers** → inicie `dynatrace-dashboard-editor-dtctl`.
2. Abra o Copilot Chat no modo **Agent** e habilite as ferramentas MCP se solicitado.
3. Teste: **"Use check_connection e list_dashboards do MCP dynatrace-dashboard-editor-dtctl. Não altere nada."**
4. Teste uma prévia: **"Encontre meu dashboard de testes e planeje ocultar a legenda do tile de latência. Mostre o diff e não publique."**

## 5. Publicar alterações somente após revisar

Por padrão, `DTCTL_ALLOW_WRITE=0` bloqueia publicação, mas permite gerar `plan_*`, diff e dry-run. Após revisar:

1. Edite `.vscode/mcp.json`: `"DTCTL_ALLOW_WRITE": "1"`.
2. Reinicie o servidor MCP.
3. **Gere uma nova prévia**, pois os planos em memória são apagados no reinício.
4. Revise o diff e aprove explicitamente a mudança no Copilot. Só então o Copilot deve chamar `publish_change` com `confirm=true` e o `plan_id` gerado na nova prévia.

O servidor salva backups JSON em `backups/` antes de atualizar documentos existentes. Não comite backups: podem conter dados internos. Para corrigir erros de permissão, confira o contexto do `dtctl` (`dtctl auth status`, safety level e escopos).

## Importante

- Essa versão é para **Dashboards novos** (não Dashboards Classic).
- A alteração é feita editando o documento JSON completo, embora você solicite apenas um campo. Antes da escrita, o MCP relê o documento e bloqueia se ele mudou. `dtctl apply` não é uma operação de atualização atômica (existe uma pequena janela para edições simultâneas).
- `dtctl apply --dry-run --no-hooks` evita publicação durante a prévia. Essa opção também desabilita hooks configurados para o `dtctl`; consulte suas políticas corporativas antes de usar.
- O SDK MCP não pôde ser instalado neste ambiente de teste sem conexão à Internet. Os testes de lógica foram executados com mocks, não houve conexão a tenant real.
