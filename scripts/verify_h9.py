#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 H6 触发率：跑基线样本 OCR，统计字间空格模式触发 + 多冒号（H6 合并场景）"""
import sys
import os
import re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from paddleocr import PaddleOCR

det = os.path.expanduser("~/.paddlex/official_models/PP-OCRv6_medium_det")
rec = os.path.expanduser("~/.paddlex/official_models/PP-OCRv6_medium_rec")

print("初始化 PaddleOCR...")
ocr = PaddleOCR(
    text_detection_model_dir=det,
    text_recognition_model_dir=rec,
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    text_det_limit_side_len=960,
)

samples = [
    "tests/fixtures/sample_property.jpg",
    "tests/fixtures/sample_contract.jpeg",
    "docs/images/notary_certificate.jpg",
    "docs/images/power_of_attorney_content.jpg",
    "docs/images/purchase_contract_first_page.jpeg",
]

total_lines = 0
spacing_triggered = 0
h6_risk = 0  # 字间空格触发 + >=2 冒号（H6 合并场景）

for img in samples:
    if not os.path.exists(img):
        print(f"\n=== {img} 不存在，跳过 ===")
        continue
    print(f"\n=== {img} ===")
    output = ocr.predict(img)
    res = output[0]
    j = res.json if hasattr(res, "json") else res
    inner = j.get("res", j) if isinstance(j, dict) else {}
    texts = inner.get("rec_texts", []) if isinstance(inner, dict) else []

    for line in texts:
        if not line or len(line.strip()) < 3:
            continue
        total_lines += 1
        parts = line.split()
        if len(parts) < 3:
            continue
        single = 0
        multi = 0
        for p in parts:
            cc = re.findall(r"[一-鿿\d]", p)
            if len(cc) <= 1:
                single += 1
            else:
                multi += 1
        total = single + multi
        if total == 0:
            continue
        ratio = single / total
        if ratio >= 0.8 and single >= 3:
            spacing_triggered += 1
            colon_count = line.count("：") + line.count(":")
            is_h6 = colon_count >= 2
            if is_h6:
                h6_risk += 1
            print(f"  [{'H6风险' if is_h6 else '字间空格'}] 冒号={colon_count} '{line}' -> '{re.sub(chr(92)+'s+','',line)}'")

print(f"\n{'='*60}")
print(f"H6 触发率统计")
print(f"{'='*60}")
print(f"样本数: {sum(1 for s in samples if os.path.exists(s))}")
print(f"OCR 文本行总数: {total_lines}")
print(f"字间空格模式触发行: {spacing_triggered}")
print(f"H6 风险行(字间空格+>=2冒号): {h6_risk}")
print(f"H6 触发率: {h6_risk}/{total_lines} = {h6_risk/total_lines*100:.1f}%" if total_lines else "N/A")
