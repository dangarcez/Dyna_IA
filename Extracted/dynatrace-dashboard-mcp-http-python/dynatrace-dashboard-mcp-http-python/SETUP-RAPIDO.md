# Setup rápido — VS Code / Copilot / Windows (sem dtctl)

1. **Extraia o ZIP** e abra a pasta `dynatrace-dashboard-mcp-http-python` no VS Code.
2. **Instale Python 3.11+** e, no PowerShell da pasta, execute:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

   Se você usa outra versão 3.11+, ajuste `py -3.11` para `py -3.12` ou `py -3.13`.

3. **Configure credenciais** (PowerShell):

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

   Preencha `DT_ENV_URL` (por exemplo, `https://abc123.apps.dynatrace.com`) e `DT_PLATFORM_TOKEN`. Solicite scopes IAM `document:documents:read` e `document:documents:write`. Seu usuário/token também precisa ter acesso aos documentos. O `.env` não deve ir para Git.

4. **No VS Code**: `Ctrl+Shift+P` → **MCP: List Servers** → iniciar `dynatrace-dashboard-editor-http`. Abra Copilot Agent e habilite as ferramentas do novo servidor. O MCP do Dynatrace para consultas permanece separado.

5. **Teste no Copilot**: “Use `connection_status` do editor HTTP e depois `list_dashboards`. Não publique nada.”

6. **Para editar**: peça “Localize o dashboard X, mostre os IDs dos gráficos, prepare alteração do eixo Y do tile 2 via `plan_update_tile_visualization`, mas não publique.”

7. **Para permitir publicação**: no `.env`, altere `DT_ALLOW_WRITE=1`, reinicie o servidor em `MCP: List Servers`, revise o diff retornado por `plan_*` e só então autorize `publish_change(plan_id, confirm=True)`. A atualização grava backup em `backups/` (sensível, não versionar).

## Linux, macOS ou WSL

Execute `python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt` e em `.vscode/mcp.json` substitua `/.venv/Scripts/python.exe` por `/.venv/bin/python`. Em Remote/Dev Container, instale o Python e configure as credenciais no ambiente remoto, não no host.

## Se não funcionar

- `ModuleNotFoundError`: execute o pip exatamente dentro do `.venv`; confira caminho do Python no `mcp.json`.
- `401/403`: conferir URL, plataforma token ou OAuth, escopos de API, IAM e permissões de compartilhamento do dashboard.
- `409`: dashboard mudou; gere uma nova prévia.
- Falha TLS/proxy: use as configurações de proxy/CA da empresa; **não desative validação TLS**.
- Seu Dynatrace é **Classic**? Este MCP não serve: o endpoint e o JSON de Classic são diferentes.

Veja `README.md` para detalhes das ferramentas, segurança e exemplos.
