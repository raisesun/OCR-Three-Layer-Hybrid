#!/usr/bin/env python3
"""
图片质量评估工具

评估指标：
1. 模糊度（拉普拉斯方差）- 越高越清晰
2. 噪声水平 - 越低越好
3. 对比度 - 适中最好
4. 亮度 - 适中最好
5. 分辨率 - 宽高
"""
import cv2
import numpy as np
from pathlib import Path
import argparse


def estimate_noise(gray_img):
    """估计图像噪声水平（使用局部标准差）"""
    # 使用3x3邻域的局部标准差
    kernel = np.ones((3, 3), np.float32) / 9
    local_mean = cv2.filter2D(gray_img.astype(np.float32), -1, kernel)
    local_sq_mean = cv2.filter2D((gray_img.astype(np.float32) ** 2), -1, kernel)
    local_var = local_sq_mean - local_mean ** 2
    local_var = np.maximum(local_var, 0)  # 避免负值
    noise_level = np.sqrt(local_var).mean()
    return noise_level


def assess_image_quality(image_path):
    """
    评估图片质量

    Returns:
        dict: 包含各项质量指标
    """
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"无法读取图片: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # 1. 模糊度（拉普拉斯方差）
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    sharpness = laplacian.var()

    # 2. 噪声水平
    noise = estimate_noise(gray)

    # 3. 对比度（标准差）
    contrast = gray.std()

    # 4. 亮度（均值）
    brightness = gray.mean()

    # 5. 分辨率
    resolution = {'width': w, 'height': h, 'max_side': max(w, h)}

    # 6. 文件大小
    file_size = Path(image_path).stat().st_size / 1024  # KB

    # 质量分级
    if sharpness > 300 and noise < 10:
        quality_level = 'high'
    elif sharpness > 100 and noise < 20:
        quality_level = 'medium'
    else:
        quality_level = 'low'

    return {
        'sharpness': sharpness,
        'noise': noise,
        'contrast': contrast,
        'brightness': brightness,
        'resolution': resolution,
        'file_size_kb': file_size,
        'quality_level': quality_level,
    }


def print_quality_report(quality):
    """打印质量报告"""
    print("\n" + "=" * 60)
    print("图片质量评估报告")
    print("=" * 60)

    print(f"\n分辨率: {quality['resolution']['width']} x {quality['resolution']['height']}")
    print(f"最大边长: {quality['resolution']['max_side']}px")
    print(f"文件大小: {quality['file_size_kb']:.1f} KB")

    print(f"\n质量指标:")
    print(f"  模糊度 (Sharpness): {quality['sharpness']:.1f} (越高越清晰)")
    print(f"  噪声水平 (Noise): {quality['noise']:.2f} (越低越好)")
    print(f"  对比度 (Contrast): {quality['contrast']:.1f} (适中最好)")
    print(f"  亮度 (Brightness): {quality['brightness']:.1f} (适中最好)")

    print(f"\n质量等级: {quality['quality_level'].upper()}")

    # 建议
    print(f"\n预处理建议:")
    if quality['quality_level'] == 'high':
        print("  ✓ 高质量图片，不需要预处理")
        print("  推荐配置: denoise=False, contrast=False")
    elif quality['quality_level'] == 'medium':
        print("  ⚠ 中等质量，建议仅去噪")
        print("  推荐配置: denoise=True, contrast=False")
    else:
        print("  ✗ 低质量，需要去噪+对比度增强")
        print("  推荐配置: denoise=True, contrast=True")

    # 分辨率建议
    max_side = quality['resolution']['max_side']
    if max_side > 4000:
        print(f"\n  ⚠ 分辨率过高（{max_side}px），建议缩放到3000-4000px")
    elif max_side < 1500:
        print(f"\n  ✗ 分辨率过低（{max_side}px），可能影响OCR准确率")


def main():
    parser = argparse.ArgumentParser(description='图片质量评估工具')
    parser.add_argument('image_path', type=str, help='图片路径')
    args = parser.parse_args()

    try:
        quality = assess_image_quality(args.image_path)
        print_quality_report(quality)
    except Exception as e:
        print(f"错误: {e}")
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
