#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资金监管文档测试脚本

使用规则层进行分类和提取测试，不依赖VLM服务。
"""

import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Any

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer
from ocr_three_layer_hybrid.interfaces import DocumentType, DocumentInfo, PageType
from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline


# 全局OCR包装器
_ocr_wrapper = None

def get_ocr_wrapper():
    """获取或创建OCR包装器（单例）"""
    global _ocr_wrapper
    if _ocr_wrapper is None:
        from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
        _ocr_wrapper = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    return _ocr_wrapper


def run_ocr(image_path: str) -> str:
    """使用PaddleOCR提取文本"""
    try:
        wrapper = get_ocr_wrapper()
        result = wrapper.run_ocr(image_path)
        return result.full_text
    except Exception as e:
        print(f"  OCR失败: {e}")
        return ""


def test_fund_supervision_classification(case_dirs: List[Path]) -> Dict[str, Any]:
    """
    测试资金监管文档分类

    Returns:
        测试结果摘要
    """
    classifier = KeywordDocumentClassifier()
    rule_layer = RuleExtractionLayer()
    pipeline = PlanEPlusPipeline(classifier=classifier, rule_layer=rule_layer, vlm_layer=None)

    results = {
        "total_images": 0,
        "classified": {},
        "fund_supervision_found": [],
        "errors": [],
    }

    for case_dir in case_dirs:
        if not case_dir.is_dir():
            continue

        case_name = case_dir.name
        print(f"\n{'='*60}")
        print(f"测试案例: {case_name}")
        print(f"{'='*60}")

        # 获取所有图片
        images = sorted(case_dir.glob('*.jp*'))
        print(f"找到 {len(images)} 张图片")

        for img_path in images:
            results["total_images"] += 1
            img_name = img_path.name

            # 运行OCR
            start_time = time.time()
            ocr_text = run_ocr(str(img_path))
            ocr_time = time.time() - start_time

            if not ocr_text:
                results["errors"].append(f"{img_name}: OCR失败")
                continue

            # 分类
            classify_start = time.time()
            doc_info = classifier.classify(str(img_path), [ocr_text])
            classify_time = time.time() - classify_start

            doc_type = doc_info.doc_type.value

            # 统计分类结果
            if doc_type not in results["classified"]:
                results["classified"][doc_type] = []
            results["classified"][doc_type].append({
                "image": img_name,
                "case": case_name,
            })

            # 检查是否是资金监管文档
            is_fund = "资金监管" in doc_type
            if is_fund:
                results["fund_supervision_found"].append({
                    "image": img_name,
                    "case": case_name,
                    "doc_type": doc_type,
                    "page_type": doc_info.page_type.value if doc_info.page_type else "unknown",
                })

                # 进行提取测试
                key_list = pipeline.key_lists.get(doc_info.doc_type, [])
                if key_list:
                    extract_start = time.time()
                    extract_result = rule_layer.extract(doc_info, key_list)
                    extract_time = time.time() - extract_start

                    print(f"\n  📋 {img_name}")
                    print(f"     类型: {doc_type} ({doc_info.page_type.value if doc_info.page_type else 'unknown'})")
                    print(f"     耗时: OCR={ocr_time:.2f}s, 分类={classify_time:.3f}s, 提取={extract_time:.3f}s")

                    # 显示提取的字段
                    extracted_fields = {k: v for k, v in extract_result.fields.items() if v}
                    if extracted_fields:
                        print(f"     提取字段 ({len(extracted_fields)}):")
                        for k, v in extracted_fields.items():
                            print(f"       - {k}: {v}")
                    else:
                        print(f"     ⚠️ 未提取到任何字段")

    return results


def print_summary(results: Dict[str, Any]):
    """打印测试结果摘要"""
    print(f"\n{'='*60}")
    print("测试结果摘要")
    print(f"{'='*60}")

    print(f"\n总图片数: {results['total_images']}")

    print(f"\n分类统计:")
    for doc_type, items in sorted(results["classified"].items()):
        print(f"  {doc_type}: {len(items)} 张")

    print(f"\n资金监管文档: {len(results['fund_supervision_found'])} 张")
    for item in results["fund_supervision_found"]:
        print(f"  - {item['case']}/{item['image']}: {item['doc_type']} ({item['page_type']})")

    if results["errors"]:
        print(f"\n错误: {len(results['errors'])} 个")
        for error in results["errors"][:5]:
            print(f"  - {error}")


def main():
    """主函数"""
    # 选择测试案例
    sample_dir = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料')

    # 选择前3个案例进行测试
    case_dirs = sorted([d for d in sample_dir.iterdir() if d.is_dir()])[:3]

    print("资金监管文档测试")
    print(f"测试案例: {[d.name for d in case_dirs]}")

    # 运行测试
    results = test_fund_supervision_classification(case_dirs)

    # 打印摘要
    print_summary(results)

    # 保存结果
    output_file = Path('/Users/dongsun/Github/OCR-Three-Layer-Hybrid/tests/fund_supervision_test_results.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_file}")


if __name__ == "__main__":
    main()
