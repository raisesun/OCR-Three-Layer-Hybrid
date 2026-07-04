#!/usr/bin/env python3
"""
购房合同多页提取测试

测试场景：
1. 处理整个购房合同文件夹的所有页面
2. 合并所有页面的提取结果
3. 验证多页提取的完整性
"""

import sys
import os
import json
import time
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ocr_three_layer_hybrid.config import OCRConfig
from ocr_three_layer_hybrid.service import OCRService


def process_contract_folder(folder_path: str, service: OCRService) -> Dict[str, Any]:
    """
    处理整个合同文件夹，合并所有页面的提取结果

    Args:
        folder_path: 合同文件夹路径
        service: OCR服务实例

    Returns:
        合并后的提取结果
    """
    # 获取所有图片文件
    images = sorted([
        f for f in os.listdir(folder_path)
        if f.lower().endswith(('.jpeg', '.jpg', '.png'))
    ])

    if not images:
        return {
            'success': False,
            'error': 'No images found in folder',
            'fields': {},
            'pages_processed': 0,
        }

    print(f"  找到 {len(images)} 张图片")

    # 合并所有页面的字段
    merged_fields = {}
    total_time = 0.0
    pages_processed = 0
    layers_used = defaultdict(int)

    for i, img_name in enumerate(images):
        img_path = os.path.join(folder_path, img_name)

        # OCR
        ocr_start = time.time()
        ocr_text = service.run_ocr(img_path)
        ocr_time = time.time() - ocr_start

        # 提取
        extract_start = time.time()
        result = service.process_single(img_path, ocr_text)
        extract_time = time.time() - extract_start

        page_time = ocr_time + extract_time
        total_time += page_time
        pages_processed += 1

        # 记录使用的层
        layer = result['extraction']['layer']
        layers_used[layer] += 1

        # 合并字段（只保留非空值）
        fields = result['extraction']['fields']
        for key, value in fields.items():
            if value and value.strip():
                # 如果已有值，优先保留更长的值（通常更完整）
                if key not in merged_fields or len(value) > len(merged_fields[key]):
                    merged_fields[key] = value

        print(f"    [{i+1}/{len(images)}] {img_name[:30]}... | 层={layer} | 字段={len([v for v in fields.values() if v])} | 耗时={page_time:.1f}s")

    # 统计非空字段数
    non_empty_fields = {k: v for k, v in merged_fields.items() if v and v.strip()}

    return {
        'success': len(non_empty_fields) > 0,
        'fields': merged_fields,
        'non_empty_count': len(non_empty_fields),
        'pages_processed': pages_processed,
        'total_time': total_time,
        'avg_time_per_page': total_time / pages_processed if pages_processed > 0 else 0,
        'layers_used': dict(layers_used),
    }


def main():
    print("=" * 70)
    print("购房合同多页提取测试")
    print("=" * 70)

    # 创建配置
    config = OCRConfig()
    config.vlm_extraction_engine = "qwen2_5_vl_7b"

    # 创建服务
    print("\n初始化 OCRService...")
    service = OCRService(config=config)
    print("✅ 初始化完成\n")

    # 测试购房合同文件夹
    test_folders = [
        "/Users/dongsun/Github/sample-OCR/增量房图片资料/202406240010",
        "/Users/dongsun/Github/sample-OCR/增量房图片资料/202404010024",
        "/Users/dongsun/Github/sample-OCR/增量房图片资料/202404250008",
    ]

    results = []

    for folder_path in test_folders:
        if not os.path.exists(folder_path):
            print(f"⚠️  文件夹不存在: {folder_path}")
            continue

        print(f"\n{'='*70}")
        print(f"处理合同: {os.path.basename(folder_path)}")
        print(f"{'='*70}")

        start_time = time.time()
        result = process_contract_folder(folder_path, service)
        total_time = time.time() - start_time

        print(f"\n结果:")
        print(f"  处理页面数: {result['pages_processed']}")
        print(f"  提取字段数: {result['non_empty_count']}")
        print(f"  总耗时: {total_time:.1f}s")
        print(f"  平均每页: {result['avg_time_per_page']:.1f}s")
        print(f"  使用层: {result['layers_used']}")

        if result['fields']:
            print(f"\n提取的字段:")
            for key, value in sorted(result['fields'].items()):
                if value and value.strip():
                    display_value = value[:60] + "..." if len(value) > 60 else value
                    print(f"  {key}: {display_value}")

        results.append({
            'folder': folder_path,
            'result': result,
        })

    # 汇总统计
    print(f"\n{'='*70}")
    print("汇总统计")
    print(f"{'='*70}")

    total_pages = sum(r['result']['pages_processed'] for r in results)
    total_fields = sum(r['result']['non_empty_count'] for r in results)
    total_time = sum(r['result']['total_time'] for r in results)

    print(f"总合同数: {len(results)}")
    print(f"总页面数: {total_pages}")
    print(f"总字段数: {total_fields}")
    print(f"总耗时: {total_time:.1f}s")
    print(f"平均每页: {total_time/total_pages:.1f}s" if total_pages > 0 else "N/A")

    print("\n✅ 测试完成")


if __name__ == "__main__":
    main()
