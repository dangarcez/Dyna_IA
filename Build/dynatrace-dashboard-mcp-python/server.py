"""MCP local para GitHub Copilot + Latest Dynatrace, usando Python SDK v2."""
from typing import Any

from mcp.server import MCPServer

import backend

mcp = MCPServer("dynatrace-dashboard-python", version="1.0.0")


@mcp.tool()
def check_connection() -> dict[str, Any]:
    """Diagnostica o dtctl (caminho DTCTL_BIN, versão, contexto e OAuth)."""
    return backend.check_connection()


@mcp.tool()
def list_dashboards() -> Any:
    """Lista os dashboards disponíveis no contexto Dynatrace atual."""
    return backend.list_dashboards()


@mcp.tool()
def get_dashboard(dashboard_id: str) -> dict[str, Any]:
    """Lê o documento JSON integral pelo ID. Consulte ANTES de qualquer atualização."""
    return backend.get_dashboard(dashboard_id)


@mcp.tool()
def list_dashboard_tiles(dashboard_id: str) -> dict[str, Any]:
    """Mostra os IDs, títulos, tipos, DQLs, layouts e visualizationSettings de todos os tiles."""
    return backend.list_dashboard_tiles(dashboard_id)


@mcp.tool()
def run_dql(dql: str) -> Any:
    """Executa DQL para validar campos e resultados. Pode gerar custos de consulta no Grail."""
    return backend.run_dql(dql)


@mcp.tool()
def create_dashboard(name: str, content: dict[str, Any] | None = None, confirm: bool = False) -> dict[str, Any]:
    """Cria dashboard Latest Dynatrace. Sem content, cria com título Markdown.

    Sempre executar prévia (confirm=false) primeiro. Só publica se confirm=true E
    DTCTL_ALLOW_WRITE=1. Para dashboards com queries, execute run_dql antes.
    """
    return backend.create_dashboard(name, content, confirm)


@mcp.tool()
def upsert_dashboard_tile(
    dashboard_id: str, kind: str = "data", tile_id: str | None = None,
    title: str | None = None, query: str | None = None,
    visualization: str | None = None,
    visualization_settings: dict[str, Any] | None = None,
    query_settings: dict[str, Any] | None = None,
    markdown: str | None = None, layout: dict[str, Any] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Adiciona ou atualiza tile e layout; preserva outros gráficos e conteúdo.

    kind='data' exige título, DQL e visualization (ex.: lineChart) em tile novo.
    visualization_settings permite definir legendas, eixos, cores, tabela etc.
    Use confirm=false para prévia e confirm=true para publicar (se escrita liberada).
    """
    return backend.upsert_dashboard_tile(
        dashboard_id, kind, tile_id, title, query, visualization,
        visualization_settings, query_settings, markdown, layout, confirm,
    )


@mcp.tool()
def update_tile_visualization(
    dashboard_id: str, tile_id: str,
    visualization: str | None = None,
    settings_patch: dict[str, Any] | None = None,
    mode: str = "merge", title: str | None = None,
    query_settings_patch: dict[str, Any] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Atualiza APENAS a visualização de um tile existente sem recriar o dashboard.

    settings_patch é um objeto do JSON `visualizationSettings` do Dynatrace:
    eixos, legenda, dataMapping, cor, séries, unidades, colunas etc.
    mode='merge' combina objetos recursivamente (arrays são substituídos);
    mode='replace' substitui todas as configurações. Para trocar tipo de gráfico,
    use mode='replace' e envie ajustes próprios do novo tipo.
    Prévia padrão confirm=false; publicação exige confirm=true e DTCTL_ALLOW_WRITE=1.
    """
    return backend.update_tile_visualization(
        dashboard_id, tile_id, visualization, settings_patch, mode, title,
        query_settings_patch, confirm,
    )


if __name__ == "__main__":
    # Stdio usa stdout para protocolo; não usar print() no processo servidor.
    mcp.run()
