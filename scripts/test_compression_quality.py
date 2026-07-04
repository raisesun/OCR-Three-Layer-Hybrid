#!/usr/bin/env python3
"""
压缩质量测试：测试不同JPEG质量对OCR准确率的影响

目标：找到文件大小与准确率的平衡点
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from PIL import Image
from ocr_three_layer_hybrid.service import OCRService
from ocr_three_layer_hybrid.config import OCRConfig


def compress_image(image_path, quality, output_dir):
    """以指定JPEG质量压缩图片"""
    img = Image.open(image_path)

    # 转换为RGB（如果是RGBA或其他模式）
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')

    # 保存为指定质量
    output_path = output_dir / f"q{quality}_{Path(image_path).name}"
    img.save(output_path, 'JPEG', quality=quality, optimize=True)

    return str(output_path)


def test_compression_quality(samples, qualities, output_dir):
    """测试不同压缩质量的影响"""
    print("=" * 80)
    print("压缩质量测试")
    print("=" * 80)

    # 使用无预处理配置（基线）
    config = OCRConfig(enable_image_preprocessing=False)
    service = OCRService(config)

    results = []

    for quality in qualities:
        print(f"\n{'='*80}")
        print(f"测试JPEG质量: {quality}%")
        print(f"{'='*80}\n")

        total_fields = 0
        total_time = 0
        total_size = 0

        for i, sample in enumerate(samples):
            image_path = sample['image_path']
            if not Path(image_path).exists():
                continue

            # 压缩图片
            compressed_path = compress_image(image_path, quality, output_dir)

            # 测量文件大小
            file_size = Path(compressed_path).stat().st_size / 1024  # KB
            total_size += file_size

            # 运行OCR和提取
            start_time = time.time()
            ocr_text = service.run_ocr(compressed_path)
            result = service.process_single(compressed_path, ocr_text)
            elapsed = time.time() - start_time
            total_time += elapsed

            # 统计字段
            fields = result.get('extraction', {}).get('fields', {})
            field_count = sum(1 for v in fields.values() if v)
            total_fields += field_count

            print(f"[{i+1}/{len(samples)}] {Path(image_path).name[:30]:30s} | "
                  f"字段数={field_count:2d} | 耗时={elapsed:.1f}s | 大小={file_size:.0f}KB")

        # 计算平均值
        avg_fields = total_fields / len(samples) if samples else 0
        avg_time = total_time / len(samples) if samples else 0
        avg_size = total_size / len(samples) if samples else 0

        results.append({
            'quality': quality,
            'avg_fields': avg_fields,
            'avg_time': avg_time,
            'avg_size': avg_size,
        })

        print(f"\nJPEG质量 {quality}% 汇总:")
        print(f"  平均字段数: {avg_fields:.1f}")
        print(f"  平均耗时: {avg_time:.1f}s")
        print(f"  平均文件大小: {avg_size:.0f}KB")

    return results


def print_comparison(results, baseline_size):
    """打印对比结果"""
    print("\n" + "=" * 80)
    print("压缩质量对比")
    print("=" * 80)

    print(f"\n{'质量':<8s} | {'字段数':<10s} | {'耗时':<10s} | {'文件大小':<12s} | {'大小减少':<10s}")
    print("-" * 70)

    for r in results:
        size_reduction = (1 - r['avg_size'] / baseline_size) * 100
        print(f"{r['quality']:3d}%    | {r['avg_fields']:5.1f}     | {r['avg_time']:5.1f}s   | "
              f"{r['avg_size']:5.0f}KB   | {size_reduction:5.1f}%")

    # 找出最佳平衡点
    print("\n" + "=" * 80)
    print("分析与建议")
    print("=" * 80)

    # 找出字段数最多的
    best_fields = max(results, key=lambda x: x['avg_fields'])
    print(f"\n最多字段数: {best_fields['quality']}% ({best_fields['avg_fields']:.1f}个)")

    # 找出速度最快的
    fastest = min(results, key=lambda x: x['avg_time'])
    print(f"最快速度: {fastest['quality']}% ({fastest['avg_time']:.1f}s)")

    # 找出文件最小的
    smallest = min(results, key=lambda x: x['avg_size'])
    print(f"最小文件: {smallest['quality']}% ({smallest['avg_size']:.0f}KB)")

    # 找出最佳平衡点（字段数 >= 基线的90% 且文件较小）
    baseline_fields = best_fields['avg_fields']
    good_results = [r for r in results if r['avg_fields'] >= baseline_fields * 0.9]
    if good_results:
        best_balance = min(good_results, key=lambda x: x['avg_size'])
        size_reduction = (1 - best_balance['avg_size'] / baseline_size) * 100
        print(f"\n最佳平衡点: {best_balance['quality']}%")
        print(f"  字段数: {best_balance['avg_fields']:.1f} ({best_balance['avg_fields']/baseline_fields*100:.0f}% of baseline)")
        print(f"  耗时: {best_balance['avg_time']:.1f}s")
        print(f"  文件大小: {best_balance['avg_size']:.0f}KB (减少{size_reduction:.1f}%)")


def main():
    """主函数"""
    # 加载测试样本（前5个，快速测试）
    samples_file = Path(__file__).parent.parent / 'tests' / 'batch_test_50_samples.json'
    with open(samples_file) as f:
        samples = json.load(f)[:5]

    print(f"测试样本数: {len(samples)}")

    # 先测量原始文件大小（作为基线）
    baseline_size = 0
    for sample in samples:
        image_path = sample['image_path']
        if Path(image_path).exists():
            baseline_size += Path(image_path).stat().st_size / 1024
    baseline_size /= len(samples)
    print(f"基线文件大小（原始）: {baseline_size:.0f}KB")

    # 测试不同压缩质量
    qualities = [95, 85, 75, 65, 55]
    output_dir = Path('/tmp/compression_test')
    output_dir.mkdir(exist_ok=True)

    results = test_compression_quality(samples, qualities, output_dir)

    # 打印对比
    print_comparison(results, baseline_size)

    print("\n" + "=" * 80)
    print("压缩质量测试完成")
    print("=" * 80)


if __name__ == '__main__':
    main()
