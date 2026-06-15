"""
Session API 测试。
"""
import pytest


class TestCreateSession:
    """测试创建课堂。"""

    @pytest.mark.asyncio
    async def test_create_session_requires_auth(self, async_client):
        """未认证用户不能创建课堂。"""
        response = await async_client.post(
            "/api/v1/sessions",
            json={"title": "测试课堂", "source": "upload"},
        )
        assert response.status_code in (401, 403)


class TestSystemStatus:
    """测试系统状态接口。"""

    @pytest.mark.asyncio
    async def test_get_system_status(self, async_client):
        """GET /status 返回系统信息。"""
        response = await async_client.get("/api/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "gpu_available" in data["data"]
        assert "available_engines" in data["data"]

    @pytest.mark.asyncio
    async def test_get_engines(self, async_client):
        """GET /engines 返回引擎列表。"""
        response = await async_client.get("/api/v1/engines")
        assert response.status_code == 200
        data = response.json()
        assert "engines" in data["data"]
        assert len(data["data"]["engines"]) >= 1  # 至少 CPU 引擎可用


class TestListSessions:
    """测试课堂列表。"""

    @pytest.mark.asyncio
    async def test_list_sessions_requires_auth(self, async_client):
        """未认证用户不能获取列表。"""
        response = await async_client.get("/api/v1/sessions")
        assert response.status_code in (401, 403)


class TestSessionDetail:
    """测试课堂详情。"""

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, async_client):
        """不存在的课堂返回 401（因为未认证）或 404。"""
        response = await async_client.get("/api/v1/sessions/99999")
        assert response.status_code in (401, 403, 404)
