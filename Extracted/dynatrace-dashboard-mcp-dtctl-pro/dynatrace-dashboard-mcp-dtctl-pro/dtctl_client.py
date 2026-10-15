"""Adaptador restrito para o binário dtctl (sem shell e sem chamadas HTTP diretas)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


class DtctlError(RuntimeError):
    pass


def resolve_binary() -> str:
    binary = os.environ.get("DTCTL_BIN", "dtctl").strip() or "dtctl"
    located = shutil.which(binary)
    if not located:
        raise DtctlError(
            f"dtctl não encontrado: {binary!r}. Informe DTCTL_BIN com o caminho absoluto "
            "no .vscode/mcp.json. No PowerShell: (Get-Command dtctl).Source"
        )
    return located


def call(args: list[str], *, timeout: int = 120, cwd: str | Path | None = None) -> str:
    """O agente não fornece argv livre; somente nossas funções chamam este adaptador."""
    command = [resolve_binary()]
    context = os.environ.get("DTCTL_CONTEXT", "").strip()
    if context:
        command += ["--context", context]
    command += ["--plain", "--no-agent", *args]
    try:
        result = subprocess.run(
            command, shell=False, check=False, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
            cwd=str(cwd) if cwd else None,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as e:
        raise DtctlError(f"dtctl excedeu o limite de {timeout} segundos") from e
    except OSError as e:
        raise DtctlError(f"Erro ao executar dtctl: {e}") from e
    if result.returncode != 0:
        error = (result.stderr or result.stdout).strip()[:3500]
        raise DtctlError(f"dtctl retornou código {result.returncode}: {error}")
    return result.stdout.strip()


def call_json(args: list[str], *, timeout: int = 120) -> Any:
    raw = call([*args, "-o", "json"], timeout=timeout)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        raise DtctlError(f"dtctl não retornou JSON válido: {raw[:400]}") from e
    # Tolera modo agent em versões/configurações inesperadas
    if isinstance(value, dict) and value.get("ok") is True and "result" in value:
        return value["result"]
    if isinstance(value, dict) and value.get("ok") is False:
        raise DtctlError(str(value.get("error", "Falha desconhecida")))
    return value


def check() -> dict[str, Any]:
    path = resolve_binary()
    version = call(["version"], timeout=20)
    return {
        "ok": True, "binary": path, "version": version[:700],
        "context": os.environ.get("DTCTL_CONTEXT") or "contexto padrão",
        "write_enabled_in_mcp": os.environ.get("DTCTL_ALLOW_WRITE") == "1",
        "auth_status": call(["auth", "status"], timeout=30)[:1500],
    }


def get_dashboards() -> Any:
    return call_json(["get", "dashboards"])


def get_dashboard(dashboard_id: str) -> dict[str, Any]:
    if not isinstance(dashboard_id, str) or not dashboard_id.strip():
        raise ValueError("dashboard_id obrigatório")
    result = call_json(["get", "dashboard", dashboard_id])
    if not isinstance(result, dict):
        raise DtctlError("Formato inesperado em dtctl get dashboard: JSON não é objeto")
    if result.get("type") != "dashboard" or not isinstance(result.get("content"), dict):
        raise DtctlError("dtctl não retornou o documento dashboard no formato id/type/content")
    if str(result.get("id")) != dashboard_id:
        raise DtctlError("ID retornado difere do ID solicitado — operação interrompida")
    return result


def query(dql: str) -> Any:
    if not isinstance(dql, str) or not dql.strip():
        raise ValueError("Query DQL não pode ser vazia")
    return call_json(["query", dql], timeout=180)


def apply_file(file_path: Path, dry_run: bool) -> str:
    args = ["apply", "-f", str(file_path), "--no-hooks"]
    if dry_run:
        args.append("--dry-run")
    return call(args, timeout=180, cwd=file_path.parent)
