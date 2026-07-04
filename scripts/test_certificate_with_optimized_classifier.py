#!/usr/bin/env python3
"""
测试优化后的分类器对凭证提取的影响
验证是否正确排除了协议信息页
"""

import sys
from pathlib import Path
import json
import re

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer
from ocr_three_layer_hybrid.interfaces import DocumentType


def test_certificate_extraction():
    """测试凭证提取"""

    # 测试案例中的凭证图片
    test_images = [
        # BBJZ-2026-0113059
        "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0113059/16ddfab108eb442d8fc7dbecdb24e4d0.jpg",
        "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0113059/7f8b2f9daa81415082e2afa79fc01fe3.jpg",

        # BBJZ-2026-0114007
        "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0114007/16bb1e492640492c8f3ffbd5a797ff46.jpg",
        "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0114007/3a0e007515c6438ebfd35a960cacac47.jpg",
        "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0114007/7f6f2c31929d4689b037a81d854644a8.jpg",
        "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0114007/d0f275344a7b4702857f5c584ebde659.jpg",

        # BBJZ-2026-0116023
        "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0116023/4649c7a671fe49e0b4d82dd24c7fba09.jpg",
        "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0116023/61cb087acc5243819f892a248082f301.jpg",
    ]

    # 初始化
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    classifier = KeywordDocumentClassifier()
    rule_layer = RuleExtractionLayer()

    # 凭证字段列表（已移除收款单位）
    cert_fields = ["协议编号", "日期", "买房人", "买房人姓名", "身份证号", "房屋坐落", "建筑面积", "监管总额"]

    results = []
    actual_certificates = []
    misclassified = []

    print("=" * 80)
    print("测试优化后的分类器对凭证提取的影响")
    print("=" * 80)

    for img_path in test_images:
        if not Path(img_path).exists():
            print(f"\n⚠️ 图片不存在: {img_path}")
            continue

        print(f"\n{'=' * 80}")
        print(f"图片: {Path(img_path).name}")
        print(f"{'=' * 80}")

        # OCR识别
        ocr_result = ocr.run_ocr(img_path)
        text = ocr_result.full_text

        # 分类
        doc_info = classifier.classify(img_path, [text])

        print(f"分类结果: {doc_info.doc_type.value}")
        print(f"置信度: {doc_info.confidence:.2f}")

        # 判断是否为真正的凭证
        is_real_certificate = False
        reasons = []

        # 凭证特征检查
        if "监管凭证" in text or "资金监管凭证" in text:
            is_real_certificate = True
            reasons.append("包含'监管凭证'关键词")

        if "协议编号" in text and ("买房人" in text or "卖房人" in text):
            is_real_certificate = True
            reasons.append("包含凭证典型字段")

        if "监管总额" in text and "建筑面积" in text:
            is_real_certificate = True
            reasons.append("包含监管总额和建筑面积")

        # 非凭证特征检查
        if "甲方" in text and "乙方" in text and "丙方" in text:
            if "监管协议" in text:
                is_real_certificate = False
                reasons.append("实际是资金监管协议")

        if "身份证号" in text and "银行" in text and "账号" in text:
            if "监管凭证" not in text:
                is_real_certificate = False
                reasons.append("实际是协议信息页（包含银行账号）")

        print(f"\n是否为真正的凭证: {'✅ 是' if is_real_certificate else '❌ 否'}")
        if reasons:
            print(f"判断依据: {', '.join(reasons)}")

        # 如果分类为凭证，测试提取效果
        if doc_info.doc_type == DocumentType.FUND_SUPERVISION_CERTIFICATE:
            if is_real_certificate:
                # 真正的凭证 - 测试提取
                doc_info.ocr_texts = [text]
                extraction_result = rule_layer.extract(doc_info, cert_fields)

                total_fields = len(cert_fields)
                extracted_fields = sum(1 for field in cert_fields if extraction_result.fields.get(field))
                completion_rate = extracted_fields / total_fields * 100

                print(f"\n字段提取结果: {extracted_fields}/{total_fields} = {completion_rate:.1f}%")

                for field in cert_fields:
                    value = extraction_result.fields.get(field, "")
                    status = "✓" if value else "✗"
                    print(f"  {status} {field}: {value if value else '[缺失]'}")

                actual_certificates.append({
                    'image': Path(img_path).name,
                    'completion_rate': completion_rate,
                    'extracted': extracted_fields,
                    'total': total_fields
                })
            else:
                # 误分类的凭证 - 记录
                misclassified.append({
                    'image': Path(img_path).name,
                    'classified_as': doc_info.doc_type.value,
                    'actually_is': '协议信息页'
                })
                print(f"\n⚠️ 误分类：被分类为凭证，但实际是协议信息页")

    # 汇总统计
    print(f"\n{'=' * 80}")
    print("汇总统计")
    print(f"{'=' * 80}")

    print(f"\n总测试图片数: {len(test_images)}")
    print(f"真正的凭证: {len(actual_certificates)}个")
    print(f"误分类的图片: {len(misclassified)}个")

    if actual_certificates:
        total_fields = sum(cert['total'] for cert in actual_certificates)
        total_extracted = sum(cert['extracted'] for cert in actual_certificates)
        avg_completion = total_extracted / total_fields * 100 if total_fields > 0 else 0

        print(f"\n真正凭证的字段提取:")
        print(f"  总字段数: {total_fields}")
        print(f"  已提取: {total_extracted}")
        print(f"  平均完成率: {avg_completion:.1f}%")

        print(f"\n各凭证详情:")
        for cert in actual_certificates:
            print(f"  {cert['image']}: {cert['extracted']}/{cert['total']} = {cert['completion_rate']:.1f}%")

    if misclassified:
        print(f"\n误分类详情:")
        for item in misclassified:
            print(f"  - {item['image']}: 被分类为 {item['classified_as']}，实际是 {item['actually_is']}")

    # 结论
    print(f"\n{'=' * 80}")
    print("结论")
    print(f"{'=' * 80}")

    if len(misclassified) == 0 and len(actual_certificates) > 0:
        avg_completion = total_extracted / total_fields * 100 if total_fields > 0 else 0
        if avg_completion >= 95:
            print(f"\n✅ 分类器优化成功！")
            print(f"   - 所有凭证都正确分类")
            print(f"   - 平均完成率: {avg_completion:.1f}%")
        else:
            print(f"\n⚠️ 分类器正确分类，但凭证提取完成率较低: {avg_completion:.1f}%")
    elif len(misclassified) > 0:
        print(f"\n⚠️ 仍有 {len(misclassified)} 个图片被误分类")
        print(f"   需要进一步优化分类器")
    else:
        print(f"\n❌ 没有找到真正的凭证，无法评估提取效果")


if __name__ == '__main__':
    test_certificate_extraction()
