"""Operações Dynatrace via dtctl. Somente biblioteca padrão de Python.

O wrapper nunca executa shell nem aceita comandos arbitrários do agente.
Destinado a documentos dashboard do Latest Dynatrace (não Dashboards Classic).
"""
from __future__ import annotations

import copy
import difflib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class DynatraceError(RuntimeError):
    """Erro legível para as ferramentas MCP."""


def _binary() -> str:
    configured = os.environ.get("DTCTL_BIN", "dtctl").strip() or "dtctl"
    resolved = shutil.which(configured)
    if not resolved:
        raise DynatraceError(
            f"dtctl não localizado: {configured!r}. Defina DTCTL_BIN com o caminho "
            "absoluto do executável no env do MCP (ex.: C:/.../dtctl.exe). "
            "No PowerShell use: (Get-Command dtctl).Source"
        )
    return resolved


def run_dtctl(args: list[str], *, json_output: bool = False, timeout: int = 120) -> str:
    """Executa somente dtctl, com argumentos fixos; DQL é argumento, não shell."""
    binary = _binary()
    context = os.environ.get("DTCTL_CONTEXT", "").strip()
    command = [binary]
    if context:
        command += ["--context", context]
    command += args
    if json_output:
        command += ["-o", "json"]
    command += ["--plain"]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise DynatraceError(f"dtctl excedeu o tempo limite de {timeout}s.") from exc
    except OSError as exc:
        raise DynatraceError(f"Não foi possível executar o dtctl: {exc}") from exc
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout).strip()
        raise DynatraceError(f"dtctl falhou (código {completed.returncode}): {message[:5000]}")
    return completed.stdout.strip()


def _json_command(args: list[str]) -> Any:
    output = run_dtctl(args, json_output=True)
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise DynatraceError(
            "O dtctl não retornou JSON puro. Confira versão/configuração do dtctl "
            "e use -o json --plain (sem --agent). Saída inicial: " + output[:450]
        ) from exc


def check_connection() -> dict[str, Any]:
    """Checa acesso local ao binário e autenticação do contexto atual."""
    exe = _binary()
    version = run_dtctl(["version"])
    doctor = run_dtctl(["doctor"], timeout=60)
    return {"dtctl_path": exe, "version": version, "context": os.getenv("DTCTL_CONTEXT", "(padrão)"), "doctor": doctor}


def list_dashboards() -> Any:
    return _json_command(["get", "dashboards"])


def get_dashboard(dashboard_id: str) -> dict[str, Any]:
    if not dashboard_id.strip():
        raise DynatraceError("dashboard_id obrigatório.")
    document = _json_command(["get", "dashboard", dashboard_id])
    _check_document(document, expected_id=dashboard_id)
    return document


def _check_document(doc: Any, *, expected_id: str | None = None) -> dict[str, Any]:
    if not isinstance(doc, dict):
        raise DynatraceError("Documento inesperado: dtctl não retornou um objeto JSON.")
    if doc.get("type") != "dashboard":
        raise DynatraceError("O documento retornado não é do tipo dashboard do Latest Dynatrace.")
    content = doc.get("content")
    if not isinstance(content, dict):
        raise DynatraceError("Documento sem content (estrutura de dashboard inválida).")
    if not isinstance(content.get("variables"), list) or not isinstance(content.get("tiles"), dict) or not isinstance(content.get("layouts"), dict):
        raise DynatraceError("content precisa conter variables:[], tiles:{} e layouts:{}.")
    if not isinstance(content.get("version"), int):
        raise DynatraceError("content.version precisa ser numérico (ex.: 21).")
    if set(content["tiles"]) != set(content["layouts"]):
        raise DynatraceError("Os IDs de content.tiles e content.layouts devem corresponder.")
    if expected_id is not None:
        if str(doc.get("id", "")) != str(expected_id):
            raise DynatraceError("ID retornado é diferente do ID solicitado. Atualização cancelada.")
    return doc


def list_dashboard_tiles(dashboard_id: str) -> dict[str, Any]:
    document = get_dashboard(dashboard_id)
    tiles = document["content"]["tiles"]
    layout = document["content"]["layouts"]
    return {
        "dashboard_id": dashboard_id,
        "name": document.get("name"),
        "tiles": [
            {
                "tile_id": tid,
                "type": tile.get("type"),
                "title": tile.get("title"),
                "query": tile.get("query"),
                "visualization": tile.get("visualization"),
                "visualizationSettings": tile.get("visualizationSettings", {}),
                "querySettings": tile.get("querySettings", {}),
                "layout": layout.get(tid),
            }
            for tid, tile in tiles.items()
        ],
    }


def run_dql(dql: str) -> Any:
    if not dql.strip():
        raise DynatraceError("DQL vazia.")
    return _json_command(["query", dql])


