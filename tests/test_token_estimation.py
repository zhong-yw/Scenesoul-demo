"""Token 估算纯函数测试"""

import pytest
from context_builders import _estimate_tokens, _estimate_messages_tokens


class TestEstimateTokens:
    """_estimate_tokens 纯函数测试"""

    def test_chinese_only(self):
        """纯中文文本：每个中文字符约 1.5 token"""
        # "你好世界" = 4个中文字符
        # int(4*1.5 + 0*0.4) + 2 = 6 + 2 = 8
        assert _estimate_tokens("你好世界") == 8

    def test_english_only(self):
        """纯英文文本：每个字符约 0.4 token"""
        # "hello" = 5个英文字符
        # int(0*1.5 + 5*0.4) + 2 = int(2.0) + 2 = 4
        result = _estimate_tokens("hello")
        assert result == 4

    def test_mixed_chinese_english(self):
        """中英混合"""
        text = "hello世界"
        # chinese=2 → 2*1.5=3, other=5 → 5*0.4=2, int(5)+2 = 7
        assert _estimate_tokens(text) == 7

    def test_empty_string(self):
        """空字符串：保底 +2"""
        assert _estimate_tokens("") == 2

    def test_special_characters(self):
        """标点和数字"""
        text = "123!@#"
        # chinese=0, other=6 → 6*0.4=2.4, int(2.4)+2=4
        assert _estimate_tokens(text) == 4

    def test_chinese_with_punctuation(self):
        """中文带标点（全角标点不在U+4E00..U+9FFF范围内，算other）"""
        text = "你好，世界！"
        # "你好世界"=4个中文字符, "，！"=2个全角标点(算other)
        # chinese=4 → 4*1.5=6, other=2 → 2*0.4=0.8, int(6+0.8)+2 = 8
        assert _estimate_tokens(text) == 8


class TestEstimateMessagesTokens:
    """_estimate_messages_tokens 纯函数测试"""

    def test_single_message(self):
        """单条消息"""
        msg = [{"role": "user", "content": "你好"}]
        # "你好"=2ch → int(2*1.5)+2=5, "user"=4 → int(4*0.4)+2=3
        user_content = _estimate_tokens("你好")
        user_role = _estimate_tokens("user")
        assert _estimate_messages_tokens(msg) == user_content + user_role

    def test_multiple_messages(self):
        """多条消息累加"""
        msgs = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "世界"}
        ]
        # 两条消息的 token 和应等于各自相加
        total = sum(_estimate_tokens(m["content"]) + _estimate_tokens(m["role"]) for m in msgs)
        assert _estimate_messages_tokens(msgs) == total

    def test_empty_content(self):
        """content 为空字符串"""
        msgs = [{"role": "user", "content": ""}]
        assert isinstance(_estimate_messages_tokens(msgs), int)

    def test_missing_content_key(self):
        """content key 缺失"""
        msgs = [{"role": "system"}]
        result = _estimate_messages_tokens(msgs)
        assert isinstance(result, int)
        assert result > 0
