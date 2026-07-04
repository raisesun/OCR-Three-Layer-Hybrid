#!/usr/bin/env python3
"""
回归测试：对比无预处理 vs 仅去噪预处理

测试目标：验证规则层优化没有引入回归问题
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from ocr_three_layer_hybrid.service import OCRService
from ocr_three_layer_hybrid.config import OCRConfig


def load_test_samples():
    """加载测试样本"""
    samples_file = Path(__file__).parent / 'batch_test_50_samples.json'
    with open(samples_file) as f:
        return json.load(f)


def test_with_config(samples, config_name, config):
    """使用指定配置测试所有样本"""
    print(f"\n{'='*80}")
    print(f"测试配置: {config_name}")
    print(f"{'='*80}\n")

    service = OCRService(config)
    results = []

    for i, sample in enumerate(samples):
        image_path = sample['image_path']
        expected_type = sample['cert_code']

        if not Path(image_path).exists():
            print(f"[{i+1}/{len(samples)}] 跳过: 图片不存在")
            continue

        start_time = time.time()

        try:
            # 运行OCR
            ocr_text = service.run_ocr(image_path)

            # 处理
            result = service.process_single(image_path, ocr_text)

            # 提取结果
            actual_type = result['classification']['doc_type']
            confidence = result['classification']['confidence']
            fields = result.get('extraction', {}).get('fields', {})
            extraction_success = result.get('extraction', {}).get('success', False)

            elapsed = time.time() - start_time

            # 统计提取的字段数
            field_count = sum(1 for v in fields.values() if v)

            results.append({
                'sample': sample,
                'actual_type': actual_type,
                'expected_type': expected_type,
                'confidence': confidence,
                'extraction_success': extraction_success,
                'field_count': field_count,
                'elapsed': elapsed,
                'fields': fields,
            })

            status = '✓' if extraction_success else '✗'
            print(f"[{i+1}/{len(samples)}] {status} {Path(image_path).name[:30]:30s} | "
                  f"{actual_type:20s} | 置信度={confidence:.2f} | "
                  f"字段数={field_count:2d} | 耗时={elapsed:.1f}s")

        except Exception as e:
            print(f"[{i+1}/{len(samples)}] ✗ 错误: {e}")
            results.append({
                'sample': sample,
                'error': str(e),
            })

    return results


def analyze_results(results, config_name):
    """分析测试结果"""
    print(f"\n{'='*80}")
    print(f"结果分析: {config_name}")
    print(f"{'='*80}\n")

    # 基本统计
    total = len(results)
    success = sum(1 for r in results if r.get('extraction_success', False))
    failed = sum(1 for r in results if 'error' in r)

    print(f"总样本数: {total}")
    print(f"提取成功: {success} ({success/total*100:.1f}%)")
    print(f"提取失败: {total - success} ({(total-success)/total*100:.1f}%)")
    print(f"错误数: {failed}")

    # 按文档类型统计
    type_stats = {}
    for r in results:
        if 'error' in r:
            continue

        expected = r['sample']['cert_code']
        if expected not in type_stats:
            type_stats[expected] = {'total': 0, 'success': 0, 'fields': []}

        type_stats[expected]['total'] += 1
        if r.get('extraction_success', False):
            type_stats[expected]['success'] += 1
            type_stats[expected]['fields'].append(r['field_count'])

    print(f"\n按文档类型统计:")
    print(f"{'文档类型':<25s} | {'成功/总数':<12s} | {'准确率':<8s} | {'平均字段数':<10s}")
    print("-" * 70)

    for doc_type, stats in sorted(type_stats.items()):
        total = stats['total']
        success = stats['success']
        accuracy = success / total * 100 if total > 0 else 0
        avg_fields = sum(stats['fields']) / len(stats['fields']) if stats['fields'] else 0

        print(f"{doc_type:<25s} | {success:3d}/{total:<3d}       | {accuracy:5.1f}%   | {avg_fields:.1f}")

    # 平均耗时
    elapsed_times = [r['elapsed'] for r in results if 'elapsed' in r]
    if elapsed_times:
        avg_elapsed = sum(elapsed_times) / len(elapsed_times)
        print(f"\n平均耗时: {avg_elapsed:.1f}s")

    return type_stats


def compare_results(results_no_preprocess, results_denoise_only):
    """对比两种配置的结果"""
    print(f"\n{'='*80}")
    print(f"配置对比")
    print(f"{'='*80}\n")

    # 按文档类型对比
    types = set()
    for r in results_no_preprocess + results_denoise_only:
        if 'error' not in r:
            types.add(r['sample']['cert_code'])

    print(f"{'文档类型':<25s} | {'无预处理':<15s} | {'仅去噪':<15s} | {'差异':<10s}")
    print("-" * 80)

    for doc_type in sorted(types):
        # 无预处理
        no_prep = [r for r in results_no_preprocess if r['sample']['cert_code'] == doc_type]
        no_prep_success = sum(1 for r in no_prep if r.get('extraction_success', False))
        no_prep_total = len(no_prep)
        no_prep_rate = no_prep_success / no_prep_total * 100 if no_prep_total > 0 else 0

        # 仅去噪
        denoise = [r for r in results_denoise_only if r['sample']['cert_code'] == doc_type]
        denoise_success = sum(1 for r in denoise if r.get('extraction_success', False))
        denoise_total = len(denoise)
        denoise_rate = denoise_success / denoise_total * 100 if denoise_total > 0 else 0

        # 差异
        diff = denoise_rate - no_prep_rate
        diff_str = f"{diff:+.1f}%" if abs(diff) > 0.1 else "="

        print(f"{doc_type:<25s} | {no_prep_rate:5.1f}% ({no_prep_success}/{no_prep_total}) | "
              f"{denoise_rate:5.1f}% ({denoise_success}/{denoise_total}) | {diff_str}")


def main():
    """主函数"""
    print("=" * 80)
    print("回归测试：无预处理 vs 仅去噪预处理")
    print("=" * 80)

    # 加载测试样本（只测试前10个，快速验证）
    samples = load_test_samples()[:10]
    print(f"\n测试样本数: {len(samples)}")

    # 测试1：无预处理（基线）
    config_no_preprocess = OCRConfig(enable_image_preprocessing=False)
    results_no_preprocess = test_with_config(samples, "无预处理", config_no_preprocess)
    stats_no_preprocess = analyze_results(results_no_preprocess, "无预处理")

    # 测试2：仅去噪
    config_denoise_only = OCRConfig(
        enable_image_preprocessing=True,
        preprocessing_denoise=True,
        preprocessing_deskew=False,
        preprocessing_contrast=False,
    )
    results_denoise_only = test_with_config(samples, "仅去噪", config_denoise_only)
    stats_denoise_only = analyze_results(results_denoise_only, "仅去噪")

    # 对比结果
    compare_results(results_no_preprocess, results_denoise_only)

    print("\n" + "=" * 80)
    print("回归测试完成")
    print("=" * 80)


if __name__ == '__main__':
    main()
