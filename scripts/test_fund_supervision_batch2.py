#!/usr/bin/env python3
"""
测试脚本 - 验证资金监管文档分类和字段提取（第2轮第1批）

测试案例：
- BBJZ-2026-0113059
- BBJZ-2026-0114007
- BBJZ-2026-0116023

验证内容：
1. 分类准确率
2. 必填字段完成率（目标：100%）
3. 处理速度
4. 新增"购房款"字段提取效果
5. 贷款字段可选逻辑
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer
from ocr_three_layer_hybrid.interfaces import DocumentType


def test_case(case_dir: Path, pipeline: PlanEPlusPipeline, ocr: PaddleOCRWrapper):
    """测试单个案例"""
    print(f"\n{'='*80}")
    print(f"测试案例: {case_dir.name}")
    print(f"{'='*80}")

    # 获取所有图片
    image_files = sorted(list(case_dir.glob("*.jpg")) + list(case_dir.glob("*.png")))
    print(f"找到 {len(image_files)} 张图片")

    results = {
        'total_images': len(image_files),
        'fund_supervision_docs': 0,
        'first_pages': 0,
        'certificates': 0,
        'stamp_pages': 0,
        'required_fields_total': 0,
        'required_fields_extracted': 0,
        'optional_fields_total': 0,
        'optional_fields_extracted': 0,
        'processing_times': []
    }

    # 分类并提取
    for img_path in image_files:
        print(f"\n处理图片: {img_path.name}")

        # OCR
        import time
        start_time = time.time()
        ocr_result = ocr.run_ocr(str(img_path))
        ocr_time = time.time() - start_time
        results['processing_times'].append(ocr_time)
        print(f"  OCR耗时: {ocr_time:.2f}秒")

        # 分类
        doc_info = pipeline.classifier.classify(str(img_path), [ocr_result.full_text])
        print(f"  分类结果: {doc_info.doc_type.value}")

        # 检查是否为资金监管文档
        if '资金监管' in doc_info.doc_type.value:
            results['fund_supervision_docs'] += 1

            # 统计文档类型
            if '首页' in doc_info.doc_type.value:
                results['first_pages'] += 1
            elif '凭证' in doc_info.doc_type.value:
                results['certificates'] += 1
            elif '签章页' in doc_info.doc_type.value:
                results['stamp_pages'] += 1

            # 提取字段（仅首页和凭证）
            if doc_info.doc_type in [DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE,
                                     DocumentType.FUND_SUPERVISION_CERTIFICATE]:
                key_list = pipeline.key_lists[doc_info.doc_type]
                extraction_result = pipeline.rule_layer.extract(doc_info, key_list)

                # 统计字段
                required_fields = [f for f in key_list if '贷款' not in f]
                optional_fields = [f for f in key_list if '贷款' in f]

                results['required_fields_total'] += len(required_fields)
                results['optional_fields_total'] += len(optional_fields)

                extracted_count = 0
                for field in required_fields:
                    if extraction_result.fields.get(field):
                        extracted_count += 1

                results['required_fields_extracted'] += extracted_count
                print(f"  必填字段: {extracted_count}/{len(required_fields)}")

                # 显示关键字段
                if doc_info.doc_type == DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE:
                    print(f"    购房款: {extraction_result.fields.get('购房款', 'N/A')}")
                    print(f"    贷款(大写): {extraction_result.fields.get('贷款(大写)', 'N/A')}")
                    print(f"    贷款(小写): {extraction_result.fields.get('贷款(小写)', 'N/A')}")

    return results


def main():
    """主函数"""
    print("="*80)
    print("第2轮测试 - 第1批（3个案例）")
    print("="*80)

    # 初始化
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    classifier = KeywordDocumentClassifier()
    rule_layer = RuleExtractionLayer()
    pipeline = PlanEPlusPipeline(classifier=classifier, rule_layer=rule_layer, vlm_layer=None)

    # 测试案例
    sample_dir = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料')
    test_cases = [
        'BBJZ-2026-0113059',
        'BBJZ-2026-0114007',
        'BBJZ-2026-0116023'
    ]

    all_results = []

    for case_name in test_cases:
        case_dir = sample_dir / case_name
        if not case_dir.exists():
            print(f"\n警告: 案例 {case_name} 不存在，跳过")
            continue

        results = test_case(case_dir, pipeline, ocr)
        results['case_name'] = case_name
        all_results.append(results)

    # 汇总统计
    print(f"\n{'='*80}")
    print("测试汇总")
    print(f"{'='*80}")

    total_images = sum(r['total_images'] for r in all_results)
    total_fund_docs = sum(r['fund_supervision_docs'] for r in all_results)
    total_first_pages = sum(r['first_pages'] for r in all_results)
    total_certificates = sum(r['certificates'] for r in all_results)
    total_stamp_pages = sum(r['stamp_pages'] for r in all_results)

    total_required = sum(r['required_fields_total'] for r in all_results)
    total_required_extracted = sum(r['required_fields_extracted'] for r in all_results)

    avg_time = sum(sum(r['processing_times']) for r in all_results) / total_images if total_images > 0 else 0

    print(f"\n总图片数: {total_images}")
    print(f"资金监管文档: {total_fund_docs}")
    print(f"  - 首页: {total_first_pages}")
    print(f"  - 凭证: {total_certificates}")
    print(f"  - 签章页: {total_stamp_pages}")

    print(f"\n必填字段统计:")
    print(f"  总字段数: {total_required}")
    print(f"  已提取: {total_required_extracted}")
    if total_required > 0:
        completion_rate = total_required_extracted / total_required * 100
        print(f"  完成率: {completion_rate:.1f}%")

    print(f"\n处理速度:")
    print(f"  平均OCR耗时: {avg_time:.2f}秒/张")

    # 各案例详情
    print(f"\n{'='*80}")
    print("各案例详情")
    print(f"{'='*80}")

    for r in all_results:
        print(f"\n{r['case_name']}:")
        print(f"  图片数: {r['total_images']}")
        print(f"  资金监管文档: {r['fund_supervision_docs']}")
        if r['required_fields_total'] > 0:
            rate = r['required_fields_extracted'] / r['required_fields_total'] * 100
            print(f"  必填字段完成率: {r['required_fields_extracted']}/{r['required_fields_total']} = {rate:.1f}%")
        avg_case_time = sum(r['processing_times']) / len(r['processing_times']) if r['processing_times'] else 0
        print(f"  平均OCR耗时: {avg_case_time:.2f}秒/张")


if __name__ == '__main__':
    main()
