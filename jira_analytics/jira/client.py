"""HTTP client for Jira Cloud REST API."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from requests import Response
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = (10, 60)  # (connect, read) seconds
MAX_RETRIES = 6
INITIAL_BACKOFF = 1.0


class JiraClientError(Exception):
    """Base exception for Jira client errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class JiraAuthError(JiraClientError):
    """Authentication or authorization failure (401/403)."""


class JiraNotFoundError(JiraClientError):
    """Resource not found (404)."""


class JiraRateLimitError(JiraClientError):
    """Rate limit exceeded (429)."""


class JiraClient:
    """
    Thin HTTP client for Jira Cloud REST API.

    Responsible ONLY for HTTP communication: authentication, retries,
    timeouts, and response parsing. No business logic.
    """

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.auth = HTTPBasicAuth(email, api_token)
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()

    def __enter__(self) -> JiraClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Perform a GET request and return parsed JSON."""
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Perform a POST request and return parsed JSON."""
        return self._request("POST", path, json=json, params=params)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        backoff = INITIAL_BACKOFF

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self._session.request(
                    method,
                    url,
                    json=json,
                    params=params,
                    timeout=self.timeout,
                )
            except requests.Timeout as exc:
                logger.warning("Request timeout (attempt %d/%d): %s", attempt, self.max_retries, url)
                if attempt == self.max_retries:
                    raise JiraClientError(f"Request timed out after {self.max_retries} attempts: {url}") from exc
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            except requests.ConnectionError as exc:
                logger.warning("Connection error (attempt %d/%d): %s", attempt, self.max_retries, exc)
                if attempt == self.max_retries:
                    raise JiraClientError(f"Connection failed after {self.max_retries} attempts: {url}") from exc
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue

            if response.status_code == 429:
                wait = self._parse_retry_after(response, backoff)
                logger.warning(
                    "Rate limited (429). Waiting %.1fs before retry %d/%d",
                    wait,
                    attempt,
                    self.max_retries,
                )
                if attempt == self.max_retries:
                    raise JiraRateLimitError("Rate limit exceeded; max retries reached", status_code=429)
                time.sleep(wait)
                backoff = min(backoff * 2, 60)
                continue

            if response.status_code in (401, 403):
                raise JiraAuthError(
                    f"Authentication failed ({response.status_code}): check JIRA_EMAIL and JIRA_API_TOKEN",
                    status_code=response.status_code,
                )

            if response.status_code == 404:
                raise JiraNotFoundError(
                    f"Resource not found: {url}",
                    status_code=404,
                )

            if response.status_code >= 500:
                logger.warning(
                    "Server error %d (attempt %d/%d): %s",
                    response.status_code,
                    attempt,
                    self.max_retries,
                    url,
                )
                if attempt == self.max_retries:
                    raise JiraClientError(
                        f"Server error {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code,
                    )
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue

            if not response.ok:
                raise JiraClientError(
                    f"Request failed ({response.status_code}): {response.text[:300]}",
                    status_code=response.status_code,
                )

            if response.status_code == 204 or not response.content:
                return None

            return response.json()

        raise JiraClientError(f"Request failed after {self.max_retries} attempts: {url}")

    @staticmethod
    def _parse_retry_after(response: Response, default: float) -> float:
        """Parse Retry-After header; fall back to exponential backoff."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return default

    def verify_connection(self) -> dict[str, Any]:
        """Verify authentication by fetching the current user."""
        return self.get("/rest/api/3/myself")

    def paginate_jql_search(
        self,
        jql: str,
        *,
        fields: list[str] | None = None,
        max_results: int = 5000,
    ) -> list[dict[str, Any]]:
        """
        Paginate through Enhanced JQL Search API results.

        Uses POST /rest/api/3/search/jql with nextPageToken.
        When only IDs are requested, up to 5000 results per page are returned.
        """
        issues: list[dict[str, Any]] = []
        next_page_token: str | None = None

        while True:
            body: dict[str, Any] = {
                "jql": jql,
                "maxResults": max_results,
            }
            if fields is not None:
                body["fields"] = fields
            if next_page_token:
                body["nextPageToken"] = next_page_token

            data = self.post("/rest/api/3/search/jql", json=body)
            batch = data.get("issues", [])
            issues.extend(batch)

            next_page_token = data.get("nextPageToken")
            is_last = data.get("isLast", True)

            logger.debug("JQL search page: %d issues (total so far: %d)", len(batch), len(issues))

            if is_last or not next_page_token:
                break

        return issues

    def bulk_fetch_issues(
        self,
        issue_keys: list[str],
        *,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch up to 100 issues via bulkfetch endpoint.

        Returns successfully fetched issue objects.
        """
        body: dict[str, Any] = {
            "issueIdsOrKeys": issue_keys,
            "fieldsByKeys": False,
        }
        if fields:
            body["fields"] = fields

        data = self.post("/rest/api/3/issue/bulkfetch", json=body)
        errors = data.get("errors", [])
        if errors:
            logger.warning("Bulkfetch returned %d issue errors", len(errors))
        return data.get("issues", [])

    def get_issue_changelog(
        self,
        issue_key: str,
        *,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Fetch the complete changelog for a single issue.

        Paginates through GET /rest/api/3/issue/{key}/changelog.
        """
        histories: list[dict[str, Any]] = []
        start_at = 0

        while True:
            data = self.get(
                f"/rest/api/3/issue/{issue_key}/changelog",
                params={"startAt": start_at, "maxResults": max_results},
            )
            batch = data.get("values", [])
            histories.extend(batch)

            if data.get("isLast", True):
                break

            start_at += len(batch)
            if not batch:
                break

        return histories

    def bulk_fetch_changelogs(
        self,
        issue_keys: list[str],
        *,
        field_ids: list[str] | None = None,
        max_results: int = 1000,
    ) -> list[dict[str, Any]]:
        """
        Fetch changelogs for up to 1000 issues via bulk changelog API.

        Paginates with nextPageToken until the token is absent. The bulk endpoint
        does not return isLast — only nextPageToken.
        """
        all_changelogs: list[dict[str, Any]] = []
        next_page_token: str | None = None
        seen_tokens: set[str] = set()
        page = 0

        while True:
            page += 1
            body: dict[str, Any] = {
                "issueIdsOrKeys": issue_keys,
                "maxResults": max_results,
            }
            if field_ids:
                body["fieldIds"] = field_ids
            if next_page_token:
                body["nextPageToken"] = next_page_token

            data = self.post("/rest/api/3/changelog/bulkfetch", json=body)

            if isinstance(data, list):
                all_changelogs.extend(data)
                logger.info(
                    "Bulk changelog page %d: issueChangeLogs=%d changeHistories=%d has_nextPageToken=false",
                    page,
                    len(data),
                    0,
                )
                break

            issue_change_logs = data.get("issueChangeLogs", [])
            if issue_change_logs:
                all_changelogs.extend(issue_change_logs)
                page_histories = sum(
                    len(entry.get("changeHistories", [])) for entry in issue_change_logs
                )
                page_issues = len(issue_change_logs)
            else:
                changelogs = (
                    data.get("changelogValues")
                    or data.get("values")
                    or []
                )
                all_changelogs.extend(changelogs)
                page_histories = len(changelogs)
                page_issues = len(changelogs)

            token = data.get("nextPageToken")
            logger.info(
                "Bulk changelog page %d: issueChangeLogs=%d changeHistories=%d has_nextPageToken=%s",
                page,
                page_issues,
                page_histories,
                token is not None,
            )

            if not token:
                break

            if token in seen_tokens:
                logger.warning(
                    "Bulk changelog pagination stopped: repeated nextPageToken on page %d",
                    page,
                )
                break

            seen_tokens.add(token)
            next_page_token = token

        return all_changelogs
