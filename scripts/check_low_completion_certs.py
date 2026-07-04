#!/usr/bin/env python3
"""
检查低完成率的凭证图片，确认它们是否真的是凭证
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.interfaces import DocumentType


def check_image(image_path: str, ocr: PaddleOCRWrapper, classifier: KeywordDocumentClassifier):
    """检查单个图片"""
    print(f"\n{'='*80}")
    print(f"检查图片: {Path(image_path).name}")
    print(f"{'='*80}")

    # OCR识别
    ocr_result = ocr.run_ocr(image_path)
    text = ocr_result.full_text

    print(f"\nOCR文本（前500字）:")
    print(text[:500])

    # 分类
    doc_info = classifier.classify(image_path, [text])
    print(f"\n分类结果: {doc_info.doc_type.value}")
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

    return is_real_certificate, doc_info.doc_type


def main():
    """主函数"""
    # 低完成率的凭证图片
    low_completion_images = [
        "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0113059/16ddfab108eb442d8fc7dbecdb24e4d0.jpg",
        "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0114007/3a0e007515c6438ebfd35a960cacac47.jpg",
        "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0114007/7f6f2c31929d4689b037a81d854644a8.jpg",
        "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0116023/61cb087acc5243819f892a248082f301.jpg",
    ]

    # 初始化
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    classifier = KeywordDocumentClassifier()

    results = []

    for img_path in low_completion_images:
        if Path(img_path).exists():
            is_real, doc_type = check_image(img_path, ocr, classifier)
            results.append({
                'image': Path(img_path).name,
                'is_real_certificate': is_real,
                'classified_as': doc_type.value
            })
        else:
            print(f"\n⚠️ 图片不存在: {img_path}")

    # 汇总统计
    print(f"\n{'='*80}")
    print("汇总统计")
    print(f"{'='*80}")

    real_count = sum(1 for r in results if r['is_real_certificate'])
    fake_count = len(results) - real_count

    print(f"\n总检查图片数: {len(results)}")
    print(f"真正的凭证: {real_count}个")
    print(f"误分类的图片: {fake_count}个")

    if fake_count > 0:
        print(f"\n误分类详情:")
        for r in results:
            if not r['is_real_certificate']:
                print(f"  - {r['image']}: 被分类为 {r['classified_as']}")


if __name__ == '__main__':
    main()
