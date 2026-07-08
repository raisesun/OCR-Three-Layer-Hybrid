#!/usr/bin/env python3
"""
用云端doubao-seed-2.0-pro基线数据作为ground truth，重新评估50张样本的准确率
V2: 使用子串匹配代替正则解析，更稳健
"""

import json
import re
from pathlib import Path
from collections import defaultdict

BASELINE_FILE = Path('/Users/dongsun/Github/sample-OCR/test_base_V2.0_full50.json')
SAMPLES_FILE = Path('/Users/dongsun/github/OCR-Three-Layer-Hybrid/tests/batch_test_50_samples.json')
TEST_RESULTS_FILE = Path('/Users/dongsun/github/OCR-Three-Layer-Hybrid/tests/batch_test_results_50.json')
OUTPUT_FILE = Path('/Users/dongsun/github/OCR-Three-Layer-Hybrid/tests/batch_test_report_v2.md')


def infer_doc_type_from_text(text: str) -> str:
    """从云端OCR文本推断文档类型"""
    if '居民身份证' in text and '公民身份号码' in text:
        return 'ID_CARD_FRONT'
    if '居民身份证' in text and ('签发机关' in text or '有效期限' in text) and '公民身份号码' not in text:
        return 'ID_CARD_BACK'
    if '结婚证' in text and '离婚' not in text:
        return 'MARRIAGE_CERTIFICATE'
    if '离婚证' in text or ('离婚' in text and '婚姻登记' in text and '常住' not in text):
        return 'DIVORCE_CERTIFICATE'
    if '常住人口登记卡' in text or '户口簿' in text or ('户别' in text and '户主' in text and '常住' in text):
        return 'HOUSEHOLD_REGISTER'
    if '商品房买卖合同' in text or ('买受人' in text and '出卖人' in text and '合同编号' in text):
        return 'PURCHASE_CONTRACT'
    if '不动产权证书' in text or ('不动产权' in text and '权利人' in text):
        return 'PROPERTY_CERTIFICATE'
    if '发票' in text and ('不动产' in text or '购房' in text):
        return 'INVOICE'
    if '存量房交易资金监管' in text or '资金监管协议' in text:
        return 'FUND_SUPERVISION'
    return 'UNKNOWN'


def normalize_for_compare(value: str) -> str:
    """标准化字段值用于比较：移除空格、标点、单位"""
    if not value:
        return ""
    v = str(value).strip()
    v = re.sub(r'[\s ,，.·:：\-_()（）\[\]【】{}]+', '', v)
    v = re.sub(r'(平方米|m2|m²|㎡|元|元整)$', '', v)
    return v


def value_in_text(value: str, text: str) -> bool:
    """检查字段值是否出现在文本中（子串匹配，容忍格式差异）"""
    if not value:
        return False
    nv = normalize_for_compare(value)
    nt = normalize_for_compare(text)
    if len(nv) < 2:
        return nv == nt
    return nv in nt


def evaluate_field(field_name: str, extracted_val: str, cloud_text: str) -> str:
    """
    评估单个字段：
    - 'exact': 值在云端文本中找到
    - 'partial': 值的部分内容在云端文本中找到
    - 'missed': 值为空但云端文本中可能有
    - 'wrong': 值非空但不在云端文本中
    - 'unknown': 无法判断（云端文本中可能没有这个字段）
    """
    if not extracted_val:
        return 'missed'

    # 完全匹配
    if value_in_text(extracted_val, cloud_text):
        return 'exact'

    # 部分匹配 - 取值的关键词（如姓名取整个值，地址取前几个字）
    nv = normalize_for_compare(extracted_val)
    nt = normalize_for_compare(cloud_text)

    # 对于姓名等短字段，检查是否完全包含
    if len(nv) <= 4:
        if nv in nt:
            return 'exact'
        return 'wrong'

    # 对于地址等长字段，检查是否有50%以上的内容匹配
    # 滑动窗口检查
    match_len = 0
    best_match = 0
    for i in range(len(nv)):
        if i < len(nt) and nv[i] == nt[i]:
            match_len += 1
            best_match = max(best_match, match_len)
        else:
            match_len = 0

    if best_match >= len(nv) * 0.5:
        return 'partial'

    # 尝试在全文中搜索子串
    # 对于长文本，取前一半和后一半分别搜索
    half = len(nv) // 2
    if half > 2:
        first_half = nv[:half]
        second_half = nv[half:]
        if first_half in nt or second_half in nt:
            return 'partial'

    return 'wrong'


