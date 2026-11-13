"""Тонкий клиент Keitaro Admin API v1 (заголовок Api-Key)."""
import httpx


class KeitaroError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class KeitaroClient:
    def __init__(self, base_url: str, api_key: str, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            base_url=f"{base_url}/admin_api/v1",
            headers={"Api-Key": api_key},
            timeout=20,
            transport=transport,
        )

    def _request(self, method: str, path: str, **kwargs):
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as e:
            raise KeitaroError(502, f"Keitaro недоступен: {e}") from e
        if response.status_code >= 400:
            try:
                message = response.json().get("error") or response.text
            except ValueError:
                message = response.text[:300]
            raise KeitaroError(response.status_code, message)
        return response.json()

    # --- справочники ---
    def offers(self) -> list[dict]:
        return self._request("GET", "/offers")

    def groups(self) -> list[dict]:
        return self._request("GET", "/groups", params={"type": "campaigns"})

    def domains(self) -> list[dict]:
        return self._request("GET", "/domains")

    def traffic_sources(self) -> list[dict]:
        return self._request("GET", "/traffic_sources")

    # --- кампании и потоки ---
    def campaigns(self) -> list[dict]:
        return self._request("GET", "/campaigns")

    def campaign(self, campaign_id: int) -> dict:
        return self._request("GET", f"/campaigns/{campaign_id}")

    def create_campaign(self, payload: dict) -> dict:
        return self._request("POST", "/campaigns", json=payload)

    def delete_campaign(self, campaign_id: int) -> None:
        self._request("DELETE", f"/campaigns/{campaign_id}")

    def streams(self, campaign_id: int) -> list[dict]:
        return self._request("GET", f"/campaigns/{campaign_id}/streams")

    def stream(self, stream_id: int) -> dict:
        return self._request("GET", f"/streams/{stream_id}")

    def create_stream(self, payload: dict) -> dict:
        return self._request("POST", "/streams", json=payload)

    def set_stream_offers(self, stream_id: int, offers: list[dict]) -> dict:
        """PUT заменяет список офферов потока целиком."""
        return self._request("PUT", f"/streams/{stream_id}", json={"offers": offers})

    # --- статистика ---
    def offer_stats(self, stream_id: int, interval: str = "7_days_ago") -> dict[int, dict]:
        report = self._request(
            "POST",
            "/report/build",
            json={
                "range": {"interval": interval, "timezone": "Europe/Moscow"},
                "dimensions": ["offer_id"],
                "measures": ["clicks", "conversions", "revenue"],
                "filters": [{"name": "stream_id", "operator": "EQUALS", "expression": stream_id}],
            },
        )
        return {int(row["offer_id"]): row for row in report.get("rows", []) if row.get("offer_id")}
