#!/usr/bin/env python3
"""
准确率评估 - 带详细日志
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ocr_three_layer_hybrid.config import OCRConfig
from ocr_three_layer_hybrid.service import OCRService

# 加载测试数据
BASELINE_FILE = Path('/Users/dongsun/Github/sample-OCR/test_base_V2.0_full50.json')
SAMPLES_FILE = Path('/Users/dongsun/github/OCR-Three-Layer-Hybrid/tests/batch_test_50_samples.json')

def load_test_data():
    print("加载测试数据...")
    with open(BASELINE_FILE, 'r', encoding='utf-8') as f:
        baseline = json.load(f)
    with open(SAMPLES_FILE, 'r', encoding='utf-8') as f:
        samples = json.load(f)
    print(f"  基线数据: {len(baseline)} 条")
    print(f"  样本数据: {len(samples)} 条")
    return baseline, samples

# 期望类型映射（英文 -> 中文）
CERT_CODE_TO_CHINESE = {
    "id_card_front": "身份证",
    "id_card_back": "身份证",
    "marriage": "结婚证",
    "hukou": "户口本",
    "purchase_contract": "购房合同",
    "stock_contract": "存量房合同",
    "property": "不动产权证书",
    "invoice": "发票",
    "fund_supervision": "资金监管协议",
    "divorce_certificate": "离婚证",
    "divorce_agreement": "离婚协议",
}

def main():
    print("=" * 70)
    print("准确率评估（带详细日志）")
    print("=" * 70)
    print()

    # 加载数据
    baseline, samples = load_test_data()
    print()

    # 创建配置
    print("创建配置...")
    config = OCRConfig()
    config.enable_vlm_fallback = True
    config.enable_position_extraction = True
    config.enable_vlm_field_fallback = True
    print(f"  VLM分类兜底: {config.enable_vlm_fallback}")
    print(f"  位置标注提取: {config.enable_position_extraction}")
    print(f"  VLM字段兜底: {config.enable_vlm_field_fallback}")
    print()

    # 创建服务
    print("创建OCR服务（可能需要30-60秒）...")
    start_time = time.time()
    try:
        service = OCRService(config=config)
        elapsed = time.time() - start_time
        print(f"✅ OCR服务创建成功（耗时 {elapsed:.1f}秒）")
    except Exception as e:
        print(f"❌ OCR服务创建失败: {e}")
        import traceback
        traceback.print_exc()
        return
    print()

    # 测试前5张样本
    print("开始测试前5张样本...")
    print()

    correct_count = 0
    for i, sample in enumerate(samples[:5]):
        image_path = sample.get('image_path', '')
        expected_type_en = sample.get('cert_code', '')
        expected_type = CERT_CODE_TO_CHINESE.get(expected_type_en, expected_type_en)
        case_id = sample.get('case_id', '')

        if not Path(image_path).exists():
            print(f"[{i+1}/5] ⚠️  图片不存在: {case_id}")
            continue

        print(f"[{i+1}/5] 处理中: {case_id}...")
        start_time = time.time()

        try:
            result = service.process_single(image_path, "")
            elapsed = time.time() - start_time

            actual_type = result['classification']['doc_type']
            is_correct = (actual_type == expected_type)

            if is_correct:
                correct_count += 1
                status = "✅"
            else:
                status = "❌"

            print(f"{status} {case_id}")
            print(f"   期望: {expected_type}")
            print(f"   实际: {actual_type}")
            print(f"   路由: {result['classification']['route']}")
            print(f"   耗时: {elapsed:.2f}秒")
            print()

        except Exception as e:
            print(f"❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()
            print()

    print("=" * 70)
    print(f"前5张样本准确率: {correct_count}/5 = {correct_count/5*100:.1f}%")
    print("=" * 70)

if __name__ == "__main__":
    main()
