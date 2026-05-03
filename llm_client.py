# 🔌 LLM 客户端 — 调用 OpenAI 兼容 API

import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class LLMClient:
    """统一的 LLM 调用客户端

    支持普通 chat 和 tool_call 两种模式。
    """

    def __init__(self, api_key=None, base_url=None, model=None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.model = model or os.getenv("OPENAI_MODEL")

        if not self.api_key:
            raise ValueError("未设置 API Key！请在环境变量中配置 OPENAI_API_KEY")
        if not self.base_url:
            raise ValueError("未设置 API Base URL！请在环境变量中配置 OPENAI_BASE_URL")
        if not self.model:
            raise ValueError("未设置模型名！请在环境变量中配置 OPENAI_MODEL")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def _build_payload(self, messages, extra=None):
        """构建请求体，处理 thinking 模式的 reasoning_content"""
        payload = {
            "model": self.model,
            "messages": messages,
        }
        if extra:
            payload.update(extra)
        return payload

    def _extract_content(self, response):
        """从响应中提取内容，处理 thinking 模式的 reasoning_content"""
        message = response.choices[0].message
        content = message.content or ""

        # 某些 provider 在 thinking 模式下把内容放在 reasoning_content
        if not content and hasattr(message, "reasoning_content") and message.reasoning_content:
            content = message.reasoning_content

        return content, message

    def chat(self, messages, max_tokens=16000, temperature=0.8):
        """普通对话调用"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            content, message = self._extract_content(response)
            return {
                "content": content,
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0
                }
            }
        except Exception as e:
            print(f"❌ LLM 调用失败: {e}")
            raise

    def chat_with_tools(self, messages, tools, max_tokens=16000, temperature=0.7):
        """带工具调用的对话"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                tools=tools,
                tool_choice="auto"
            )
            content, message = self._extract_content(response)

            result = {
                "content": content,
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0
                }
            }

            if message.tool_calls:
                result["tool_calls"] = [{
                    "id": tc.id,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                } for tc in message.tool_calls]
            else:
                result["tool_calls"] = None

            return result

        except Exception as e:
            print(f"❌ LLM 工具调用失败: {e}")
            raise
