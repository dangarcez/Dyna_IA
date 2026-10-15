"""Operações locais puras sobre documentos de dashboard Latest Dynatrace."""
from __future__ import annotations

import copy
import difflib
import json
from typing import Any


def default_dashboard() -> dict[str, Any]:
    return {"version": 21, "variables": [], "tiles": {}, "layouts": {}}


def validate_dashboard(doc: dict[str, Any]) -> None:
    """Verificação estrutural conservadora; não substitui validação Dynatrace."""
    if not isinstance(doc, dict):
        raise ValueError("O conteúdo do dashboard deve ser um objeto JSON.")
    if not isinstance(doc.get("version"), int) or isinstance(doc.get("version"), bool):
        raise ValueError("Campo 'version' deve ser número inteiro.")
    if not isinstance(doc.get("variables"), list):
        raise ValueError("Campo 'variables' deve ser lista.")
    tiles, layouts = doc.get("tiles"), doc.get("layouts")
    if not isinstance(tiles, dict) or not isinstance(layouts, dict):
        raise ValueError("Campos 'tiles' e 'layouts' devem ser objetos.")
    if set(tiles) != set(layouts):
        raise ValueError(f"IDs divergentes entre tiles/layouts: {sorted(set(tiles)^set(layouts))}")
    for tile_id, tile in tiles.items():
        if not isinstance(tile_id, str) or not isinstance(tile, dict) or not isinstance(tile.get("type"), str):
            raise ValueError(f"Tile '{tile_id}': objeto com 'type' string obrigatório.")
        if tile["type"] == "data":
            for key in ("title", "query", "visualization"):
                if not isinstance(tile.get(key), str):
                    raise ValueError(f"Tile '{tile_id}': '{key}' obrigatório como string.")
            for key in ("visualizationSettings", "querySettings"):
                if not isinstance(tile.get(key), dict):
                    raise ValueError(f"Tile '{tile_id}': '{key}' obrigatório como objeto.")
        if tile.get("timeframe") is not None and not isinstance(tile.get("timeframe"), dict):
            raise ValueError(f"Tile '{tile_id}': timeframe precisa ser objeto.")
        bounds = layouts[tile_id]
        if not isinstance(bounds, dict):
            raise ValueError(f"Layout '{tile_id}' deve ser objeto.")
        for key in ("x", "y", "w", "h"):
            n = bounds.get(key)
            if not isinstance(n, int) or isinstance(n, bool) or n < 0 or (key in ("w", "h") and n == 0):
                raise ValueError(f"Layout '{tile_id}': '{key}' deve ser inteiro positivo (x/y podem ser 0).")
    if "settings" in doc and not isinstance(doc["settings"], dict):
        raise ValueError("'settings' deve ser objeto JSON.")


