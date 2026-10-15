"""Planejamento, validação, diff e publicação em duas etapas com dtctl.

Sem persistência de planos; restart invalida planos, evitando aprovação obsoleta.
Não oferece garantia de atualização transacional no servidor; há pequena janela
entre a re-leitura e o dtctl apply (limite conhecido do caminho CLI).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import secrets
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import dtctl_client as cli
from dashboard_logic import (
    add_tile, deep_merge, default_dashboard, diff_json, patch_visualization,
    pointer_update, validate_dashboard,
)

ROOT = Path(__file__).resolve().parent
PLAN_TTL = 900
MAX_PLANS = 25


@dataclass
class Plan:
    kind: str
    name: str
    dashboard_id: str
    old: dict[str, Any] | None
    new: dict[str, Any]
    created: float
    operation: str
    dry_run: str


PLANS: dict[str, Plan] = {}


def _fingerprint(document: dict[str, Any]) -> str:
    payload = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _purge() -> None:
    now = time.monotonic()
    for key in list(PLANS):
        if now - PLANS[key].created > PLAN_TTL:
            del PLANS[key]


def _validate_resource(document: dict[str, Any], old: dict[str, Any] | None) -> None:
    if not isinstance(document, dict) or document.get("type") != "dashboard":
        raise ValueError("Documento deve conter type='dashboard'.")
    name = document.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Nome do dashboard não pode ser vazio.")
    if not isinstance(document.get("content"), dict):
        raise ValueError("content é obrigatório como objeto JSON.")
    validate_dashboard(document["content"])
    for tile_id, bounds in document["content"]["layouts"].items():
        if bounds["x"] + bounds["w"] > 24:
            raise ValueError(f"Tile {tile_id}: layout excede as 24 colunas (x + w).")
    if old is None:
        if document.get("id"):
            raise ValueError("Para criação, não informe ID.")
    elif document.get("id") != old.get("id"):
        raise ValueError("ID do documento não pode ser alterado.")


def _apply(document: dict[str, Any], dry_run: bool) -> str:
    # Arquivo com permissão restrita e exclusão ao sair. Sem shell/argumentos externos.
    with tempfile.TemporaryDirectory(prefix="dynatrace-mcp-") as folder:
        temp = Path(folder) / "dashboard.json"
        temp.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            temp.chmod(0o600)
        except OSError:
            pass
        return cli.apply_file(temp, dry_run)


def _summary(plan_id: str, plan: Plan) -> dict[str, Any]:
    return {
        "plan_id": plan_id, "operation": plan.operation, "kind": plan.kind,
        "dashboard_id": plan.dashboard_id or None, "dashboard_name": plan.name,
        "published": False, "expires_in_seconds": max(0, int(PLAN_TTL - (time.monotonic() - plan.created))),
        "diff": diff_json(plan.old, plan.new), "dtctl_dry_run": plan.dry_run[:5500],
        "instructions": "Revisar diff e dry-run; para publicar chame publish_change(plan_id, confirm=True). DTCTL_ALLOW_WRITE=1 é obrigatório.",
    }


def _register(plan: Plan) -> dict[str, Any]:
    _validate_resource(plan.new, plan.old)
    if plan.old == plan.new:
        raise ValueError("Nenhuma diferença detectada")
    plan.dry_run = _apply(plan.new, dry_run=True)
    _purge()
    if len(PLANS) >= MAX_PLANS:
        oldest = min(PLANS, key=lambda i: PLANS[i].created)
        del PLANS[oldest]
    plan_id = secrets.token_urlsafe(18)
    PLANS[plan_id] = plan
    return _summary(plan_id, plan)


def _update(dashboard_id: str, operation: str, transform: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    original = cli.get_dashboard(dashboard_id)
    _validate_resource(original, original)
    candidate = transform(copy.deepcopy(original))
    if not isinstance(candidate, dict):
        raise ValueError("Operação retornou documento inválido")
    # Campos gerenciados pela CLI permanecem intocados com exceção de name/content.
    unexpected = {k for k in original.keys() | candidate.keys()
                  if k not in {"content", "name", "description"} and original.get(k) != candidate.get(k)}
    if unexpected:
        raise ValueError(f"Alteração em metadados protegidos: {sorted(unexpected)}")
    return _register(Plan("update", str(original.get("name")), dashboard_id,
                          original, candidate, time.monotonic(), operation, ""))


def plan_create_dashboard(name: str, content: dict[str, Any] | None = None, description: str = "") -> dict[str, Any]:
    if not isinstance(name, str) or len(name.strip()) > 128 or not name.strip():
        raise ValueError("Informe nome de 1 a 128 caracteres")
    if len(description) > 256:
        raise ValueError("Descrição acima de 256 caracteres")
    candidate: dict[str, Any] = {"name": name.strip(), "type": "dashboard",
                                  "content": copy.deepcopy(content) if content is not None else default_dashboard()}
    if description:
        candidate["description"] = description
    return _register(Plan("create", name, "", None, candidate, time.monotonic(), "create dashboard", ""))


def plan_add_tile(dashboard_id: str, tile: dict[str, Any], layout: dict[str, int] | None = None, tile_id: str = "") -> dict[str, Any]:
    def modify(doc: dict[str, Any]) -> dict[str, Any]:
        updated, _ = add_tile(doc["content"], tile, layout, tile_id)
        doc["content"] = updated
        return doc
    return _update(dashboard_id, "add tile", modify)


def plan_upsert_tile(dashboard_id: str, tile_id: str, tile_patch: dict[str, Any], layout_patch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Cria tile se não existir (exige tile completo), atualiza parcialmente se existe."""
    if not tile_id:
        raise ValueError("tile_id obrigatório")
    def modify(doc: dict[str, Any]) -> dict[str, Any]:
        tiles = doc["content"]["tiles"]
        if tile_id in tiles:
            if "type" in tile_patch and tile_patch["type"] != tiles[tile_id].get("type"):
                raise ValueError("Trocar tipo base do tile é destrutivo; remova e crie novo")
            tiles[tile_id] = deep_merge(tiles[tile_id], tile_patch)
            if layout_patch:
                doc["content"]["layouts"][tile_id] = deep_merge(doc["content"]["layouts"][tile_id], layout_patch)
        else:
            doc["content"], _ = add_tile(doc["content"], tile_patch, layout_patch, tile_id)
        return doc
    return _update(dashboard_id, "upsert tile", modify)


