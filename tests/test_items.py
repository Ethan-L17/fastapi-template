"""Items CRUD 路由测试。"""

import pytest


@pytest.fixture(autouse=True)
def _reset_fake_db():
    """每个测试前后清空 items 路由的内存数据库。"""
    from app.routers.items import fake_db
    import app.routers.items as mod
    fake_db.clear()
    mod._counter = 0
    yield
    fake_db.clear()
    mod._counter = 0


async def test_list_items_empty(client):
    resp = await client.get("/api/items/")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_and_get(client):
    # 创建
    resp = await client.post("/api/items/", json={"name": "foo", "price": 1.5})
    assert resp.status_code == 201
    item = resp.json()
    assert item["name"] == "foo"
    assert item["price"] == 1.5
    assert item["id"] == 1

    # 获取
    resp = await client.get("/api/items/1")
    assert resp.status_code == 200
    assert resp.json()["name"] == "foo"


async def test_get_not_found(client):
    resp = await client.get("/api/items/999")
    assert resp.status_code == 404


async def test_list_after_create(client):
    await client.post("/api/items/", json={"name": "a", "price": 1})
    await client.post("/api/items/", json={"name": "b", "price": 2})
    resp = await client.get("/api/items/")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2


async def test_delete(client):
    await client.post("/api/items/", json={"name": "x", "price": 10})
    resp = await client.delete("/api/items/1")
    assert resp.status_code == 204

    # 确认已删除
    resp = await client.get("/api/items/1")
    assert resp.status_code == 404


async def test_delete_not_found(client):
    resp = await client.delete("/api/items/999")
    assert resp.status_code == 404
