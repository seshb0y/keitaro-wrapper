from pydantic import BaseModel, Field


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    geo: str = Field(description="Коды стран ISO 3166-1 alpha-2 через запятую: MX,AU,RO")
    offer_id: int
    group_id: int | None = None
    domain_id: int | None = None
    traffic_source_id: int | None = None


class ShareItem(BaseModel):
    offer_id: int
    share: int = 0
    pinned: bool = False
    removed: bool = False


class SharesIn(BaseModel):
    items: list[ShareItem]
