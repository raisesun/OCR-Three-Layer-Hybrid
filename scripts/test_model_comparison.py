#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLM 模型对比测试脚本

对比 Qwen2.5-VL-3B vs Qwen2.5-VL-7B 的提取能力
"""

import json
import logging
import time
import sys
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

# 配置日志
logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)s %(name)s: %(message)s',
    stream=sys.stderr,
)

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
from ocr_three_layer_hybrid.interfaces import DocumentType, ProcessingLayer
from ocr_three_layer_hybrid.config import OCRConfig, QwenVLServiceConfig


@dataclass
class ModelTestResult:
    """单个模型的测试结果"""
    model_name: str
    total_samples: int
    success_count: int
    total_fields: int
    total_matched: int
    total_time: float
    accuracy: float
    details: List[Dict]


def load_samples():
    """加载测试样本"""
    with open('tests/batch_test_50_samples.json') as f:
        samples = json.load(f)
    return [s for s in samples if s.get('cert_code') in ('purchase_contract', 'stock_contract')]


def compute_accuracy(extracted_fields, ref_fields):
    """计算字段准确率（基于实际提取）"""
    non_empty_extracted = {k: v for k, v in extracted_fields.items() if v}

    if not non_empty_extracted:
        return {
            'accuracy': None,
            'matched': 0,
            'total_extracted': 0,
            'matched_fields': [],
            'missing_in_ref': []
        }

    matched = 0
    matched_fields = []
    missing_in_ref = []

    for key, ext_value in non_empty_extracted.items():
        if key not in ref_fields:
            missing_in_ref.append(key)
        else:
            ref_value = ref_fields[key]
            ext_clean = ext_value.replace(' ', '')
            ref_clean = ref_value.replace(' ', '')
            if ref_clean in ext_clean or ext_clean in ref_clean:
                matched += 1
                matched_fields.append(key)

    total_extracted = len(non_empty_extracted)
    accuracy = matched / total_extracted if total_extracted > 0 else None

    return {
        'accuracy': accuracy,
        'matched': matched,
        'total_extracted': total_extracted,
        'matched_fields': matched_fields,
        'missing_in_ref': missing_in_ref
    }


def test_model(model_name: str, port: int, samples: List[Dict]) -> ModelTestResult:
    """测试单个模型"""
    print(f"\n{'='*80}", file=sys.stderr)
    print(f"测试模型: {model_name} (端口 {port})", file=sys.stderr)
    print(f"{'='*80}", file=sys.stderr)

    # 初始化 OCR
    ocr = PaddleOCRWrapper()

    # 创建自定义 VLM 层
    from ocr_three_layer_hybrid.vlm_layer import VLMExtractionLayer
    vlm_layer = VLMExtractionLayer(
        model_name=model_name,
        base_url=f"http://localhost:{port}/v1"
    )

    # 初始化 Pipeline
    pipeline = PlanEPlusPipeline(vlm_layer=vlm_layer)

    results = []
    total_fields = 0
    total_matched = 0
    success_count = 0
    total_time = 0.0

    for i, sample in enumerate(samples, 1):
        image_path = sample['image_path']
        cert_code = sample['cert_code']
        case_id = sample['case_id']
        ref_fields = sample.get('ref_fields', {})

        print(f"\n[{i}/{len(samples)}] {Path(image_path).name} (case={case_id})", file=sys.stderr)

        # 运行 OCR
        t0 = time.time()
        ocr_texts = ocr.run_ocr_text(image_path)
        ocr_time = time.time() - t0

        # Pipeline 处理
        t1 = time.time()
        result = pipeline.process(image_path, ocr_texts)
        process_time = time.time() - t1

        # 统计
        non_empty_fields = {k: v for k, v in result.fields.items() if v}
        accuracy_result = compute_accuracy(result.fields, ref_fields)

        total_fields += accuracy_result['total_extracted']
        total_matched += accuracy_result['matched']
        if result.success:
            success_count += 1
        total_time += ocr_time + process_time

        # 记录详情
        detail = {
            'index': i,
            'image': Path(image_path).name,
            'case_id': case_id,
            'classified_type': result.doc_type.value if result.doc_type else "unknown",
            'success': result.success,
            'extracted_fields': len(non_empty_fields),
            'matched_fields': accuracy_result['matched'],
            'accuracy': accuracy_result['accuracy'],
            'ocr_time': round(ocr_time, 2),
            'process_time': round(process_time, 2),
        }
        results.append(detail)

        # 打印进度
        acc_str = f"{accuracy_result['accuracy']:.0%}" if accuracy_result['accuracy'] else "N/A"
        print(f"  提取: {len(non_empty_fields)}个, 匹配: {accuracy_result['matched']}/{accuracy_result['total_extracted']} = {acc_str}", file=sys.stderr)
        print(f"  耗时: OCR={ocr_time:.1f}s + 处理={process_time:.1f}s", file=sys.stderr)

    # 计算总体准确率
    overall_accuracy = total_matched / total_fields if total_fields > 0 else 0

    print(f"\n{'='*80}", file=sys.stderr)
    print(f"模型 {model_name} 测试完成", file=sys.stderr)
    print(f"{'='*80}", file=sys.stderr)
    print(f"总样本: {len(samples)}", file=sys.stderr)
    print(f"成功数: {success_count}/{len(samples)}", file=sys.stderr)
    print(f"总提取字段: {total_fields}", file=sys.stderr)
    print(f"总匹配字段: {total_matched}", file=sys.stderr)
    print(f"平均准确率: {overall_accuracy:.0%}", file=sys.stderr)
    print(f"总耗时: {total_time:.1f}s", file=sys.stderr)
    print(f"平均耗时: {total_time/len(samples):.1f}s/样本", file=sys.stderr)

    return ModelTestResult(
        model_name=model_name,
        total_samples=len(samples),
        success_count=success_count,
        total_fields=total_fields,
        total_matched=total_matched,
        total_time=total_time,
        accuracy=overall_accuracy,
        details=results
    )


def main():
    # 加载样本
    samples = load_samples()
    print(f"加载了 {len(samples)} 个合同样本", file=sys.stderr)

    # 检查 VLM 服务是否运行
    import requests

    models_to_test = [
        ("Qwen2.5-VL-3B", 8083),  # 3B 模型，端口 8083
        ("Qwen2.5-VL-7B", 8082),  # 7B 模型，端口 8082
    ]

    # 检查服务状态
    for model_name, port in models_to_test:
        try:
            resp = requests.get(f"http://localhost:{port}/v1/models", timeout=5)
            if resp.status_code == 200:
                print(f"✓ {model_name} 服务运行中 (端口 {port})", file=sys.stderr)
            else:
                print(f"✗ {model_name} 服务异常 (端口 {port})", file=sys.stderr)
                return
        except Exception as e:
            print(f"✗ {model_name} 服务未启动 (端口 {port}): {e}", file=sys.stderr)
            print(f"\n请先启动服务:", file=sys.stderr)
            print(f"  {model_name}: cd /Users/dongsun/Github/models-OCR/{model_name.replace('-', '').replace('.', '')} && llama-server ...", file=sys.stderr)
            return

    # 运行测试
    all_results = []

    for model_name, port in models_to_test:
        result = test_model(model_name, port, samples)
        all_results.append(result)

    # 输出对比报告
    print(f"\n{'='*80}", file=sys.stderr)
    print(f"模型对比报告", file=sys.stderr)
    print(f"{'='*80}", file=sys.stderr)

    print(f"\n{'模型':<20} {'样本数':<10} {'成功率':<10} {'准确率':<10} {'总耗时':<10} {'平均耗时':<10}", file=sys.stderr)
    print("-" * 80, file=sys.stderr)

    for r in all_results:
        success_rate = r.success_count / r.total_samples
        avg_time = r.total_time / r.total_samples
        print(f"{r.model_name:<20} {r.total_samples:<10} {success_rate:<10.0%} {r.accuracy:<10.0%} {r.total_time:<10.1f}s {avg_time:<10.1f}s", file=sys.stderr)

    # 保存详细结果
    output_path = 'tests/model_comparison_results.json'
    with open(output_path, 'w') as f:
        json.dump([r.__dict__ for r in all_results], f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到: {output_path}", file=sys.stderr)


if __name__ == '__main__':
    main()
