#!/usr/bin/env python3
"""测试配置模块"""

import sys
sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.config import (
    OCRConfig,
    VLMServiceConfig,
    QwenVLServiceConfig,
    ThresholdsConfig,
)


def test_thresholds_config_defaults():
    """测试阈值配置默认值"""
    config = ThresholdsConfig()

    # 分类器置信度
    assert config.confidence_partial_match == 0.6
    assert config.confidence_strong_signal == 0.9
    assert config.confidence_combination == 0.85
    assert config.confidence_backup == 0.85

    # 图像处理
    assert config.image_max_side == 2000
    assert config.image_quality == 75

    # VLM参数
    assert config.vlm_timeout == 120.0
    assert config.vlm_max_tokens == 1024
    assert config.vlm_max_pages == 15

    # 位置提取
    assert config.position_row_tolerance == 0.030
    assert config.position_merge_gap == 0.08
    assert config.position_big_gap == 0.25


def test_ocr_config_has_thresholds():
    """测试OCRConfig包含阈值配置"""
    config = OCRConfig()

    assert hasattr(config, 'thresholds')
    assert isinstance(config.thresholds, ThresholdsConfig)
    assert config.thresholds.confidence_partial_match == 0.6


def test_thresholds_config_custom_values():
    """测试自定义阈值"""
    config = ThresholdsConfig(
        confidence_partial_match=0.7,
        image_max_side=3000,
        vlm_timeout=60.0,
    )

    assert config.confidence_partial_match == 0.7
    assert config.image_max_side == 3000
    assert config.vlm_timeout == 60.0


if __name__ == "__main__":
    test_thresholds_config_defaults()
    print("✅ test_thresholds_config_defaults")

    test_ocr_config_has_thresholds()
    print("✅ test_ocr_config_has_thresholds")

    test_thresholds_config_custom_values()
    print("✅ test_thresholds_config_custom_values")

    print("\n✅ 所有配置测试通过")
