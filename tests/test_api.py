def create(client, **kw):
    body = {"name": "campaign1", "geo": "mx, AU", "offer_id": 101, **kw}
    return client.post("/api/campaigns", json=body)


def test_create_campaign_two_streams(client, fake):
    r = create(client)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    campaign = fake.campaigns[cid]
    assert campaign["name"] == "test_ivanov_campaign1"
    assert campaign["group_id"] == 9799
    assert campaign["alias"].startswith("test-ivanov-campaign1-")

    geo, offers = sorted((s for s in fake.streams.values() if s["campaign_id"] == cid), key=lambda s: s["position"])
    assert geo["schema"] == "redirect" and geo["action_payload"] == "https://google.com"
    assert geo["filters"] == [{"name": "country", "mode": "accept", "payload": ["MX", "AU"]}]
    assert offers["schema"] == "landings"
    assert offers["offers"] == [{"offer_id": 101, "share": 100, "state": "active"}]

    listed = client.get("/api/campaigns").json()
    assert listed[0]["created_here"] and listed[0]["geo"] == "MX,AU"


def test_create_keeps_existing_prefix(client, fake):
    r = create(client, name="test_ivanov_x")
    assert fake.campaigns[r.json()["id"]]["name"] == "test_ivanov_x"


def test_create_validation(client):
    assert create(client, geo="Mexico").status_code == 422
    assert create(client, geo=" ").status_code == 422
    assert create(client, offer_id=999).status_code == 422


def test_create_rolls_back_campaign_if_stream_fails(client, fake):
    fake.fail_stream_create = True
    r = create(client)
    assert r.status_code == 400
    assert fake.deleted and not fake.campaigns


def test_meta_survives_missing_permissions(client):
    meta = client.get("/api/meta").json()
    assert meta["groups"] == [{"id": 9799, "name": "VZ adrobot test"}]
    assert meta["domains"] == [] and "permission" in meta["errors"]["domains"]


def test_offer_search(client):
    assert [o["id"] for o in client.get("/api/offers?q=beta").json()] == [102]
    assert [o["id"] for o in client.get("/api/offers?q=103").json()] == [103]


def test_editor_add_remove_pin_push(client, fake):
    cid = create(client).json()["id"]
    view = client.get(f"/api/campaigns/{cid}").json()
    stream = next(s for s in view["streams"] if s["is_offer_stream"])
    sid = stream["id"]
    assert stream["offers"][0]["stats"]["clicks"] == 7

    # добавили два оффера → 34/33/33
    items = [{"offer_id": 101}, {"offer_id": 102}, {"offer_id": 103}]
    items = client.post("/api/rebalance", json={"items": items}).json()["items"]
    assert [i["share"] for i in items] == [34, 33, 33]

    # закрепили 102 на 50%, сняли 103 → 50/50, 103 = 0
    items[1].update(share=50, pinned=True)
    items[2]["removed"] = True
    items = client.post("/api/rebalance", json={"items": items}).json()["items"]
    assert [i["share"] for i in items] == [50, 50, 0]

    r = client.put(f"/api/streams/{sid}/offers", json={"items": items})
    assert r.status_code == 200, r.text
    assert fake.streams[sid]["offers"] == [
        {"offer_id": 101, "share": 50, "state": "active"},
        {"offer_id": 102, "share": 50, "state": "active"},
    ]
    # снятый оффер и закрепление пережили перезагрузку — из нашей БД
    offers = {o["offer_id"]: o for o in r.json()["offers"]}
    assert offers[103]["removed"] and offers[102]["pinned"]
    reloaded = next(s for s in client.get(f"/api/campaigns/{cid}").json()["streams"] if s["id"] == sid)
    assert {o["offer_id"]: o["removed"] for o in reloaded["offers"]} == {101: False, 102: False, 103: True}


def test_push_rejects_wrong_total(client, fake):
    cid = create(client).json()["id"]
    sid = next(s["id"] for s in fake.streams.values() if s["campaign_id"] == cid and s["schema"] == "landings")
    r = client.put(f"/api/streams/{sid}/offers", json={"items": [{"offer_id": 101, "share": 60}, {"offer_id": 102, "share": 50}]})
    assert r.status_code == 422 and "110" in r.json()["detail"]
    assert fake.streams[sid]["offers"] == [{"offer_id": 101, "share": 100, "state": "active"}]


def test_campaign_list_mine_filter(client, fake):
    create(client)
    fake.campaigns[1] = {"id": 1, "name": "Чужая кампания"}
    assert {c["name"] for c in client.get("/api/campaigns").json()} == {"test_ivanov_campaign1", "Чужая кампания"}
    assert [c["name"] for c in client.get("/api/campaigns?mine=true").json()] == ["test_ivanov_campaign1"]