def main():
    print("=" * 60)
    print("用云端基线数据重新评估准确率 (V2 - 子串匹配)")
    print("=" * 60)

    with open(BASELINE_FILE) as f:
        baseline = json.load(f)
    with open(SAMPLES_FILE) as f:
        samples = json.load(f)
    with open(TEST_RESULTS_FILE) as f:
        test_results = json.load(f)

    baseline_map = {r['filename']: r for r in baseline['results']}
    classifier_map = {r['image']: r for r in test_results['classifier']['results']}
    rule_map = {r['image']: r for r in test_results['rule_layer']['results']}
    vlm_map = {r['image']: r for r in test_results['vlm_layer']['results']}
    llm_map = {r['image']: r for r in test_results['llm_layer']['results']}

    # 分类器评估
    classifier_stats = defaultdict(lambda: {"total": 0, "correct": 0, "wrong": 0})
    classifier_details = []

    # 各层提取评估
    layer_stats = {"RULE": {"total": 0, "exact": 0, "partial": 0, "missed": 0, "wrong": 0},
                   "VLM": {"total": 0, "exact": 0, "partial": 0, "missed": 0, "wrong": 0},
                   "LLM": {"total": 0, "exact": 0, "partial": 0, "missed": 0, "wrong": 0}}
    extraction_details = []

    # 按文档类型统计
    type_stats = defaultdict(lambda: {"total": 0, "exact": 0, "partial": 0, "missed": 0, "wrong": 0})

    for sample in samples:
        image = sample['image']
        cert_code = sample['cert_code']

        if image not in baseline_map:
            continue

        cloud_text = baseline_map[image]['recognition']['text']
        inferred_type = infer_doc_type_from_text(cloud_text)

        # === 分类器评估 ===
        if image in classifier_map:
            cr = classifier_map[image]
            actual = cr['actual']

            type_match = False
            if 'ID_CARD' in inferred_type and actual == 'ID_CARD':
                type_match = True
            elif inferred_type == 'MARRIAGE_CERTIFICATE' and actual == 'MARRIAGE_CERTIFICATE':
                type_match = True
            elif inferred_type == 'DIVORCE_CERTIFICATE' and actual == 'MARRIAGE_CERTIFICATE':
                type_match = True
            elif inferred_type == 'HOUSEHOLD_REGISTER' and actual == 'HOUSEHOLD_REGISTER':
                type_match = True
            elif inferred_type == 'PURCHASE_CONTRACT' and actual == 'PURCHASE_CONTRACT':
                type_match = True
            elif inferred_type == 'PROPERTY_CERTIFICATE' and actual == 'PROPERTY_CERTIFICATE':
                type_match = True
            elif inferred_type == 'INVOICE' and actual == 'PROPERTY_CERTIFICATE':
                type_match = True
            elif inferred_type == 'FUND_SUPERVISION' and actual in ('PURCHASE_CONTRACT', 'PROPERTY_CERTIFICATE'):
                type_match = True

            classifier_stats[cert_code]["total"] += 1
            if type_match:
                classifier_stats[cert_code]["correct"] += 1
            else:
                classifier_stats[cert_code]["wrong"] += 1

            classifier_details.append({
                "image": image[:20],
                "cert_code": cert_code,
                "inferred_type": inferred_type,
                "actual": actual,
                "correct": type_match,
            })

        # === 提取层评估 ===
        layers_to_check = []
        if image in rule_map:
            layers_to_check.append(("RULE", rule_map[image].get('extracted_fields', {})))
        if image in vlm_map:
            layers_to_check.append(("VLM", vlm_map[image].get('extracted_fields', {})))
        if image in llm_map:
            layers_to_check.append(("LLM", llm_map[image].get('extracted_fields', {})))

        for layer_name, extracted_fields in layers_to_check:
            for field_name, ext_val in extracted_fields.items():
                if not ext_val:  # 跳过空值
                    layer_stats[layer_name]["missed"] += 1
                    type_stats[cert_code]["missed"] += 1
                    continue

                status = evaluate_field(field_name, ext_val, cloud_text)
                layer_stats[layer_name][status] += 1
                layer_stats[layer_name]["total"] += 1
                type_stats[cert_code][status] += 1
                type_stats[cert_code]["total"] += 1

                extraction_details.append({
                    "image": image[:20],
                    "layer": layer_name,
                    "cert_code": cert_code,
                    "field": field_name,
                    "extracted": ext_val,
                    "status": status,
                })

    # === 输出结果 ===
    total_cls = sum(s["total"] for s in classifier_stats.values())
    correct_cls = sum(s["correct"] for s in classifier_stats.values())
    cls_acc = correct_cls / total_cls if total_cls > 0 else 0

    print("\n" + "=" * 60)
    print("分类器评估结果")
    print("=" * 60)
    print(f"总准确率: {correct_cls}/{total_cls} = {cls_acc:.1%}\n")
    print("按文档类型:")
    for doc_type, stats in sorted(classifier_stats.items()):
        acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
        print(f"  {doc_type:25s}: {stats['correct']}/{stats['total']} = {acc:.0%}")

    print("\n" + "=" * 60)
    print("各层提取评估结果 (子串匹配)")
    print("=" * 60)
    for layer in ["RULE", "VLM", "LLM"]:
        s = layer_stats[layer]
        total = s["total"]
        if total == 0:
            continue
        exact_acc = s["exact"] / total
        partial_acc = (s["exact"] + s["partial"] * 0.5) / total
        print(f"\n{layer}层:")
        print(f"  总字段: {total}")
        print(f"  完全匹配: {s['exact']} ({exact_acc:.0%})")
        print(f"  部分匹配: {s['partial']}")
        print(f"  遗漏(空值): {s['missed']}")
        print(f"  错误: {s['wrong']}")
        print(f"  准确率(完全+0.5*部分): {partial_acc:.1%}")

    print("\n" + "=" * 60)
    print("按文档类型的提取准确率")
    print("=" * 60)
    for doc_type, stats in sorted(type_stats.items()):
        total = stats["total"]
        if total == 0:
            continue
        acc = (stats["exact"] + stats["partial"] * 0.5) / total
        print(f"  {doc_type:25s}: {acc:.1%} (exact={stats['exact']}, partial={stats['partial']}, missed={stats['missed']}, wrong={stats['wrong']})")

    # 生成报告
    _generate_report(classifier_details, classifier_stats, layer_stats, type_stats, extraction_details)


