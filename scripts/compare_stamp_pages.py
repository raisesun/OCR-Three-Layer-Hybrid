#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比案例2的签章页（成功识别）和案例1的签章页（未识别）
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier


def main():
    """主函数"""
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    classifier = KeywordDocumentClassifier()

    # 案例2的签章页（成功识别）
    case2_stamp = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0107026/699370a96a974d30a945a652200a37b7.jpg')
    # 案例1的签章页（未识别）
    case1_stamp = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2025-1013085/616f8a1d2f704b56abeddefea635fa7b.jpg')

    for case_name, img_path in [("案例2", case2_stamp), ("案例1", case1_stamp)]:
        print("=" * 60)
        print(f"{case_name} 签章页")
        print("=" * 60)
        print(f"图片: {img_path.name}\n")

        result = ocr.run_ocr(str(img_path))
        text = result.full_text

        print(f"OCR文本（前500字符）:")
        print(text[:500])
        print()

        # 分类
        doc_info = classifier.classify(str(img_path), [text])
        print(f"分类结果:")
        print(f"  文档类型: {doc_info.doc_type.value}")
        print(f"  页面类型: {doc_info.page_type.value if doc_info.page_type else 'unknown'}")

        # 关键词检查
        print(f"\n关键词检查:")
        keywords = ["资金监管", "协议", "存量房", "甲方", "乙方", "丙方", "签章", "签约日期"]
        for kw in keywords:
            if kw in text:
                print(f"  ✓ '{kw}'")
            else:
                print(f"  ✗ '{kw}'")
        print()


if __name__ == "__main__":
    main()
