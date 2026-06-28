#!/usr/bin/env python3
"""
端到端Pipeline测试

使用基线数据测试完整的分类+提取流程，报告：
1. 分类准确率
2. 提取成功率
3. 各步骤耗时
4. 各处理层的使用情况
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.vlm_classifier import VLMDocumentClassifier, HybridDocumentClassifier
from ocr_three_layer_hybrid.vlm_layer import VLMExtractionLayer
from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline


def load_baseline(baseline_file: str) -> Dict:
    """加载基线数据"""
    with open(baseline_file, "r", encoding="utf-8") as f:
        return json.load(f)


def run_e2e_test(baseline_file: str, enable_vlm_fallback: bool = True):
    """
    运行端到端测试

    Args:
        baseline_file: 基线数据文件路径
        enable_vlm_fallback: 是否启用VLM分类兜底
    """
    data = load_baseline(baseline_file)

    # 初始化Pipeline
    print("=" * 60)
    print("端到端Pipeline测试")
    print("=" * 60)
    print(f"基线数据: {baseline_file}")
    print(f"VLM分类兜底: {'启用' if enable_vlm_fallback else '禁用'}")
    print()

    # 创建Pipeline（包含VLM提取层）
    vlm_layer = VLMExtractionLayer()
    pipeline = PlanEPlusPipeline(
        enable_vlm_classification_fallback=enable_vlm_fallback,
        vlm_layer=vlm_layer,
    )

    # 统计变量
    total = 0
    correct = 0
    errors = []
    appendix_skipped = 0
    extraction_success = 0
    extraction_failed = 0

    # 按类型统计
    type_stats: Dict[str, Dict] = {}

    # 按处理层统计
    layer_stats: Dict[str, int] = {}

    total_start = time.time()

    for case in data["cases"]:
        for img in case["images"]:
            parsed = img.get("ocr_result", {}).get("parsed")
            if not parsed:
                continue

            expected_type = parsed.get("doc_type", "")
            if expected_type == "未知" or not expected_type:
                continue

            total += 1
            page_status = parsed.get("page_status", "")
            file_path = img.get("file_path", "")
            text = parsed.get("text", "")

            # 运行Pipeline
            start_time = time.time()
            result = pipeline.process(file_path, [text] if text else [])
            elapsed = time.time() - start_time

            # 获取实际类型
            actual_type = result.doc_type.value if result.doc_type else "未知"

            # 统计处理层
            layer_name = result.layer.value if result.layer else "unknown"
            layer_stats[layer_name] = layer_stats.get(layer_name, 0) + 1

            # 统计提取结果
            if result.success:
                if result.error_message == "附属页面，跳过提取":
                    appendix_skipped += 1
                else:
                    extraction_success += 1
            else:
                extraction_failed += 1

            # 统计类型分布
            if actual_type not in type_stats:
                type_stats[actual_type] = {"total": 0, "correct": 0}
            type_stats[actual_type]["total"] += 1

            # 检查分类是否正确
            is_correct = actual_type == expected_type
            # 附属页面特殊处理：VLM识别为附属页面也算正确
            if not is_correct and page_status == "附属页面" and actual_type == "未知":
                is_correct = True

            if is_correct:
                correct += 1
                type_stats[actual_type]["correct"] += 1
            else:
                errors.append({
                    "file": Path(file_path).name,
                    "case_id": case["case_id"],
                    "expected": expected_type,
                    "actual": actual_type,
                    "page_status": page_status,
                    "layer": layer_name,
                    "time": elapsed,
                })

    total_time = time.time() - total_start

    # 输出结果
    accuracy = correct / total * 100 if total > 0 else 0

    print("-" * 60)
    print("测试汇总")
    print("-" * 60)
    print(f"总图片数:        {total}")
    print(f"正确分类:        {correct} ({accuracy:.1f}%)")
    print(f"错误分类:        {len(errors)}")
    print(f"附属页面跳过:    {appendix_skipped}")
    print(f"提取成功:        {extraction_success}")
    print(f"提取失败:        {extraction_failed}")
    print(f"总耗时:          {total_time:.2f}s")
    print(f"平均每张:        {total_time/total*1000:.0f}ms")
    print()

    print("-" * 60)
    print("处理层使用统计")
    print("-" * 60)
    for layer, count in sorted(layer_stats.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        print(f"  {layer:12s}: {count:3d} ({pct:.1f}%)")
    print()

    print("-" * 60)
    print("文档类型分布")
    print("-" * 60)
    for doc_type, stats in sorted(type_stats.items(), key=lambda x: -x[1]["total"]):
        t = stats["total"]
        c = stats["correct"]
        acc = c / t * 100 if t > 0 else 0
        print(f"  {doc_type:12s}: {t:3d}张, 正确{c:3d} ({acc:.0f}%)")
    print()

    if errors:
        print("-" * 60)
        print(f"错误详情 ({len(errors)}个)")
        print("-" * 60)
        for e in errors:
            print(f"  [{e['case_id']}] {e['file']}")
            print(f"    期望: {e['expected']} → 实际: {e['actual']}")
            print(f"    页面状态: {e['page_status']}, 处理层: {e['layer']}")
            print()

    return {
        "total": total,
        "correct": correct,
        "errors": len(errors),
        "accuracy": accuracy,
        "appendix_skipped": appendix_skipped,
        "extraction_success": extraction_success,
        "extraction_failed": extraction_failed,
        "total_time": total_time,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="端到端Pipeline测试")
    parser.add_argument(
        "baseline_file",
        nargs="?",
        default="/Users/dongsun/Github/sample-OCR/baseline_v3/baseline_8cases.json",
        help="基线数据文件路径",
    )
    parser.add_argument(
        "--no-vlm-fallback",
        action="store_true",
        help="禁用VLM分类兜底",
    )

    args = parser.parse_args()

    if not Path(args.baseline_file).exists():
        print(f"错误: 文件不存在: {args.baseline_file}")
        sys.exit(1)

    result = run_e2e_test(
        args.baseline_file,
        enable_vlm_fallback=not args.no_vlm_fallback,
    )

    # 退出码：有错误返回1
    sys.exit(0 if result["errors"] == 0 else 1)


if __name__ == "__main__":
    main()
