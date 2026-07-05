#!/usr/bin/env python3
"""VLM服务稳定性诊断工具"""

import sys
sys.path.insert(0, 'src')

import time
import requests
from pathlib import Path
from ocr_three_layer_hybrid.service import OCRService


def check_vlm_health(port=8082):
    """检查VLM服务健康状态"""
    try:
        resp = requests.get(f"http://localhost:{port}/health", timeout=3)
        if resp.status_code == 200:
            print(f"✅ VLM服务健康 (端口{port})")
            return True
        else:
            print(f"❌ VLM服务异常 (状态码: {resp.status_code})")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ VLM服务不可用 (端口{port})")
        return False
    except Exception as e:
        print(f"❌ VLM服务检查失败: {e}")
        return False


def get_image_info(image_path):
    """获取图片信息"""
    from PIL import Image
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            file_size = Path(image_path).stat().st_size / 1024  # KB
            return {
                'width': width,
                'height': height,
                'max_side': max(width, height),
                'file_size_kb': file_size,
            }
    except Exception as e:
        return {'error': str(e)}


def test_single_image(image_path, service):
    """测试单张图片处理"""
    print(f"\n测试图片: {Path(image_path).name}")

    # 获取图片信息
    info = get_image_info(image_path)
    if 'error' in info:
        print(f"  ❌ 无法读取图片: {info['error']}")
        return False

    print(f"  尺寸: {info['width']}x{info['height']} (最大边: {info['max_side']})")
    print(f"  文件大小: {info['file_size_kb']:.1f} KB")

    # 检查VLM服务状态
    if not check_vlm_health():
        print("  ❌ VLM服务不可用")
        return False

    # 处理图片
    start = time.time()
    try:
        result = service.process_image(image_path)
        elapsed = time.time() - start

        success = result['extraction']['success']
        fields = result['extraction']['fields']
        field_count = len([v for v in fields.values() if v])

        status = '✅' if success else '❌'
        print(f"  {status} 处理成功" if success else f"  {status} 处理失败")
        print(f"  字段数: {field_count}")
        print(f"  耗时: {elapsed:.1f}s")

        # 再次检查VLM服务状态
        check_vlm_health()

        return success
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ❌ 处理异常: {e}")
        print(f"  耗时: {elapsed:.1f}s")

        # 检查是否崩溃
        check_vlm_health()
        return False


def main():
    """主函数"""
    import json

    print("="*60)
    print("VLM服务稳定性诊断")
    print("="*60)

    # 检查VLM服务
    print("\n1. 检查VLM服务状态")
    if not check_vlm_health():
        print("请先启动VLM服务")
        return

    # 加载测试样本
    print("\n2. 加载测试样本")
    with open('tests/batch_test_50_samples.json') as f:
        samples = json.load(f)

    # 初始化服务
    print("\n3. 初始化OCR服务")
    service = OCRService()

    # 逐个测试
    print("\n4. 开始诊断测试")
    success_count = 0
    test_count = min(10, len(samples))

    for i, sample in enumerate(samples[:test_count], 1):
        print(f"\n[{i}/{test_count}]")
        if test_single_image(sample['image_path'], service):
            success_count += 1

        # 每次测试后等待1秒
        time.sleep(1)

    # 汇总
    print("\n" + "="*60)
    print(f"诊断结果: {success_count}/{test_count} 成功")
    print("="*60)


if __name__ == "__main__":
    main()
