#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2.0 架构渐进式精度和速度评测

策略：
1. 先处理1个业务目录，建立单文件处理时间基准
2. 每次增加1-3个业务目录
3. 先读取所有图片，按时间基准预估处理时间
4. 如果超时或准确率低于90%，停下来分析
5. 如果正常，更新基准时间
"""

import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

# 添加路径
PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR / "src"))

from ocr_three_layer_hybrid.service import OCRService
from ocr_three_layer_hybrid.config import OCRConfig

# ========== 配置 ==========

BASELINE_FILE = Path("/Users/dongsun/Github/sample-OCR/baseline_v3/baseline_fields.json")
SAMPLE_BASE = Path("/Users/dongsun/Github/sample-OCR")

# 超时阈值（秒）- 单个业务目录的最大处理时间
TIMEOUT_PER_CASE = 600  # 10分钟
# 准确率阈值
ACCURACY_THRESHOLD = 0.90

# 业务目录列表（按图片数量从小到大排序）
INCREMENTAL_CASES = [
    "202404260010",   # 4张
    "202411070032",   # 5张
    "202402190050",   # 10张
    "202403180015",   # 10张
    "202403080014",   # 11张
    "202407200006",   # 11张
    "202410090006",   # 11张
    "202502050035",   # 12张
    "202410220008",   # 12张
    "202404250008",   # 13张
    "202402270015",   # 15张
    "202402280061",   # 16张
    "202406200020",   # 18张
    "202410040008",   # 18张
    "202408020050",   # 22张
    "202407040017",   # 23张
    "202404170016",   # 24张
    "202404010024",   # 34张
    "202406240010",   # 57张
    "202411060009",   # 58张
]

STOCK_CASES = [
    "BBJZ-2026-0122038",  # 18张
    "BBJZ-2026-0129012",  # 21张
    "BBJZ-2026-0128061",  # 22张
    "BBJZ-2026-0107026",  # 24张
    "BBJZ-2025-1013085",  # 26张
    "BBJZ-2026-0124005",  # 25张
    "BBJZ-2026-0113059",  # 26张
    "BBJZ-2026-0128021",  # 26张
    "BBJZ-2026-0129058",  # 26张
    "BBJZ-2026-0114007",  # 76张 (large!)
]


def load_baseline() -> Dict[str, Any]:
    """加载基线数据"""
    with open(BASELINE_FILE) as f:
        data = json.load(f)
    cases = {}
    for case in data['cases']:
        case_id = case['case_id']
        cases[case_id] = case
    return cases


def get_case_images(case_id: str) -> List[str]:
    """获取业务目录下的所有图片路径"""
    # 判断是增量房还是存量房
    if case_id.startswith("BBJZ"):
        base_dir = SAMPLE_BASE / "存量房图片资料" / case_id
    else:
        base_dir = SAMPLE_BASE / "增量房图片资料" / case_id

    if not base_dir.exists():
        return []

    images = sorted([
        str(f) for f in base_dir.iterdir()
        if f.is_file() and f.suffix.lower() in {'.jpg', '.jpeg', '.png'}
    ])
    return images


def process_case(
    service: OCRService,
    case_id: str,
    baseline_case: Dict = None,
) -> Dict[str, Any]:
    """处理单个业务目录"""
    images = get_case_images(case_id)
    if not images:
        return {"error": f"目录不存在或没有图片: {case_id}"}

    start_time = time.time()
    results = []

    for img_path in images:
        img_start = time.time()
        # OCR
        ocr_text = service.run_ocr(img_path)
        ocr_time = time.time() - img_start

        # 分类+提取
        result = service.process_single(img_path, ocr_text)
        img_time = time.time() - img_start

        results.append({
            "file_path": img_path,
            "file_name": Path(img_path).name,
            "ocr_time": round(ocr_time, 2),
            "total_time": round(img_time, 2),
            "doc_type": result["classification"]["doc_type"],
            "route": result["classification"]["route"],
            "layer": result["extraction"]["layer"],
            "success": result["extraction"]["success"],
            "fields": result["extraction"]["fields"],
            "field_count": len([v for v in result["extraction"]["fields"].values() if v and v.strip()]),
        })

    total_time = time.time() - start_time

    return {
        "case_id": case_id,
        "image_count": len(images),
        "results": results,
        "total_time": round(total_time, 2),
        "avg_time_per_image": round(total_time / len(images), 2),
    }


def evaluate_accuracy(
    case_result: Dict,
    baseline_case: Dict,
) -> Dict[str, Any]:
    """评估准确率"""
    if not baseline_case:
        return {"accuracy": None, "message": "无基线数据"}

    baseline_images = {img['filename']: img for img in baseline_case.get('images', [])}

    total_fields = 0
    correct_fields = 0
    type_correct = 0
    type_total = 0

    for result in case_result.get('results', []):
        filename = result['file_name']
        baseline_img = baseline_images.get(filename)
        if not baseline_img:
            continue

        # 类型准确率
        type_total += 1
        expected_type = baseline_img.get('doc_type', '')
        actual_type = result['doc_type']

        # DocumentType枚举值是中文，直接比较
        if actual_type == expected_type:
            type_correct += 1

        # 字段准确率
        expected_fields = baseline_img.get('fields', {})
        actual_fields = result.get('fields', {})

        for field_name, expected_value in expected_fields.items():
            if expected_value and str(expected_value).strip():
                total_fields += 1
                actual_value = actual_fields.get(field_name, '')
                # 简单的字符串匹配（去除空格后比较）
                if str(actual_value).strip() == str(expected_value).strip():
                    correct_fields += 1

    type_accuracy = type_correct / type_total if type_total > 0 else 0
    field_accuracy = correct_fields / total_fields if total_fields > 0 else 0

    return {
        "type_accuracy": round(type_accuracy, 4),
        "type_correct": type_correct,
        "type_total": type_total,
        "field_accuracy": round(field_accuracy, 4),
        "field_correct": correct_fields,
        "field_total": total_fields,
        "overall_accuracy": round((type_accuracy + field_accuracy) / 2, 4),
    }


def print_case_summary(case_result: Dict, accuracy: Dict):
    """打印单个业务目录的结果摘要"""
    case_id = case_result.get('case_id', 'unknown')
    image_count = case_result.get('image_count', 0)
    total_time = case_result.get('total_time', 0)
    avg_time = case_result.get('avg_time_per_image', 0)

    print(f"\n{'='*60}")
    print(f"业务目录: {case_id}")
    print(f"{'='*60}")
    print(f"图片数量: {image_count}")
    print(f"总耗时: {total_time:.1f}s ({total_time/60:.1f}分钟)")
    print(f"平均每张图片: {avg_time:.1f}s")

    # 文档类型分布
    type_dist = defaultdict(int)
    layer_dist = defaultdict(int)
    total_fields = 0
    for r in case_result.get('results', []):
        type_dist[r['doc_type']] += 1
        layer_dist[r['layer']] += 1
        total_fields += r['field_count']

    print(f"文档类型分布: {dict(type_dist)}")
    print(f"提取层分布: {dict(layer_dist)}")
    print(f"总提取字段数: {total_fields}")

    # 准确率
    if accuracy.get('type_accuracy') is not None:
        print(f"\n--- 准确率评估 ---")
        print(f"类型准确率: {accuracy['type_accuracy']*100:.1f}% ({accuracy['type_correct']}/{accuracy['type_total']})")
        print(f"字段准确率: {accuracy['field_accuracy']*100:.1f}% ({accuracy['field_correct']}/{accuracy['field_total']})")
        print(f"综合准确率: {accuracy['overall_accuracy']*100:.1f}%")


def main():
    """主测试流程"""
    print("="*60)
    print("v2.0 架构渐进式精度和速度评测")
    print("="*60)

    # 初始化服务
    config = OCRConfig()
    config.vlm_extraction_engine = "qwen2_5_vl_7b"
    service = OCRService(config)

    # 加载基线数据
    baseline = load_baseline()
    print(f"已加载 {len(baseline)} 个业务目录的基线数据")
    print(f"基线覆盖: {list(baseline.keys())}")

    # ========== Phase 1: 建立基准 ==========
    print("\n" + "="*60)
    print("Phase 1: 建立处理时间基准")
    print("="*60)

    # 选择一个有基线数据的小业务目录
    baseline_cases_with_data = [c for c in INCREMENTAL_CASES if c in baseline]
    if not baseline_cases_with_data:
        print("❌ 没有找到有基线数据的业务目录")
        return

    # 选择第一个有基线数据的case
    first_case = baseline_cases_with_data[0]  # 202402190050
    print(f"\n选择基准业务目录: {first_case}")

    images = get_case_images(first_case)
    print(f"图片数量: {len(images)}")

    # 处理第一个case
    print(f"\n开始处理 {first_case}...")
    case_result = process_case(service, first_case)
    baseline_case = baseline.get(first_case)
    accuracy = evaluate_accuracy(case_result, baseline_case)

    print_case_summary(case_result, accuracy)

    # 建立基准
    baseline_time_per_image = case_result['avg_time_per_image']
    print(f"\n📊 基准时间: {baseline_time_per_image:.1f}s/张")

    # 检查准确率
    if accuracy.get('overall_accuracy', 0) < ACCURACY_THRESHOLD:
        print(f"\n❌ 准确率 {accuracy['overall_accuracy']*100:.1f}% 低于阈值 {ACCURACY_THRESHOLD*100:.1f}%")
        print("停下来分析原因...")
        return
    else:
        print(f"\n✅ 准确率 {accuracy['overall_accuracy']*100:.1f}% 达标")

    # ========== Phase 2: 渐进式扩展 ==========
    print("\n" + "="*60)
    print("Phase 2: 渐进式扩展测试")
    print("="*60)

    # 接下来测试有基线数据的case
    remaining_cases = [c for c in baseline_cases_with_data if c != first_case]
    print(f"剩余有基线数据的业务目录: {remaining_cases}")

    current_baseline = baseline_time_per_image
    processed_cases = [first_case]

    for case_id in remaining_cases:
        print(f"\n--- 处理业务目录: {case_id} ---")

        images = get_case_images(case_id)
        estimated_time = len(images) * current_baseline
        print(f"图片数量: {len(images)}")
        print(f"预估处理时间: {estimated_time:.1f}s ({estimated_time/60:.1f}分钟)")

        # 检查是否超时
        if estimated_time > TIMEOUT_PER_CASE:
            print(f"❌ 预估时间 {estimated_time:.1f}s 超过阈值 {TIMEOUT_PER_CASE}s")
            print("停下来讨论优化方案...")
            break

        # 处理
        case_result = process_case(service, case_id)
        baseline_case = baseline.get(case_id)
        accuracy = evaluate_accuracy(case_result, baseline_case)

        print_case_summary(case_result, accuracy)

        # 更新基准（如果更快）
        if case_result['avg_time_per_image'] < current_baseline:
            current_baseline = case_result['avg_time_per_image']
            print(f"\n📊 更新基准时间: {current_baseline:.1f}s/张")

        # 检查准确率
        if accuracy.get('overall_accuracy', 0) < ACCURACY_THRESHOLD:
            print(f"\n❌ 准确率 {accuracy['overall_accuracy']*100:.1f}% 低于阈值 {ACCURACY_THRESHOLD*100:.1f}%")
            print("停下来分析原因...")
            break
        else:
            print(f"\n✅ 准确率 {accuracy['overall_accuracy']*100:.1f}% 达标")
            processed_cases.append(case_id)

    # ========== 汇总 ==========
    print("\n" + "="*60)
    print("测试汇总")
    print("="*60)
    print(f"已处理业务目录: {processed_cases}")
    print(f"最终基准时间: {current_baseline:.1f}s/张")
    print(f"超时阈值: {TIMEOUT_PER_CASE}s/业务目录")
    print(f"准确率阈值: {ACCURACY_THRESHOLD*100:.1f}%")


if __name__ == "__main__":
    main()
