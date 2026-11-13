"""Бизнес-логика: создание кампании и редактор офферов потока."""
import re
import secrets
import time

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import shares
from app.config import Settings
from app.keitaro import KeitaroClient, KeitaroError
from app.models import CampaignRecord, PushLog, StreamOfferState
from app.schemas import CampaignCreate, ShareItem

GEO_RE = re.compile(r"^[A-Z]{2}$")


class InputError(ValueError):
    pass


# --- офферы: кэш на минуту, их ~200 и меняются редко ---
_offers_cache: tuple[float, list[dict]] = (0.0, [])


def all_offers(client: KeitaroClient, ttl: float = 60) -> list[dict]:
    global _offers_cache
    fetched_at, offers = _offers_cache
    if not offers or time.monotonic() - fetched_at > ttl:
        offers = [o for o in client.offers() if o.get("state") != "deleted"]
        _offers_cache = (time.monotonic(), offers)
    return offers


def reset_offers_cache() -> None:
    global _offers_cache
    _offers_cache = (0.0, [])


def search_offers(client: KeitaroClient, query: str, limit: int = 20) -> list[dict]:
    q = query.strip().lower()
    found = [
        {"id": o["id"], "name": o["name"], "state": o.get("state")}
        for o in all_offers(client)
        if not q or q in o["name"].lower() or q == str(o["id"])
    ]
    return found[:limit]


def offer_names(client: KeitaroClient) -> dict[int, str]:
    return {o["id"]: o["name"] for o in all_offers(client)}


# --- создание кампании ---
def parse_geo(raw: str) -> list[str]:
    codes = [c.strip().upper() for c in re.split(r"[,\s;]+", raw) if c.strip()]
    if not codes:
        raise InputError("Укажите хотя бы одну страну: MX, AU, RO…")
    bad = [c for c in codes if not GEO_RE.match(c)]
    if bad:
        raise InputError(f"Не похоже на код страны: {', '.join(bad)}. Нужны двухбуквенные коды ISO")
    return list(dict.fromkeys(codes))  # без повторов, порядок сохранён


def make_name(raw: str, prefix: str) -> str:
    name = raw.strip()
    return name if name.startswith(prefix) else prefix + name