def deep_merge(original: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(original, dict) or not isinstance(patch, dict):
        raise ValueError("Merge exige objetos JSON.")
    out = copy.deepcopy(original)
    for k, value in patch.items():
        if k in out and isinstance(out[k], dict) and isinstance(value, dict):
            out[k] = deep_merge(out[k], value)
        else:
            out[k] = copy.deepcopy(value)
    return out


def pointer_update(obj: dict[str, Any], path: str, *, operation: str, value: Any = None) -> dict[str, Any]:
    """RFC6901 (JSON pointer), incluindo acesso a índices de arrays."""
    if not isinstance(path, str) or not path.startswith("/") or path == "/":
        raise ValueError("Use um JSON Pointer, ex.: /tiles/2/visualizationSettings/legend/showLegend")
    if operation not in {"set", "remove"}:
        raise ValueError("operation deve ser 'set' ou 'remove'.")
    segments = [segment.replace("~1", "/").replace("~0", "~") for segment in path[1:].split("/")]
    result = copy.deepcopy(obj)
    curr: Any = result
    for key in segments[:-1]:
        if isinstance(curr, dict):
            if key not in curr:
                if operation == "remove":
                    raise ValueError(f"Caminho não existe: {path}")
                curr[key] = {}
            curr = curr[key]
        elif isinstance(curr, list):
            if not key.isdigit() or int(key) >= len(curr):
                raise ValueError(f"Índice inexistente: {key}")
            curr = curr[int(key)]
        else:
            raise ValueError(f"Não é possível navegar por {key}.")
    key = segments[-1]
    if isinstance(curr, dict):
        if operation == "remove":
            if key not in curr:
                raise ValueError(f"Propriedade inexistente: {path}")
            del curr[key]
        else:
            curr[key] = copy.deepcopy(value)
    elif isinstance(curr, list):
        if key == "-" and operation == "set":
            curr.append(copy.deepcopy(value))
        elif key.isdigit() and int(key) < len(curr):
            if operation == "remove":
                curr.pop(int(key))
            else:
                curr[int(key)] = copy.deepcopy(value)
        else:
            raise ValueError(f"Índice inválido: {key}")
    else:
        raise ValueError("Destino não é objeto nem lista.")
    return result


def add_tile(doc: dict[str, Any], tile: dict[str, Any], layout: dict[str, int] | None = None, tile_id: str = "") -> tuple[dict[str, Any], str]:
    result = copy.deepcopy(doc)
    existing = result["tiles"]
    if not tile_id:
        used = {int(k) for k in existing if k.isdigit()}
        i = 1
        while i in used:
            i += 1
        tile_id = str(i)
    if tile_id in existing:
        raise ValueError(f"Tile '{tile_id}' já existe. Use plan_patch_tile.")
    bottom = max((v.get("y", 0) + v.get("h", 0) for v in result["layouts"].values()), default=0)
    layout = layout if layout is not None else {"x": 0, "y": bottom, "w": 24, "h": 1 if tile.get("type") == "markdown" else 8}
    result["tiles"][tile_id] = copy.deepcopy(tile)
    result["layouts"][tile_id] = copy.deepcopy(layout)
    validate_dashboard(result)
    return result, tile_id


def patch_visualization(doc: dict[str, Any], tile_id: str, visualization: str = "", settings_patch: dict[str, Any] | None = None, mode: str = "merge") -> dict[str, Any]:
    result = copy.deepcopy(doc)
    tile = result["tiles"].get(tile_id)
    if tile is None:
        raise ValueError(f"Tile '{tile_id}' não encontrado.")
    if tile.get("type") not in ("data", "code"):
        raise ValueError("A visualização está disponível para tiles de dados/código.")
    if mode not in {"merge", "replace"}:
        raise ValueError("mode deve ser merge ou replace.")
    if visualization and visualization != tile.get("visualization") and mode != "replace":
        raise ValueError("Ao mudar o tipo de gráfico use mode='replace' para não herdar opções incompatíveis.")
    if visualization:
        tile["visualization"] = visualization
    if settings_patch is not None:
        if not isinstance(settings_patch, dict):
            raise ValueError("settings_patch deve ser objeto JSON.")
        tile["visualizationSettings"] = (deep_merge(tile.get("visualizationSettings", {}), settings_patch) if mode == "merge" else copy.deepcopy(settings_patch))
    elif visualization and mode == "replace":
        tile["visualizationSettings"] = {}
    validate_dashboard(result)
    return result


def diff_json(before: dict[str, Any] | None, after: dict[str, Any], max_chars: int = 16000) -> str:
    b = json.dumps(before or {}, ensure_ascii=False, sort_keys=True, indent=2).splitlines(keepends=True)
    a = json.dumps(after, ensure_ascii=False, sort_keys=True, indent=2).splitlines(keepends=True)
    text = "".join(difflib.unified_diff(b, a, fromfile="antes", tofile="depois"))
    return (text[:max_chars] + "\n... [diff truncado]") if len(text) > max_chars else text
