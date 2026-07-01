#!/usr/bin/env python3
"""
Phase 2 准确率对比测试：PP-OCRv6 vs GLM-OCR

测试内容：
1. 使用 PP-OCRv6 测试50张样本的准确率
2. 使用 GLM-OCR 测试50张样本的准确率（可选，需要较长时间）
3. 对比两种引擎的准确率和速度

使用方法：
    # 只测试 PP-OCRv6
    python scripts/phase2_accuracy_comparison.py --engine ppocr

    # 只测试 GLM-OCR
    python scripts/phase2_accuracy_comparison.py --engine glm_ocr

    # 测试两种引擎（需要较长时间）
    python scripts/phase2_accuracy_comparison.py --engine both
"""

import sys
import json
import time
import argparse
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
    """加载测试数据"""
    print("📂 加载测试数据...")
    samples_file = Path('/Users/dongsun/github/OCR-Three-Layer-Hybrid/tests/batch_test_50_samples.json')

    with open(samples_file, 'r', encoding='utf-8') as f:
        samples = json.load(f)

    print(f"  ✅ 样本数据: {len(samples)} 条")
    return samples

def test_engine(engine_name, samples):
    """测试指定引擎的准确率"""
    print()
    print("=" * 70)
    print(f"测试引擎: {engine_name}")
    print("=" * 70)
    print()

    # 创建配置
    print("⚙️  创建配置...")
    config = OCRConfig()
    config.ocr_engine = engine_name
    config.enable_vlm_fallback = True
    config.enable_position_extraction = True
    config.enable_vlm_field_fallback = True
    print(f"  OCR 引擎: {config.ocr_engine}")
    print(f"  VLM 分类兜底: {config.enable_vlm_fallback}")
    print(f"  位置标注提取: {config.enable_position_extraction}")
    print(f"  VLM 字段兜底: {config.enable_vlm_field_fallback}")
    print()

    # 创建服务
    print("🔧 创建 OCR 服务...")
    start_time = time.time()
    service = OCRService(config=config)
    elapsed = time.time() - start_time
    print(f"  ✅ OCR 服务创建成功（耗时 {elapsed:.1f}秒）")
    print()

    # 统计结果
    correct_count = 0
    total_count = 0
    ocr_time_total = 0
    process_time_total = 0
    type_stats = defaultdict(lambda: {'correct': 0, 'total': 0})
    errors = []

    # 测试所有样本
    print(f"🚀 开始测试 {len(samples)} 张样本...")
    print()

    start_time = time.time()
    for i, sample in enumerate(samples):
        image_path = sample.get('image_path', '')
        expected_type_en = sample.get('cert_code', '')
        expected_type = CERT_CODE_TO_CHINESE.get(expected_type_en, expected_type_en)
        case_id = sample.get('case_id', '')

        if not Path(image_path).exists():
            print(f"  [{i+1}/{len(samples)}] ⚠️  图片不存在: {case_id}")
            continue

        total_count += 1
        type_stats[expected_type]['total'] += 1

        try:
            # 先调用 OCR 获取文本
            ocr_start = time.time()
            ocr_text = service.run_ocr(image_path)
            ocr_time = time.time() - ocr_start
            ocr_time_total += ocr_time

            # 再处理图片（分类 + 提取）
            process_start = time.time()
            result = service.process_single(image_path, ocr_text)
            process_time = time.time() - process_start
            process_time_total += process_time

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
                    'ocr_time': ocr_time,
                })

            # 每10张输出一次进度
            if (i + 1) % 10 == 0:
                accuracy = correct_count / total_count * 100
                print(f"  [{i+1}/{len(samples)}] 当前准确率: {accuracy:.1f}% ({correct_count}/{total_count})")

        except Exception as e:
            print(f"  [{i+1}/{len(samples)}] ❌ 处理失败: {case_id} - {e}")

    total_time = time.time() - start_time

    # 输出结果
    print()
    print("=" * 70)
    print(f"评估结果: {engine_name}")
    print("=" * 70)
    print()

    # 总体准确率
    overall_accuracy = correct_count / total_count * 100 if total_count > 0 else 0
    print(f"📊 总体准确率: {correct_count}/{total_count} = {overall_accuracy:.1f}%")
    print(f"⏱️  总耗时: {total_time:.1f}秒")
    print(f"⏱️  平均耗时: {total_time/total_count:.1f}秒/张")
    print(f"  - OCR 平均耗时: {ocr_time_total/total_count:.1f}秒/张")
    print(f"  - 处理平均耗时: {process_time_total/total_count:.1f}秒/张")
    print()

    # 按类型统计
    print("📋 按文档类型统计:")
    for doc_type, stats in sorted(type_stats.items()):
        accuracy = stats['correct'] / stats['total'] * 100 if stats['total'] > 0 else 0
        print(f"  {doc_type:20s}: {stats['correct']:3d}/{stats['total']:3d} = {accuracy:5.1f}%")
    print()

    # 错误详情
    if errors:
        print(f"❌ 错误详情 ({len(errors)}个):")
        for error in errors[:10]:  # 只显示前10个
            print(f"  {error['case_id']}: 期望={error['expected']}, 实际={error['actual']} (OCR={error['ocr_length']}字, {error['ocr_time']:.1f}秒)")
        if len(errors) > 10:
            print(f"  ... 还有 {len(errors) - 10} 个错误")
    print()

    return {
        'engine': engine_name,
        'total': total_count,
        'correct': correct_count,
        'accuracy': overall_accuracy,
        'total_time': total_time,
        'avg_time': total_time / total_count,
        'ocr_avg_time': ocr_time_total / total_count,
        'process_avg_time': process_time_total / total_count,
        'type_stats': dict(type_stats),
        'errors': errors,
    }

