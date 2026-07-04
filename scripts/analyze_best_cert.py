#!/usr/bin/env python3
"""
分析最佳凭证案例（5/9字段）
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

    # 最佳凭证图片
    img_path = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0113059/7f8b2f9daa81415082e2afa79fc01fe3.jpg')

    print("="*80)
    print(f"分析凭证: {img_path.name}")
    print("="*80)

    # OCR
    ocr_result = ocr.run_ocr(str(img_path))

    print(f"\n完整OCR文本:\n{ocr_result.full_text}")

    # 分类
    doc_info = pipeline.classifier.classify(str(img_path), [ocr_result.full_text])
    print(f"\n{'='*80}")
    print(f"分类结果: {doc_info.doc_type.value}")
    print(f"{'='*80}")

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

    # 分析正则表达式
    print(f"\n{'='*80}")
    print("正则表达式诊断:")
    print(f"{'='*80}")

    import re
    full_text = ocr_result.full_text

    # 日期
    print("\n【日期】")
    patterns = [
        r'日期\s*[:：]\s*(\d{4}年\d{1,2}月\d{1,2}日)',
        r'(\d{4}年\d{1,2}月\d{1,2}日)',
        r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
    ]
    for i, pattern in enumerate(patterns, 1):
        match = re.search(pattern, full_text)
        if match:
            print(f"  模式{i} ✓: {match.group(1)}")
            break
    else:
        print(f"  ✗ 所有模式都失败")
        for line in full_text.split('\n'):
            if '日期' in line or '年' in line or '月' in line:
                print(f"    实际文本: {line.strip()}")

    # 买房人
    print("\n【买房人】")
    patterns = [
        r'买房人\s*[:：]\s*([^\n]+)',
        r'买方\s*[:：]\s*([^\n]+)',
        r'买受人\s*[:：]\s*([^\n]+)',
    ]
    for i, pattern in enumerate(patterns, 1):
        match = re.search(pattern, full_text)
        if match:
            print(f"  模式{i} ✓: {match.group(1)}")
            break
    else:
        print(f"  ✗ 所有模式都失败")
        for line in full_text.split('\n'):
            if '买房' in line or '买方' in line or '买受人' in line:
                print(f"    实际文本: {line.strip()}")

    # 房屋坐落
    print("\n【房屋坐落】")
    patterns = [
        r'房屋坐落\s*[:：]\s*([^\n]+)',
        r'坐落\s*[:：]\s*([^\n]+)',
        r'位于\s*([^\n，,。]+(?:号|室|栋|楼|单元|层))',
    ]
    for i, pattern in enumerate(patterns, 1):
        match = re.search(pattern, full_text)
        if match:
            print(f"  模式{i} ✓: {match.group(1)}")
            break
    else:
        print(f"  ✗ 所有模式都失败")
        for line in full_text.split('\n'):
            if '房屋' in line or '坐落' in line or '位于' in line:
                print(f"    实际文本: {line.strip()}")

    # 监管总额
    print("\n【监管总额】")
    patterns = [
        r'监管总额\s*[:：]\s*([^\n]+)',
        r'监管金额\s*[:：]\s*([^\n]+)',
        r'人民币\s*([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)',
        r'[¥￥]\s*([\d,.]+)',
    ]
    for i, pattern in enumerate(patterns, 1):
        match = re.search(pattern, full_text)
        if match:
            print(f"  模式{i} ✓: {match.group(1)}")
            break
    else:
        print(f"  ✗ 所有模式都失败")
        for line in full_text.split('\n'):
            if '监管' in line or '人民币' in line or '¥' in line or '￥' in line:
                print(f"    实际文本: {line.strip()}")

    # 收款单位
    print("\n【收款单位】")
    patterns = [
        r'收款单位\s*[:：]\s*([^\n]+)',
        r'收款人\s*[:：]\s*([^\n]+)',
    ]
    for i, pattern in enumerate(patterns, 1):
        match = re.search(pattern, full_text)
        if match:
            print(f"  模式{i} ✓: {match.group(1)}")
            break
    else:
        print(f"  ✗ 所有模式都失败")
        for line in full_text.split('\n'):
            if '收款' in line:
                print(f"    实际文本: {line.strip()}")


if __name__ == '__main__':
    main()
