"""Тесты API против фейкового Keitaro (httpx.MockTransport) и временной SQLite."""
import itertools
import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app import service
from app.config import Settings, get_settings
from app.db import Base, get_db, make_engine
from app.keitaro import KeitaroClient
from app.main import app, get_client

OFFERS = [
    {"id": 101, "name": "101 Alpha [RO]", "state": "active"},
    {"id": 102, "name": "102 Beta [HU]", "state": "active"},
    {"id": 103, "name": "103 Gamma [CZ]", "state": "active"},
]


class FakeKeitaro:
    """Минимальная модель трекера: кампании, потоки, офферы."""

    def __init__(self):
        self.ids = itertools.count(1000)
        self.campaigns: dict[int, dict] = {}
        self.streams: dict[int, dict] = {}
        self.fail_stream_create = False
        self.deleted: list[int] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/admin_api/v1")
        body = json.loads(request.content) if request.content else {}
        m = request.method

        if path == "/offers" and m == "GET":
            return httpx.Response(200, json=OFFERS)
        if path == "/groups" and m == "GET":
            return httpx.Response(200, json=[{"id": 9799, "name": "VZ adrobot test"}])
        if path in ("/domains", "/traffic_sources") and m == "GET":
            return httpx.Response(403, json={"error": "You have no permission to access this page"})
        if path == "/campaigns" and m == "GET":
            return httpx.Response(200, json=list(self.campaigns.values()))
        if path == "/campaigns" and m == "POST":
            c = {"id": next(self.ids), "group": "VZ adrobot test", **body}
            self.campaigns[c["id"]] = c
            return httpx.Response(200, json=c)
        if (mt := re.fullmatch(r"/campaigns/(\d+)", path)):
            cid = int(mt[1])
            if m == "DELETE":
                self.deleted.append(cid)
                self.campaigns.pop(cid, None)
                return httpx.Response(200, json={})
            return httpx.Response(200, json=self.campaigns[cid])
        if (mt := re.fullmatch(r"/campaigns/(\d+)/streams", path)):
            cid = int(mt[1])
            return httpx.Response(200, json=[s for s in self.streams.values() if s["campaign_id"] == cid])
        if path == "/streams" and m == "POST":
            if self.fail_stream_create:
                return httpx.Response(400, json={"error": "bad stream"})
            s = {"id": next(self.ids), "filters": [], **body}
            s["offers"] = [{"offer_id": o["offer_id"], "share": o["share"], "state": o["state"]} for o in body.get("offers", [])]
            self.streams[s["id"]] = s
            return httpx.Response(200, json=s)
        if (mt := re.fullmatch(r"/streams/(\d+)", path)):
            s = self.streams[int(mt[1])]
            if m == "PUT":
                s["offers"] = body["offers"]
            return httpx.Response(200, json=s)
        if path == "/report/build":
            return httpx.Response(200, json={"rows": [{"offer_id": 101, "clicks": 7, "conversions": 1, "revenue": 2.5}]})
        return httpx.Response(404, json={"error": f"unexpected {m} {path}"})


@pytest.fixture
def fake():
    return FakeKeitaro()


@pytest.fixture
def client(fake, tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def db():
        with Session() as s:
            yield s

    settings = Settings(
        keitaro_url="https://kt.test", keitaro_api_key="k", database_url="", campaign_prefix="test_ivanov_",
        default_group_id=9799, default_domain_id=None, default_traffic_source_id=None,
        geo_redirect_url="https://google.com",
    )
    kt = KeitaroClient("https://kt.test", "k", transport=httpx.MockTransport(fake.handle))
    app.dependency_overrides = {get_db: db, get_client: lambda: kt, get_settings: lambda: settings}
    service.reset_offers_cache()
    yield TestClient(app)
    app.dependency_overrides = {}
