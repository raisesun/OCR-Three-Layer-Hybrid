#!/usr/bin/env python3
"""测试VLM健康检查器"""

import sys
sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.vlm_health_checker import (
    VLMHealthChecker,
    DegradationStrategy,
    with_health_check,
)


def test_health_checker():
    """测试健康检查器"""
    print("测试VLM健康检查器...")

    # 测试1：检查健康状态
    checker = VLMHealthChecker(base_url="http://localhost:8082")
    is_healthy = checker.check_health()
    print(f"  健康状态: {'✅ 健康' if is_healthy else '❌ 不健康'}")
    assert is_healthy, "VLM服务应该是健康的"

    # 测试2：等待健康状态
    is_ready = checker.wait_for_healthy(timeout=5.0)
    print(f"  等待健康: {'✅ 就绪' if is_ready else '❌ 超时'}")
    assert is_ready, "VLM服务应该就绪"

    # 测试3：属性访问
    assert checker.is_healthy, "is_healthy属性应该返回True"
    print(f"  属性访问: ✅")

    print("✅ 健康检查器测试通过\n")


def test_degradation_strategy():
    """测试降级策略"""
    print("测试降级策略...")

    # 测试1：返回空结果
    result = DegradationStrategy.return_empty_result()
    assert result["success"] is False
    assert result["degraded"] is True
    print(f"  空结果: ✅")

    # 测试2：返回缓存结果
    cache = {"test_key": {"success": True, "fields": {"name": "test"}}}
    result = DegradationStrategy.return_cached_result("test_key", cache)
    assert result["success"] is True
    assert result["degraded"] is True
    assert result["from_cache"] is True
    print(f"  缓存结果: ✅")

    # 测试3：缓存不存在
    result = DegradationStrategy.return_cached_result("missing_key", cache)
    assert result["success"] is False
    print(f"  缓存缺失: ✅")

    print("✅ 降级策略测试通过\n")


def test_decorator():
    """测试装饰器"""
    print("测试装饰器...")

    checker = VLMHealthChecker(base_url="http://localhost:8082")

    # 测试1：正常调用
    @with_health_check(checker, fallback=DegradationStrategy.return_empty_result)
    def normal_call():
        return {"success": True, "data": "ok"}

    result = normal_call()
    assert result["success"] is True
    print(f"  正常调用: ✅")

    # 测试2：服务不可用时降级
    checker._is_healthy = False
    result = normal_call()
    assert result["success"] is False
    assert result["degraded"] is True
    print(f"  降级调用: ✅")

    # 恢复健康状态
    checker._is_healthy = True

    print("✅ 装饰器测试通过\n")


if __name__ == "__main__":
    test_health_checker()
    test_degradation_strategy()
    test_decorator()
    print("="*60)
    print("✅ 所有健康检查测试通过")
    print("="*60)
