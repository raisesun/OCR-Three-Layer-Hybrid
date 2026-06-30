#!/usr/bin/env python3
"""
快速准确率测试：测试几张代表性图片
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ocr_three_layer_hybrid.config import OCRConfig
from ocr_three_layer_hybrid.service import OCRService

# 测试样本（从50张中选择代表性样本）
TEST_SAMPLES = [
    # 身份证正面
    {"image_path": "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0107026/4d9fd39863044a649884db86a1b1ecbf.jpg", "expected_type": "身份证", "desc": "身份证正面-陈春燕"},
]

def main():
    print("=" * 70)
    print("快速准确率测试")
    print("=" * 70)
    print()

    # 创建服务（启用所有VLM功能）
    config = OCRConfig()
    config.enable_vlm_fallback = True  # 启用VLM分类兜底
    config.enable_position_extraction = True  # 启用位置标注提取
    config.enable_vlm_field_fallback = True  # 启用VLM字段兜底

    service = OCRService(config=config)

    correct_count = 0
    total_count = 0

    for sample in TEST_SAMPLES:
        image_path = sample['image_path']
        if not Path(image_path).exists():
            print(f"图片不存在: {image_path}")
            continue

        total_count += 1
        try:
            result = service.process_single(image_path, "")
            actual_type = result['classification']['doc_type']
            is_correct = (actual_type == sample['expected_type'])

            if is_correct:
                correct_count += 1
                status = "✅"
            else:
                status = "❌"

            print(f"{status} {sample['desc']}")
            print(f"   期望: {sample['expected_type']}")
            print(f"   实际: {actual_type}")
            print(f"   路由: {result['classification']['route']}")
            print()

        except Exception as e:
            print(f"❌ {sample['desc']}")
            print(f"   错误: {e}")
            print()

    print("=" * 70)
    print(f"分类准确率: {correct_count}/{total_count} = {correct_count/total_count*100:.1f}%")
    print("=" * 70)

if __name__ == "__main__":
    main()
