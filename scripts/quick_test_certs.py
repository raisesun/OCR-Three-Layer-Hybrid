#!/usr/bin/env python3
"""
快速测试凭证优化效果
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer
from ocr_three_layer_hybrid.interfaces import DocumentType


def quick_test():
    """快速测试"""
    # 初始化
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    classifier = KeywordDocumentClassifier()
    rule_layer = RuleExtractionLayer()
    pipeline = PlanEPlusPipeline(classifier=classifier, rule_layer=rule_layer, vlm_layer=None)

    # 测试3个凭证
    test_images = [
        '/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0113059/7f8b2f9daa81415082e2afa79fc01fe3.jpg',
        '/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0113059/16ddfab108eb442d8fc7dbecdb24e4d0.jpg',
        '/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0114007/16bb1e492640492c8f3ffbd5a797ff46.jpg',
    ]

    results = []

    for img_path_str in test_images:
        img_path = Path(img_path_str)
        if not img_path.exists():
            continue

        print(f"\n{'='*80}")
        print(f"凭证: {img_path.name}")
        print(f"{'='*80}")

        # OCR
        ocr_result = ocr.run_ocr(str(img_path))

        # 分类
        doc_info = pipeline.classifier.classify(str(img_path), [ocr_result.full_text])

        if doc_info.doc_type != DocumentType.FUND_SUPERVISION_CERTIFICATE:
            print(f"  跳过：分类为 {doc_info.doc_type.value}")
            continue

        # 提取字段
        key_list = pipeline.key_lists[doc_info.doc_type]
        extraction_result = pipeline.rule_layer.extract(doc_info, key_list)

        # 统计
        total = len(key_list)
        extracted = sum(1 for f in key_list if extraction_result.fields.get(f))

        print(f"\n完成率: {extracted}/{total} = {extracted/total*100:.1f}%")

        # 显示所有字段
        for field in key_list:
            value = extraction_result.fields.get(field, "")
            status = "✓" if value else "✗"
            print(f"  {status} {field}: {value if value else '[缺失]'}")

        results.append({
            'image': img_path.name,
            'total': total,
            'extracted': extracted,
            'rate': extracted / total * 100
        })

    return results


if __name__ == '__main__':
    results = quick_test()

    print(f"\n{'='*80}")
    print("汇总")
    print(f"{'='*80}")

    if results:
        total_fields = sum(r['total'] for r in results)
        total_extracted = sum(r['extracted'] for r in results)
        avg_rate = total_extracted / total_fields * 100 if total_fields > 0 else 0

        print(f"\n凭证数: {len(results)}")
        print(f"总字段: {total_fields}")
        print(f"已提取: {total_extracted}")
        print(f"平均完成率: {avg_rate:.1f}%")

        for r in results:
            print(f"  {r['image']}: {r['extracted']}/{r['total']} = {r['rate']:.1f}%")
