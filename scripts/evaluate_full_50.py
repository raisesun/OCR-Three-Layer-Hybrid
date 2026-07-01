#!/usr/bin/env python3
"""
完整50张样本准确率评估
"""

import sys
import json
import time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ocr_three_layer_hybrid.config import OCRConfig
from ocr_three_layer_hybrid.service import OCRService

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

def load_test_data():
    print("加载测试数据...")
    samples_file = Path('/Users/dongsun/github/OCR-Three-Layer-Hybrid/tests/batch_test_50_samples.json')

    with open(samples_file, 'r', encoding='utf-8') as f:
        samples = json.load(f)

    print(f"  样本数据: {len(samples)} 条")
    return samples

def main():
    print("=" * 70)
    print("完整50张样本准确率评估")
    print("=" * 70)
    print()

    # 加载数据
    samples = load_test_data()
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
    print("创建OCR服务...")
    start_time = time.time()
    service = OCRService(config=config)
    elapsed = time.time() - start_time
    print(f"✅ OCR服务创建成功（耗时 {elapsed:.1f}秒）")
    print()

    # 统计结果
    correct_count = 0
    total_count = 0
    type_stats = defaultdict(lambda: {'correct': 0, 'total': 0})
    errors = []

    # 测试所有样本
    print(f"开始测试 {len(samples)} 张样本...")
    print()

    start_time = time.time()
    for i, sample in enumerate(samples):
        image_path = sample.get('image_path', '')
        expected_type_en = sample.get('cert_code', '')
        expected_type = CERT_CODE_TO_CHINESE.get(expected_type_en, expected_type_en)
        case_id = sample.get('case_id', '')

        if not Path(image_path).exists():
            print(f"[{i+1}/{len(samples)}] ⚠️  图片不存在: {case_id}")
            continue

        total_count += 1
        type_stats[expected_type]['total'] += 1

        try:
            # 先调用OCR获取文本
            ocr_start = time.time()
            ocr_text = service.run_ocr(image_path)
            ocr_time = time.time() - ocr_start

            # 再处理图片
            result = service.process_single(image_path, ocr_text)
            actual_type = result['classification']['doc_type']
            is_correct = (actual_type == expected_type)

            if is_correct:
                correct_count += 1
                type_stats[expected_type]['correct'] += 1
                status = "✅"
            else:
                status = "❌"
                errors.append({
                    'case_id': case_id,
                    'expected': expected_type,
                    'actual': actual_type,
                    'ocr_length': len(ocr_text),
                })

            # 每10张输出一次进度
            if (i + 1) % 10 == 0:
                accuracy = correct_count / total_count * 100
                print(f"[{i+1}/{len(samples)}] 当前准确率: {accuracy:.1f}% ({correct_count}/{total_count})")

        except Exception as e:
            print(f"[{i+1}/{len(samples)}] ❌ 处理失败: {case_id} - {e}")

    total_time = time.time() - start_time

    # 输出结果
    print()
    print("=" * 70)
    print("评估结果")
    print("=" * 70)
    print()

    # 总体准确率
    overall_accuracy = correct_count / total_count * 100 if total_count > 0 else 0
    print(f"总体准确率: {correct_count}/{total_count} = {overall_accuracy:.1f}%")
    print(f"总耗时: {total_time:.1f}秒")
    print(f"平均耗时: {total_time/total_count:.1f}秒/张")
    print()

    # 按类型统计
    print("按文档类型统计:")
    for doc_type, stats in sorted(type_stats.items()):
        accuracy = stats['correct'] / stats['total'] * 100 if stats['total'] > 0 else 0
        print(f"  {doc_type:20s}: {stats['correct']:3d}/{stats['total']:3d} = {accuracy:5.1f}%")
    print()

    # 错误详情
    if errors:
        print(f"错误详情 ({len(errors)}个):")
        for error in errors[:10]:  # 只显示前10个
            print(f"  {error['case_id']}: 期望={error['expected']}, 实际={error['actual']}")
        if len(errors) > 10:
            print(f"  ... 还有 {len(errors) - 10} 个错误")
    print()

    print("=" * 70)
    print("评估完成")
    print("=" * 70)

if __name__ == "__main__":
    main()
