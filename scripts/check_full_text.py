#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查看签章页完整OCR文本
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper


def main():
    """主函数"""
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    img_path = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2025-1013085/616f8a1d2f704b56abeddefea635fa7b.jpg')

    print("=" * 60)
    print("签章页完整OCR文本")
    print("=" * 60)
    print(f"\n图片: {img_path.name}\n")

    result = ocr.run_ocr(str(img_path))
    text = result.full_text

    print(text)
    print("\n" + "=" * 60)
    print(f"文本长度: {len(text)} 字符")
    print("=" * 60)

    # 检查关键词
    print("\n关键词检查:")
    keywords = [
        "资金监管", "协议", "凭证", "存量房",
        "甲方", "乙方", "丙方", "签章", "签字",
        "签约日期", "第4页", "第3页"
    ]
    for kw in keywords:
        if kw in text:
            print(f"  ✓ '{kw}' - 存在")
        else:
            print(f"  ✗ '{kw}' - 缺失")


if __name__ == "__main__":
    main()
