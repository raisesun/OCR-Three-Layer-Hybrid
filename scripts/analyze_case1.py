#!/usr/bin/env python3
"""
分析BBJZ-2026-0112065的所有图片，找到真正的凭证
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer


def main():
    # 初始化
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    classifier = KeywordDocumentClassifier()
    rule_layer = RuleExtractionLayer()
    pipeline = PlanEPlusPipeline(classifier=classifier, rule_layer=rule_layer, vlm_layer=None)

    # 测试案例
    case_dir = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0112065')
    image_files = sorted(list(case_dir.glob("*.jpg")))

    print("="*80)
    print(f"分析案例: {case_dir.name}")
    print(f"图片数量: {len(image_files)}")
    print("="*80)

    for img_path in image_files:
        print(f"\n{'='*80}")
        print(f"图片: {img_path.name}")
        print(f"{'='*80}")

        # OCR
        ocr_result = ocr.run_ocr(str(img_path))

        # 分类
        doc_info = pipeline.classifier.classify(str(img_path), [ocr_result.full_text])

        print(f"分类结果: {doc_info.doc_type.value}")

        # 显示前300字符的OCR文本
        print(f"\nOCR文本（前300字符）:")
        print(ocr_result.full_text[:300])

        # 如果是凭证，显示完整分析
        if doc_info.doc_type.value == "资金监管凭证":
            print(f"\n{'='*80}")
            print("这是凭证！完整OCR文本:")
            print(f"{'='*80}")
            print(ocr_result.full_text)

            # 提取字段
            key_list = pipeline.key_lists[doc_info.doc_type]
            extraction_result = pipeline.rule_layer.extract(doc_info, key_list)

            print(f"\n{'='*80}")
            print("字段提取结果:")
            print(f"{'='*80}")

            for field in key_list:
                value = extraction_result.fields.get(field, "")
                status = "✓" if value else "✗"
                print(f"{status} {field}: {value if value else '[缺失]'}")

            break  # 只分析第一个凭证


if __name__ == '__main__':
    main()
