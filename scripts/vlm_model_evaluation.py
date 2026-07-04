#!/usr/bin/env python3
"""
VLM 模型多维度评测脚本

评测维度：
1. 准确率：字段提取的准确性
2. 速度：推理耗时
3. 完整性：能提取的字段数量
4. 鲁棒性：对不同文档类型的适应性

评测模型：
- GLM-OCR（端口8080）
- Qwen2.5-VL-7B（端口8082）

增强功能：
- 多页文档支持：购房合同、存量房合同按文件夹处理
- 性能优化：选择性处理关键页面（前15页）

使用方法：
    python scripts/vlm_model_evaluation.py
"""

import sys
import json
import time
import os
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ocr_three_layer_hybrid.config import OCRConfig
from ocr_three_layer_hybrid.service import OCRService

# 多页文档类型（需要处理整个文件夹）
MULTI_PAGE_DOC_TYPES = {'purchase_contract', 'stock_contract'}

# 多页文档最大处理页数（性能优化）
MAX_PAGES_PER_CONTRACT = 15

# 期望字段映射（用于准确率评估）
EXPECTED_FIELDS = {
    "身份证": ["姓名", "性别", "民族", "出生", "住址", "公民身份号码"],
    "户口本": ["户主姓名", "户号", "住址", "姓名", "与户主关系", "公民身份号码"],
    "结婚证": ["持证人", "登记日期", "结婚证字号", "男方姓名", "女方姓名"],
    "离婚证": ["持证人", "登记日期", "离婚证字号"],
    "发票": ["发票代码", "发票号码", "开票日期", "价税合计"],
    "购房合同": ["合同编号", "买受人", "出卖人", "总价款"],
    "存量房合同": ["合同编号", "买受人", "出卖人", "总价款"],
}


def load_test_samples() -> List[Dict]:
    """加载测试样本"""
    samples_file = Path('/Users/dongsun/github/OCR-Three-Layer-Hybrid/tests/batch_test_50_samples.json')
    with open(samples_file, 'r', encoding='utf-8') as f:
        samples = json.load(f)
    return samples


def process_multi_page_document(
    folder_path: str,
    service: OCRService,
    max_pages: int = MAX_PAGES_PER_CONTRACT
) -> Dict[str, Any]:
    """
    处理多页文档（购房合同、存量房合同）

    Args:
        folder_path: 文档文件夹路径
        service: OCR服务实例
        max_pages: 最大处理页数（性能优化）

    Returns:
        合并后的提取结果
    """
    # 获取所有图片文件
    images = sorted([
        f for f in os.listdir(folder_path)
        if f.lower().endswith(('.jpeg', '.jpg', '.png'))
    ])

    if not images:
        return {
            'success': False,
            'fields': {},
            'pages_processed': 0,
            'total_time': 0.0,
        }

    # 限制处理页数（性能优化）
    images_to_process = images[:max_pages]

    # 合并所有页面的字段
    merged_fields = {}
    total_time = 0.0
    pages_processed = 0
    layers_used = defaultdict(int)

    for img_name in images_to_process:
        img_path = os.path.join(folder_path, img_name)

        # OCR
        ocr_start = time.time()
        ocr_text = service.run_ocr(img_path)
        ocr_time = time.time() - ocr_start

        # 提取
        extract_start = time.time()
        result = service.process_single(img_path, ocr_text)
        extract_time = time.time() - extract_start

        page_time = ocr_time + extract_time
        total_time += page_time
        pages_processed += 1

        # 记录使用的层
        layer = result.get('extraction', {}).get('layer', 'unknown')
        layers_used[layer] += 1

        # 合并字段（只保留非空值，优先保留更长的值）
        fields = result.get('extraction', {}).get('fields', {})
        for key, value in fields.items():
            if value and value.strip():
                if key not in merged_fields or len(value) > len(merged_fields[key]):
                    merged_fields[key] = value

    # 统计非空字段数
    non_empty_fields = {k: v for k, v in merged_fields.items() if v and v.strip()}

    return {
        'success': len(non_empty_fields) > 0,
        'fields': merged_fields,
        'pages_processed': pages_processed,
        'total_time': total_time,
        'layers_used': dict(layers_used),
    }


