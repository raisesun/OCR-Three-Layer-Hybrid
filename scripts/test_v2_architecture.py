#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2.0 架构定向评测脚本

验证内容：
1. 合同类文档（购房合同、存量房合同）的VLM层提取效果
2. 房产证的VLM层提取效果
3. UNKNOWN文档的类型识别+提取功能
4. 多页文档提取功能

对比 v1.0 vs v2.0 的性能提升
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Any

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ocr_three_layer_hybrid.service import OCRService
from ocr_three_layer_hybrid.config import OCRConfig
from ocr_three_layer_hybrid.interfaces import DocumentType


def test_single_image(service: OCRService, image_path: str, expected_type: str = "") -> Dict[str, Any]:
    """测试单张图片处理"""
    start_time = time.time()

    # OCR
    ocr_text = service.run_ocr(image_path)
    ocr_time = time.time() - start_time

    # 分类+提取
    result = service.process_single(image_path, ocr_text)
    total_time = time.time() - start_time

    return {
        "image_path": image_path,
        "file_name": Path(image_path).name,
        "expected_type": expected_type,
        "actual_type": result["classification"]["doc_type"],
        "route": result["classification"]["route"],
        "layer": result["extraction"]["layer"],
        "success": result["extraction"]["success"],
        "fields": result["extraction"]["fields"],
        "field_count": len([v for v in result["extraction"]["fields"].values() if v and v.strip()]),
        "ocr_time": round(ocr_time, 2),
        "total_time": round(total_time, 2),
        "error": result["extraction"].get("error_message", ""),
    }


def test_multi_page(service: OCRService, folder_path: str, max_pages: int = 10) -> Dict[str, Any]:
    """测试多页文档处理"""
    # 收集图片
    images = sorted([
        str(f) for f in Path(folder_path).iterdir()
        if f.is_file() and f.suffix.lower() in {'.jpg', '.jpeg', '.png'}
    ])

    if not images:
        return {"error": f"目录中没有图片: {folder_path}"}

    images_to_process = images[:max_pages]

    start_time = time.time()
    result = service.process_multi_page(images_to_process, max_pages=max_pages)
    total_time = time.time() - start_time

    return {
        "folder_path": folder_path,
        "total_pages": len(images),
        "processed_pages": len(images_to_process),
        "doc_type": result["classification"]["doc_type"],
        "layer": result["extraction"]["layer"],
        "success": result["extraction"]["success"],
        "fields": result["extraction"]["fields"],
        "field_count": len([v for v in result["extraction"]["fields"].values() if v and v.strip()]),
        "total_time": round(total_time, 2),
        "error": result["extraction"].get("error_message", ""),
    }


def main():
    """主测试流程"""
    # 测试数据路径
    sample_base = Path("/Users/dongsun/Github/sample-OCR")

    # 初始化服务（使用 Qwen2.5-VL-7B 作为 VLM 引擎）
    config = OCRConfig()
    config.vlm_extraction_engine = "qwen2_5_vl_7b"
    service = OCRService(config)

    print("=" * 80)
    print("v2.0 架构定向评测")
    print("=" * 80)
    print(f"VLM引擎: Qwen2.5-VL-7B (端口8082)")
    print()

    # ========== 测试1: 单张图片分类和提取 ==========
    print("【测试1】单张图片分类和提取")
    print("-" * 60)

    test_images = [
        # 增量房业务
        ("增量房图片资料/202402190050", "购房合同", "202402190050/02f6e6e2e8c197b68f1f2f8e8e8e8e8e.jpg"),
        # 存量房业务
        ("存量房图片资料/BBJZ-2025-1013085", "存量房合同", "BBJZ-2025-1013085/027aa4151f75424c8529755ada5e6064.jpg"),
    ]

    for base_dir, expected, img_rel in test_images:
        img_path = sample_base / base_dir.split("/")[0] / img_rel.split("/")[0] / img_rel.split("/")[1]
        if img_path.exists():
            result = test_single_image(service, str(img_path), expected)
            print(f"\n📄 {result['file_name']}")
            print(f"   期望类型: {expected}")
            print(f"   实际类型: {result['actual_type']}")
            print(f"   路由: {result['route']}")
            print(f"   提取层: {result['layer']}")
            print(f"   提取字段: {result['field_count']} 个")
            print(f"   耗时: {result['total_time']}s")
            if result['fields']:
                for k, v in result['fields'].items():
                    if v and v.strip():
                        print(f"     - {k}: {v[:50]}{'...' if len(v) > 50 else ''}")
            if result['error']:
                print(f"   ❌ 错误: {result['error']}")
        else:
            print(f"\n⚠️  图片不存在: {img_path}")

    # ========== 测试2: 多页文档处理（购房合同） ==========
    print("\n\n【测试2】多页文档处理（购房合同）")
    print("-" * 60)

    contract_folder = sample_base / "增量房图片资料" / "202402190050"
    if contract_folder.exists():
        result = test_multi_page(service, str(contract_folder), max_pages=5)
        print(f"\n📁 目录: {contract_folder.name}")
        print(f"   总页数: {result.get('total_pages', 0)}")
        print(f"   处理页数: {result.get('processed_pages', 0)}")
        print(f"   文档类型: {result.get('doc_type', 'unknown')}")
        print(f"   提取层: {result.get('layer', 'none')}")
        print(f"   成功: {result.get('success', False)}")
        print(f"   提取字段: {result.get('field_count', 0)} 个")
        print(f"   总耗时: {result.get('total_time', 0)}s")
        if result.get('fields'):
            print(f"   提取结果:")
            for k, v in result['fields'].items():
                if v and v.strip():
                    print(f"     - {k}: {v[:60]}{'...' if len(v) > 60 else ''}")
        if result.get('error'):
            print(f"   ❌ 错误: {result['error']}")
    else:
        print(f"\n⚠️  目录不存在: {contract_folder}")

    # ========== 测试3: 存量房合同多页处理 ==========
    print("\n\n【测试3】多页文档处理（存量房合同）")
    print("-" * 60)

    stock_folder = sample_base / "存量房图片资料" / "BBJZ-2025-1013085"
    if stock_folder.exists():
        result = test_multi_page(service, str(stock_folder), max_pages=5)
        print(f"\n📁 目录: {stock_folder.name}")
        print(f"   总页数: {result.get('total_pages', 0)}")
        print(f"   处理页数: {result.get('processed_pages', 0)}")
        print(f"   文档类型: {result.get('doc_type', 'unknown')}")
        print(f"   提取层: {result.get('layer', 'none')}")
        print(f"   成功: {result.get('success', False)}")
        print(f"   提取字段: {result.get('field_count', 0)} 个")
        print(f"   总耗时: {result.get('total_time', 0)}s")
        if result.get('fields'):
            print(f"   提取结果:")
            for k, v in result['fields'].items():
                if v and v.strip():
                    print(f"     - {k}: {v[:60]}{'...' if len(v) > 60 else ''}")
        if result.get('error'):
            print(f"   ❌ 错误: {result['error']}")
    else:
        print(f"\n⚠️  目录不存在: {stock_folder}")

    # ========== 测试4: UNKNOWN文档类型识别+提取 ==========
    print("\n\n【测试4】UNKNOWN文档类型识别+提取")
    print("-" * 60)
    print("(使用无法分类的文档测试VLM的类型识别+提取组合功能)")
    print("（需要找到一个无法被规则分类器识别的文档）")

    print("\n" + "=" * 80)
    print("评测完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