def make_alias(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "campaign"
    return f"{slug}-{secrets.token_hex(3)}"  # alias уникален в трекере


def create_campaign(data: CampaignCreate, client: KeitaroClient, db: Session, settings: Settings) -> CampaignRecord:
    geo = parse_geo(data.geo)
    name = make_name(data.name, settings.campaign_prefix)
    if data.offer_id not in offer_names(client):
        raise InputError(f"Оффер {data.offer_id} не найден в Keitaro")

    group_id = data.group_id or settings.default_group_id
    domain_id = data.domain_id or settings.default_domain_id
    source_id = data.traffic_source_id or settings.default_traffic_source_id

    payload = {"name": name, "alias": make_alias(name), "type": "position", "state": "active"}
    for key, value in (("group_id", group_id), ("domain_id", domain_id), ("traffic_source_id", source_id)):
        if value:
            payload[key] = value
    campaign = client.create_campaign(payload)

    try:
        geo_stream = client.create_stream({
            "campaign_id": campaign["id"],
            "type": "regular",
            "name": f"{','.join(geo)} -> Google",
            "position": 1,
            "schema": "redirect",
            "action_type": "http",
            "action_payload": settings.geo_redirect_url,
            "collect_clicks": True,
            "filters": [{"name": "country", "mode": "accept", "payload": geo}],
        })
        offer_stream = client.create_stream({
            "campaign_id": campaign["id"],
            "type": "regular",
            "name": "Offers",
            "position": 2,
            "schema": "landings",
            "action_type": "http",
            "collect_clicks": True,
            "offers": [{"offer_id": data.offer_id, "share": 100, "state": "active"}],
        })
    except KeitaroError:
        # не оставляем в трекере полусобранную кампанию без потоков
        client.delete_campaign(campaign["id"])
        raise

    record = CampaignRecord(
        keitaro_id=campaign["id"], name=name, alias=campaign["alias"], geo=",".join(geo),
        offer_id=data.offer_id, group_id=group_id, domain_id=domain_id, traffic_source_id=source_id,
        geo_stream_id=geo_stream["id"], offer_stream_id=offer_stream["id"],
    )
    db.add(record)
    db.commit()
    return record


# --- редактор ---
def _states(db: Session, stream_id: int) -> dict[int, StreamOfferState]:
    rows = db.scalars(select(StreamOfferState).where(StreamOfferState.stream_id == stream_id))
    return {r.offer_id: r for r in rows}


def stream_view(stream: dict, client: KeitaroClient, db: Session, names: dict[int, str]) -> dict:
    view = {
        "id": stream["id"],
        "name": stream["name"],
        "position": stream["position"],
        "schema": stream["schema"],
        "action_payload": stream.get("action_payload"),
        "filters": [
            {"name": f["name"], "mode": f["mode"], "payload": f.get("payload")}
            for f in stream.get("filters", [])
        ],
        "is_offer_stream": stream["schema"] == "landings" or bool(stream.get("offers")),
        "offers": [],
    }
    if not view["is_offer_stream"]:
        return view

    states = _states(db, stream["id"])
    try:
        stats = client.offer_stats(stream["id"])
    except KeitaroError:
        stats = {}

    active, removed, seen = [], [], set()
    for o in stream.get("offers", []):
        state = states.get(o["offer_id"])
        is_removed = o.get("state") != "active"
        item = {
            "offer_id": o["offer_id"],
            "share": 0 if is_removed else o["share"],
            "pinned": bool(state and state.pinned) and not is_removed,
            "removed": is_removed,
        }
        (removed if is_removed else active).append(item)
        seen.add(o["offer_id"])
    # снятые через обёртку: в Keitaro их уже нет, держим для «Bring back»
    for offer_id, state in states.items():
        if state.removed and offer_id not in seen:
            removed.append({"offer_id": offer_id, "share": 0, "pinned": False, "removed": True})

    active.sort(key=lambda i: -i["share"])  # sort стабильный: при равных долях порядок Keitaro
    for item in active + removed:
        item["name"] = names.get(item["offer_id"], f"Оффер {item['offer_id']} (нет доступа)")
        row = stats.get(item["offer_id"], {})
        item["stats"] = {k: row.get(k, 0) for k in ("clicks", "conversions", "revenue")}
        view["offers"].append(item)
    return view


def campaign_view(campaign_id: int, client: KeitaroClient, db: Session, settings: Settings) -> dict:
    campaign = client.campaign(campaign_id)
    names = offer_names(client)
    streams = sorted(client.streams(campaign_id), key=lambda s: s["position"])
    return {
        "campaign": {
            "id": campaign["id"],
            "name": campaign["name"],
            "alias": campaign["alias"],
            "group_id": campaign.get("group_id"),
            "domain_id": campaign.get("domain_id"),
            "traffic_source_id": campaign.get("traffic_source_id"),
            "keitaro_url": f"{settings.keitaro_url}/admin/#!/campaign/{campaign['id']}/main",
        },
        "streams": [stream_view(s, client, db, names) for s in streams],
    }


def preview(items: list[ShareItem]) -> list[dict]:
    result = shares.rebalance([shares.Item(**i.model_dump()) for i in items])
    return [vars(i) for i in result]


def push_offers(stream_id: int, items: list[ShareItem], client: KeitaroClient, db: Session) -> dict:
    parsed = [shares.Item(**i.model_dump()) for i in items]
    shares.validate(parsed)

    before = client.stream(stream_id).get("offers", [])
    payload = [{"offer_id": i.offer_id, "share": i.share, "state": "active"} for i in parsed if not i.removed]
    updated = client.set_stream_offers(stream_id, payload)

    db.execute(delete(StreamOfferState).where(StreamOfferState.stream_id == stream_id))
    for i in parsed:
        if i.pinned or i.removed:
            db.add(StreamOfferState(stream_id=stream_id, offer_id=i.offer_id, pinned=i.pinned, removed=i.removed))
    db.add(PushLog(
        stream_id=stream_id,
        before=[{"offer_id": o["offer_id"], "share": o["share"], "state": o.get("state")} for o in before],
        after=payload,
    ))
    db.commit()
    return stream_view(updated, client, db, offer_names(client))
