#!/usr/bin/env python3
"""
扩大测试：运行50个样本的完整测试

目标：验证优化效果，发现新的优化点
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from ocr_three_layer_hybrid.service import OCRService
from ocr_three_layer_hybrid.config import OCRConfig


def load_test_samples():
    """加载所有测试样本"""
    samples_file = Path(__file__).parent / 'batch_test_50_samples.json'
    with open(samples_file) as f:
        return json.load(f)


def test_samples(samples, config_name, config):
    """测试所有样本"""
    print(f"\n{'='*80}")
    print(f"测试配置: {config_name}")
    print(f"样本数: {len(samples)}")
    print(f"{'='*80}\n")

    service = OCRService(config)
    results = []

    for i, sample in enumerate(samples):
        image_path = sample['image_path']
        expected_type = sample['cert_code']
        ref_fields = sample.get('ref_fields', {})

        if not Path(image_path).exists():
            print(f"[{i+1}/{len(samples)}] 跳过: 图片不存在 - {Path(image_path).name}")
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

            # 计算字段准确率（如果有参考字段）
            field_accuracy = None
            if ref_fields:
                correct = 0
                total = 0
                for key, expected_value in ref_fields.items():
                    if expected_value and str(expected_value).strip():
                        total += 1
                        actual_value = fields.get(key, '')
                        if str(actual_value).strip() == str(expected_value).strip():
                            correct += 1
                if total > 0:
                    field_accuracy = correct / total * 100

            results.append({
                'sample': sample,
                'actual_type': actual_type,
                'expected_type': expected_type,
                'confidence': confidence,
                'extraction_success': extraction_success,
                'field_count': field_count,
                'field_accuracy': field_accuracy,
                'elapsed': elapsed,
                'fields': fields,
            })

            status = '✓' if extraction_success else '✗'
            acc_str = f"{field_accuracy:.0f}%" if field_accuracy is not None else "N/A"
            print(f"[{i+1}/{len(samples)}] {status} {Path(image_path).name[:35]:35s} | "
                  f"{actual_type:20s} | 字段={field_count:2d} | 准确率={acc_str:6s} | "
                  f"耗时={elapsed:.1f}s")

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
            type_stats[expected] = {
                'total': 0,
                'success': 0,
                'fields': [],
                'accuracies': [],
            }

        type_stats[expected]['total'] += 1
        if r.get('extraction_success', False):
            type_stats[expected]['success'] += 1
            type_stats[expected]['fields'].append(r['field_count'])
            if r['field_accuracy'] is not None:
                type_stats[expected]['accuracies'].append(r['field_accuracy'])

    print(f"\n按文档类型统计:")
    print(f"{'文档类型':<25s} | {'成功/总数':<12s} | {'成功率':<8s} | {'平均字段':<10s} | {'平均准确率':<12s}")
    print("-" * 85)

    for doc_type, stats in sorted(type_stats.items()):
        total = stats['total']
        success = stats['success']
        success_rate = success / total * 100 if total > 0 else 0
        avg_fields = sum(stats['fields']) / len(stats['fields']) if stats['fields'] else 0
        avg_accuracy = sum(stats['accuracies']) / len(stats['accuracies']) if stats['accuracies'] else 0

        print(f"{doc_type:<25s} | {success:3d}/{total:<3d}       | {success_rate:5.1f}%   | "
              f"{avg_fields:5.1f}     | {avg_accuracy:5.1f}%")

    # 平均耗时
    elapsed_times = [r['elapsed'] for r in results if 'elapsed' in r]
    if elapsed_times:
        avg_elapsed = sum(elapsed_times) / len(elapsed_times)
        total_elapsed = sum(elapsed_times)
        print(f"\n平均耗时: {avg_elapsed:.1f}s")
        print(f"总耗时: {total_elapsed:.1f}s ({total_elapsed/60:.1f}分钟)")

    # 整体平均准确率
    all_accuracies = [r['field_accuracy'] for r in results if r.get('field_accuracy') is not None]
    if all_accuracies:
        overall_accuracy = sum(all_accuracies) / len(all_accuracies)
        print(f"\n整体平均字段准确率: {overall_accuracy:.1f}%")

    return type_stats


def save_results(results, config_name, output_file):
    """保存详细结果到JSON"""
    output_data = {
        'config': config_name,
        'total_samples': len(results),
        'results': [],
    }

    for r in results:
        if 'error' in r:
            output_data['results'].append({
                'image': Path(r['sample']['image_path']).name,
                'expected_type': r['sample']['cert_code'],
                'error': r['error'],
            })
        else:
            output_data['results'].append({
                'image': Path(r['sample']['image_path']).name,
                'expected_type': r['sample']['cert_code'],
                'actual_type': r['actual_type'],
                'confidence': r['confidence'],
                'extraction_success': r['extraction_success'],
                'field_count': r['field_count'],
                'field_accuracy': r['field_accuracy'],
                'elapsed': r['elapsed'],
            })

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\n详细结果已保存到: {output_file}")


def main():
    """主函数"""
    print("=" * 80)
    print("扩大测试：50个样本完整测试")
    print("=" * 80)

    # 加载所有测试样本
    samples = load_test_samples()
    print(f"\n总样本数: {len(samples)}")

    # 测试：使用当前默认配置（分辨率2000px，质量75%，无预处理）
    config = OCRConfig(enable_image_preprocessing=False)
    results = test_samples(samples, "默认配置（2000px, 75%, 无预处理）", config)

    # 分析结果
    type_stats = analyze_results(results, "默认配置")

    # 保存详细结果
    output_file = Path(__file__).parent.parent / 'tests' / 'test_50_samples_results.json'
    save_results(results, "默认配置（2000px, 75%, 无预处理）", output_file)

    print("\n" + "=" * 80)
    print("扩大测试完成")
    print("=" * 80)


if __name__ == '__main__':
    main()
