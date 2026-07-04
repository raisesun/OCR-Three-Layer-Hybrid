#!/usr/bin/env python3
"""
诊断凭证字段提取问题

分析凭证的OCR文本，找出字段提取失败的原因
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer
from ocr_three_layer_hybrid.interfaces import DocumentType


def analyze_certificate(case_dir: Path, pipeline: PlanEPlusPipeline, ocr: PaddleOCRWrapper):
    """分析凭证的OCR文本"""
    print(f"\n{'='*80}")
    print(f"分析案例: {case_dir.name}")
    print(f"{'='*80}")

    # 获取所有图片
    image_files = sorted(list(case_dir.glob("*.jpg")) + list(case_dir.glob("*.png")))

    # 查找凭证图片
    for img_path in image_files:
        # OCR
        ocr_result = ocr.run_ocr(str(img_path))

        # 分类
        doc_info = pipeline.classifier.classify(str(img_path), [ocr_result.full_text])

        # 如果是凭证
        if doc_info.doc_type == DocumentType.FUND_SUPERVISION_CERTIFICATE:
            print(f"\n凭证图片: {img_path.name}")
            print(f"OCR文本:\n{ocr_result.full_text}")
            print(f"\n{'='*80}")
            print("字段提取结果:")
            print(f"{'='*80}")

            # 提取字段
            key_list = pipeline.key_lists[doc_info.doc_type]
            extraction_result = pipeline.rule_layer.extract(doc_info, key_list)

            # 显示结果
            for field in key_list:
                value = extraction_result.fields.get(field, "")
                status = "✓" if value else "✗"
                print(f"{status} {field}: {value if value else '[缺失]'}")

            # 分析正则表达式匹配情况
            print(f"\n{'='*80}")
            print("正则表达式诊断:")
            print(f"{'='*80}")

            import re
            full_text = ocr_result.full_text

            # 日期
            print("\n【日期】")
            match = re.search(r'日期\s*[:：]\s*(\d{4}年\d{1,2}月\d{1,2}日)', full_text)
            if match:
                print(f"  ✓ 匹配成功: {match.group(1)}")
            else:
                print(f"  ✗ 匹配失败")
                # 查找包含"日期"的行
                for line in full_text.split('\n'):
                    if '日期' in line:
                        print(f"    实际文本: {line.strip()}")

            # 买房人
            print("\n【买房人】")
            match = re.search(r'买房人\s*[:：]\s*([^\n]+)', full_text)
            if match:
                print(f"  ✓ 匹配成功: {match.group(1)}")
            else:
                print(f"  ✗ 匹配失败")
                for line in full_text.split('\n'):
                    if '买房人' in line:
                        print(f"    实际文本: {line.strip()}")

            # 买房人姓名
            print("\n【买房人姓名】")
            match = re.search(r'买房人姓名\s*[:：]\s*([^\n]+)', full_text)
            if match:
                print(f"  ✓ 匹配成功: {match.group(1)}")
            else:
                print(f"  ✗ 匹配失败")
                for line in full_text.split('\n'):
                    if '买房人' in line or '姓名' in line:
                        print(f"    实际文本: {line.strip()}")

            # 身份证号
            print("\n【身份证号】")
            match = re.search(r'身份证号\s*[:：]\s*([^\n]+)', full_text)
            if match:
                print(f"  ✓ 匹配成功: {match.group(1)}")
            else:
                print(f"  ✗ 匹配失败")
                for line in full_text.split('\n'):
                    if '身份证' in line:
                        print(f"    实际文本: {line.strip()}")

            # 房屋坐落
            print("\n【房屋坐落】")
            match = re.search(r'房屋坐落\s*[:：]\s*([^\n]+)', full_text)
            if match:
                print(f"  ✓ 匹配成功: {match.group(1)}")
            else:
                print(f"  ✗ 匹配失败")
                for line in full_text.split('\n'):
                    if '房屋' in line or '坐落' in line:
                        print(f"    实际文本: {line.strip()}")

            # 建筑面积
            print("\n【建筑面积】")
            match = re.search(r'建筑面积\s*[:：]\s*([^\n]+)', full_text)
            if match:
                print(f"  ✓ 匹配成功: {match.group(1)}")
            else:
                print(f"  ✗ 匹配失败")
                for line in full_text.split('\n'):
                    if '建筑面积' in line or '平方米' in line:
                        print(f"    实际文本: {line.strip()}")

            # 监管总额
            print("\n【监管总额】")
            match = re.search(r'监管总额\s*[:：]\s*([^\n]+)', full_text)
            if match:
                print(f"  ✓ 匹配成功: {match.group(1)}")
            else:
                print(f"  ✗ 匹配失败")
                for line in full_text.split('\n'):
                    if '监管总额' in line or '人民币' in line:
                        print(f"    实际文本: {line.strip()}")

            # 收款单位
            print("\n【收款单位】")
            match = re.search(r'收款单位\s*[:：]\s*([^\n]+)', full_text)
            if match:
                print(f"  ✓ 匹配成功: {match.group(1)}")
            else:
                print(f"  ✗ 匹配失败")
                for line in full_text.split('\n'):
                    if '收款单位' in line or '收款' in line:
                        print(f"    实际文本: {line.strip()}")

            print(f"\n{'='*80}\n")

            # 只分析第一个凭证
            return True

    print(f"\n未找到凭证图片")
    return False


def main():
    """主函数"""
    print("="*80)
    print("凭证字段提取诊断")
    print("="*80)

    # 初始化
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
    classifier = KeywordDocumentClassifier()
    rule_layer = RuleExtractionLayer()
    pipeline = PlanEPlusPipeline(classifier=classifier, rule_layer=rule_layer, vlm_layer=None)

    # 测试案例
    sample_dir = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料')
    test_case = 'BBJZ-2026-0113059'

    case_dir = sample_dir / test_case
    if not case_dir.exists():
        print(f"错误: 案例 {test_case} 不存在")
        return

    analyze_certificate(case_dir, pipeline, ocr)


if __name__ == '__main__':
    main()
