#!/usr/bin/env python3
"""
测试所有凭证的优化效果
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer
from ocr_three_layer_hybrid.interfaces import DocumentType


def test_all_certificates():
    """测试所有凭证"""
    # 初始化
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    classifier = KeywordDocumentClassifier()
    rule_layer = RuleExtractionLayer()
    pipeline = PlanEPlusPipeline(classifier=classifier, rule_layer=rule_layer, vlm_layer=None)

    # 测试案例
    sample_dir = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料')
    test_cases = ['BBJZ-2026-0113059', 'BBJZ-2026-0114007', 'BBJZ-2026-0116023']

    results = []

    for case_name in test_cases:
        case_dir = sample_dir / case_name
        if not case_dir.exists():
            continue

        print(f"\n{'='*80}")
        print(f"案例: {case_name}")
        print(f"{'='*80}")

        # 获取所有图片
        image_files = sorted(list(case_dir.glob("*.jpg")))

        for img_path in image_files:
            # OCR
            ocr_result = ocr.run_ocr(str(img_path))

            # 分类
            doc_info = pipeline.classifier.classify(str(img_path), [ocr_result.full_text])

            # 如果是凭证
            if doc_info.doc_type == DocumentType.FUND_SUPERVISION_CERTIFICATE:
                # 提取字段
                key_list = pipeline.key_lists[doc_info.doc_type]
                extraction_result = pipeline.rule_layer.extract(doc_info, key_list)

                # 统计
                total = len(key_list)
                extracted = sum(1 for f in key_list if extraction_result.fields.get(f))

                print(f"\n凭证: {img_path.name}")
                print(f"  完成率: {extracted}/{total} = {extracted/total*100:.1f}%")

                # 显示关键字段
                for field in ["日期", "买房人", "身份证号", "监管总额"]:
                    value = extraction_result.fields.get(field, "")
                    status = "✓" if value else "✗"
                    print(f"    {status} {field}: {value if value else '[缺失]'}")

                results.append({
                    'case': case_name,
                    'image': img_path.name,
                    'total': total,
                    'extracted': extracted,
                    'rate': extracted / total * 100
                })

    return results


if __name__ == '__main__':
    results = test_all_certificates()

    print(f"\n{'='*80}")
    print("汇总统计")
    print(f"{'='*80}")

    if results:
        total_fields = sum(r['total'] for r in results)
        total_extracted = sum(r['extracted'] for r in results)
        avg_rate = total_extracted / total_fields * 100 if total_fields > 0 else 0

        print(f"\n总凭证数: {len(results)}")
        print(f"总字段数: {total_fields}")
        print(f"已提取: {total_extracted}")
        print(f"平均完成率: {avg_rate:.1f}%")

        print(f"\n各凭证详情:")
        for r in results:
            print(f"  {r['case']} / {r['image']}: {r['extracted']}/{r['total']} = {r['rate']:.1f}%")
