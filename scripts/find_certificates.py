#!/usr/bin/env python3
"""
查找并分析所有凭证图片

遍历多个案例，找到真正的凭证图片
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer
from ocr_three_layer_hybrid.interfaces import DocumentType


def find_all_certificates(sample_dir: Path, pipeline: PlanEPlusPipeline, ocr: PaddleOCRWrapper):
    """查找所有凭证图片"""
    print("="*80)
    print("查找所有凭证图片")
    print("="*80)

    certificates = []

    # 遍历所有案例
    for case_dir in sorted(sample_dir.iterdir()):
        if not case_dir.is_dir():
            continue

        case_name = case_dir.name
        print(f"\n案例: {case_name}")

        # 获取所有图片
        image_files = sorted(list(case_dir.glob("*.jpg")) + list(case_dir.glob("*.png")))

        for img_path in image_files:
            # OCR
            ocr_result = ocr.run_ocr(str(img_path))

            # 分类
            doc_info = pipeline.classifier.classify(str(img_path), [ocr_result.full_text])

            # 如果是凭证
            if doc_info.doc_type == DocumentType.FUND_SUPERVISION_CERTIFICATE:
                # 检查是否包含"凭证"关键词
                has_cert_keyword = "凭证" in ocr_result.full_text[:100]
                has_amount = "人民币" in ocr_result.full_text or "¥" in ocr_result.full_text

                certificates.append({
                    'case': case_name,
                    'image': img_path.name,
                    'has_cert_keyword': has_cert_keyword,
                    'has_amount': has_amount,
                    'ocr_text': ocr_result.full_text[:500]  # 只显示前500字符
                })

                print(f"  凭证: {img_path.name}")
                print(f"    包含'凭证': {has_cert_keyword}")
                print(f"    包含金额: {has_amount}")

    return certificates


def main():
    """主函数"""
    # 初始化
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    classifier = KeywordDocumentClassifier()
    rule_layer = RuleExtractionLayer()
    pipeline = PlanEPlusPipeline(classifier=classifier, rule_layer=rule_layer, vlm_layer=None)

    # 测试案例
    sample_dir = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料')
    test_cases = ['BBJZ-2026-0113059', 'BBJZ-2026-0114007', 'BBJZ-2026-0116023']

    all_certificates = []

    for case_name in test_cases:
        case_dir = sample_dir / case_name
        if not case_dir.exists():
            print(f"案例 {case_name} 不存在，跳过")
            continue

        certificates = find_all_certificates(case_dir, pipeline, ocr)
        all_certificates.extend(certificates)

    print(f"\n{'='*80}")
    print(f"共找到 {len(all_certificates)} 个凭证")
    print(f"{'='*80}")

    # 分析凭证格式
    for i, cert in enumerate(all_certificates[:3], 1):  # 只分析前3个
        print(f"\n{'='*80}")
        print(f"凭证 {i}: {cert['case']} / {cert['image']}")
        print(f"{'='*80}")
        print(f"OCR文本（前500字符）:\n{cert['ocr_text']}")


if __name__ == '__main__':
    main()
