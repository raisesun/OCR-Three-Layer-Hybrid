#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速验证：签章页修复
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier


def main():
    """主函数"""
    # 初始化
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    classifier = KeywordDocumentClassifier()

    # 测试签章页图片
    img_path = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2025-1013085/616f8a1d2f704b56abeddefea635fa7b.jpg')

    print("=" * 60)
    print("验证签章页修复")
    print("=" * 60)
    print(f"\n图片: {img_path.name}")

    # OCR
    result = ocr.run_ocr(str(img_path))
    text = result.full_text

    print(f"\nOCR文本（前300字符）:")
    print(text[:300])

    # 分类
    doc_info = classifier.classify(str(img_path), [text])

    print(f"\n分类结果:")
    print(f"  文档类型: {doc_info.doc_type.value}")
    print(f"  页面类型: {doc_info.page_type.value if doc_info.page_type else 'unknown'}")

    # 预期结果
    expected_doc_type = "资金监管协议-签章页"
    expected_page_type = "盖章页"

    if doc_info.doc_type.value == expected_doc_type:
        print(f"\n✓ 文档类型正确: {doc_info.doc_type.value}")
    else:
        print(f"\n✗ 文档类型错误: 期望 {expected_doc_type}, 实际 {doc_info.doc_type.value}")

    if doc_info.page_type and doc_info.page_type.value == expected_page_type:
        print(f"✓ 页面类型正确: {doc_info.page_type.value}")
    else:
        print(f"✗ 页面类型错误: 期望 {expected_page_type}, 实际 {doc_info.page_type.value if doc_info.page_type else 'unknown'}")


if __name__ == "__main__":
    main()