def plan_patch_tile(dashboard_id: str, tile_id: str, patch: dict[str, Any], mode: str = "merge") -> dict[str, Any]:
    if mode not in {"merge", "replace"} or not isinstance(patch, dict):
        raise ValueError("mode=merge|replace e patch como objeto JSON")
    def modify(doc: dict[str, Any]) -> dict[str, Any]:
        tiles = doc["content"]["tiles"]
        if tile_id not in tiles:
            raise ValueError(f"Tile {tile_id} não encontrado")
        if mode == "merge" and "type" in patch and tiles[tile_id].get("type") != patch["type"]:
            raise ValueError("Mudança de type requer replace explícito")
        tiles[tile_id] = deep_merge(tiles[tile_id], patch) if mode == "merge" else copy.deepcopy(patch)
        return doc
    return _update(dashboard_id, "patch tile", modify)


def plan_edit_tile_dql(dashboard_id: str, tile_id: str, query: str, query_settings_patch: dict[str, Any] | None = None) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query não pode ser vazia")
    if query_settings_patch is not None and not isinstance(query_settings_patch, dict):
        raise ValueError("query_settings_patch deve ser objeto JSON")
    def modify(doc: dict[str, Any]) -> dict[str, Any]:
        tile = doc["content"]["tiles"].get(tile_id)
        if not tile or tile.get("type") != "data":
            raise ValueError("Tile de dados não encontrado")
        tile["query"] = query
        if query_settings_patch is not None:
            tile["querySettings"] = deep_merge(tile.get("querySettings", {}), query_settings_patch)
        return doc
    return _update(dashboard_id, "edit tile DQL", modify)


def plan_visualization(dashboard_id: str, tile_id: str, visualization: str = "", settings_patch: dict[str, Any] | None = None, mode: str = "merge") -> dict[str, Any]:
    if not visualization and settings_patch is None:
        raise ValueError("Informe visualization e/ou settings_patch")
    def modify(doc: dict[str, Any]) -> dict[str, Any]:
        doc["content"] = patch_visualization(doc["content"], tile_id, visualization, settings_patch, mode)
        return doc
    return _update(dashboard_id, "edit visualization", modify)


