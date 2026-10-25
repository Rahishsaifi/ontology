"""Read-only SuccessFactors OData client."""

from __future__ import annotations

import logging
import time
from urllib.parse import parse_qs, quote, urlparse

import httpx

from app.connector.auth import ResolvedAuth, build_provider, safe_http_message
from app.connector.odata import EntityPage, demo_matches, extract_records
from app.connector.pagination import identifier, validate_base_url, validate_next_link
from app.errors import ConnectorError, UpstreamAuthenticationError, ValidationFailed
from app.models.catalog import SchemaCatalog

logger = logging.getLogger(__name__)


def validate_select(entity, fields: list[str]) -> list[str]:
    known = set(entity.property_map())
    cleaned: list[str] = []
    for field in fields:
        identifier(field, "Field")
        if field not in known:
            raise ValidationFailed(
                f"Field '{field}' is not in the discovered metadata for {entity.qualified_name}."
            )
        if field not in cleaned:
            cleaned.append(field)
    if not cleaned:
        raise ValidationFailed("A $select list is required so the connector does not download every field.")
    return cleaned


class SuccessFactorsClient:
    """HTTP client that only issues GET requests against the configured OData host."""

    def __init__(
        self,
        auth: ResolvedAuth,
        *,
        timeout: float = 30,
        max_retries: int = 3,
        page_size: int = 100,
        tls_verify: bool = True,
        allow_insecure_http: bool = False,
        transport: httpx.BaseTransport | None = None,
        sleeper=time.sleep,
    ) -> None:
        self.auth = auth
        self.base_url = validate_base_url(auth.base_url, allow_insecure_http=allow_insecure_http)
        self.max_retries = max_retries
        self.page_size = page_size
        self._sleeper = sleeper
        self._client = httpx.Client(
            transport=transport,
            timeout=timeout,
            verify=tls_verify,
            follow_redirects=False,
        )
        self._provider = None

    def close(self) -> None:
        self._client.close()

    def _headers(self, *, accept: str) -> dict[str, str]:
        if self._provider is None:
            self._provider = build_provider(self.auth, client=self._client)
        return {"Accept": accept, **self._provider.headers()}

    def _request(self, url: str, params: dict | None, *, accept: str = "application/json") -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.get(url, params=params, headers=self._headers(accept=accept))
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise ConnectorError("The SuccessFactors request failed before a response was received.") from exc
                self._sleeper(min(8, 0.2 * (2**attempt)))
                continue
            if response.status_code in {301, 302, 303, 307, 308}:
                raise ConnectorError("SuccessFactors returned a redirect, which was not followed.")
            if response.status_code in {401, 403}:
                raise UpstreamAuthenticationError("SuccessFactors rejected the configured credentials.")
            if response.status_code == 406:
                raise ConnectorError(
                    "SuccessFactors returned 406 Not Acceptable. "
                    "$metadata must be requested as XML; entity feeds use JSON."
                )
            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= self.max_retries:
                    raise ConnectorError(safe_http_message(response))
                self._sleeper(self._retry_delay(response, attempt))
                continue
            if response.status_code >= 400:
                raise ConnectorError(safe_http_message(response))
            self._reject_html(response)
            logger.info("SuccessFactors GET completed status=%s", response.status_code)
            return response
        raise ConnectorError("The SuccessFactors request failed.") from last_error

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        header = response.headers.get("Retry-After", "")
        if header.isdigit():
            return min(int(header), 30)
        return min(8, 0.2 * (2**attempt))

    def _reject_html(self, response: httpx.Response) -> None:
        content_type = response.headers.get("content-type", "")
        start = response.text.lstrip()[:80].lower()
        if "html" in content_type.lower() or start.startswith("<!doctype html") or start.startswith("<html"):
            raise UpstreamAuthenticationError(
                "SuccessFactors returned an HTML page instead of OData. Check the service URL and credentials."
            )

    def get_metadata(self) -> bytes:
        # OData $metadata is EDMX XML. Accept: application/json causes HTTP 406 on SuccessFactors.
        response = self._request(
            f"{self.base_url}/$metadata",
            None,
            accept="application/xml",
        )
        return response.content

    def fetch_page(
        self,
        entity_set: str,
        *,
        select: list[str],
        catalog: SchemaCatalog,
        top: int | None = None,
        filter_expr: str | None = None,
        next_url: str | None = None,
    ) -> EntityPage:
        identifier(entity_set, "Entity set")
        entity = catalog.entity_for_set(entity_set)
        if entity is None:
            raise ValidationFailed(f"Entity set '{entity_set}' is not in the discovered catalog.")
        selected = validate_select(entity, select)
        page_size = max(1, min(top or self.page_size, 1000))
        if next_url:
            url = validate_next_link(next_url, self.base_url)
            params = None
        else:
            url = f"{self.base_url}/{entity_set}"
            params = {"$format": "json", "$top": str(page_size), "$select": ",".join(selected)}
            if filter_expr:
                params["$filter"] = filter_expr
        response = self._request(url, params)
        try:
            payload = response.json()
        except Exception as exc:
            raise ConnectorError("SuccessFactors did not return JSON.") from exc
        records, link = extract_records(payload)
        if link:
            link = validate_next_link(link, self.base_url)
        return EntityPage(records=records, next_url=link)


class DemoConnector:
    """Labeled synthetic source. It never opens a network connection."""

    def __init__(self, metadata_xml: bytes, records: dict[str, list[dict]], *, page_size: int = 100) -> None:
        self._metadata = metadata_xml
        self._records = records
        self.page_size = page_size
        self.base_url = "https://demo.successfactors.local/odata/v2"
        self.mode = "demo"

    def close(self) -> None:
        return None

    def get_metadata(self) -> bytes:
        return self._metadata

    def fetch_page(
        self,
        entity_set: str,
        *,
        select: list[str],
        catalog: SchemaCatalog,
        top: int | None = None,
        filter_expr: str | None = None,
        next_url: str | None = None,
    ) -> EntityPage:
        from app.connector.demo import DEMO_BASE_URL

        identifier(entity_set, "Entity set")
        entity = catalog.entity_for_set(entity_set)
        if entity is None:
            raise ValidationFailed(f"Entity set '{entity_set}' is not in the synthetic catalog.")
        selected = validate_select(entity, select)
        page_size = max(1, min(top or self.page_size, 1000))
        skip = 0
        active_filter = filter_expr
        if next_url:
            safe = validate_next_link(next_url, DEMO_BASE_URL)
            parsed = urlparse(safe)
            entity_set = identifier(parsed.path.rstrip("/").split("/")[-1], "Entity set")
            query = parse_qs(parsed.query)
            skip = int(query.get("$skip", ["0"])[0])
            page_size = int(query.get("$top", [str(page_size)])[0])
            if "$filter" in query:
                active_filter = query["$filter"][0]
            if "$select" in query:
                selected = validate_select(entity, query["$select"][0].split(","))
        rows = [row for row in self._records.get(entity_set, []) if demo_matches(row, active_filter)]
        window = rows[skip : skip + page_size]
        projected = [{field: row.get(field) for field in selected} for row in window]
        link = None
        if skip + page_size < len(rows):
            link = (
                f"{DEMO_BASE_URL}/{entity_set}?$skip={skip + page_size}&$top={page_size}"
                f"&$select={','.join(selected)}"
            )
            if active_filter:
                link += "&$filter=" + quote(active_filter, safe="")
            link = validate_next_link(link, DEMO_BASE_URL)
        return EntityPage(records=projected, next_url=link)
