#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""external_services 单元测试"""

import os
import base64
import tempfile
import pytest
from unittest.mock import MagicMock, patch, Mock

from ocr_three_layer_hybrid.external_services import (
    encode_image_base64,
    VLMClient,
)
from ocr_three_layer_hybrid.config import VLMServiceConfig


class TestEncodeImageBase64:
    """encode_image_base64 测试"""

    def test_encode_valid_image(self):
        """编码有效图片文件"""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # JPEG header-like
            f.flush()
            path = f.name

        try:
            result = encode_image_base64(path)
            # 应该是有效的 base64 字符串
            decoded = base64.b64decode(result)
            assert len(decoded) > 0
        finally:
            os.unlink(path)

    def test_encode_nonexistent_file(self):
        """文件不存在应抛异常"""
        with pytest.raises(FileNotFoundError):
            encode_image_base64("/nonexistent/path.jpg")

    def test_encode_empty_file(self):
        """空文件也能编码（返回空字符串的base64）"""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            path = f.name

        try:
            result = encode_image_base64(path)
            decoded = base64.b64decode(result)
            assert decoded == b""
        finally:
            os.unlink(path)


class TestVLMClient:
    """VLMClient 测试"""

    def test_init_default_config(self):
        """默认配置初始化"""
        client = VLMClient()
        assert client.config.base_url == "http://localhost:8080/v1"
        client.close()

    def test_init_custom_config(self):
        """自定义配置初始化"""
        config = VLMServiceConfig(base_url="http://custom:9090/v1")
        client = VLMClient(config)
        assert client.config.base_url == "http://custom:9090/v1"
        client.close()

    def test_context_manager(self):
        """上下文管理器"""
        with VLMClient() as client:
            assert client is not None
            assert client.config is not None

    def test_call_file_not_found(self):
        """图片不存在应抛 FileNotFoundError"""
        client = VLMClient()
        with pytest.raises(FileNotFoundError):
            client.call("test prompt", "/nonexistent/image.jpg")
        client.close()

    @patch.object(VLMClient, '_create_session')
    def test_call_success(self, mock_create_session):
        """成功调用"""
        # 创建临时图片文件
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
            f.flush()
            img_path = f.name

        try:
            mock_session = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": '{"姓名": "张三"}'}}]
            }
            mock_response.raise_for_status = MagicMock()
            mock_session.post.return_value = mock_response
            mock_create_session.return_value = mock_session

            client = VLMClient()
            client._local.session = mock_session
            result = client.call("提取姓名", img_path, max_tokens=512)

            assert result == '{"姓名": "张三"}'
            mock_session.post.assert_called_once()
        finally:
            os.unlink(img_path)

    @patch.object(VLMClient, '_create_session')
    def test_call_empty_choices(self, mock_create_session):
        """空 choices 返回空字符串"""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
            f.flush()
            img_path = f.name

        try:
            mock_session = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"choices": []}
            mock_response.raise_for_status = MagicMock()
            mock_session.post.return_value = mock_response

            client = VLMClient()
            client._local.session = mock_session
            result = client.call("test", img_path)
            assert result == ""
        finally:
            os.unlink(img_path)

    @patch.object(VLMClient, '_create_session')
    def test_call_http_error(self, mock_create_session):
        """HTTP 错误应抛出 RequestException"""
        import requests

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
            f.flush()
            img_path = f.name

        try:
            mock_session = MagicMock()
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                "500 Server Error"
            )
            mock_session.post.return_value = mock_response

            client = VLMClient()
            client._local.session = mock_session

            with pytest.raises(requests.exceptions.HTTPError):
                client.call("test prompt", img_path)
        finally:
            os.unlink(img_path)

    @patch.object(VLMClient, '_create_session')
    def test_call_payload_structure(self, mock_create_session):
        """验证请求 payload 结构正确"""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
            f.flush()
            img_path = f.name

        try:
            mock_session = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
            mock_response.raise_for_status = MagicMock()
            mock_session.post.return_value = mock_response

            config = VLMServiceConfig(base_url="http://test:9999/v1", model_name="test-model")
            client = VLMClient(config)
            client._local.session = mock_session
            client.call("extract name", img_path, max_tokens=256)

            # 验证调用参数
            call_args = mock_session.post.call_args
            assert call_args[0][0] == "http://test:9999/v1/chat/completions"
            payload = call_args[1]["json"]
            assert payload["model"] == "test-model"
            assert payload["max_tokens"] == 256
            assert payload["temperature"] == 0.1
            assert len(payload["messages"]) == 1
            content_parts = payload["messages"][0]["content"]
            assert content_parts[0]["type"] == "text"
            assert content_parts[0]["text"] == "extract name"
            assert content_parts[1]["type"] == "image_url"
            assert content_parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        finally:
            os.unlink(img_path)

    @patch.object(VLMClient, '_create_session')
    def test_call_empty_message_content(self, mock_create_session):
        """message.content 为空时返回空字符串"""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
            f.flush()
            img_path = f.name

        try:
            mock_session = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": ""}}]
            }
            mock_response.raise_for_status = MagicMock()
            mock_session.post.return_value = mock_response

            client = VLMClient()
            client._local.session = mock_session
            result = client.call("test", img_path)
            assert result == ""
        finally:
            os.unlink(img_path)


class TestVLMClientClose:
    """VLMClient close/context manager 测试"""

    def test_close_session(self):
        """close() 应关闭底层 session"""
        client = VLMClient()
        mock_session = MagicMock()
        client._local.session = mock_session

        client.close()
        mock_session.close.assert_called_once()

    def test_close_idempotent(self):
        """多次 close() 不报错"""
        client = VLMClient()
        mock_session = MagicMock()
        client._local.session = mock_session

        client.close()
        client.close()  # 第二次调用不应报错
        assert mock_session.close.call_count == 2

    def test_close_when_session_is_none(self):
        """session 为 None 时 close() 不报错"""
        client = VLMClient()
        client._local.session = None
        # 不应抛出异常
        client.close()

    def test_context_manager_exit_returns_false(self):
        """__exit__ 返回 False（不吞异常）"""
        client = VLMClient()
        result = client.__exit__(None, None, None)
        assert result is False

    def test_context_manager_closes_on_exit(self):
        """退出上下文时关闭 session"""
        with VLMClient() as client:
            mock_session = MagicMock()
            client._local.session = mock_session
        mock_session.close.assert_called_once()