def plan_layout(dashboard_id: str, tile_id: str, patch: dict[str, int]) -> dict[str, Any]:
    if not isinstance(patch, dict) or not patch or not set(patch) <= {"x", "y", "w", "h"}:
        raise ValueError("layout_patch aceita x, y, w, h")
    def modify(doc: dict[str, Any]) -> dict[str, Any]:
        layout = doc["content"]["layouts"].get(tile_id)
        if layout is None:
            raise ValueError(f"Layout {tile_id} não encontrado")
        doc["content"]["layouts"][tile_id] = deep_merge(layout, patch)
        return doc
    return _update(dashboard_id, "edit tile layout", modify)


def plan_remove_tile(dashboard_id: str, tile_id: str) -> dict[str, Any]:
    def modify(doc: dict[str, Any]) -> dict[str, Any]:
        tiles, layouts = doc["content"]["tiles"], doc["content"]["layouts"]
        if tile_id not in tiles:
            raise ValueError("Tile não encontrado")
        del tiles[tile_id]
        del layouts[tile_id]
        return doc
    return _update(dashboard_id, "remove tile", modify)


def plan_pointer(dashboard_id: str, json_pointer: str, value: Any = None, operation: str = "set") -> dict[str, Any]:
    if not json_pointer.startswith("/") or json_pointer == "/":
        raise ValueError("Use JSON Pointer: /tiles/2/visualizationSettings/legend/showLegend")
    first = json_pointer.split("/")[1]
    if first not in {"tiles", "layouts", "variables", "settings", "annotations"}:
        raise ValueError("Somente JSON Pointers no content: tiles, layouts, variables, settings, annotations")
    def modify(doc: dict[str, Any]) -> dict[str, Any]:
        doc["content"] = pointer_update(doc["content"], json_pointer, operation=operation, value=value)
        return doc
    return _update(dashboard_id, "patch JSON pointer", modify)



def plan_batch_patches(dashboard_id: str, patches: list[dict[str, Any]]) -> dict[str, Any]:
    """Várias mudanças de JSON Pointer em um único diff/dry-run/aprovação."""
    if not isinstance(patches, list) or not 1 <= len(patches) <= 25:
        raise ValueError("Informe entre 1 e 25 patches")
    permitted = {"tiles", "layouts", "variables", "settings", "annotations"}
    for patch in patches:
        if not isinstance(patch, dict) or not isinstance(patch.get("path"), str):
            raise ValueError("Cada patch exige path string")
        if patch["path"].split("/")[1:2] == [] or not patch["path"].startswith("/"):
            raise ValueError("path deve ser JSON Pointer absoluto dentro de content")
        if patch["path"].split("/")[1] not in permitted:
            raise ValueError("Patch pode alterar somente tiles/layouts/variables/settings/annotations")
        if patch.get("operation", "set") not in {"set", "remove"}:
            raise ValueError("operation deve ser set ou remove")
        if patch.get("operation", "set") == "set" and "value" not in patch:
            raise ValueError("Patch set exige value explícito (até null)")

    def modify(doc: dict[str, Any]) -> dict[str, Any]:
        current = doc["content"]
        for patch in patches:
            current = pointer_update(current, patch["path"], operation=patch.get("operation", "set"), value=patch.get("value"))
        doc["content"] = current
        return doc
    return _update(dashboard_id, f"batch of {len(patches)} JSON pointers", modify)


