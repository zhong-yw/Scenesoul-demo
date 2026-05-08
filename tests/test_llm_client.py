"""LLM 客户端测试"""

from unittest.mock import patch, MagicMock

import pytest
from llm_client import LLMClient


class TestInit:
    """构造函数测试"""

    @patch("llm_client.os.getenv")
    def test_reads_env_vars(self, mock_getenv):
        mock_getenv.side_effect = lambda key, default=None: {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_BASE_URL": "https://test.url/v1",
            "OPENAI_MODEL": "test-model"
        }.get(key, default)
        with patch("llm_client.OpenAI") as mock_openai:
            client = LLMClient()
            mock_openai.assert_called_once_with(api_key="test-key", base_url="https://test.url/v1")
            assert client.model == "test-model"

    @patch("llm_client.os.getenv")
    def test_explicit_params_override_env(self, mock_getenv):
        with patch("llm_client.OpenAI"):
            client = LLMClient(api_key="explicit", base_url="https://explicit/v1", model="explicit-model")
            assert client.api_key == "explicit"
            assert client.model == "explicit-model"


class TestChat:
    """chat 方法测试"""

    @patch("llm_client.OpenAI")
    def test_success(self, mock_openai_class):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "test reply"
        mock_response.model = "test-model"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        client = LLMClient(api_key="key", base_url="url", model="m")
        result = client.chat([{"role": "user", "content": "hi"}])
        assert result["content"] == "test reply"
        assert result["model"] == "test-model"
        assert result["usage"]["prompt_tokens"] == 10
        assert result["usage"]["completion_tokens"] == 5

    @patch("llm_client.OpenAI")
    def test_empty_content(self, mock_openai_class):
        """content 为 None 时返回空字符串"""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = None
        mock_response.model = "m"
        mock_response.usage = None

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        client = LLMClient(api_key="key", base_url="url", model="m")
        result = client.chat([{"role": "user", "content": "hi"}])
        assert result["content"] == ""

    @patch("llm_client.OpenAI")
    def test_reasoning_content_fallback(self, mock_openai_class):
        """content 为空时使用 reasoning_content"""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = None
        mock_response.choices[0].message.reasoning_content = "推理文本"
        mock_response.model = "m"
        mock_response.usage = None

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        client = LLMClient(api_key="key", base_url="url", model="m")
        result = client.chat([{"role": "user", "content": "hi"}])
        assert result["content"] == "推理文本"

    @patch("llm_client.OpenAI")
    def test_api_error(self, mock_openai_class):
        """异常 re-raise"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Connection error")
        mock_openai_class.return_value = mock_client

        client = LLMClient(api_key="key", base_url="url", model="m")
        with pytest.raises(Exception, match="Connection error"):
            client.chat([{"role": "user", "content": "hi"}])
