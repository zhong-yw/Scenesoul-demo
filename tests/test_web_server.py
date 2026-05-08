"""Web UI API 测试"""

from unittest.mock import MagicMock

import pytest


class TestWebAPI:
    """Flask API 路由测试"""

    @pytest.fixture
    def app(self):
        from ui import web_server

        web_server.app.config.update({"TESTING": True})
        web_server.runtime = None
        web_server.conversation_log = []
        yield web_server.app
        web_server.runtime = None
        web_server.conversation_log = []

    @pytest.fixture
    def client(self, app):
        return app.test_client()

    def test_api_status_uninitialized(self, client):
        resp = client.get("/api/status")
        data = resp.get_json()
        assert data["error"] == "未初始化"

    def test_api_send_empty_message(self, client):
        resp = client.post("/api/send", json={"message": ""})
        data = resp.get_json()
        assert data["error"] == "未初始化"

    def test_api_send_missing_message(self, client):
        resp = client.post("/api/send", json={})
        data = resp.get_json()
        assert data["error"] == "未初始化"

    def test_api_send_validation_after_init(self, client):
        from ui import web_server

        mock_runtime = MagicMock()
        web_server.runtime = mock_runtime

        resp = client.post("/api/send", json={"message": ""})
        data = resp.get_json()
        assert data["error"] == "消息不能为空"

    def test_api_send_success(self, client):
        from ui import web_server

        mock_runtime = MagicMock()
        mock_runtime.handle_user_input.return_value = {
            "events": [{"type": "narrator", "content": "你走近了。"}, {"type": "brain", "content": "你好"}]
        }
        web_server.runtime = mock_runtime

        resp = client.post("/api/send", json={"message": "你好"})
        data = resp.get_json()
        assert data["status"] == "ok"
        mock_runtime.handle_user_input.assert_called_once_with("你好")

    def test_api_think_wait(self, client):
        from ui import web_server

        mock_runtime = MagicMock()
        mock_runtime.tick.return_value = {"status": "wait", "remaining": 3.2, "events": []}
        web_server.runtime = mock_runtime

        resp = client.get("/api/think")
        data = resp.get_json()
        assert data["status"] == "wait"
        assert "remaining" in data
