"""GraphQL client for Twenty CRM API."""

import os

import httpx


class TwentyAPIError(Exception):
    """Base error for Twenty API interactions."""


class TwentyConnectionError(TwentyAPIError):
    """Cannot reach the Twenty server."""


class TwentyAuthError(TwentyAPIError):
    """Authentication failed (invalid or missing API key)."""


class TwentyQueryError(TwentyAPIError):
    """GraphQL query returned errors."""

    def __init__(self, errors: list[dict], query: str = ""):
        self.errors = errors
        self.query = query
        messages = "; ".join(e.get("message", str(e)) for e in errors)
        super().__init__(f"GraphQL errors: {messages}")


class TwentyClient:
    """Thin wrapper around httpx for Twenty CRM's GraphQL API."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.environ.get("TWENTY_API_URL", "http://localhost:3000")).rstrip("/")
        self.api_key = api_key or os.environ.get("TWENTY_API_KEY", "")
        self._http = httpx.Client(
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
        )

    def _post(self, url: str, payload: dict) -> dict:
        """Send a POST request and return parsed JSON."""
        try:
            resp = self._http.post(url, json=payload)
        except httpx.ConnectError as exc:
            raise TwentyConnectionError(f"Cannot reach Twenty at {self.base_url}: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise TwentyConnectionError(f"Timeout connecting to Twenty at {self.base_url}: {exc}") from exc

        if resp.status_code == 401:
            raise TwentyAuthError("Invalid or missing Twenty API key")
        if resp.status_code == 403:
            raise TwentyAuthError("Forbidden — check your Twenty API key permissions")
        resp.raise_for_status()
        return resp.json()

    def query(self, query_str: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL query against the data API."""
        payload: dict = {"query": query_str}
        if variables:
            payload["variables"] = variables
        data = self._post(f"{self.base_url}/api", payload)
        if "errors" in data:
            raise TwentyQueryError(data["errors"], query_str)
        return data.get("data", {})

    def mutate(self, mutation_str: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL mutation against the data API."""
        return self.query(mutation_str, variables)

    def paginate(self, query_str: str, variables: dict | None, connection_path: str) -> list[dict]:
        """Iterate all pages of a Relay cursor connection.

        Args:
            query_str: A GraphQL query with an $after variable for cursor pagination.
            variables: Initial variables dict (will have 'after' injected).
            connection_path: Dot-separated path to the connection field in the response
                             (e.g. "people" for data.people.edges).
        """
        results: list[dict] = []
        vars_ = dict(variables or {})

        while True:
            data = self.query(query_str, vars_)
            connection = data
            for key in connection_path.split("."):
                connection = connection[key]

            edges = connection.get("edges", [])
            results.extend(edge["node"] for edge in edges)

            page_info = connection.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            vars_["after"] = page_info["endCursor"]

        return results

    def metadata_query(self, query_str: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL query against the metadata API."""
        payload: dict = {"query": query_str}
        if variables:
            payload["variables"] = variables
        data = self._post(f"{self.base_url}/metadata", payload)
        if "errors" in data:
            raise TwentyQueryError(data["errors"], query_str)
        return data.get("data", {})

    def health_check(self) -> bool:
        """Verify the API is reachable and authenticated."""
        try:
            self.query("{ currentWorkspace { id } }")
            return True
        except TwentyAPIError:
            return False