def evaluate_vlm_model(
    engine_name: str,
    samples: List[Dict],
    max_samples: int = 10
) -> Dict[str, Any]:
    """
    评测指定 VLM 模型

    Args:
        engine_name: VLM 引擎名称（glm_ocr | qwen2_5_vl_7b）
        samples: 测试样本列表
        max_samples: 最大测试样本数

    Returns:
        评测结果字典
    """
    print(f"\n{'='*70}")
    print(f"评测 VLM 模型: {engine_name}")
    print(f"{'='*70}\n")

    # 创建配置
    config = OCRConfig()
    config.vlm_extraction_engine = engine_name
    config.enable_vlm_fallback = False  # 禁用 VLM 兜底，只测试主 VLM 层
    config.enable_position_extraction = False  # 禁用位置标注，只测试 VLM
    config.enable_vlm_field_fallback = False

    # 创建服务
    print(f"初始化 OCRService (VLM={engine_name})...")
    service = OCRService(config=config)
    print(f"✅ 初始化完成\n")

    # 统计结果
    results = {
        'engine': engine_name,
        'total_samples': 0,
        'successful_extractions': 0,
        'total_fields_extracted': 0,
        'correct_fields': 0,
        'total_time': 0.0,
        'by_doc_type': defaultdict(lambda: {
            'count': 0,
            'success': 0,
            'fields_extracted': 0,
            'correct_fields': 0,
            'time': 0.0,
        }),
        'errors': [],
    }

    # 测试样本
    test_count = min(max_samples, len(samples))
    print(f"开始测试 {test_count} 个样本...\n")

    for i, sample in enumerate(samples[:test_count]):
        image_path = sample.get('image_path', '')
        expected_type_cn = sample.get('cert_code', '')

        # 映射文档类型
        cert_code_to_cn = {
            'id_card_front': '身份证',
            'id_card_back': '身份证',
            'marriage': '结婚证',
            'hukou': '户口本',
            'purchase_contract': '购房合同',
            'stock_contract': '存量房合同',
            'property': '不动产权证书',
            'invoice': '发票',
            'divorce_certificate': '离婚证',
        }
        doc_type = cert_code_to_cn.get(expected_type_cn, '未知')

        if not Path(image_path).exists():
            print(f"[{i+1}/{test_count}] ⚠️  图片不存在: {image_path}")
            continue

        results['total_samples'] += 1
        results['by_doc_type'][doc_type]['count'] += 1

        try:
            # 检查是否为多页文档
            is_multi_page = expected_type_cn in MULTI_PAGE_DOC_TYPES

            if is_multi_page:
                # 多页文档处理：处理整个文件夹
                folder_path = str(Path(image_path).parent)
                multi_result = process_multi_page_document(folder_path, service)

                total_time = multi_result['total_time']
                extracted_fields = multi_result['fields']
                extraction_success = multi_result['success']
                extraction_layer = 'multi-page'

                # 输出进度
                status = "✅" if extraction_success else "❌"
                field_count = len([v for v in extracted_fields.values() if v])
                pages_processed = multi_result['pages_processed']
                print(f"[{i+1}/{test_count}] {status} {doc_type} | "
                      f"字段={field_count} | "
                      f"页数={pages_processed} | "
                      f"耗时={total_time:.1f}s")
            else:
                # 单页文档处理：只处理当前图片
                # 先 OCR
                ocr_start = time.time()
                ocr_text = service.run_ocr(image_path)
                ocr_time = time.time() - ocr_start

                # 再提取
                extract_start = time.time()
                result = service.process_single(image_path, ocr_text)
                extract_time = time.time() - extract_start
                total_time = ocr_time + extract_time

                # 统计提取结果
                extracted_fields = result.get('extraction', {}).get('fields', {})
                extraction_success = result.get('extraction', {}).get('success', False)
                extraction_layer = result.get('extraction', {}).get('layer', 'unknown')

                # 输出进度
                status = "✅" if extraction_success else "❌"
                field_count = len([v for v in extracted_fields.values() if v])
                print(f"[{i+1}/{test_count}] {status} {doc_type} | "
                      f"字段={field_count} | "
                      f"层={extraction_layer} | "
                      f"耗时={total_time:.1f}s")

            results['total_time'] += total_time
            results['by_doc_type'][doc_type]['time'] += total_time

            if extraction_success:
                results['successful_extractions'] += 1
                results['by_doc_type'][doc_type]['success'] += 1

            # 统计字段数量
            field_count = len([v for v in extracted_fields.values() if v])
            results['total_fields_extracted'] += field_count
            results['by_doc_type'][doc_type]['fields_extracted'] += field_count

            # 评估准确率（如果有期望字段）
            expected = EXPECTED_FIELDS.get(doc_type, [])
            if expected:
                correct = 0
                for field_name in expected:
                    if field_name in extracted_fields and extracted_fields[field_name]:
                        correct += 1
                results['correct_fields'] += correct
                results['by_doc_type'][doc_type]['correct_fields'] += correct

        except Exception as e:
            import traceback
            error_msg = f"{doc_type}: {str(e)}"
            results['errors'].append(error_msg)
            print(f"[{i+1}/{test_count}] ❌ {doc_type} | 错误: {str(e)[:100]}")
            print(f"   详细错误: {traceback.format_exc()}")

    # 计算指标
    total_samples = results['total_samples']
    if total_samples > 0:
        results['success_rate'] = results['successful_extractions'] / total_samples * 100
        results['avg_fields_per_doc'] = results['total_fields_extracted'] / total_samples
        results['avg_time_per_doc'] = results['total_time'] / total_samples

        if results['total_fields_extracted'] > 0:
            results['field_accuracy'] = results['correct_fields'] / results['total_fields_extracted'] * 100
        else:
            results['field_accuracy'] = 0.0

    return results