def _merge(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Merge recursivo de objetos; listas e escalares são substituídos."""
    result = copy.deepcopy(target)
    for key, value in patch.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _grid_columns(content: dict[str, Any]) -> int:
    settings = content.get("settings", {})
    if not isinstance(settings, dict):
        return 24
    grid = settings.get("gridLayout", {})
    if not isinstance(grid, dict):
        return 24
    return int(grid.get("columnsCount", 24))


def _valid_layout(layout: dict[str, Any], columns: int) -> None:
    if not isinstance(layout, dict):
        raise DynatraceError("layout precisa ser um objeto JSON.")
    for key in ("x", "y", "w", "h"):
        if key not in layout or type(layout[key]) is not int:
            raise DynatraceError(f"layout.{key} precisa ser inteiro.")
    if layout["x"] < 0 or layout["y"] < 0 or layout["w"] < 1 or layout["h"] < 1:
        raise DynatraceError("layout precisa ter x/y >= 0 e w/h >= 1.")
    if layout["x"] + layout["w"] > columns:
        raise DynatraceError(f"layout excede as {columns} colunas do dashboard.")


def _diff(before: dict[str, Any] | None, after: dict[str, Any]) -> str:
    old = json.dumps(before, ensure_ascii=False, sort_keys=True, indent=2).splitlines() if before else []
    new = json.dumps(after, ensure_ascii=False, sort_keys=True, indent=2).splitlines()
    diff = "\n".join(difflib.unified_diff(old, new, fromfile="atual", tofile="proposto", lineterm=""))
    if len(diff) > 16000:
        return diff[:16000] + "\n... diff truncado. Obtenha documento via get_dashboard."
    return diff


def _backup(old: dict[str, Any]) -> str:
    target_dir = Path(os.getenv("DTCTL_BACKUP_DIR", str(Path(__file__).parent / "backups"))).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(old["id"]))[:90]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = target_dir / f"dashboard-{safe_id}-{timestamp}-{uuid4().hex[:8]}.json"
    with target.open("x", encoding="utf-8") as file:
        os.chmod(target, 0o600)
        json.dump(old, file, indent=2, ensure_ascii=False)
    return str(target)


def _apply_document(new_doc: dict[str, Any], *, old_doc: dict[str, Any] | None, confirm: bool) -> dict[str, Any]:
    _check_document(new_doc, expected_id=str(old_doc["id"]) if old_doc else None)
    if old_doc is None and "id" in new_doc:
        raise DynatraceError("Nunca defina manualmente id no dashboard novo.")
    if old_doc is not None and "id" not in new_doc:
        raise DynatraceError("id removido do dashboard em atualização, operação cancelada.")
    diff = _diff(old_doc, new_doc)
    with tempfile.TemporaryDirectory(prefix="dt-mcp-") as tmpdir:
        source = Path(tmpdir) / "dashboard.json"
        source.write_text(json.dumps(new_doc, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(source, 0o600)
        preview = run_dtctl(["apply", "-f", str(source), "--dry-run"], timeout=180)
        response: dict[str, Any] = {
            "status": "PREVIA_SEM_PUBLICAR", "dashboard_id": new_doc.get("id"),
            "dry_run": preview, "diff": diff,
            "informacao": "Revise o diff; para publicar use confirm=true e DTCTL_ALLOW_WRITE=1.",
        }
        if not confirm:
            return response
        if os.getenv("DTCTL_ALLOW_WRITE", "0").lower() not in {"1", "true", "yes"}:
            response["status"] = "BLOQUEADO_SEM_PERMISSAO_DE_ESCRITA"
            return response
        backup = _backup(old_doc) if old_doc is not None else None
        try:
            published = run_dtctl(["apply", "-f", str(source)], timeout=180)
        except Exception as exc:
            raise DynatraceError(f"Falha ao publicar; backup anterior: {backup or '(novo documento)'}; erro: {exc}") from exc
        return {"status": "PUBLICADO", "resultado": published, "backup": backup, "dashboard_id": new_doc.get("id"), "diff": diff}


def create_dashboard(name: str, content: dict[str, Any] | None = None, confirm: bool = False) -> dict[str, Any]:
    if not name.strip():
        raise DynatraceError("name é obrigatório.")
    if content is None:
        content = {
            "version": 21, "variables": [],
            "tiles": {"1": {"type": "markdown", "content": "# " + name}},
            "layouts": {"1": {"x": 0, "y": 0, "w": 24, "h": 2}},
        }
    doc = {"name": name, "type": "dashboard", "content": copy.deepcopy(content)}
    return _apply_document(doc, old_doc=None, confirm=confirm)


def upsert_dashboard_tile(
    dashboard_id: str, kind: str = "data", tile_id: str | None = None,
    title: str | None = None, query: str | None = None,
    visualization: str | None = None,
    visualization_settings: dict[str, Any] | None = None,
    query_settings: dict[str, Any] | None = None,
    markdown: str | None = None,
    layout: dict[str, Any] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    if kind not in {"data", "markdown"}:
        raise DynatraceError("kind deve ser data ou markdown.")
    old = get_dashboard(dashboard_id)
    doc = copy.deepcopy(old)
    content = doc["content"]
    tiles = content["tiles"]
    layouts = content["layouts"]
    if tile_id is None:
        numeric = [int(k) for k in tiles if k.isdigit()]
        tile_id = str(max(numeric, default=0) + 1)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", tile_id):
        raise DynatraceError("tile_id só admite letras, números, _ e -.")
    existing = tiles.get(tile_id)
    if existing and existing.get("type") != kind:
        raise DynatraceError("Não altere kind de tile existente. Escolha outro tile_id.")
    if existing and kind == "data" and visualization is not None and visualization != existing.get("visualization"):
        raise DynatraceError("Para trocar o tipo de gráfico de um tile existente, use update_tile_visualization com mode='replace'.")
    if kind == "markdown":
        value = markdown if markdown is not None else (existing or {}).get("content")
        if not isinstance(value, str):
            raise DynatraceError("Informe markdown para um tile novo.")
        new_tile = {**copy.deepcopy(existing or {}), "type": "markdown", "content": value}
    else:
        new_tile = copy.deepcopy(existing or {})
        new_tile["type"] = "data"
        for key, value in (("title", title), ("query", query), ("visualization", visualization)):
            if value is not None:
                new_tile[key] = value
        if not all(isinstance(new_tile.get(k), str) and new_tile[k].strip() for k in ("title", "query", "visualization")):
            raise DynatraceError("Tiles data precisam de title, query e visualization.")
        new_tile.setdefault("visualizationSettings", {})
        new_tile.setdefault("querySettings", {})
        if visualization_settings is not None:
            new_tile["visualizationSettings"] = _merge(new_tile["visualizationSettings"], visualization_settings)
        if query_settings is not None:
            new_tile["querySettings"] = _merge(new_tile["querySettings"], query_settings)
    if tile_id not in layouts:
        bottom = max((int(l.get("y", 0)) + int(l.get("h", 0)) for l in layouts.values()), default=0)
        default_layout = {"x": 0, "y": bottom, "w": _grid_columns(content), "h": 2 if kind == "markdown" else 8}
    else:
        default_layout = layouts[tile_id]
    new_layout = _merge(default_layout, layout or {})
    _valid_layout(new_layout, _grid_columns(content))
    tiles[tile_id] = new_tile
    layouts[tile_id] = new_layout
    result = _apply_document(doc, old_doc=old, confirm=confirm)
    result["tile_id"] = tile_id
    return result


def update_tile_visualization(
    dashboard_id: str, tile_id: str,
    visualization: str | None = None,
    settings_patch: dict[str, Any] | None = None,
    mode: str = "merge", title: str | None = None,
    query_settings_patch: dict[str, Any] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Altera visualização e seu JSON em um tile existente, mantendo demais dados.

    mode=merge: merge profundo de visualizationSettings (listas substituídas).
    mode=replace: substitui visualizationSettings completamente.
    """
    if mode not in {"merge", "replace"}:
        raise DynatraceError("mode deve ser 'merge' ou 'replace'.")
    if visualization is None and settings_patch is None and title is None and query_settings_patch is None:
        raise DynatraceError("Informe pelo menos uma alteração.")
    old = get_dashboard(dashboard_id)
    doc = copy.deepcopy(old)
    tile = doc["content"]["tiles"].get(tile_id)
    if tile is None:
        raise DynatraceError(f"Tile {tile_id!r} não encontrado; use list_dashboard_tiles.")
    if tile.get("type") not in {"data", "code"}:
        raise DynatraceError("Somente tiles data ou code possuem visualizações configuráveis.")
    current_viz = tile.get("visualization")
    if visualization is not None:
        if not visualization.strip():
            raise DynatraceError("visualization não pode estar vazia.")
        if visualization != current_viz and mode != "replace":
            raise DynatraceError("Mudança de tipo de gráfico requer mode='replace' para não manter configurações incompatíveis.")
        tile["visualization"] = visualization
    if settings_patch is not None:
        if not isinstance(settings_patch, dict):
            raise DynatraceError("settings_patch deve ser um objeto JSON.")
        current = tile.get("visualizationSettings", {})
        if not isinstance(current, dict):
            raise DynatraceError("visualizationSettings existente não é objeto JSON.")
        tile["visualizationSettings"] = (_merge(current, settings_patch) if mode == "merge" else copy.deepcopy(settings_patch))
    elif mode == "replace":
        tile["visualizationSettings"] = {}
    if title is not None:
        if not title.strip():
            raise DynatraceError("title não pode estar vazio.")
        tile["title"] = title
    if query_settings_patch is not None:
        if not isinstance(query_settings_patch, dict):
            raise DynatraceError("query_settings_patch deve ser objeto JSON.")
        tile["querySettings"] = _merge(tile.get("querySettings", {}), query_settings_patch)
    result = _apply_document(doc, old_doc=old, confirm=confirm)
    result["tile_id"] = tile_id
    result["visualization"] = tile.get("visualization")
    result["visualizationSettings"] = tile.get("visualizationSettings", {})
    return result
