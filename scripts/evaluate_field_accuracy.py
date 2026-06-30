#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段级准确率评估脚本

使用 baseline_fields.json 作为 ground truth，
逐字段对比系统提取结果与基线数据，计算字段级准确率。

用法:
    python3 scripts/evaluate_field_accuracy.py               # 全量评估
    python3 scripts/evaluate_field_accuracy.py --limit 5     # 前5张测试
    python3 scripts/evaluate_field_accuracy.py --case 202402190050  # 指定Case
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 添加路径
PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR / "src"))
sys.path.insert(0, str(PROJECT_DIR / "demo"))

from ocr_service import OCRService
from baseline_service import BaselineService


# ========== 配置 ==========

BASELINE_DIR = Path("/Users/dongsun/Github/sample-OCR/baseline_v3")
BASELINE_FILE = BASELINE_DIR / "baseline_8cases.json"
FIELDS_FILE = BASELINE_DIR / "baseline_fields.json"
OUTPUT_FILE = PROJECT_DIR / "field_accuracy_report.json"

# 字段名映射（系统提取的字段名 → 基线字段名）
FIELD_NAME_MAP: Dict[str, Dict[str, str]] = {
    "不动产权证书": {
        "不动产权证书号": "证书号",
        "房屋坐落": "房屋地址",
    },
    "发票": {
        "不含税金额": "",  # 基线无此字段
        "税额": "",         # 基线无此字段
    },
}


# ========== 工具函数 ==========

def normalize(value: str) -> str:
    """标准化字段值用于比较"""
    if not value:
        return ""
    # 去除首尾空白
    v = value.strip()
    # 统一标点
    v = v.replace("（", "(").replace("）", ")")
    v = v.replace("：", ":").replace("，", ",")
    v = v.replace("—", "-").replace("–", "-")
    # 地址字段：去除内部空格（OCR 输出 "445号 6排8号" vs 基线 "445号6排8号"）
    # 对于包含地址关键词的字段，去掉所有空格再比较
    if any(k in v for k in ("号", "路", "街", "区", "市", "省", "县", "镇", "乡", "村")):
        v_no_space = v.replace(" ", "")
        if len(v_no_space) > 5:  # 避免短值误处理
            v = v_no_space
    # 去除多余空格
    v = " ".join(v.split())
    return v


def compare_field(expected: str, actual: str) -> Tuple[str, bool]:
    """
    对比单个字段值

    Returns:
        (match_type, is_correct)
        match_type: "exact" | "normalized" | "partial" | "missed" | "wrong" | "empty_both"
    """
    exp = normalize(expected)
    act = normalize(actual)

    # 都为空
    if not exp and not act:
        return ("empty_both", True)

    # 精确匹配
    if exp == act:
        return ("exact", True)

    # 标准化后匹配
    if exp and act and exp == act:
        return ("normalized", True)

    # 关系字段语义等价（"配偶" = "妻"/"夫"，"户主" 可对应不同称呼）
    RELATION_SYNONYMS = {
        "配偶": {"妻", "夫", "妻子", "丈夫"},
        "妻": {"配偶", "妻子"},
        "夫": {"配偶", "丈夫"},
    }
    if exp in RELATION_SYNONYMS and act in RELATION_SYNONYMS[exp]:
        return ("normalized", True)

    # 部分匹配（互相包含）
    if exp and act:
        if exp in act or act in exp:
            return ("partial", True)

    # 基线有值但系统未提取
    if exp and not act:
        return ("missed", False)

    # 基线无值但系统提取了（不算错，但标记）
    if not exp and act:
        return ("extra", True)

    # 都有值但不匹配
    return ("wrong", False)


def get_baseline_fields(filename: str, baseline_fields: Dict) -> Optional[Dict[str, str]]:
    """从基线字段数据中获取指定图片的字段 ground truth"""
    for case in baseline_fields.get("cases", []):
        for img in case.get("images", []):
            if img.get("filename") == filename:
                return img.get("fields", {})
    return None


def load_baseline_images() -> List[Dict]:
    """加载基线图片列表（用于评估，复用 BaselineService）"""
    svc = BaselineService()
    return svc.get_all_images()


