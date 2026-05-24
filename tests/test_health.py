"""根路由和健康检查测试。"""


async def test_root(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"message": "Welcome to FastAPI Project"}


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
