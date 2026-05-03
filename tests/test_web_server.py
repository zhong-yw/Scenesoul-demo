"""Web UI API 测试"""

import json
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask


# 必须在导入 web_server 之前 patch 关键依赖
@pytest.fixture(autouse=True)
def mock_all_agents():
    with patch("ui.web_server.LLMClient"), \
         patch("ui.web_server.BrainAgent"), \
         patch("ui.web_server.NarratorAgent"):
        yield


class TestWebAPI:
    """Flask API 路由测试"""

    @pytest.fixture
    def app(self):
        """创建 Flask 测试应用"""
        from ui.web_server import app
        app.config.update({"TESTING": True})
        yield app

    @pytest.fixture
    def client(self, app):
        return app.test_client()

    def test_api_status_uninitialized(self, client):
        """未初始化时返回 error"""
        resp = client.get("/api/status")
        data = resp.get_json()
        assert data["error"] == "未初始化"

    def test_api_send_empty_message(self, client):
        """空消息返回错误"""
        resp = client.post("/api/send", json={"message": ""})
        data = resp.get_json()
        assert data["error"] == "消息不能为空"

    def test_api_send_missing_message(self, client):
        """缺少 message 字段"""
        resp = client.post("/api/send", json={})
        data = resp.get_json()
        assert data["error"] == "消息不能为空"

    def test_api_think_wait(self, client):
        """思考间隔未到时返回 wait"""
        from ui.web_server import last_think_time
        import time
        last_think_time = time.time()  # 刚思考过
        resp = client.get("/api/think")
        data = resp.get_json()
        assert data["status"] == "wait"
        assert "remaining" in data
