"""MCP local (stdio) para escrita granular de dashboards Latest Dynatrace via HTTPS.

Python >=3.11; SDK MCP v2. stdout reservado ao protocolo MCP.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from mcp.server import MCPServer

from dashboard_logic import (add_tile, deep_merge, default_dashboard,
                             diff_json, patch_visualization,
                             pointer_update, validate_dashboard)
from dynatrace_http import DynatraceDocuments

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)
mcp = MCPServer("Dynatrace Dashboard Editor HTTP")

PLAN_TTL_SECONDS = 15 * 60
MAX_PLANS = 20


@dataclass
class Plan:
    kind: str  # create | update
    name: str
    description: str
    dashboard_id: str
    expected_version: str
    before: dict[str, Any] | None
    after: dict[str, Any]
    created: float


_plans: dict[str, Plan] = {}


def _client() -> DynatraceDocuments:
    return DynatraceDocuments.from_env()


def _fingerprint(obj: dict[str, Any]) -> str:
    encoded = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _compact_plans() -> None:
    now = time.monotonic()
    for key, plan in list(_plans.items()):
        if now - plan.created > PLAN_TTL_SECONDS:
            del _plans[key]
    while len(_plans) >= MAX_PLANS:
        del _plans[next(iter(_plans))]


def _plan_summary(plan: Plan, plan_id: str) -> dict[str, Any]:
    return {
        "status": "PREVIEW_ONLY_NOT_PUBLISHED",
        "plan_id": plan_id,
        "operation": plan.kind,
        "dashboard_id": plan.dashboard_id or None,
        "dashboard_name": plan.name,
        "expected_document_version": plan.expected_version or None,
        "expires_in_seconds": PLAN_TTL_SECONDS,
        "diff": diff_json(plan.before, plan.after),
        "next_step": "Solicite aprovação humana e então chame publish_change(plan_id, confirm=True).",
    }


def _register(plan: Plan) -> dict[str, Any]:
    _compact_plans()
    plan_id = secrets.token_urlsafe(18)
    _plans[plan_id] = plan
    return _plan_summary(plan, plan_id)


def _plan_change(dashboard_id: str, transform: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    with _client() as c:  # adicionado suporte a context manager abaixo
        meta, original = c.get_dashboard(dashboard_id)
    if "write" not in meta.get("access", []):
        raise PermissionError("O documento não tem acesso de edição (access: write).")
    modified = transform(copy.deepcopy(original))
    validate_dashboard(modified)
    if original == modified:
        raise ValueError("Não houve alteração no dashboard.")
    return _register(Plan(kind="update", name=meta["name"], description=meta.get("description", ""),
        dashboard_id=dashboard_id, expected_version=str(meta["version"]),
        before=original, after=modified, created=time.monotonic()))


def _backup(document_id: str, metadata: dict, content: dict) -> str:
    folder = Path(os.environ.get("DT_BACKUP_DIR", str(ROOT / "backups"))).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if not folder.is_dir():
        raise RuntimeError("Diretório de backup inválido.")
    filename = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}.json"
    path = folder / filename
    with open(path, "x", encoding="utf-8") as stream:
        json.dump({"document_id": document_id, "metadata": metadata, "content": content}, stream, ensure_ascii=False, indent=2)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return str(path)


@mcp.tool()
def connection_status() -> dict[str, Any]:
    """Testa HTTPS, autorização e acesso ao Document Service (somente leitura)."""
    with _client() as c:
        data = c.list_dashboards(page_size=1)
        return {"ok": True, "environment": c.root, "dashboards_accessible": data.get("totalCount"),
            "auth_method": "platform_token" if c.token else "oauth_client_credentials",
            "writes_enabled_locally": os.environ.get("DT_ALLOW_WRITE") == "1"}


@mcp.tool()
def list_dashboards(page_size: int = 50, page_key: str = "") -> dict[str, Any]:
    """Lista metadados dos dashboards acessíveis ao token; não consulta Grail."""
    with _client() as c:
        return c.list_dashboards(page_size=page_size, page_key=page_key)


@mcp.tool()
def get_dashboard(dashboard_id: str) -> dict[str, Any]:
    """Lê metadata (version, access) e conteúdo JSON completo do dashboard."""
    with _client() as c:
        metadata, content = c.get_dashboard(dashboard_id)
    return {"metadata": metadata, "content": content}


@mcp.tool()
def list_dashboard_tiles(dashboard_id: str) -> dict[str, Any]:
    """Lista tiles e layouts para localizar o ID do gráfico que precisa de edição."""
    with _client() as c:
        meta, content = c.get_dashboard(dashboard_id)
    return {"dashboard_id": dashboard_id, "dashboard_name": meta.get("name"), "tiles": [
        {"tile_id": tile_id, "type": tile.get("type"), "title": tile.get("title"),
         "visualization": tile.get("visualization"), "layout": content.get("layouts", {}).get(tile_id)}
        for tile_id, tile in content.get("tiles", {}).items()]}


@mcp.tool()
def get_dashboard_tile(dashboard_id: str, tile_id: str) -> dict[str, Any]:
    """Obtém tile, visualizationSettings, querySettings e layout completos antes de editar."""
    with _client() as c:
        _, content = c.get_dashboard(dashboard_id)
    if tile_id not in content.get("tiles", {}):
        raise ValueError(f"Tile '{tile_id}' não encontrado.")
    return {"tile_id": tile_id, "tile": content["tiles"][tile_id], "layout": content["layouts"][tile_id]}


@mcp.tool()
def plan_create_dashboard(name: str, content: dict[str, Any] | None = None, description: str = "") -> dict[str, Any]:
    """Prepara criação de dashboard privado, NÃO publica. Aceita documento JSON completo ou cria vazio."""
    if not name.strip() or len(name) > 128 or len(description) > 256:
        raise ValueError("Nome obrigatório (até 128 caracteres); descrição até 256.")
    candidate = copy.deepcopy(content) if content is not None else default_dashboard()
    validate_dashboard(candidate)
    return _register(Plan(kind="create", name=name, description=description,
        dashboard_id="", expected_version="", before=None, after=candidate, created=time.monotonic()))


@mcp.tool()
def plan_add_tile(dashboard_id: str, tile: dict[str, Any], layout: dict[str, int] | None = None, tile_id: str = "") -> dict[str, Any]:
    """Prepara inclusão de tile (data/markdown/code/slo) com layout opcional; ID automático se vazio."""
    def transform(doc):
        updated, _ = add_tile(doc, tile=tile, layout=layout, tile_id=tile_id)
        return updated
    return _plan_change(dashboard_id, transform)


@mcp.tool()
def plan_patch_tile(dashboard_id: str, tile_id: str, patch: dict[str, Any], mode: str = "merge") -> dict[str, Any]:
    """Edita parcialmente um tile (query, título, querySettings, etc.) preservando outros campos."""
    if mode not in ("merge", "replace"):
        raise ValueError("mode deve ser merge ou replace.")
    def transform(doc):
        if tile_id not in doc["tiles"]:
            raise ValueError(f"Tile '{tile_id}' não encontrado.")
        doc["tiles"][tile_id] = deep_merge(doc["tiles"][tile_id], patch) if mode == "merge" else copy.deepcopy(patch)
        return doc
    return _plan_change(dashboard_id, transform)


@mcp.tool()
def plan_update_tile_visualization(dashboard_id: str, tile_id: str, visualization: str = "", settings_patch: dict[str, Any] | None = None, mode: str = "merge") -> dict[str, Any]:
    """Edita granularmente visualization e visualizationSettings (legend, axes, coloring etc.). Merge preserva os demais campos; replace limpa settings antigos."""
    return _plan_change(dashboard_id, lambda doc: patch_visualization(doc, tile_id, visualization, settings_patch, mode))


@mcp.tool()
def plan_update_tile_layout(dashboard_id: str, tile_id: str, layout_patch: dict[str, int]) -> dict[str, Any]:
    """Altera posição e tamanho de um gráfico: x, y, w, h na grade de 24 colunas."""
    def transform(doc):
        if tile_id not in doc["layouts"]:
            raise ValueError(f"Tile '{tile_id}' não encontrado.")
        doc["layouts"][tile_id] = deep_merge(doc["layouts"][tile_id], layout_patch)
        return doc
    return _plan_change(dashboard_id, transform)


@mcp.tool()
def plan_delete_tile(dashboard_id: str, tile_id: str) -> dict[str, Any]:
    """Prepara remoção de tile e layout correspondente; exige confirmação na publicação."""
    def transform(doc):
        if tile_id not in doc["tiles"]:
            raise ValueError(f"Tile '{tile_id}' não encontrado.")
        del doc["tiles"][tile_id]
        del doc["layouts"][tile_id]
        return doc
    return _plan_change(dashboard_id, transform)


@mcp.tool()
def plan_patch_dashboard_field(dashboard_id: str, json_pointer: str, value: Any = None, operation: str = "set") -> dict[str, Any]:
    """Edição avançada por JSON Pointer RFC6901 em qualquer campo (settings, variables, séries, cores etc.). Use /tiles/ID/visualizationSettings/axes/yAxis/label, por exemplo. 'remove' exclui campo."""
    return _plan_change(dashboard_id, lambda doc: pointer_update(doc, json_pointer, operation=operation, value=value))


@mcp.tool()
def plan_replace_dashboard_content(dashboard_id: str, new_content: dict[str, Any]) -> dict[str, Any]:
    """Substitui o conteúdo inteiro (metadados de nome/permissões são preservados); gere prévia e revise antes de publicar."""
    return _plan_change(dashboard_id, lambda _doc: copy.deepcopy(new_content))


@mcp.tool()
def review_change(plan_id: str) -> dict[str, Any]:
    """Exibe novamente o diff de uma mudança pendente e ID necessário para confirmação."""
    _compact_plans()
    if plan_id not in _plans:
        raise ValueError("Plano expirado ou inexistente. Gere uma nova prévia.")
    return _plan_summary(_plans[plan_id], plan_id)


@mcp.tool()
def discard_change(plan_id: str) -> dict[str, Any]:
    """Descarta uma mudança pendente sem publicar."""
    existed = _plans.pop(plan_id, None) is not None
    return {"discarded": existed, "published": False}


@mcp.tool()
def publish_change(plan_id: str, confirm: bool = False) -> dict[str, Any]:
    """PUBLICA prévia existente somente com confirm=True e DT_ALLOW_WRITE=1. Verifica versão, grava backup local e só então envia via HTTPS."""
    if not confirm:
        raise PermissionError("É obrigatório confirmar explicitamente: confirm=True.")
    if os.environ.get("DT_ALLOW_WRITE", "0") != "1":
        raise PermissionError("Escrita desabilitada. Coloque DT_ALLOW_WRITE=1 no .env e reinicie o MCP.")
    _compact_plans()
    if plan_id not in _plans:
        raise ValueError("Plano expirado ou inexistente. Gere uma nova prévia.")
    plan = _plans[plan_id]
    validate_dashboard(plan.after)
    with _client() as c:
        if plan.kind == "create":
            result = c.create_dashboard(name=plan.name, content=plan.after, description=plan.description)
            del _plans[plan_id]
            return {"status": "PUBLISHED", "operation": "create", "document": result}
        meta, latest = c.get_dashboard(plan.dashboard_id)
        if "write" not in meta.get("access", []):
            raise PermissionError("O token não tem acesso write a este documento.")
        if str(meta["version"]) != plan.expected_version or _fingerprint(latest) != _fingerprint(plan.before or {}):
            raise RuntimeError("Documento foi modificado após a prévia. Gere uma nova alteração para evitar sobrescrita.")
        backup_file = _backup(plan.dashboard_id, meta, latest)  # falha de backup bloqueia escrita
        result = c.update_content(plan.dashboard_id, plan.after, version=plan.expected_version)
    del _plans[plan_id]
    return {"status": "PUBLISHED", "operation": "update", "dashboard_id": plan.dashboard_id,
            "backup_file_local": backup_file, "document": result}


if __name__ == "__main__":
    mcp.run(transport="stdio")