def main():
    parser = argparse.ArgumentParser(description='Phase 2 准确率对比测试')
    parser.add_argument('--engine', choices=['ppocr', 'glm_ocr', 'both'], default='ppocr',
                       help='选择测试引擎（默认: ppocr）')
    args = parser.parse_args()

    print("=" * 70)
    print("Phase 2 准确率对比测试")
    print("=" * 70)
    print()

    # 加载数据
    samples = load_test_data()
    print()

    results = []

    if args.engine in ['ppocr', 'both']:
        result = test_engine('ppocr', samples)
        results.append(result)

    if args.engine in ['glm_ocr', 'both']:
        result = test_engine('glm_ocr', samples)
        results.append(result)

    # 对比结果
    if len(results) > 1:
        print()
        print("=" * 70)
        print("📊 引擎对比")
        print("=" * 70)
        print()

        ppocr_result = next((r for r in results if r['engine'] == 'ppocr'), None)
        glm_result = next((r for r in results if r['engine'] == 'glm_ocr'), None)

        if ppocr_result and glm_result:
            print(f"{'指标':<20} {'PP-OCRv6':<15} {'GLM-OCR':<15} {'对比':<15}")
            print("-" * 70)
            print(f"{'准确率':<20} {ppocr_result['accuracy']:.1f}%{'':<10} {glm_result['accuracy']:.1f}%{'':<10} {'':<15}")
            print(f"{'平均耗时':<20} {ppocr_result['avg_time']:.1f}秒{'':<10} {glm_result['avg_time']:.1f}秒{'':<10} {'':<15}")
            print(f"{'OCR 平均耗时':<20} {ppocr_result['ocr_avg_time']:.1f}秒{'':<10} {glm_result['ocr_avg_time']:.1f}秒{'':<10} {'':<15}")
            print(f"{'处理平均耗时':<20} {ppocr_result['process_avg_time']:.1f}秒{'':<10} {glm_result['process_avg_time']:.1f}秒{'':<10} {'':<15}")
            print()

            # 结论
            if ppocr_result['accuracy'] > glm_result['accuracy']:
                print("✅ 结论: PP-OCRv6 准确率更高")
            elif ppocr_result['accuracy'] < glm_result['accuracy']:
                print("✅ 结论: GLM-OCR 准确率更高")
            else:
                print("✅ 结论: 两者准确率相当")

            if ppocr_result['avg_time'] < glm_result['avg_time']:
                print("✅ 结论: PP-OCRv6 速度更快")
            elif ppocr_result['avg_time'] > glm_result['avg_time']:
                print("✅ 结论: GLM-OCR 速度更快")
            else:
                print("✅ 结论: 两者速度相当")

    print()
    print("=" * 70)
    print("🎉 测试完成")
    print("=" * 70)

if __name__ == "__main__":
    main()
