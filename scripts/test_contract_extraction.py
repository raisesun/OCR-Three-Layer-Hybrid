#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
购房合同提取精度测试

针对50样本中的购房合同/存量房合同样本，测试：
1. 分类器是否正确识别
2. 处理层（rule/vlm）
3. 字段提取精度
"""

import json
import logging
import time
import sys
from pathlib import Path

# 配置日志（只输出到stderr，不干扰JSON输出）
logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)s %(name)s: %(message)s',
    stream=sys.stderr,
)

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
from ocr_three_layer_hybrid.interfaces import DocumentType, ProcessingLayer


def load_samples():
    """加载购房合同和存量房合同样本"""
    with open('tests/batch_test_50_samples.json') as f:
        samples = json.load(f)
    return [s for s in samples if s.get('cert_code') in ('purchase_contract', 'stock_contract')]


def cert_code_to_chinese(cert_code):
    """将英文cert_code转换为中文名称"""
    mapping = {
        'purchase_contract': ['购房合同', '购房合同-首页', '购房合同-内容页', '购房合同-签署页'],
        'stock_contract': ['存量房合同', '存量房合同-首页', '存量房合同-内容页', '存量房合同-签署页'],
    }
    return mapping.get(cert_code, [cert_code])


def compute_accuracy(extracted_fields, ref_fields):
    """计算字段准确率

    基于实际提取的字段评估，而不是基于基准数据。
    对于每个实际提取到的非空字段，检查是否在基准数据中存在且匹配。

    Returns:
        dict: {
            'accuracy': 准确率 (0-1)，如果没有提取任何字段则为None
            'matched': 匹配的字段数
            'total_extracted': 实际提取的非空字段数
            'matched_fields': 匹配的字段列表
            'mismatched_fields': 不匹配的字段列表（提取值与基准不一致）
            'missing_in_ref': 提取了但基准数据中没有的字段
        }
    """
    # 只统计非空字段
    non_empty_extracted = {k: v for k, v in extracted_fields.items() if v}

    if not non_empty_extracted:
        return {
            'accuracy': None,
            'matched': 0,
            'total_extracted': 0,
            'matched_fields': [],
            'mismatched_fields': [],
            'missing_in_ref': []
        }

    matched = 0
    matched_fields = []
    mismatched_fields = []
    missing_in_ref = []

    for key, ext_value in non_empty_extracted.items():
        if key not in ref_fields:
            # 基准数据中没有这个字段
            missing_in_ref.append(key)
        else:
            ref_value = ref_fields[key]
            # 简单的字符串匹配（去除空格后比较）
            ext_clean = ext_value.replace(' ', '')
            ref_clean = ref_value.replace(' ', '')
            if ref_clean in ext_clean or ext_clean in ref_clean:
                matched += 1
                matched_fields.append(key)
            else:
                mismatched_fields.append({
                    'field': key,
                    'extracted': ext_value,
                    'reference': ref_value
                })

    total_extracted = len(non_empty_extracted)
    accuracy = matched / total_extracted if total_extracted > 0 else None

    return {
        'accuracy': accuracy,
        'matched': matched,
        'total_extracted': total_extracted,
        'matched_fields': matched_fields,
        'mismatched_fields': mismatched_fields,
        'missing_in_ref': missing_in_ref
    }


def main():
    samples = load_samples()

    print(f"加载了 {len(samples)} 个合同样本", file=sys.stderr)
    print("正在初始化OCR引擎...", file=sys.stderr)

    ocr = PaddleOCRWrapper()
    pipeline = PlanEPlusPipeline()

    results = []

    for i, sample in enumerate(samples, 1):
        image_path = sample['image_path']
        cert_code = sample['cert_code']
        case_id = sample['case_id']
        ref_fields = sample.get('ref_fields', {})

        print(f"\n[{i}/{len(samples)}] 处理: {Path(image_path).name} (case={case_id}, type={cert_code})", file=sys.stderr)

        # 运行OCR
        t0 = time.time()
        ocr_texts = ocr.run_ocr_text(image_path)
        ocr_time = time.time() - t0
        full_text = ' '.join(ocr_texts)

        print(f"  OCR: {len(ocr_texts)} 行, 耗时 {ocr_time:.1f}s", file=sys.stderr)
        print(f"  OCR前100字: {full_text[:100]}...", file=sys.stderr)

        # Pipeline处理
        t1 = time.time()
        result = pipeline.process(image_path, ocr_texts)
        process_time = time.time() - t1

        # 提取信息
        layer_name = result.layer.value if result.layer else "unknown"
        doc_type_name = result.doc_type.value if result.doc_type else "unknown"

        # 计算准确率
        accuracy_result = compute_accuracy(result.fields, ref_fields)
        accuracy = accuracy_result['accuracy']

        # 统计提取到的非空字段
        non_empty_fields = {k: v for k, v in result.fields.items() if v}

        result_info = {
            'index': i,
            'image': Path(image_path).name,
            'case_id': case_id,
            'expected_type': cert_code,
            'classified_type': doc_type_name,
            'classified_correct': any(doc_type_name == expected for expected in cert_code_to_chinese(cert_code)),
            'processing_layer': layer_name,
            'success': result.success,
            'extracted_fields': result.fields,
            'non_empty_count': len(non_empty_fields),
            'non_empty_fields': non_empty_fields,
            'ref_fields': ref_fields,
            'accuracy': accuracy,
            'accuracy_detail': accuracy_result,
            'ocr_time': round(ocr_time, 2),
            'process_time': round(process_time, 2),
            'error_message': result.error_message if not result.success else None,
        }

        results.append(result_info)

        # 打印结果
        print(f"  分类: {doc_type_name} (期望: {cert_code}) {'✅' if result_info['classified_correct'] else '❌'}", file=sys.stderr)
        print(f"  处理层: {layer_name}", file=sys.stderr)
        print(f"  提取成功: {result.success}", file=sys.stderr)
        print(f"  提取字段: {len(non_empty_fields)} 个非空", file=sys.stderr)
        if non_empty_fields:
            for k, v in non_empty_fields.items():
                print(f"    {k}: {v[:50]}{'...' if len(v) > 50 else ''}", file=sys.stderr)
        if ref_fields:
            print(f"  参考字段: {list(ref_fields.keys())}", file=sys.stderr)
            if accuracy is not None:
                print(f"  准确率: {accuracy:.0%} ({accuracy_result['matched']}/{accuracy_result['total_extracted']})", file=sys.stderr)
                if accuracy_result['mismatched_fields']:
                    print(f"  ⚠️ 不匹配字段: {[f['field'] for f in accuracy_result['mismatched_fields']]}", file=sys.stderr)
                if accuracy_result['missing_in_ref']:
                    print(f"  ℹ️ 基准数据中缺失: {accuracy_result['missing_in_ref']}", file=sys.stderr)
            else:
                print(f"  准确率: N/A (无提取字段或无参考数据)", file=sys.stderr)
        if result.error_message:
            print(f"  错误: {result.error_message}", file=sys.stderr)
        print(f"  耗时: OCR={ocr_time:.1f}s + 处理={process_time:.1f}s", file=sys.stderr)

    # 汇总统计
    print("\n" + "="*80, file=sys.stderr)
    print("汇总统计", file=sys.stderr)
    print("="*80, file=sys.stderr)

    # 按处理层统计
    rule_results = [r for r in results if r['processing_layer'] == 'rule']
    vlm_results = [r for r in results if r['processing_layer'] == 'vlm']

    print(f"\n总样本数: {len(results)}", file=sys.stderr)
    print(f"Rule层处理: {len(rule_results)} 个", file=sys.stderr)
    print(f"VLM层处理: {len(vlm_results)} 个", file=sys.stderr)

    # 分类正确率
    correct_classify = sum(1 for r in results if r['classified_correct'])
    print(f"\n分类正确率: {correct_classify}/{len(results)} ({correct_classify/len(results):.0%})", file=sys.stderr)

    # 提取成功率
    success_count = sum(1 for r in results if r['success'])
    print(f"提取成功率: {success_count}/{len(results)} ({success_count/len(results):.0%})", file=sys.stderr)

    # 字段准确率（只计算有参考数据的样本）
    accuracy_results = [r for r in results if r['accuracy'] is not None]
    if accuracy_results:
        avg_accuracy = sum(r['accuracy'] for r in accuracy_results) / len(accuracy_results)
        print(f"字段平均准确率: {avg_accuracy:.0%} ({len(accuracy_results)} 个有参考数据的样本)", file=sys.stderr)

    # Rule层 vs VLM层对比
    if rule_results:
        rule_success = sum(1 for r in rule_results if r['success'])
        rule_accuracy_results = [r for r in rule_results if r['accuracy'] is not None]
        rule_avg_accuracy = sum(r['accuracy'] for r in rule_accuracy_results) / len(rule_accuracy_results) if rule_accuracy_results else 0
        rule_avg_fields = sum(r['non_empty_count'] for r in rule_results) / len(rule_results)
        print(f"\nRule层: 成功率={rule_success}/{len(rule_results)}, 平均字段数={rule_avg_fields:.1f}, 平均准确率={rule_avg_accuracy:.0%}", file=sys.stderr)

    if vlm_results:
        vlm_success = sum(1 for r in vlm_results if r['success'])
        vlm_accuracy_results = [r for r in vlm_results if r['accuracy'] is not None]
        vlm_avg_accuracy = sum(r['accuracy'] for r in vlm_accuracy_results) / len(vlm_accuracy_results) if vlm_accuracy_results else 0
        vlm_avg_fields = sum(r['non_empty_count'] for r in vlm_results) / len(vlm_results)
        print(f"VLM层:  成功率={vlm_success}/{len(vlm_results)}, 平均字段数={vlm_avg_fields:.1}, 平均准确率={vlm_avg_accuracy:.0%}", file=sys.stderr)

    # 输出JSON结果
    output_path = 'tests/contract_test_results.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到: {output_path}", file=sys.stderr)


if __name__ == '__main__':
    main()
