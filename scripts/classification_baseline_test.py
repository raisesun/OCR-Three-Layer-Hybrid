#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分类准确率基线测试

用当前 KeywordDocumentClassifier 对 50 样本重跑分类，输出准确率报告。
基于 tests/archive/batch_test_results_50.ocr_cache.json 的 OCR 文本，
绕过 OCR 服务直接测分类逻辑（隔离分类与 OCR 两层）。

用法:
    python3 scripts/classification_baseline_test.py [--label 改前] [--out path]
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier

# cert_code -> 可接受的 doc_type.value 前缀集合
EXPECT_PREFIX = {
    "fund_supervision_certificate": ["资金监管凭证"],
    "fund_supervision": ["资金监管协议"],
    "property": ["不动产权证书"],
    "id_card_front": ["身份证"],
    "id_card_back": ["身份证"],
    "household_register": ["户口本"],
    "hukou": ["户口本"],
    "marriage": ["结婚证"],
    "divorce_certificate": ["离婚证"],
    "divorce_agreement": ["离婚协议"],
    "purchase_contract": ["购房合同"],
    "stock_contract": ["存量房合同"],
    "invoice": ["发票"],
}

ROOT = Path(__file__).resolve().parent.parent
OCR_CACHE = ROOT / "tests" / "archive" / "batch_test_results_50.ocr_cache.json"
SAMPLES = ROOT / "tests" / "results" / "batch_test_50_samples.json"


def classify_all():
    cache = json.load(open(OCR_CACHE))
    samples = json.load(open(SAMPLES))
    clf = KeywordDocumentClassifier()

    results = []
    for s in samples:
        img = s["image"]
        key = [k for k in cache if img.split(".")[0] in k]
        if not key:
            results.append({"image": img, "cert_code": s["cert_code"], "skipped": "no_ocr"})
            continue
        text = " ".join(cache[key[0]][0])
        info = clf.classify_from_text(key[0], text)
        expect_prefixes = EXPECT_PREFIX.get(s["cert_code"], [])
        ok = any(info.doc_type.value.startswith(p) for p in expect_prefixes)
        results.append({
            "image": img,
            "case_id": s.get("case_id", ""),
            "cert_code": s["cert_code"],
            "expected_prefix": expect_prefixes,
            "actual_type": info.doc_type.value,
            "confidence": round(info.confidence, 3),
            "correct": ok,
            "route": info.metadata.get("route", "") if info.metadata else "",
        })
    return results


def summarize(results):
    total = sum(1 for r in results if not r.get("skipped"))
    correct = sum(1 for r in results if r.get("correct"))
    by_type = defaultdict(lambda: {"n": 0, "ok": 0})
    errors = []
    for r in results:
        if r.get("skipped"):
            continue
        t = r["cert_code"]
        by_type[t]["n"] += 1
        if r["correct"]:
            by_type[t]["ok"] += 1
        else:
            errors.append(r)
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total * 100, 1) if total else 0,
        "by_type": {k: {"n": v["n"], "ok": v["ok"], "accuracy": round(v["ok"] / v["n"] * 100) if v["n"] else 0} for k, v in sorted(by_type.items(), key=lambda x: -x[1]["n"])},
        "errors": errors,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="baseline", help="报告标签（如 改前/改后）")
    ap.add_argument("--out", default=None, help="输出JSON路径（默认只打印）")
    args = ap.parse_args()

    results = classify_all()
    summary = summarize(results)

    print(f"=== 分类准确率基线 [{args.label}] ===")
    print(f"整体: {summary['correct']}/{summary['total']} = {summary['accuracy']}%\n")
    print("按类型:")
    for t, st in summary["by_type"].items():
        print(f"  {t}: {st['ok']}/{st['n']} = {st['accuracy']}%")
    print(f"\n错误样本({len(summary['errors'])}个):")
    for e in summary["errors"]:
        print(f"  {e['image'][:24]}.. 期望[{e['expected_prefix']}] 实际[{e['actual_type']}] conf={e['confidence']} ({e['route']})")

    if args.out:
        out = {
            "label": args.label,
            "results": results,
            "summary": summary,
        }
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"\n报告已写入: {args.out}")


if __name__ == "__main__":
    main()
