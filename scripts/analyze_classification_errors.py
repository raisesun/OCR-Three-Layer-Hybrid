#!/usr/bin/env python3
"""
分析分类错误原因
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ocr_three_layer_hybrid.config import OCRConfig
from ocr_three_layer_hybrid.service import OCRService

# 错误样本列表
ERROR_SAMPLES = [
    # 身份证错误
    {"case_id": "202406240010", "expected": "身份证", "actual": "离婚协议", "desc": "身份证→离婚协议"},
    {"case_id": "BBJZ-2026-0119050", "expected": "身份证", "actual": "户口本", "desc": "身份证→户口本"},
    {"case_id": "BBJZ-2026-0116023", "expected": "身份证", "actual": "未知", "desc": "身份证→未知"},
    # 结婚证错误
    {"case_id": "BBJZ-2026-0113059", "expected": "结婚证", "actual": "离婚证", "desc": "结婚证→离婚证"},
    {"case_id": "BBJZ-2025-1013085", "expected": "结婚证", "actual": "离婚证", "desc": "结婚证→离婚证"},
]

def load_samples():
    samples_file = Path('/Users/dongsun/github/OCR-Three-Layer-Hybrid/tests/batch_test_50_samples.json')
    with open(samples_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    print("=" * 70)
    print("分类错误原因分析")
    print("=" * 70)
    print()

    samples = load_samples()
    sample_map = {s['case_id']: s for s in samples}

    # 创建服务
    config = OCRConfig()
    config.enable_vlm_fallback = True
    config.enable_position_extraction = False  # 暂时禁用位置标注，加速测试
    config.enable_vlm_field_fallback = False

    service = OCRService(config=config)

    for error in ERROR_SAMPLES:
        case_id = error['case_id']
        sample = sample_map.get(case_id)
        if not sample:
            print(f"❌ 未找到样本: {case_id}")
            continue

        image_path = sample['image_path']
        if not Path(image_path).exists():
            print(f"❌ 图片不存在: {case_id}")
            continue

        print(f"分析: {error['desc']}")
        print(f"  Case ID: {case_id}")
        print(f"  图片: {Path(image_path).name}")

        try:
            # 获取OCR文本
            result = service.process_single(image_path, "")
            ocr_text = result.get('ocr_text', '')
            classification = result['classification']

            print(f"  期望: {error['expected']}")
            print(f"  实际: {classification['doc_type']}")
            print(f"  路由: {classification['route']}")
            print(f"  置信度: {classification['confidence']}")
            print(f"  主要信号: {classification.get('primary_signals', [])}")
            print(f"  OCR文本长度: {len(ocr_text)}字")
            print(f"  OCR文本前200字: {ocr_text[:200]}")
            print()

        except Exception as e:
            print(f"❌ 处理失败: {e}")
            print()

if __name__ == "__main__":
    main()
