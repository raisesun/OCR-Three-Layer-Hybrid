#!/usr/bin/env python3
"""
VLM服务连通性测试
验证VLM服务是否正常启动
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ocr_three_layer_hybrid.config import OCRConfig
from ocr_three_layer_hybrid.service import OCRService

def test_vlm_services():
    """测试VLM服务连通性"""
    print("=" * 70)
    print("VLM服务连通性测试")
    print("=" * 70)
    print()

    # 创建配置
    config = OCRConfig()
    config.enable_vlm_fallback = True
    config.enable_position_extraction = False  # 暂时禁用位置标注
    config.enable_vlm_field_fallback = True

    print("配置:")
    print(f"  VLM分类兜底: {config.enable_vlm_fallback}")
    print(f"  位置标注提取: {config.enable_position_extraction}")
    print(f"  VLM字段兜底: {config.enable_vlm_field_fallback}")
    print()

    print("VLM服务配置:")
    print(f"  GLM-OCR: {config.vlm_service.base_url}")
    print(f"  Qwen分类: {config.classification.base_url}")
    print()

    # 尝试创建服务
    print("正在创建OCR服务...")
    try:
        service = OCRService(config=config)
        print("✅ OCR服务创建成功")
    except Exception as e:
        print(f"❌ OCR服务创建失败: {e}")
        return False

    print()
    print("=" * 70)
    print("测试完成")
    print("=" * 70)
    return True

if __name__ == "__main__":
    success = test_vlm_services()
    sys.exit(0 if success else 1)