def plan_settings(dashboard_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(patch, dict) or not patch:
        raise ValueError("settings patch deve ser um objeto não vazio")
    def modify(doc: dict[str, Any]) -> dict[str, Any]:
        content = doc["content"]
        content["settings"] = deep_merge(content.get("settings", {}), patch)
        return doc
    return _update(dashboard_id, "edit dashboard settings", modify)


def plan_variable(dashboard_id: str, action: str, name: str, definition: dict[str, Any] | None = None) -> dict[str, Any]:
    if action not in {"add", "replace", "remove"} or not name:
        raise ValueError("action=add|replace|remove e name obrigatório")
    if action != "remove" and (not isinstance(definition, dict) or not definition):
        raise ValueError("definition (objeto JSON completo) obrigatória")
    def modify(doc: dict[str, Any]) -> dict[str, Any]:
        variables = doc["content"]["variables"]
        indices = [i for i, v in enumerate(variables) if isinstance(v, dict) and (v.get("key") == name or v.get("name") == name)]
        if len(indices) > 1:
            raise ValueError("Variável duplicada; corrija manualmente")
        if action == "add":
            if indices:
                raise ValueError("Variável já existe")
            if definition.get("key", definition.get("name")) != name:
                raise ValueError("key/name da definição deve coincidir com name")
            variables.append(copy.deepcopy(definition))
        else:
            if not indices:
                raise ValueError("Variável não encontrada")
            if action == "remove":
                del variables[indices[0]]
            else:
                if definition.get("key", definition.get("name")) != name:
                    raise ValueError("key/name da definição deve coincidir com name")
                variables[indices[0]] = copy.deepcopy(definition)
        return doc
    return _update(dashboard_id, f"{action} variable", modify)


def plan_replace_content(dashboard_id: str, content: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(content, dict):
        raise ValueError("content precisa ser objeto JSON")
    def modify(doc: dict[str, Any]) -> dict[str, Any]:
        doc["content"] = copy.deepcopy(content)
        return doc
    return _update(dashboard_id, "replace content", modify)


def plan_rename(dashboard_id: str, name: str, description: str | None = None) -> dict[str, Any]:
    if not name.strip() or len(name) > 128:
        raise ValueError("Nome inválido")
    def modify(doc: dict[str, Any]) -> dict[str, Any]:
        doc["name"] = name.strip()
        if description is not None:
            doc["description"] = description
        return doc
    return _update(dashboard_id, "rename dashboard", modify)


def review(plan_id: str) -> dict[str, Any]:
    _purge()
    if plan_id not in PLANS:
        raise ValueError("Plano não encontrado ou expirado")
    return _summary(plan_id, PLANS[plan_id])


def discard(plan_id: str) -> dict[str, Any]:
    return {"discarded": PLANS.pop(plan_id, None) is not None, "published": False}


def _backup(doc: dict[str, Any]) -> str:
    backup_dir = Path(os.environ.get("DTCTL_BACKUP_DIR", str(ROOT / "backups"))).expanduser().resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(doc.get("id", "no-id")))[:85]
    name = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{safe_id}-{secrets.token_hex(4)}.json"
    path = backup_dir / name
    with path.open("x", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=2, ensure_ascii=False)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return str(path)


def publish(plan_id: str, confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        raise PermissionError("Publicação requer confirm=True (aprovação explícita)")
    if os.environ.get("DTCTL_ALLOW_WRITE", "0") != "1":
        raise PermissionError("Escrita bloqueada. Defina DTCTL_ALLOW_WRITE=1 e reinicie o MCP")
    _purge()
    if plan_id not in PLANS:
        raise ValueError("Plano inexistente/expirado. Prepare nova prévia")
    plan = PLANS[plan_id]
    _validate_resource(plan.new, plan.old)
    saved_backup: str | None = None
    if plan.kind == "update":
        current = cli.get_dashboard(plan.dashboard_id)
        # Protege contra mudança desde a prévia (mas dtctl apply não é operação atômica).
        if _fingerprint(current) != _fingerprint(plan.old or {}):
            raise RuntimeError("Dashboard mudou desde a prévia. Gere um novo plano; nada foi publicado")
        saved_backup = _backup(current)  # qualquer falha impede a publicação
    # revalida usando dtctl antes de aplicar
    dry_run = _apply(plan.new, dry_run=True)
    try:
        outcome = _apply(plan.new, dry_run=False)
    except Exception as e:
        raise RuntimeError(f"Falha no dtctl apply. Backup preservado em: {saved_backup or '(criação)'}; {e}") from e
    del PLANS[plan_id]
    return {
        "published": True, "kind": plan.kind, "dashboard_id": plan.dashboard_id or None,
        "backup_file": saved_backup, "dtctl_dry_run": dry_run[:3000],
        "dtctl_apply_result": outcome[:6000],
        "notice": "Apliquei o documento completo. Faça um novo get_dashboard para verificar o estado remoto.",
    }
