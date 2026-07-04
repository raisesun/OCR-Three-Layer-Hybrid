#!/usr/bin/env python3
"""
对比测试：预处理前后字段提取效果
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer
from ocr_three_layer_hybrid.interfaces import DocumentType
from ocr_three_layer_hybrid.text_preprocessor import OCRTextPreprocessor


def test_with_preprocessing(enable_preprocessing: bool):
    """测试字段提取（可选择是否启用预处理）"""
    # 初始化
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    classifier = KeywordDocumentClassifier()

    # 根据参数决定是否启用预处理
    if enable_preprocessing:
        # 使用默认的RuleExtractionLayer（已集成预处理）
        rule_layer = RuleExtractionLayer()
    else:
        # 临时禁用预处理
        import ocr_three_layer_hybrid.rule_layer as rule_module
        original_preprocess = rule_module.preprocess_text
        rule_module.preprocess_text = lambda x: x  # 禁用预处理
        rule_layer = RuleExtractionLayer()
        rule_module.preprocess_text = original_preprocess  # 恢复

    pipeline = PlanEPlusPipeline(classifier=classifier, rule_layer=rule_layer, vlm_layer=None)

    # 测试凭证
    test_images = [
        '/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0113059/7f8b2f9daa81415082e2afa79fc01fe3.jpg',
        '/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0114007/16bb1e492640492c8f3ffbd5a797ff46.jpg',
    ]

    results = []

    for img_path_str in test_images:
        img_path = Path(img_path_str)
        if not img_path.exists():
            continue

        # OCR
        ocr_result = ocr.run_ocr(str(img_path))

        # 分类
        doc_info = pipeline.classifier.classify(str(img_path), [ocr_result.full_text])

        if doc_info.doc_type != DocumentType.FUND_SUPERVISION_CERTIFICATE:
            continue

        # 提取字段
        key_list = pipeline.key_lists[doc_info.doc_type]
        extraction_result = pipeline.rule_layer.extract(doc_info, key_list)

        # 统计
        total = len(key_list)
        extracted = sum(1 for f in key_list if extraction_result.fields.get(f))

        results.append({
            'image': img_path.name,
            'total': total,
            'extracted': extracted,
            'rate': extracted / total * 100,
            'fields': extraction_result.fields
        })

    return results


def main():
    """主函数"""
    print("="*80)
    print("对比测试：预处理前后字段提取效果")
    print("="*80)

    # 测试1：不启用预处理
    print("\n" + "="*80)
    print("测试1: 不启用预处理")
    print("="*80)
    results_without = test_with_preprocessing(enable_preprocessing=False)

    # 测试2：启用预处理
    print("\n" + "="*80)
    print("测试2: 启用预处理")
    print("="*80)
    results_with = test_with_preprocessing(enable_preprocessing=True)

    # 对比结果
    print("\n" + "="*80)
    print("对比结果")
    print("="*80)

    for i, (r1, r2) in enumerate(zip(results_without, results_with), 1):
        print(f"\n凭证 {i}: {r1['image']}")
        print(f"  不启用预处理: {r1['extracted']}/{r1['total']} = {r1['rate']:.1f}%")
        print(f"  启用预处理:   {r2['extracted']}/{r2['total']} = {r2['rate']:.1f}%")
        improvement = r2['extracted'] - r1['extracted']
        if improvement > 0:
            print(f"  改进: +{improvement}个字段 ✓")
        elif improvement < 0:
            print(f"  下降: {improvement}个字段 ✗")
        else:
            print(f"  无变化: 0个字段")

    # 汇总统计
    total_without = sum(r['extracted'] for r in results_without)
    total_with = sum(r['extracted'] for r in results_with)
    total_fields = sum(r['total'] for r in results_without)

    print("\n" + "="*80)
    print("汇总统计")
    print("="*80)
    print(f"总字段数: {total_fields}")
    print(f"不启用预处理: {total_without}/{total_fields} = {total_without/total_fields*100:.1f}%")
    print(f"启用预处理:   {total_with}/{total_fields} = {total_with/total_fields*100:.1f}%")
    print(f"改进: +{total_with - total_without}个字段")


if __name__ == '__main__':
    main()
