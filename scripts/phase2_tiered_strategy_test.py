#!/usr/bin/env python3
"""
Phase 2 分层策略准确率测试

测试内容：
1. 使用分层策略（tiered）测试50张样本的准确率
2. 对比 PP-OCRv6（单独）和 分层策略 的效果
3. 统计触发第二阶段（PaddleOCR-VL）的次数

使用方法：
    python scripts/phase2_tiered_strategy_test.py
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
    """加载测试数据"""
    print("📂 加载测试数据...")
    samples_file = Path('/Users/dongsun/github/OCR-Three-Layer-Hybrid/tests/batch_test_50_samples.json')

    with open(samples_file, 'r', encoding='utf-8') as f:
        samples = json.load(f)

    print(f"  ✅ 样本数据: {len(samples)} 条")
    return samples

def test_tiered_strategy(samples):
    """测试分层策略"""
    print()
    print("=" * 70)
    print("测试分层策略 (tiered)")
    print("=" * 70)
    print()

    # 创建配置
    print("⚙️  创建配置...")
    config = OCRConfig()
    config.ocr_engine = "tiered"  # 使用分层策略
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

    # 统计分层策略触发情况
    stage1_count = 0  # 仅使用 PP-OCRv6
    stage2_count = 0  # 触发了 PaddleOCR-VL

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

            # 判断是否触发了第二阶段
            # 通过检查日志或 OCR 文本长度来判断
            # 这里简单判断：如果 OCR 耗时 > 50秒，说明触发了第二阶段
            if ocr_time > 50:
                stage2_count += 1
            else:
                stage1_count += 1

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
    print("评估结果: 分层策略 (tiered)")
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

    # 分层策略统计
    print("📊 分层策略触发统计:")
    print(f"  阶段1（仅 PP-OCRv6）: {stage1_count} 次 ({stage1_count/total_count*100:.1f}%)")
    print(f"  阶段2（触发 PaddleOCR-VL）: {stage2_count} 次 ({stage2_count/total_count*100:.1f}%)")
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
        'engine': 'tiered',
        'total': total_count,
        'correct': correct_count,
        'accuracy': overall_accuracy,
        'total_time': total_time,
        'avg_time': total_time / total_count,
        'ocr_avg_time': ocr_time_total / total_count,
        'process_avg_time': process_time_total / total_count,
        'stage1_count': stage1_count,
        'stage2_count': stage2_count,
        'type_stats': dict(type_stats),
        'errors': errors,
    }

def main():
    print("=" * 70)
    print("Phase 2 分层策略准确率测试")
    print("=" * 70)
    print()

    # 加载数据
    samples = load_test_data()
    print()

    # 测试分层策略
    result = test_tiered_strategy(samples)

    # 输出总结
    print()
    print("=" * 70)
    print("📊 测试总结")
    print("=" * 70)
    print()
    print(f"分层策略准确率: {result['accuracy']:.1f}%")
    print(f"对比基线 (GLM-OCR): 66%")
    print(f"对比 PP-OCRv6 (单独): 70.0%")
    print(f"提升: +{result['accuracy'] - 66:.1f}% (vs 基线), +{result['accuracy'] - 70:.1f}% (vs PP-OCRv6)")
    print()
    print(f"分层策略触发情况:")
    print(f"  阶段1（快速）: {result['stage1_count']} 次 ({result['stage1_count']/result['total']*100:.1f}%)")
    print(f"  阶段2（精确）: {result['stage2_count']} 次 ({result['stage2_count']/result['total']*100:.1f}%)")
    print()

    if result['accuracy'] >= 80:
        print("✅ 目标达成: 准确率 >= 80%")
    elif result['accuracy'] >= 75:
        print("⚠️  接近目标: 准确率 >= 75% (目标 80%)")
    else:
        print("❌ 未达目标: 准确率 < 75% (目标 80%)")

    print()
    print("=" * 70)
    print("🎉 测试完成")
    print("=" * 70)

if __name__ == "__main__":
    main()
