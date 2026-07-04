#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断脚本：分析分类为"未知"的图片和缺失的签章页
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

    # 选择几个"未知"图片进行分析
    sample_dir = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2025-1013085')

    # 从测试结果中找出"未知"图片
    unknown_images = [
        "3873ae23c0fe4d12a309374a3552cf25.jpg",
        "4efd9f49d2064231b3b7c6fc3af3f003.jpg",
        "616f8a1d2f704b56abeddefea635fa7b.jpg",
    ]

    print("=" * 60)
    print("诊断分析：未知图片")
    print("=" * 60)

    for img_name in unknown_images:
        img_path = sample_dir / img_name
        if not img_path.exists():
            continue

        print(f"\n📄 {img_name}")
        print("-" * 60)

        # OCR
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
        print(f"  置信度: {doc_info.confidence:.2f}" if doc_info.confidence else "  置信度: N/A")

        # 显示关键词匹配情况
        print(f"\n关键词匹配检查:")
        keywords_to_check = [
            "资金监管", "协议", "凭证", "签章", "甲方", "乙方",
            "身份证号", "银行", "账号", "编号", "签署日期"
        ]
        for kw in keywords_to_check:
            if kw in text:
                print(f"  ✓ '{kw}' - 存在")
            else:
                print(f"  ✗ '{kw}' - 缺失")

    # 检查案例2的签章页（应该存在但未识别）
    print("\n" + "=" * 60)
    print("诊断分析：案例2的签章页")
    print("=" * 60)

    case2_dir = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0107026')
    # 案例2识别到了签章页：699370a96a974d30a945a652200a37b7.jpg
    # 检查案例1和案例3为什么没有识别到签章页

    print("\n案例1的未知图片（可能包含签章页）:")
    case1_unknown = [
        "3873ae23c0fe4d12a309374a3552cf25.jpg",
        "4efd9f49d2064231b3b7c6fc3af3f003.jpg",
        "616f8a1d2f704b56abeddefea635fa7b.jpg",
        "6a8478fed9264eb299bb1a367ea1255c.jpg",
        "912c6cc841d34fc5955084b22d49cf3f.jpg",
    ]

    for img_name in case1_unknown[:3]:  # 只检查前3个
        img_path = sample_dir / img_name
        if not img_path.exists():
            continue

        result = ocr.run_ocr(str(img_path))
        text = result.full_text

        # 检查是否包含签章页特征
        stamp_signals = ["甲方（签章）", "乙方（签章）", "丙方（签章）", "签约日期"]
        has_stamp = any(signal in text for signal in stamp_signals)

        if has_stamp:
            print(f"\n📄 {img_name} - 可能是签章页")
            print(f"文本（前300字符）: {text[:300]}")


if __name__ == "__main__":
    main()
