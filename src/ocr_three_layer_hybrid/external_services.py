#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一外部服务客户端

封装所有对外部模型的 HTTP 调用，消除各模块中重复的请求代码。

- VLMClient: 视觉模型客户端（支持 GLM-OCR / Qwen2.5-VL-7B），用于字段提取和纯OCR

v2.1 简化：
- 移除 ClassificationClient（VLM分类兜底已移除）
- 移除 LLMClient（LLM层已移除）
"""

import base64
import logging
import threading
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import VLMServiceConfig

logger = logging.getLogger(__name__)


def encode_image_base64(image_path: str, max_size: int = 20 * 1024 * 1024) -> str:
    """读取图片文件并返回 base64 编码字符串

    Args:
        max_size: 文件大小上限（字节），默认 20MB（H14: 防 OOM）
    Raises:
        ValueError: 文件超过大小上限
    """
    import os
    file_size = os.path.getsize(image_path)
    if file_size > max_size:
        raise ValueError(f"图片过大: {file_size} 字节，超过上限 {max_size}")
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


class VLMClient:
    """视觉模型客户端（支持 GLM-OCR / Qwen2.5-VL-7B）

    封装对 llama-server 的 OpenAI 兼容 API 调用。
    用于：
    - VLMExtractionLayer: 字段提取
    - OCRService.run_ocr: 纯文本提取
    - VLMFieldRetryHandler: Rule层字段级VLM重试
    """

    def __init__(self, config: Optional[VLMServiceConfig] = None):
        self.config = config or VLMServiceConfig()
        self._local = threading.local()  # H13: per-thread Session（线程安全）

    def _create_session(self) -> requests.Session:
        """创建带有重试机制的HTTP会话"""
        session = requests.Session()

        # 配置重试策略
        retry_strategy = Retry(
            total=3,  # 最大重试次数
            backoff_factor=1,  # 重试间隔：1s, 2s, 4s
            status_forcelist=[429, 500, 502, 503, 504],  # 需要重试的HTTP状态码
            allowed_methods=["POST"],  # 只重试POST请求
        )

        # 挂载重试适配器
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def _get_session(self) -> requests.Session:
        """获取当前线程的 Session（延迟创建，每线程一个，H13 线程安全）"""
        session = getattr(self._local, "session", None)
        if session is None:
            session = self._create_session()
            self._local.session = session
        return session

    def close(self):
        """关闭当前线程的 HTTP 会话（per-thread Session；其他线程的由 GC 清理）"""
        session = getattr(self._local, "session", None)
        if session is not None:
            session.close()
            logger.debug("VLMClient 当前线程 HTTP 会话已关闭")

    def __del__(self):
        """析构时确保关闭 HTTP 会话（安全网）"""
        try:
            self.close()
        except Exception:
            pass

    def __enter__(self):
        """支持上下文管理器"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时关闭会话"""
        self.close()
        return False

    def call(self, prompt: str, image_path: str, max_tokens: int = 1024) -> str:
        """
        发送视觉+文本请求，返回模型响应文本

        Args:
            prompt: 文本提示
            image_path: 图片文件路径
            max_tokens: 最大输出 token 数

        Returns:
            模型响应文本

        Raises:
            requests.exceptions.RequestException: HTTP 请求失败
            FileNotFoundError: 图片文件不存在
        """
        if not Path(image_path).exists():
            raise FileNotFoundError(f"图片不存在: {image_path}")

        image_b64 = encode_image_base64(image_path)
        # 根据扩展名推断 MIME（避免硬编码 image/jpeg 对 PNG/BMP 等解码异常）
        import mimetypes
        mime, _ = mimetypes.guess_type(image_path)
        mime = mime or "image/jpeg"

        payload = {
            "model": self.config.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                        },
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }

        resp = self._get_session().post(
            f"{self.config.base_url}/chat/completions",
            json=payload,
            timeout=self.config.timeout,
            verify=True,  # 显式启用SSL验证
        )
        resp.raise_for_status()

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            return ""

        return choices[0].get("message", {}).get("content", "")
