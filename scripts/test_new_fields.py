#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试新的字段定义（包含购房款）
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer
from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline


def main():
    """主函数"""
    # 初始化
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    classifier = KeywordDocumentClassifier()
    rule_layer = RuleExtractionLayer()
    pipeline = PlanEPlusPipeline(classifier=classifier, rule_layer=rule_layer, vlm_layer=None)

    # 选择案例3的首页
    img_path = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0112065/10495d3a216346a684c65de32bcdb8bc.jpg')

    print("=" * 80)
    print("测试新字段定义（包含购房款）")
    print("=" * 80)
    print(f"\n图片: {img_path.name}")

    # OCR
    result = ocr.run_ocr(str(img_path))
    text = result.full_text

    # 分类
    doc_info = classifier.classify(str(img_path), [text])
    print(f"文档类型: {doc_info.doc_type.value}")

    # 获取字段列表
    key_list = pipeline.key_lists.get(doc_info.doc_type, [])
    print(f"\n预期字段 ({len(key_list)}个):")
    for i, field in enumerate(key_list, 1):
        print(f"  {i:2d}. {field}")

    # 提取字段
    extract_result = rule_layer.extract(doc_info, key_list)

    print(f"\n实际提取字段:")
    extracted_count = 0
    for field in key_list:
        value = extract_result.fields.get(field, "")
        if value:
            print(f"  ✓ {field}: {value}")
            extracted_count += 1
        else:
            # 检查是否是可选字段（贷款）
            is_optional = "贷款" in field
            status = "⚠️ [可选-无贷款]" if is_optional else "✗ [缺失]"
            print(f"  {status} {field}")

    print(f"\n完成率: {extracted_count}/{len(key_list)} = {extracted_count/len(key_list)*100:.1f}%")

    # 特别检查购房款
    print(f"\n特别检查:")
    print(f"  购房款: {extract_result.fields.get('购房款', 'N/A')}")
    print(f"  购房款(大写): {extract_result.fields.get('购房款(大写)', 'N/A')}")
    print(f"  购房款(小写): {extract_result.fields.get('购房款(小写)', 'N/A')}")
    print(f"  贷款(大写): {extract_result.fields.get('贷款(大写)', 'N/A')}")
    print(f"  贷款(小写): {extract_result.fields.get('贷款(小写)', 'N/A')}")


if __name__ == "__main__":
    main()
