#!/usr/bin/env python3
"""
VLM服务健康检查包装器

提供服务健康检查、自动重试、降级策略。
"""

import time
import logging
from typing import Optional, Callable, Any
import requests

logger = logging.getLogger(__name__)


class VLMHealthChecker:
    """VLM服务健康检查器"""

    def __init__(
        self,
        base_url: str,
        health_endpoint: str = "/health",
        timeout: float = 3.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.health_endpoint = health_endpoint
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._last_health_check = 0
        self._is_healthy = True

    def check_health(self) -> bool:
        """检查服务健康状态"""
        try:
            resp = requests.get(
                f"{self.base_url}{self.health_endpoint}",
                timeout=self.timeout,
            )
            is_healthy = resp.status_code == 200
            self._is_healthy = is_healthy
            self._last_health_check = time.time()
            return is_healthy
        except Exception as e:
            logger.warning(f"健康检查失败: {e}")
            self._is_healthy = False
            self._last_health_check = time.time()
            return False

    @property
    def is_healthy(self) -> bool:
        """获取当前健康状态（带缓存，避免频繁检查）"""
        # 每10秒检查一次
        if time.time() - self._last_health_check > 10:
            self.check_health()
        return self._is_healthy

    def wait_for_healthy(self, timeout: float = 60.0) -> bool:
        """等待服务变为健康状态"""
        start = time.time()
        while time.time() - start < timeout:
            if self.check_health():
                return True
            time.sleep(self.retry_delay)
        return False


def with_health_check(
    health_checker: VLMHealthChecker,
    fallback: Optional[Callable] = None,
):
    """
    装饰器：为函数添加健康检查和降级策略

    Args:
        health_checker: 健康检查器
        fallback: 降级函数（当服务不可用时调用）

    Example:
        @with_health_check(health_checker, fallback=lambda *args: {"error": "服务不可用"})
        def call_vlm(prompt, image):
            # VLM调用逻辑
            pass
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs) -> Any:
            # 检查健康状态
            if not health_checker.is_healthy:
                logger.warning("VLM服务不可用，使用降级策略")
                if fallback:
                    return fallback(*args, **kwargs)
                raise RuntimeError("VLM服务不可用")

            # 执行原函数
            try:
                return func(*args, **kwargs)
            except requests.exceptions.RequestException as e:
                logger.error(f"VLM调用失败: {e}")
                # 检查是否服务崩溃
                health_checker.check_health()
                if fallback:
                    return fallback(*args, **kwargs)
                raise

        return wrapper
    return decorator


class DegradationStrategy:
    """降级策略"""

    @staticmethod
    def return_empty_result(*args, **kwargs) -> dict:
        """返回空结果"""
        return {
            "success": False,
            "fields": {},
            "error": "VLM服务不可用",
            "degraded": True,
        }

    @staticmethod
    def return_cached_result(cache_key: str, cache: dict, *args, **kwargs) -> dict:
        """返回缓存结果"""
        if cache_key in cache:
            logger.info(f"使用缓存结果: {cache_key}")
            return {
                **cache[cache_key],
                "degraded": True,
                "from_cache": True,
            }
        return DegradationStrategy.return_empty_result(*args, **kwargs)

    @staticmethod
    def raise_with_message(message: str = "VLM服务不可用"):
        """抛出异常"""
        def raiser(*args, **kwargs):
            raise RuntimeError(message)
        return raiser
