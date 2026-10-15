"""MCP Python para edição GRANULAR de dashboards Latest Dynatrace via dtctl.

Transporte MCP: stdio. dtctl executado localmente; sem API HTTP escrita no projeto.
Nunca escreva logs em stdout: saída reservada ao protocolo MCP.
"""
from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

import dtctl_client as cli
import planner

mcp = MCPServer("dynatrace-dashboard-editor-dtctl", version="2.0.0")


@mcp.tool()
def check_connection() -> dict[str, Any]:
    """Verifica binário dtctl, versão, contexto e autenticação, sem modificar dashboards."""
    return cli.check()


@mcp.tool()
def list_dashboards() -> Any:
    """Lista dashboards existentes; use o ID exato para evitar nomes ambíguos."""
    return cli.get_dashboards()


@mcp.tool()
def get_dashboard(dashboard_id: str) -> dict[str, Any]:
    """Obtém JSON COMPLETO com id, name, content (tiles/layouts/variables/settings)."""
    return cli.get_dashboard(dashboard_id)


@mcp.tool()
def list_dashboard_tiles(dashboard_id: str) -> dict[str, Any]:
    """Lista IDs de tiles, títulos, tipos, visualização, DQL e layout para escolher alvo."""
    resource = cli.get_dashboard(dashboard_id)
    content = resource["content"]
    return {"dashboard_id": dashboard_id, "dashboard_name": resource.get("name"), "tiles": [
        {"tile_id": key, "type": tile.get("type"), "title": tile.get("title"),
         "visualization": tile.get("visualization"), "query": tile.get("query"),
         "layout": content["layouts"].get(key)}
        for key, tile in content["tiles"].items()
    ]}


@mcp.tool()
def get_dashboard_tile(dashboard_id: str, tile_id: str) -> dict[str, Any]:
    """Lê tile com querySettings, visualizationSettings e layout ANTES de editar suas propriedades."""
    content = cli.get_dashboard(dashboard_id)["content"]
    if tile_id not in content["tiles"]:
        raise ValueError("Tile não encontrado")
    return {"tile_id": tile_id, "tile": content["tiles"][tile_id], "layout": content["layouts"][tile_id]}


@mcp.tool()
def run_dql(dql: str) -> Any:
    """Executa DQL somente para validação (pode consumir Grail); também há MCP Dynatrace de consulta."""
    return cli.query(dql)


@mcp.tool()
def plan_create_dashboard(name: str, content: dict[str, Any] | None = None, description: str = "") -> dict[str, Any]:
    """Gera prévia e dry-run de novo dashboard, SEM publicar. Deixe content vazio para dashboard vazio."""
    return planner.plan_create_dashboard(name, content, description)


@mcp.tool()
def plan_add_tile(dashboard_id: str, tile: dict[str, Any], layout: dict[str, int] | None = None, tile_id: str = "") -> dict[str, Any]:
    """Inclui tile data/markdown/code/slo. ID automático se omitido. Dry-run e diff sem publicar."""
    return planner.plan_add_tile(dashboard_id, tile, layout, tile_id)


