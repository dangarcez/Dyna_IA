"""Cliente HTTPS para Dynatrace Document Service API; sem dtctl."""
from __future__ import annotations

import json
import os
import time
from urllib.parse import quote, urlsplit

import httpx


BASE_PATH = "/platform/document/v1/documents"
MAX_UPLOAD = 15 * 1024 * 1024  # limite local conservador; API admite até 50 MB


class DynatraceError(RuntimeError):
    pass


class DynatraceDocuments:
    def __init__(self, *, url: str, token: str = "", client_id: str = "", client_secret: str = "", scopes: str = "", transport=None):
        parsed = urlsplit(url.strip().rstrip("/"))
        if parsed.scheme != "https" or not parsed.hostname or parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("DT_ENV_URL deve ser somente a URL HTTPS do ambiente, sem caminho, por exemplo https://abc.apps.dynatrace.com")
        self.root = url.strip().rstrip("/")
        self.token = token.strip()
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.scopes = scopes.strip()
        if not self.token and not (self.client_id and self.client_secret and self.scopes):
            raise ValueError("Informe DT_PLATFORM_TOKEN ou DT_OAUTH_CLIENT_ID, DT_OAUTH_CLIENT_SECRET e DT_OAUTH_SCOPES")
        self._access_token = ""
        self._expires = 0.0
        self.client = httpx.Client(timeout=30.0, follow_redirects=False, transport=transport)

    @classmethod
    def from_env(cls):
        url = os.environ.get("DT_ENV_URL", "")
        if not url:
            raise ValueError("Configure DT_ENV_URL no arquivo .env.")
        return cls(url=url, token=os.environ.get("DT_PLATFORM_TOKEN", ""), client_id=os.environ.get("DT_OAUTH_CLIENT_ID", ""), client_secret=os.environ.get("DT_OAUTH_CLIENT_SECRET", ""), scopes=os.environ.get("DT_OAUTH_SCOPES", ""))

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _bearer(self) -> str:
        if self.token:
            return self.token
        if self._access_token and time.monotonic() + 40 < self._expires:
            return self._access_token
        response = self.client.post("https://sso.dynatrace.com/sso/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": self.client_id,
            "client_secret": self.client_secret, "scope": self.scopes,
        })
        self._raise_for_status(response)
        payload = response.json()
        self._access_token = payload.get("access_token", "")
        self._expires = time.monotonic() + float(payload.get("expires_in", 300))
        if not self._access_token:
            raise DynatraceError("OAuth não retornou access_token.")
        return self._access_token

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_error or response.status_code in (301, 302, 303, 307, 308):
            if response.status_code in (401, 403):
                extra = "Verifique o token/OAuth, escopos IAM e compartilhamento do documento."
            elif response.status_code == 409:
                extra = "Conflito de versão: recrie a prévia antes de publicar."
            else:
                extra = "Confira o endereço, payload e Swagger do seu ambiente."
            msg = response.text[:400]
            for secret in (self.token, self.client_secret, self._access_token):
                if secret:
                    msg = msg.replace(secret, "[REDACTED]")
            raise DynatraceError(f"Dynatrace HTTP {response.status_code}: {extra} Detalhe: {msg}")

    def _request(self, method: str, path: str, *, params=None, data=None, files=None) -> httpx.Response:
        resp = self.client.request(method, self.root + BASE_PATH + path,
            params=params, data=data, files=files,
            headers={"Authorization": "Bearer " + self._bearer(), "Accept": "application/json"})
        self._raise_for_status(resp)
        return resp

    def list_dashboards(self, page_size: int = 50, page_key: str = "") -> dict:
        params = {"filter": "type='dashboard'", "page-size": min(1000, max(1, page_size))}
        if page_key:
            params["page-key"] = page_key
        return self._request("GET", "", params=params).json()

    def get_metadata(self, document_id: str) -> dict:
        return self._request("GET", f"/{quote(document_id, safe='')}/metadata").json()

    def get_content(self, document_id: str) -> dict:
        resp = self._request("GET", f"/{quote(document_id, safe='')}/content")
        try:
            result = resp.json()
            if not isinstance(result, dict):
                raise ValueError("Conteúdo não é objeto JSON")
            return result
        except (ValueError, json.JSONDecodeError) as exc:
            raise DynatraceError("Conteúdo retornado não é dashboard JSON. Confirme se é um documento tipo 'dashboard'.") from exc

    def get_dashboard(self, document_id: str) -> tuple[dict, dict]:
        metadata = self.get_metadata(document_id)
        if metadata.get("type") != "dashboard":
            raise DynatraceError("O documento solicitado não é do tipo 'dashboard'.")
        return metadata, self.get_content(document_id)

    @staticmethod
    def _content_part(doc: dict):
        payload = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(payload) > MAX_UPLOAD:
            raise ValueError("Documento excede o limite local de 15 MB.")
        return {"content": ("dashboard.json", payload, "application/json")}

    def create_dashboard(self, name: str, content: dict, description: str = "") -> dict:
        data = {"name": name, "type": "dashboard"}
        if description:
            data["description"] = description
        return self._request("POST", "", data=data, files=self._content_part(content)).json()

    def update_content(self, document_id: str, content: dict, version: str) -> dict:
        # O Document Service exige optimistic locking da metadata (não a versão do schema no conteúdo).
        return self._request("PUT", f"/{quote(document_id, safe='')}/content",
            params={"optimistic-locking-version": version}, files=self._content_part(content)).json()
