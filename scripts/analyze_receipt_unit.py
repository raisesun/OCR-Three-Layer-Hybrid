#!/usr/bin/env python3
"""
分析收款单位字段问题
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper


def analyze_receipt_unit():
    """分析收款单位"""
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")

    # 测试凭证
    test_images = [
        '/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0113059/7f8b2f9daa81415082e2afa79fc01fe3.jpg',
        '/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0114007/16bb1e492640492c8f3ffbd5a797ff46.jpg',
    ]

    for img_path_str in test_images:
        img_path = Path(img_path_str)
        if not img_path.exists():
            continue

        print(f"\n{'='*80}")
        print(f"凭证: {img_path.name}")
        print(f"{'='*80}")

        # OCR
        ocr_result = ocr.run_ocr(str(img_path))
        text = ocr_result.full_text

        # 查找收款单位相关内容
        lines = text.split('\n')
        print("\n收款单位相关内容:")
        for i, line in enumerate(lines):
            if '收款' in line or '签章' in line or '专用章' in line or '公司' in line:
                # 显示上下文
                start = max(0, i-2)
                end = min(len(lines), i+3)
                for j in range(start, end):
                    marker = '>>>' if j == i else '   '
                    print(f"{marker} Line {j}: {repr(lines[j])}")
                print()

        # 显示完整文本（最后20行）
        print("\n完整文本（最后20行）:")
        for i, line in enumerate(lines[-20:]):
            print(f"{len(lines)-20+i}: {line}")


if __name__ == '__main__':
    analyze_receipt_unit()
