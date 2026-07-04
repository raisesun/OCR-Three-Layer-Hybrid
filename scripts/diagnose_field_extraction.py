#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段提取问题诊断脚本

分析为什么某些字段无法提取
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer
from ocr_three_layer_hybrid.interfaces import DocumentType


def main():
    """主函数"""
    # 初始化
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    classifier = KeywordDocumentClassifier()
    rule_layer = RuleExtractionLayer()

    # 选择案例3的首页（只提取了6个字段）
    img_path = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0112065/10495d3a216346a684c65de32bcdb8bc.jpg')

    print("=" * 80)
    print("字段提取问题诊断")
    print("=" * 80)
    print(f"\n图片: {img_path.name}")
    print(f"案例: BBJZ-2026-0112065")
    print(f"预期字段: 13个")
    print(f"实际提取: 6个")

    # OCR
    print("\n" + "=" * 80)
    print("第1步：OCR文本")
    print("=" * 80)
    result = ocr.run_ocr(str(img_path))
    text = result.full_text
    print(f"\nOCR文本长度: {len(text)} 字符")
    print(f"\n完整OCR文本:")
    print(text)

    # 分类
    print("\n" + "=" * 80)
    print("第2步：分类结果")
    print("=" * 80)
    doc_info = classifier.classify(str(img_path), [text])
    print(f"文档类型: {doc_info.doc_type.value}")
    print(f"页面类型: {doc_info.page_type.value if doc_info.page_type else 'unknown'}")

    # 提取
    print("\n" + "=" * 80)
    print("第3步：字段提取")
    print("=" * 80)

    # 定义预期字段
    expected_fields = [
        "编号", "甲方", "乙方", "丙方",
        "签署日期", "网上签约备案合同号",
        "房屋地址", "建筑面积", "不动产权证号",
        "购房款(大写)", "购房款(小写)",
        "贷款(大写)", "贷款(小写)"
    ]

    print(f"\n预期字段 ({len(expected_fields)}个):")
    for i, field in enumerate(expected_fields, 1):
        print(f"  {i:2d}. {field}")

    # 提取字段
    key_list = expected_fields
    extract_result = rule_layer.extract(doc_info, key_list)

    print(f"\n实际提取字段 ({len([v for v in extract_result.fields.values() if v])}个):")
    extracted = []
    missing = []
    for field in expected_fields:
        value = extract_result.fields.get(field, "")
        if value:
            print(f"  ✓ {field}: {value}")
            extracted.append(field)
        else:
            print(f"  ✗ {field}: [缺失]")
            missing.append(field)

    # 分析缺失字段
    print("\n" + "=" * 80)
    print("第4步：缺失字段分析")
    print("=" * 80)

    print(f"\n缺失字段 ({len(missing)}个):")
    for field in missing:
        print(f"\n  ❌ {field}")
        # 检查OCR文本中是否有相关关键词
        keywords_map = {
            "签署日期": ["签署日期", "签约日期", "日期", "年", "月", "日"],
            "网上签约备案合同号": ["网上签约", "备案合同号", "合同号", "Y("],
            "房屋地址": ["房屋地址", "房屋坐落", "地址", "坐落"],
            "购房款(小写)": ["购房款", "小写", "￥", "元"],
            "贷款(小写)": ["贷款", "小写", "￥", "元"],
        }

        if field in keywords_map:
            print(f"    检查关键词: {keywords_map[field]}")
            for kw in keywords_map[field]:
                if kw in text:
                    # 找到关键词，显示上下文
                    idx = text.find(kw)
                    start = max(0, idx - 30)
                    end = min(len(text), idx + 50)
                    context = text[start:end].replace('\n', ' ')
                    print(f"      ✓ '{kw}' 存在: ...{context}...")
                else:
                    print(f"      ✗ '{kw}' 不存在")


if __name__ == "__main__":
    main()
