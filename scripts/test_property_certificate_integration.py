#!/usr/bin/env python3
"""
测试不动产权证书分类和提取的集成效果
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer
from ocr_three_layer_hybrid.interfaces import DocumentType


def test_integration():
    """测试分类和提取的集成效果"""

    # 测试样本
    test_images = [
        # 首页
        {
            "path": "/Users/dongsun/Github/sample-OCR/demo-不动产权证书/存量/BBJZ-2026-0127041/bd1015fe78b84ec6bfa743504ca4a63c.jpg",
            "expected_type": DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE,
            "description": "首页"
        },
        # 内容页
        {
            "path": "/Users/dongsun/Github/sample-OCR/demo-不动产权证书/存量/BBJZ-2026-0129058/0d7b511c1e7144f4bad4f60335aa1226.jpg",
            "expected_type": DocumentType.PROPERTY_CERTIFICATE_CONTENT,
            "description": "内容页"
        },
        # 附图页
        {
            "path": "/Users/dongsun/Github/sample-OCR/demo-不动产权证书/存量/BBJZ-2026-0121076/a81d1cfaf102418f848c0626ad1b5eb6.jpg",
            "expected_type": DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT,
            "description": "附图页"
        },
    ]

    # 初始化
    print("正在初始化OCR引擎...")
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    classifier = KeywordDocumentClassifier()
    rule_layer = RuleExtractionLayer()

    # 内容页的字段列表
    content_fields = [
        "不动产编号", "权利人", "共有情况", "坐落",
        "不动产单元号", "权利类型", "权利性质", "用途", "面积", "使用期限"
    ]

    print("\n" + "=" * 80)
    print("测试不动产权证书分类和提取集成效果")
    print("=" * 80)

    results = []

    for i, test_info in enumerate(test_images, 1):
        img_path = test_info["path"]
        expected_type = test_info["expected_type"]
        description = test_info["description"]

        if not Path(img_path).exists():
            print(f"\n❌ 图片不存在: {img_path}")
            continue

        print(f"\n{'=' * 80}")
        print(f"[{i}/{len(test_images)}] 测试: {description}")
        print(f"图片: {Path(img_path).name}")
        print(f"{'=' * 80}")

        # OCR识别
        print("正在进行OCR识别...")
        ocr_result = ocr.run_ocr(img_path)
        text = ocr_result.full_text

        # 分类
        print("正在分类...")
        doc_info = classifier.classify(img_path, [text])

        print(f"分类结果: {doc_info.doc_type.value}")
        print(f"期望类型: {expected_type.value}")

        classification_correct = doc_info.doc_type == expected_type
        print(f"分类是否正确: {'✅ 正确' if classification_correct else '❌ 错误'}")

        # 提取（只对内容页）
        if doc_info.doc_type == DocumentType.PROPERTY_CERTIFICATE_CONTENT:
            print("\n正在提取字段...")
            doc_info.ocr_texts = [text]
            extraction_result = rule_layer.extract(doc_info, content_fields)

            total_fields = len(content_fields)
            extracted_count = sum(1 for field in content_fields if extraction_result.fields.get(field))
            completion_rate = extracted_count / total_fields * 100

            print(f"\n提取结果: {extracted_count}/{total_fields} = {completion_rate:.1f}%")

            for field in content_fields:
                value = extraction_result.fields.get(field, "")
                status = "✓" if value else "✗"
                print(f"  {status} {field}: {value if value else '[缺失]'}")

            results.append({
                "description": description,
                "classification_correct": classification_correct,
                "completion_rate": completion_rate,
                "extracted": extracted_count,
                "total": total_fields
            })
        else:
            print(f"\n跳过提取（非内容页）")
            results.append({
                "description": description,
                "classification_correct": classification_correct,
                "completion_rate": None,
                "extracted": 0,
                "total": 0
            })

    # 统计
    print(f"\n{'=' * 80}")
    print("统计报告")
    print(f"{'=' * 80}")

    total_tests = len(results)
    correct_classifications = sum(1 for r in results if r["classification_correct"])
    classification_accuracy = correct_classifications / total_tests * 100 if total_tests > 0 else 0

    print(f"\n总测试数: {total_tests}")
    print(f"分类正确数: {correct_classifications}")
    print(f"分类准确率: {classification_accuracy:.1f}%")

    # 内容页提取统计
    content_results = [r for r in results if r["completion_rate"] is not None]
    if content_results:
        total_extracted = sum(r["extracted"] for r in content_results)
        total_fields = sum(r["total"] for r in content_results)
        avg_completion = total_extracted / total_fields * 100 if total_fields > 0 else 0

        print(f"\n内容页提取:")
        print(f"  总字段数: {total_fields}")
        print(f"  已提取: {total_extracted}")
        print(f"  平均完成率: {avg_completion:.1f}%")

    print(f"\n{'=' * 80}")


if __name__ == "__main__":
    test_integration()