@mcp.tool()
def plan_upsert_tile(dashboard_id: str, tile_id: str, tile_patch: dict[str, Any], layout_patch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Inclui tile com JSON completo ou atualiza parcialmente um existente. Preserva demais tiles."""
    return planner.plan_upsert_tile(dashboard_id, tile_id, tile_patch, layout_patch)


@mcp.tool()
def plan_patch_tile(dashboard_id: str, tile_id: str, patch: dict[str, Any], mode: str = "merge") -> dict[str, Any]:
    """Modifica propriedades de tile: title, description, timeframe, segments, querySettings, séries etc. merge preserva campos; replace substitui."""
    return planner.plan_patch_tile(dashboard_id, tile_id, patch, mode)


@mcp.tool()
def plan_edit_tile_dql(dashboard_id: str, tile_id: str, query: str, query_settings_patch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Troca somente DQL de um tile data (e opcionalmente querySettings), sem tocar na visualização."""
    return planner.plan_edit_tile_dql(dashboard_id, tile_id, query, query_settings_patch)


@mcp.tool()
def plan_update_tile_visualization(dashboard_id: str, tile_id: str, visualization: str = "", settings_patch: dict[str, Any] | None = None, mode: str = "merge") -> dict[str, Any]:
    """Configura TIPO/APARÊNCIA da visualização: eixos, legenda, cores, séries, tabela, unidade, dataMapping, limites etc. mode=merge faz merge profundo; mode=replace limpa settings antigos. MUDANÇA DE TIPO exige replace."""
    return planner.plan_visualization(dashboard_id, tile_id, visualization, settings_patch, mode)


@mcp.tool()
def plan_update_tile_layout(dashboard_id: str, tile_id: str, layout_patch: dict[str, int]) -> dict[str, Any]:
    """Move/redimensiona um gráfico atualizando x,y,w,h na grade de 24 colunas."""
    return planner.plan_layout(dashboard_id, tile_id, layout_patch)


@mcp.tool()
def plan_remove_tile(dashboard_id: str, tile_id: str) -> dict[str, Any]:
    """Exclui tile e layout correspondente, somente na prévia até publicação aprovada."""
    return planner.plan_remove_tile(dashboard_id, tile_id)


@mcp.tool()
def plan_patch_dashboard_field(dashboard_id: str, json_pointer: str, value: Any = None, operation: str = "set") -> dict[str, Any]:
    """Edição granular por JSON Pointer RELATIVO A content. Ex.: /tiles/2/visualizationSettings/legend/showLegend (value=false) ou /variables/0/name. operation=set|remove. NÃO prefixe /content."""
    return planner.plan_pointer(dashboard_id, json_pointer, value, operation)



@mcp.tool()
def plan_batch_dashboard_patches(dashboard_id: str, patches: list[dict[str, Any]]) -> dict[str, Any]:
    """Aplica 1-25 ajustes granulares em uma ÚNICA prévia: [{"path":"/tiles/2/visualizationSettings/legend/showLegend","operation":"set","value":false}]. Caminhos relativos a content; suporta set/remove."""
    return planner.plan_batch_patches(dashboard_id, patches)


@mcp.tool()
def plan_update_dashboard_settings(dashboard_id: str, settings_patch: dict[str, Any]) -> dict[str, Any]:
    """Atualiza parcialmente content.settings (timeframe, filtros e outras configurações)."""
    return planner.plan_settings(dashboard_id, settings_patch)


@mcp.tool()
def plan_manage_variable(dashboard_id: str, action: str, name: str, definition: dict[str, Any] | None = None) -> dict[str, Any]:
    """Gerencia variável de dashboard: action=add|replace|remove, name é key ou name. definition deve ser objeto completo no formato do tenant."""
    return planner.plan_variable(dashboard_id, action, name, definition)


@mcp.tool()
def plan_rename_dashboard(dashboard_id: str, name: str, description: str | None = None) -> dict[str, Any]:
    """Altera nome e opcionalmente descrição do dashboard, sem editar tiles."""
    return planner.plan_rename(dashboard_id, name, description)


@mcp.tool()
def plan_replace_dashboard_content(dashboard_id: str, content: dict[str, Any]) -> dict[str, Any]:
    """Substitui o content INTEIRO com prévia. Use apenas para migração/refatoração deliberada."""
    return planner.plan_replace_content(dashboard_id, content)


@mcp.tool()
def review_change(plan_id: str) -> dict[str, Any]:
    """Reapresenta alterações propostas, diff e saída de dry-run. Não publica."""
    return planner.review(plan_id)


@mcp.tool()
def discard_change(plan_id: str) -> dict[str, Any]:
    """Descarta plano de alteração pendente sem escrever no Dynatrace."""
    return planner.discard(plan_id)


@mcp.tool()
def publish_change(plan_id: str, confirm: bool = False) -> dict[str, Any]:
    """Publica plano revisado com confirm=true e DTCTL_ALLOW_WRITE=1. Confere documento atual, salva backup local e chama dtctl apply. Exige aprovação humana."""
    return planner.publish(plan_id, confirm)


if __name__ == "__main__":
    mcp.run(transport="stdio")