def evaluate_field_accuracy(
    limit: Optional[int] = None,
    case_filter: Optional[str] = None,
):
    """
    字段级准确率评估

    Args:
        limit: 最多评估N张图片（调试用）
        case_filter: 只评估指定Case
    """
    print("=" * 60)
    print("字段级准确率评估")
    print("=" * 60)

    # 加载数据
    with open(FIELDS_FILE, "r", encoding="utf-8") as f:
        baseline_fields = json.load(f)

    all_images = load_baseline_images()

    # 过滤
    if case_filter:
        all_images = [img for img in all_images if img.get("case_id") == case_filter]

    if limit:
        all_images = all_images[:limit]

    # 过滤掉文件不存在的图片
    valid_images = [img for img in all_images if Path(img.get("file_path", "")).exists()]
    skipped = len(all_images) - len(valid_images)
    if skipped > 0:
        print(f"⏭️ 跳过 {skipped} 张（文件不存在）")

    print(f"\n📊 评估图片数: {len(valid_images)}")
    print(f"📁 基线文件: {FIELDS_FILE}")
    print()

    # 初始化服务
    ocr_service = OCRService(enable_vlm_fallback=True)

    # 逐张评估
    total_fields = 0
    match_stats = {"exact": 0, "normalized": 0, "partial": 0, "missed": 0, "extra": 0, "empty_both": 0, "wrong": 0}
    type_stats = defaultdict(lambda: {"total": 0, "correct": 0, "match": defaultdict(int)})
    field_stats = defaultdict(lambda: {"total": 0, "exact": 0, "partial": 0, "missed": 0, "wrong": 0, "empty_both": 0, "extra": 0})
    errors = []
    results = []

    start_time = time.time()

    for idx, img in enumerate(valid_images, 1):
        file_path = img["file_path"]
        filename = img.get("file_name", Path(file_path).name)
        expected_type = img["expected_type"]
        text = img.get("text", "")

        # 获取基线字段
        baseline = get_baseline_fields(filename, baseline_fields)
        if baseline is None:
            continue

        # 运行系统处理
        try:
            result = ocr_service.process_single(file_path, text)
        except Exception as e:
            errors.append({"filename": filename, "error": str(e)})
            continue

        # 提取系统字段
        system_fields = result.get("extraction", {}).get("fields", {})

        # 逐字段对比
        all_field_names = set(list(baseline.keys()) + list(system_fields.keys()))
        img_correct = 0
        img_total = 0

        for field_name in all_field_names:
            expected_val = baseline.get(field_name, "")
            actual_val = system_fields.get(field_name, "")

            match_type, is_correct = compare_field(expected_val, actual_val)
            img_total += 1
            total_fields += 1
            match_stats[match_type] += 1

            if is_correct:
                img_correct += 1

            # 按字段名统计
            field_stats[field_name]["total"] += 1
            if match_type in field_stats[field_name]:
                field_stats[field_name][match_type] += 1

            # 记录错误
            if match_type in ("missed", "wrong"):
                errors.append({
                    "filename": filename,
                    "doc_type": expected_type,
                    "field": field_name,
                    "expected": expected_val,
                    "actual": actual_val,
                    "match_type": match_type,
                })

        # 按类型统计
        type_stats[expected_type]["total"] += img_total
        type_stats[expected_type]["correct"] += img_correct
        type_stats[expected_type]["match"]["exact"] += sum(
            1 for fn in all_field_names
            if compare_field(
                baseline.get(fn, ""), system_fields.get(fn, "")
            )[0] in ("exact", "normalized")
        )

        results.append({
            "filename": filename,
            "doc_type": expected_type,
            "field_accuracy": round(img_correct / img_total * 100, 1) if img_total > 0 else 0,
            "total_fields": img_total,
            "correct_fields": img_correct,
        })

        # 进度
        acc = round(img_correct / img_total * 100, 1) if img_total > 0 else 0
        print(f"  [{idx}/{len(valid_images)}] {filename} ({expected_type}) — 字段准确率: {acc}% ({img_correct}/{img_total})")

    total_time = time.time() - start_time

    # ========== 统计汇总 ==========

    print("\n" + "=" * 60)
    print("评估结果汇总")
    print("=" * 60)

    # 总体准确率
    correct_fields = match_stats["exact"] + match_stats["normalized"] + match_stats["empty_both"] + match_stats["partial"] + match_stats["extra"]
    wrong_fields = match_stats["missed"] + match_stats["wrong"]
    overall_accuracy = round(correct_fields / total_fields * 100, 1) if total_fields > 0 else 0

    print(f"\n📊 总体统计:")
    print(f"  总字段数: {total_fields}")
    print(f"  匹配字段: {correct_fields} (精确={match_stats['exact']}, 标准化={match_stats['normalized']}, 部分={match_stats['partial']}, 都为空={match_stats['empty_both']}, 额外={match_stats['extra']})")
    print(f"  不匹配字段: {wrong_fields} (遗漏={match_stats['missed']}, 错误={match_stats['wrong']})")
    print(f"  字段级准确率: {overall_accuracy}%")

    # 精确匹配率（只算 exact + normalized）
    strict_correct = match_stats["exact"] + match_stats["normalized"]
    strict_accuracy = round(strict_correct / total_fields * 100, 1) if total_fields > 0 else 0
    print(f"  严格准确率(精确匹配): {strict_accuracy}%")

    # 按文档类型
    print(f"\n📋 按文档类型:")
    for doc_type, stats in sorted(type_stats.items()):
        if stats["total"] > 0:
            acc = round(stats["correct"] / stats["total"] * 100, 1)
            print(f"  {doc_type}: {acc}% ({stats['correct']}/{stats['total']})")

    # 按字段名
    print(f"\n🔍 按字段名:")
    for field_name, stats in sorted(field_stats.items(), key=lambda x: -x[1]["total"]):
        total = stats["total"]
        exact = stats.get("exact", 0)
        partial = stats.get("partial", 0)
        missed = stats.get("missed", 0)
        wrong = stats.get("wrong", 0)
        acc = round((exact + partial) / total * 100, 1) if total > 0 else 0
        print(f"  {field_name}: {acc}% (精确={exact}, 部分={partial}, 遗漏={missed}, 错误={wrong}, 总={total})")

    # 耗时
    avg_time = round(total_time / len(valid_images) * 1000, 1) if valid_images else 0
    print(f"\n⏱️  耗时: {total_time:.1f}s ({avg_time}ms/张)")

    # 错误详情（前20条）
    if errors:
        print(f"\n❌ 字段错误详情 (共 {len(errors)} 条，显示前20条):")
        for err in errors[:20]:
            print(f"  [{err['doc_type']}] {err['filename']}: {err['field']}")
            print(f"    期望: '{err['expected']}'")
            print(f"    实际: '{err['actual']}'")
            print(f"    类型: {err['match_type']}")

    # 保存详细结果
    report = {
        "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_images": len(valid_images),
        "total_fields": total_fields,
        "overall_accuracy": overall_accuracy,
        "strict_accuracy": strict_accuracy,
        "match_stats": match_stats,
        "type_accuracy": {
            t: {
                "total": s["total"],
                "correct": s["correct"],
                "accuracy": round(s["correct"] / s["total"] * 100, 1) if s["total"] > 0 else 0,
            }
            for t, s in type_stats.items()
        },
        "field_accuracy": {
            fn: {
                "total": s["total"],
                "exact": s.get("exact", 0),
                "partial": s.get("partial", 0),
                "missed": s.get("missed", 0),
                "wrong": s.get("wrong", 0),
                "empty_both": s.get("empty_both", 0),
                "extra": s.get("extra", 0),
                "accuracy": round((s.get("exact", 0) + s.get("normalized", 0) + s.get("partial", 0) + s.get("empty_both", 0) + s.get("extra", 0)) / s["total"] * 100, 1) if s["total"] > 0 else 0,
            }
            for fn, s in field_stats.items()
        },
        "per_image": results,
        "errors": errors[:100],  # 最多保存100条
        "timing": {
            "total_s": round(total_time, 1),
            "avg_ms_per_image": avg_time,
        },
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n💾 详细报告已保存: {OUTPUT_FILE}")

    return report


# ========== Case-level (multi-page merge) evaluation ==========

def merge_fields(field_list: List[Dict[str, str]]) -> Dict[str, str]:
    """合并多页字段：取第一个非空值"""
    merged = {}
    for fields in field_list:
        for k, v in fields.items():
            if v and v.strip() and k not in merged:
                merged[k] = v
    return merged


def evaluate_case_level(
    limit: Optional[int] = None,
    case_filter: Optional[str] = None,
):
    """
    Case 级别字段准确率评估（多页合并）

    将同一 case 中相同文档类型的所有图片视为一个文档的多个页面，
    合并提取字段和基线字段后进行比较。
    """
    print("=" * 60)
    print("Case 级别字段准确率评估（多页合并）")
    print("=" * 60)

    # 加载数据
    with open(FIELDS_FILE, "r", encoding="utf-8") as f:
        baseline_fields = json.load(f)

    all_images = load_baseline_images()

    if case_filter:
        all_images = [img for img in all_images if img.get("case_id") == case_filter]

    # 过滤掉文件不存在的图片
    valid_images = [img for img in all_images if Path(img.get("file_path", "")).exists()]
    skipped = len(all_images) - len(valid_images)
    if skipped > 0:
        print(f"⏭️ 跳过 {skipped} 张（文件不存在）")

    print(f"\n📊 评估图片数: {len(valid_images)}")
    print(f"📁 基线文件: {FIELDS_FILE}")
    print()

    # 按 (case_id, expected_type) 分组
    from collections import defaultdict
    groups = defaultdict(list)
    for img in valid_images:
        key = (img.get("case_id", ""), img["expected_type"])
        groups[key].append(img)

    if limit:
        # 限制组数
        group_keys = list(groups.keys())[:limit]
        groups = {k: groups[k] for k in group_keys}

    # 初始化服务
    ocr_service = OCRService(enable_vlm_fallback=True)

    # 统计
    total_fields = 0
    match_stats = {"exact": 0, "normalized": 0, "partial": 0, "missed": 0, "extra": 0, "empty_both": 0, "wrong": 0}
    type_stats = defaultdict(lambda: {"total": 0, "correct": 0})
    field_stats = defaultdict(lambda: {"total": 0, "exact": 0, "partial": 0, "missed": 0, "wrong": 0, "empty_both": 0, "extra": 0})
    errors = []
    results = []

    start_time = time.time()
    group_idx = 0

    for (case_id, doc_type), imgs in sorted(groups.items()):
        group_idx += 1
        filenames = [img.get("file_name", Path(img["file_path"]).name) for img in imgs]

        # 处理所有页面并收集提取字段
        page_extracted = []
        page_baselines = []
        for img in imgs:
            file_path = img["file_path"]
            text = img.get("text", "")
            filename = img.get("file_name", Path(file_path).name)
            try:
                result = ocr_service.process_single(file_path, text)
                sys_fields = result.get("extraction", {}).get("fields", {})
                page_extracted.append(sys_fields)
            except Exception as e:
                page_extracted.append({})

            baseline = get_baseline_fields(filename, baseline_fields)
            page_baselines.append(baseline or {})

        # 合并字段
        merged_sys = merge_fields(page_extracted)
        merged_baseline = merge_fields(page_baselines)

        # 比较
        all_keys = set(list(merged_baseline.keys()) + list(merged_sys.keys()))
        correct = 0
        total = len(all_keys)

        for key in all_keys:
            exp = merged_baseline.get(key, "")
            act = merged_sys.get(key, "")
            mt, ok = compare_field(exp, act)
            total_fields += 1
            match_stats[mt] += 1
            if ok:
                correct += 1
            field_stats[key]["total"] += 1
            if mt in field_stats[key]:
                field_stats[key][mt] += 1
            if mt in ("missed", "wrong"):
                errors.append({
                    "case_id": case_id,
                    "doc_type": doc_type,
                    "field": key,
                    "expected": exp,
                    "actual": act,
                    "match_type": mt,
                    "pages": len(imgs),
                })

        type_stats[doc_type]["total"] += total
        type_stats[doc_type]["correct"] += correct
        acc = round(correct / total * 100, 1) if total > 0 else 0
        results.append({
            "case_id": case_id,
            "doc_type": doc_type,
            "pages": len(imgs),
            "field_accuracy": acc,
            "total_fields": total,
            "correct_fields": correct,
        })
        print(f"  [{group_idx}] {case_id} / {doc_type} ({len(imgs)}页) — 准确率: {acc}% ({correct}/{total})")

    total_time = time.time() - start_time

    # ========== 汇总 ==========
    print("\n" + "=" * 60)
    print("Case 级别评估结果汇总")
    print("=" * 60)

    correct_fields = match_stats["exact"] + match_stats["normalized"] + match_stats["empty_both"] + match_stats["partial"] + match_stats["extra"]
    wrong_fields = match_stats["missed"] + match_stats["wrong"]
    overall_accuracy = round(correct_fields / total_fields * 100, 1) if total_fields > 0 else 0
    strict_correct = match_stats["exact"] + match_stats["normalized"]
    strict_accuracy = round(strict_correct / total_fields * 100, 1) if total_fields > 0 else 0

    print(f"\n📊 总体统计:")
    print(f"  总字段数: {total_fields}")
    print(f"  匹配字段: {correct_fields} (精确={match_stats['exact']}, 部分={match_stats['partial']}, 都为空={match_stats['empty_both']}, 额外={match_stats['extra']})")
    print(f"  不匹配字段: {wrong_fields} (遗漏={match_stats['missed']}, 错误={match_stats['wrong']})")
    print(f"  字段级准确率: {overall_accuracy}%")
    print(f"  严格准确率(精确匹配): {strict_accuracy}%")

    print(f"\n📋 按文档类型:")
    for doc_type, stats in sorted(type_stats.items()):
        if stats["total"] > 0:
            acc = round(stats["correct"] / stats["total"] * 100, 1)
            print(f"  {doc_type}: {acc}% ({stats['correct']}/{stats['total']})")

    print(f"\n🔍 按字段名 (显示有错误的):")
    for field_name, stats in sorted(field_stats.items(), key=lambda x: -(x[1].get("missed", 0) + x[1].get("wrong", 0))):
        missed = stats.get("missed", 0)
        wrong = stats.get("wrong", 0)
        if missed + wrong > 0:
            total = stats["total"]
            exact = stats.get("exact", 0)
            partial = stats.get("partial", 0)
            acc = round((exact + partial) / total * 100, 1) if total > 0 else 0
            print(f"  {field_name}: {acc}% (精确={exact}, 部分={partial}, 遗漏={missed}, 错误={wrong}, 总={total})")

    avg_time = round(total_time / max(len(results), 1) * 1000, 1)
    print(f"\n⏱️  耗时: {total_time:.1f}s ({avg_time}ms/文档组)")

    if errors:
        print(f"\n❌ 字段错误详情 (共 {len(errors)} 条，显示前30条):")
        for err in errors[:30]:
            print(f"  [{err['doc_type']}] {err['case_id']}: {err['field']} ({err['pages']}页)")
            print(f"    期望: '{err['expected']}'")
            print(f"    实际: '{err['actual']}'")
            print(f"    类型: {err['match_type']}")

    # 保存报告
    report = {
        "eval_type": "case_level",
        "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_images": len(valid_images),
        "total_groups": len(results),
        "total_fields": total_fields,
        "overall_accuracy": overall_accuracy,
        "strict_accuracy": strict_accuracy,
        "match_stats": match_stats,
        "type_accuracy": {
            t: {"total": s["total"], "correct": s["correct"],
                "accuracy": round(s["correct"] / s["total"] * 100, 1) if s["total"] > 0 else 0}
            for t, s in type_stats.items()
        },
        "per_group": results,
        "errors": errors[:100],
    }
    output = PROJECT_DIR / "field_accuracy_report_case.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n💾 详细报告已保存: {output}")


# ========== CLI ==========

def main():
    parser = argparse.ArgumentParser(description="字段级准确率评估")
    parser.add_argument("--limit", type=int, help="最多评估N张图片/组")
    parser.add_argument("--case", type=str, help="只评估指定Case")
    parser.add_argument("--case-level", action="store_true",
                        help="Case级别评估（多页合并），默认图片级别")
    args = parser.parse_args()

    if args.case_level:
        evaluate_case_level(
            limit=args.limit,
            case_filter=args.case,
        )
    else:
        evaluate_field_accuracy(
            limit=args.limit,
            case_filter=args.case,
        )


if __name__ == "__main__":
    main()
