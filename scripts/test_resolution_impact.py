#!/usr/bin/env python3
"""
分辨率测试：测试不同分辨率对OCR准确率的影响

目标：找到准确率、速度、文件大小的最佳平衡点
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from PIL import Image
from ocr_three_layer_hybrid.service import OCRService
from ocr_three_layer_hybrid.config import OCRConfig


def resize_image(image_path, max_side, output_dir):
    """缩放图片到指定最大边长"""
    img = Image.open(image_path)
    w, h = img.size

    if max(w, h) <= max_side:
        return image_path  # 不需要缩放

    # 计算缩放比例
    scale = max_side / max(w, h)
    new_w, new_h = int(w * scale), int(h * scale)

    # 高质量缩放
    img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # 保存
    output_path = output_dir / f"resized_{max_side}_{Path(image_path).name}"
    img_resized.save(output_path, quality=95, optimize=True)

    return str(output_path)


def test_resolution(samples, resolutions, output_dir):
    """测试不同分辨率的影响"""
    print("=" * 80)
    print("分辨率测试")
    print("=" * 80)

    # 使用仅去噪配置（已验证最佳）
    config = OCRConfig(
        enable_image_preprocessing=True,
        preprocessing_denoise=True,
        preprocessing_deskew=False,
        preprocessing_contrast=False,
    )
    service = OCRService(config)

    results = []

    for resolution in resolutions:
        print(f"\n{'='*80}")
        print(f"测试分辨率: {resolution}px")
        print(f"{'='*80}\n")

        total_accuracy = 0
        total_fields = 0
        total_expected = 0
        total_time = 0
        total_size = 0

        for i, sample in enumerate(samples):
            image_path = sample['image_path']
            if not Path(image_path).exists():
                continue

            # 缩放图片
            resized_path = resize_image(image_path, resolution, output_dir)

            # 测量文件大小
            file_size = Path(resized_path).stat().st_size / 1024  # KB
            total_size += file_size

            # 运行OCR和提取
            start_time = time.time()
            ocr_text = service.run_ocr(resized_path)
            result = service.process_single(resized_path, ocr_text)
            elapsed = time.time() - start_time
            total_time += elapsed

            # 统计字段
            fields = result.get('extraction', {}).get('fields', {})
            field_count = sum(1 for v in fields.values() if v)
            total_fields += field_count

            # 如果有基线字段，计算准确率
            ref_fields = sample.get('ref_fields', {})
            if ref_fields:
                correct = 0
                expected = 0
                for key, expected_value in ref_fields.items():
                    if expected_value and str(expected_value).strip():
                        expected += 1
                        actual_value = fields.get(key, '')
                        if str(actual_value).strip() == str(expected_value).strip():
                            correct += 1

                if expected > 0:
                    accuracy = correct / expected * 100
                    total_accuracy += accuracy
                    total_expected += expected

            print(f"[{i+1}/{len(samples)}] {Path(image_path).name[:30]:30s} | "
                  f"字段数={field_count:2d} | 耗时={elapsed:.1f}s | 大小={file_size:.0f}KB")

        # 计算平均值
        avg_accuracy = total_accuracy / len(samples) if samples else 0
        avg_fields = total_fields / len(samples) if samples else 0
        avg_time = total_time / len(samples) if samples else 0
        avg_size = total_size / len(samples) if samples else 0

        results.append({
            'resolution': resolution,
            'avg_accuracy': avg_accuracy,
            'avg_fields': avg_fields,
            'avg_time': avg_time,
            'avg_size': avg_size,
        })

        print(f"\n分辨率 {resolution}px 汇总:")
        print(f"  平均准确率: {avg_accuracy:.1f}%")
        print(f"  平均字段数: {avg_fields:.1f}")
        print(f"  平均耗时: {avg_time:.1f}s")
        print(f"  平均文件大小: {avg_size:.0f}KB")

    return results


def print_comparison(results):
    """打印对比结果"""
    print("\n" + "=" * 80)
    print("分辨率对比")
    print("=" * 80)

    print(f"\n{'分辨率':<12s} | {'准确率':<10s} | {'字段数':<10s} | {'耗时':<10s} | {'文件大小':<12s}")
    print("-" * 70)

    for r in results:
        print(f"{r['resolution']:<12d} | {r['avg_accuracy']:5.1f}%    | "
              f"{r['avg_fields']:5.1f}     | {r['avg_time']:5.1f}s   | {r['avg_size']:5.0f}KB")

    # 找出最佳平衡点
    print("\n" + "=" * 80)
    print("分析与建议")
    print("=" * 80)

    # 找出准确率最高的
    best_accuracy = max(results, key=lambda x: x['avg_accuracy'])
    print(f"\n最高准确率: {best_accuracy['resolution']}px ({best_accuracy['avg_accuracy']:.1f}%)")

    # 找出速度最快的
    fastest = min(results, key=lambda x: x['avg_time'])
    print(f"最快速度: {fastest['resolution']}px ({fastest['avg_time']:.1f}s)")

    # 找出文件最小的
    smallest = min(results, key=lambda x: x['avg_size'])
    print(f"最小文件: {smallest['resolution']}px ({smallest['avg_size']:.0f}KB)")

    # 找出最佳平衡点（准确率 >= 90% 且速度较快）
    good_results = [r for r in results if r['avg_accuracy'] >= 85]
    if good_results:
        best_balance = min(good_results, key=lambda x: x['avg_time'])
        print(f"\n最佳平衡点: {best_balance['resolution']}px")
        print(f"  准确率: {best_balance['avg_accuracy']:.1f}%")
        print(f"  耗时: {best_balance['avg_time']:.1f}s")
        print(f"  文件大小: {best_balance['avg_size']:.0f}KB")


def main():
    """主函数"""
    # 加载测试样本（前5个，快速测试）
    samples_file = Path(__file__).parent.parent / 'tests' / 'batch_test_50_samples.json'
    with open(samples_file) as f:
        samples = json.load(f)[:5]

    print(f"测试样本数: {len(samples)}")

    # 测试不同分辨率
    resolutions = [4000, 3000, 2000, 1500]
    output_dir = Path('/tmp/resolution_test')
    output_dir.mkdir(exist_ok=True)

    results = test_resolution(samples, resolutions, output_dir)

    # 打印对比
    print_comparison(results)

    print("\n" + "=" * 80)
    print("分辨率测试完成")
    print("=" * 80)


if __name__ == '__main__':
    main()
