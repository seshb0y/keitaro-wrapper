"""FastAPI-приложение: страницы и JSON API обёртки над Keitaro."""
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import service
from app.config import Settings, get_settings
from app.db import get_db
from app.keitaro import KeitaroClient, KeitaroError
from app.models import CampaignRecord
from app.schemas import CampaignCreate, SharesIn
from app.shares import ShareError

BASE = Path(__file__).parent
app = FastAPI(title="Keitaro wrapper")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


@lru_cache
def get_client() -> KeitaroClient:
    s = get_settings()
    return KeitaroClient(s.keitaro_url, s.keitaro_api_key)


@app.exception_handler(KeitaroError)
def keitaro_error(_: Request, e: KeitaroError):
    # 4xx Keitaro (нет прав, не найдено) отдаём как есть, остальное — 502
    status = e.status if 400 <= e.status < 500 else 502
    return JSONResponse({"detail": f"Keitaro: {e.message}"}, status_code=status)


@app.exception_handler(ShareError)
@app.exception_handler(service.InputError)
def input_error(_: Request, e: ValueError):
    return JSONResponse({"detail": str(e)}, status_code=422)


# --- страницы ---
@app.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
def campaign_page(request: Request, campaign_id: int):
    return templates.TemplateResponse(request, "campaign.html", {"campaign_id": campaign_id})


# --- API ---
def _optional(fetch) -> tuple[list[dict], str | None]:
    """Справочник, к которому у ключа может не быть прав: не роняем форму."""
    try:
        return fetch(), None
    except KeitaroError as e:
        return [], e.message


@app.get("/api/meta")
def meta(client: KeitaroClient = Depends(get_client), settings: Settings = Depends(get_settings)):
    groups, groups_err = _optional(client.groups)
    domains, domains_err = _optional(client.domains)
    sources, sources_err = _optional(client.traffic_sources)
    return {
        "prefix": settings.campaign_prefix,
        "defaults": {
            "group_id": settings.default_group_id,
            "domain_id": settings.default_domain_id,
            "traffic_source_id": settings.default_traffic_source_id,
        },
        "groups": [{"id": g["id"], "name": g["name"]} for g in groups],
        "domains": [{"id": d["id"], "name": d["name"]} for d in domains],
        "traffic_sources": [{"id": t["id"], "name": t["name"]} for t in sources],
        "errors": {"groups": groups_err, "domains": domains_err, "traffic_sources": sources_err},
    }


@app.get("/api/offers")
def offers(q: str = "", limit: int = 20, client: KeitaroClient = Depends(get_client)):
    return service.search_offers(client, q, min(limit, 100))


@app.get("/api/campaigns")
def campaigns(
    mine: bool = False,
    client: KeitaroClient = Depends(get_client),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """mine=true — только кампании с нашим префиксом (аккаунт Keitaro общий с другими)."""
    ours = {r.keitaro_id: r for r in db.scalars(select(CampaignRecord))}
    result = []
    for c in sorted(client.campaigns(), key=lambda c: -c["id"]):
        if mine and not c["name"].startswith(settings.campaign_prefix):
            continue
        record = ours.get(c["id"])
        result.append({
            "id": c["id"],
            "name": c["name"],
            "group": c.get("group"),
            "created_here": record is not None,
            "geo": record.geo if record else None,
        })
    return result


@app.post("/api/campaigns", status_code=201)
def create_campaign(
    data: CampaignCreate,
    client: KeitaroClient = Depends(get_client),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    record = service.create_campaign(data, client, db, settings)
    return {"id": record.keitaro_id, "name": record.name, "url": f"/campaigns/{record.keitaro_id}"}


@app.get("/api/campaigns/{campaign_id}")
def campaign(
    campaign_id: int,
    client: KeitaroClient = Depends(get_client),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return service.campaign_view(campaign_id, client, db, settings)


@app.post("/api/rebalance")
def rebalance(data: SharesIn):
    """Черновой пересчёт долей, в Keitaro ничего не отправляет."""
    return {"items": service.preview(data.items)}


@app.put("/api/streams/{stream_id}/offers")
def push_offers(
    stream_id: int,
    data: SharesIn,
    client: KeitaroClient = Depends(get_client),
    db: Session = Depends(get_db),
):
    return service.push_offers(stream_id, data.items, client, db)