def _generate_report(classifier_details, classifier_stats, layer_stats, type_stats, extraction_details):
    lines = []
    lines.append("# 50张样本批量测试报告 V2（基于云端基线 + 子串匹配）\n")
    lines.append("> Ground Truth: doubao-seed-2.0-pro 云端模型")
    lines.append("> 评估方法: 将系统提取的字段值与云端OCR文本做子串匹配")
    lines.append("> 评估时间: 2026-06-28\n")

    lines.append("## 一、总体结果\n")
    total_cls = sum(s["total"] for s in classifier_stats.values())
    correct_cls = sum(s["correct"] for s in classifier_stats.values())
    cls_acc = correct_cls / total_cls if total_cls > 0 else 0

    lines.append(f"### 分类器: {cls_acc:.1%} ({correct_cls}/{total_cls})\n")
    lines.append("| 文档类型 | 正确 | 总数 | 准确率 |")
    lines.append("|---------|------|------|--------|")
    for doc_type, stats in sorted(classifier_stats.items()):
        acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
        lines.append(f"| {doc_type} | {stats['correct']} | {stats['total']} | {acc:.0%} |")

    lines.append("\n### 提取层准确率\n")
    lines.append("| 层级 | 完全匹配 | 部分匹配 | 遗漏 | 错误 | 综合准确率 |")
    lines.append("|------|---------|---------|------|------|-----------|")
    for layer in ["RULE", "VLM", "LLM"]:
        s = layer_stats[layer]
        total = s["total"]
        if total == 0:
            continue
        acc = (s["exact"] + s["partial"] * 0.5) / total
        lines.append(f"| {layer} | {s['exact']} | {s['partial']} | {s['missed']} | {s['wrong']} | **{acc:.1%}** |")

    lines.append("\n### 按文档类型统计\n")
    lines.append("| 文档类型 | 字段总数 | 完全匹配 | 部分匹配 | 遗漏 | 错误 | 准确率 |")
    lines.append("|---------|---------|---------|---------|------|------|--------|")
    for doc_type, stats in sorted(type_stats.items()):
        total = stats["total"]
        if total == 0:
            continue
        acc = (stats["exact"] + stats["partial"] * 0.5) / total
        lines.append(f"| {doc_type} | {total} | {stats['exact']} | {stats['partial']} | {stats['missed']} | {stats['wrong']} | {acc:.1%} |")

    # 分类器错误详情
    lines.append("\n## 二、分类器错误详情\n")
    lines.append("| 图片 | 预期类型 | 云端推断 | 系统分类 |")
    lines.append("|------|---------|---------|---------|")
    for d in classifier_details:
        if not d["correct"]:
            lines.append(f"| {d['image']}... | {d['cert_code']} | {d['inferred_type']} | {d['actual']} |")

    # 错误提取详情
    lines.append("\n## 三、提取错误详情 (wrong字段)\n")
    lines.append("| 图片 | 层级 | 类型 | 字段 | 提取值 |")
    lines.append("|------|------|------|------|--------|")
    wrong_count = 0
    for d in extraction_details:
        if d["status"] == "wrong":
            lines.append(f"| {d['image']}... | {d['layer']} | {d['cert_code']} | {d['field']} | {d['extracted'][:30]} |")
            wrong_count += 1
            if wrong_count >= 50:
                lines.append(f"| ... | 还有更多 | | | |")
                break

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"\n报告已保存: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
