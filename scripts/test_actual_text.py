#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试实际OCR文本中的正则表达式
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper


def main():
    """主函数"""
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    img_path = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0112065/10495d3a216346a684c65de32bcdb8bc.jpg')

    result = ocr.run_ocr(str(img_path))
    full_text = result.full_text

    print("=" * 80)
    print("测试实际OCR文本")
    print("=" * 80)

    # 测试不动产权证号
    print("\n1. 不动产权证号")
    print("-" * 80)

    # 查找包含"不动产权"的行
    lines = full_text.split('\n')
    for i, line in enumerate(lines):
        if "不动产权" in line:
            print(f"行 {i}: {line}")

    # 测试正则
    import re
    pattern = r'[一-龥]*\s*[（(]\s*\d{4}\s*[）)]\s*[一-龥]+\s*市?\s*不动产权第\s*[A-Z0-9]+\s*号'
    match = re.search(pattern, full_text)
    print(f"\n正则匹配结果: {match.group(0) if match else '无匹配'}")

    # 测试购房款(小写)
    print("\n2. 购房款(小写)")
    print("-" * 80)

    # 查找包含"小写"的行
    for i, line in enumerate(lines):
        if "小写" in line:
            print(f"行 {i}: {line}")

    # 测试正则
    pattern2 = r'[（(]小写\s*([\d,.]+)\s*元[)）][^\n]*?购房款'
    match2 = re.search(pattern2, full_text)
    print(f"\n正则匹配结果: {match2.group(1) if match2 else '无匹配'}")

    # 测试跨行匹配
    print("\n3. 跨行匹配测试")
    print("-" * 80)

    # 使用 [\s\S] 代替 [^\n]
    pattern3 = r'[（(]小写\s*([\d,.]+)\s*元[)）][\s\S]*?购房款'
    match3 = re.search(pattern3, full_text)
    print(f"使用 [\\s\\S] 匹配: {match3.group(1) if match3 else '无匹配'}")

    # 使用 re.DOTALL
    match4 = re.search(pattern2, full_text, re.DOTALL)
    print(f"使用 re.DOTALL: {match4.group(1) if match4 else '无匹配'}")


if __name__ == "__main__":
    main()