def print_evaluation_report(results: Dict[str, Any]):
    """打印评测报告"""
    engine = results['engine']

    print(f"\n{'='*70}")
    print(f"评测报告: {engine}")
    print(f"{'='*70}\n")

    # 总体指标
    print("📊 总体指标:")
    print(f"  测试样本数: {results['total_samples']}")
    print(f"  成功提取数: {results['successful_extractions']}")
    print(f"  成功率: {results.get('success_rate', 0):.1f}%")
    print(f"  平均字段数: {results.get('avg_fields_per_doc', 0):.1f} 字段/文档")
    print(f"  字段准确率: {results.get('field_accuracy', 0):.1f}%")
    print(f"  平均耗时: {results.get('avg_time_per_doc', 0):.1f} 秒/文档")
    print()

    # 按文档类型统计
    print("📋 按文档类型统计:")
    print(f"  {'文档类型':<12} {'样本数':>6} {'成功数':>6} {'成功率':>8} {'平均字段':>8} {'平均耗时':>8}")
    print(f"  {'-'*60}")

    for doc_type, stats in sorted(results['by_doc_type'].items()):
        count = stats['count']
        success = stats['success']
        success_rate = success / count * 100 if count > 0 else 0
        avg_fields = stats['fields_extracted'] / count if count > 0 else 0
        avg_time = stats['time'] / count if count > 0 else 0

        print(f"  {doc_type:<12} {count:>6} {success:>6} {success_rate:>7.1f}% {avg_fields:>8.1f} {avg_time:>7.1f}s")

    print()

    # 错误统计
    if results['errors']:
        print(f"❌ 错误 ({len(results['errors'])}个):")
        for error in results['errors'][:5]:
            print(f"  - {error}")
        if len(results['errors']) > 5:
            print(f"  ... 还有 {len(results['errors']) - 5} 个错误")

    print()


def compare_models(glm_results: Dict[str, Any], qwen_results: Dict[str, Any]):
    """对比两个模型的评测结果"""
    print(f"\n{'='*70}")
    print("📊 模型对比")
    print(f"{'='*70}\n")

    metrics = [
        ('成功率', 'success_rate', '%'),
        ('平均字段数', 'avg_fields_per_doc', '字段/文档'),
        ('字段准确率', 'field_accuracy', '%'),
        ('平均耗时', 'avg_time_per_doc', '秒/文档'),
    ]

    print(f"  {'指标':<15} {'GLM-OCR':>15} {'Qwen2.5-VL-7B':>15} {'差异':>15}")
    print(f"  {'-'*65}")

    for metric_name, metric_key, unit in metrics:
        glm_value = glm_results.get(metric_key, 0)
        qwen_value = qwen_results.get(metric_key, 0)
        diff = qwen_value - glm_value

        if metric_key == 'avg_time_per_doc':
            # 耗时越短越好
            diff_symbol = "✅" if diff < 0 else "❌"
        else:
            # 其他指标越高越好
            diff_symbol = "✅" if diff > 0 else "❌"

        print(f"  {metric_name:<15} {glm_value:>14.1f}{unit:<3} {qwen_value:>14.1f}{unit:<3} {diff_symbol} {diff:>+10.1f}")

    print()


def main():
    print("="*70)
    print("VLM 模型多维度评测")
    print("="*70)

    # 加载测试样本
    samples = load_test_samples()
    print(f"加载测试样本: {len(samples)} 个")

    # 评测参数
    max_samples = 50  # 每个模型测试 50 个样本（全量测试）

    # 评测 GLM-OCR
    glm_results = evaluate_vlm_model('glm_ocr', samples, max_samples)
    print_evaluation_report(glm_results)

    # 评测 Qwen2.5-VL-7B
    qwen_results = evaluate_vlm_model('qwen2_5_vl_7b', samples, max_samples)
    print_evaluation_report(qwen_results)

    # 对比两个模型
    compare_models(glm_results, qwen_results)

    print("="*70)
    print("✅ 评测完成")
    print("="*70)


if __name__ == "__main__":
    main()
