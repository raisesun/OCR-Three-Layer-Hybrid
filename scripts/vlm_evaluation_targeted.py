#!/usr/bin/env python3
"""
VLM 模型定向评测 - 按业务分类测试

针对修复后的 VLM 分类器(Qwen2.5-VL-7B)进行验证测试
每个业务分类只测试一个子目录,快速验证修复效果

评测目标:
1. 验证 VLM 分类兜底功能是否正常(Qwen2.5-VL-7B)
2. 对比 GLM-OCR 和 Qwen2.5-VL-7B 在两个业务分类上的表现
3. 验证多页文档处理(购房合同/存量房合同)

使用方法:
    python3 scripts/vlm_evaluation_targeted.py
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


def process_single_directory(
    folder_path: str,
    service: OCRService,
    business_type: str,
    max_pages: int = 15
) -> Dict[str, Any]:
    """
    处理单个业务目录

    Args:
        folder_path: 业务目录路径
        service: OCR服务实例
        business_type: 业务类型(存量房/增量房)
        max_pages: 多页文档最大处理页数

    Returns:
        处理结果统计
    """
    folder_name = Path(folder_path).name

    # 获取所有图片文件
    images = sorted([
        f for f in os.listdir(folder_path)
        if f.lower().endswith(('.jpeg', '.jpg', '.png'))
    ])

    if not images:
        return {
            'business_type': business_type,
            'folder': folder_name,
            'success': False,
            'error': 'No images found',
            'total_images': 0,
            'processed_images': 0,
            'fields_extracted': 0,
            'doc_types': {},
            'layers_used': {},
            'total_time': 0.0,
        }

    print(f"\n处理目录: {folder_name}")
    print(f"  图片数量: {len(images)}")

    # 统计结果
    results = {
        'business_type': business_type,
        'folder': folder_name,
        'success': True,
        'total_images': len(images),
        'processed_images': 0,
        'fields_extracted': 0,
        'doc_types': defaultdict(int),
        'layers_used': defaultdict(int),
        'classification_methods': defaultdict(int),
        'total_time': 0.0,
        'errors': [],
    }

    for i, img_name in enumerate(images[:max_pages]):
        img_path = os.path.join(folder_path, img_name)

        try:
            # OCR
            ocr_start = time.time()
            ocr_text = service.run_ocr(img_path)
            ocr_time = time.time() - ocr_start

            # 分类 + 提取
            process_start = time.time()
            result = service.process_single(img_path, ocr_text)
            process_time = time.time() - process_start

            total_time = ocr_time + process_time
            results['total_time'] += total_time
            results['processed_images'] += 1

            # 统计分类结果
            doc_type = result['classification']['doc_type']
            route = result['classification']['route']
            results['doc_types'][doc_type] += 1

            # 统计分类方法
            if route == 'vlm_classification':
                results['classification_methods']['vlm_fallback'] += 1
            else:
                results['classification_methods']['rule'] += 1

            # 统计提取层
            layer = result['extraction']['layer']
            results['layers_used'][layer] += 1

            # 统计提取字段数
            fields = result['extraction']['fields']
            field_count = len([v for v in fields.values() if v and v.strip()])
            results['fields_extracted'] += field_count

            # 输出进度
            status = "✅" if result['extraction']['success'] else "❌"
            print(f"  [{i+1}/{len(images)}] {img_name[:40]}... | {status} | 类型={doc_type} | 层={layer} | 字段={field_count} | 耗时={total_time:.1f}s")

        except Exception as e:
            error_msg = f"{img_name}: {str(e)}"
            results['errors'].append(error_msg)
            print(f"  [{i+1}/{len(images)}] {img_name[:40]}... | ❌ 错误: {str(e)[:50]}")

    # 转换 defaultdict 为普通 dict
    results['doc_types'] = dict(results['doc_types'])
    results['layers_used'] = dict(results['layers_used'])
    results['classification_methods'] = dict(results['classification_methods'])

    return results


def evaluate_business_category(
    base_path: str,
    business_type: str,
    service: OCRService,
    sample_count: int = 1
) -> List[Dict[str, Any]]:
    """
    评测一个业务分类

    Args:
        base_path: 业务分类根目录
        business_type: 业务类型名称
        service: OCR服务实例
        sample_count: 测试的子目录数量

    Returns:
        各子目录的处理结果列表
    """
    print(f"\n{'='*70}")
    print(f"评测业务分类: {business_type}")
    print(f"{'='*70}")

    # 获取子目录列表
    subdirs = sorted([
        d for d in os.listdir(base_path)
        if os.path.isdir(os.path.join(base_path, d))
    ])

    if not subdirs:
        print(f"⚠️  未找到子目录: {base_path}")
        return []

    # 只处理前 sample_count 个子目录
    test_subdirs = subdirs[:sample_count]
    print(f"测试子目录数: {len(test_subdirs)} / {len(subdirs)}")

    results = []
    for subdir in test_subdirs:
        subdir_path = os.path.join(base_path, subdir)
        result = process_single_directory(subdir_path, service, business_type)
        results.append(result)

    return results


def print_business_summary(results: List[Dict[str, Any]], business_type: str):
    """打印业务分类的汇总统计"""
    if not results:
        print(f"\n{business_type}: 无测试结果")
        return

    print(f"\n{'='*70}")
    print(f"{business_type} - 汇总统计")
    print(f"{'='*70}")

    total_images = sum(r['processed_images'] for r in results)
    total_fields = sum(r['fields_extracted'] for r in results)
    total_time = sum(r['total_time'] for r in results)

    # 合并文档类型统计
    all_doc_types = defaultdict(int)
    all_layers = defaultdict(int)
    all_methods = defaultdict(int)

    for r in results:
        for doc_type, count in r['doc_types'].items():
            all_doc_types[doc_type] += count
        for layer, count in r['layers_used'].items():
            all_layers[layer] += count
        for method, count in r['classification_methods'].items():
            all_methods[method] += count

    print(f"\n测试目录数: {len(results)}")
    print(f"处理图片数: {total_images}")
    print(f"提取字段数: {total_fields}")
    print(f"总耗时: {total_time:.1f}s")
    print(f"平均耗时: {total_time/total_images:.1f}s/张" if total_images > 0 else "N/A")

    print(f"\n文档类型分布:")
    for doc_type, count in sorted(all_doc_types.items(), key=lambda x: -x[1]):
        print(f"  {doc_type}: {count}")

    print(f"\n提取层分布:")
    for layer, count in sorted(all_layers.items(), key=lambda x: -x[1]):
        print(f"  {layer}: {count}")

    print(f"\n分类方法分布:")
    for method, count in sorted(all_methods.items(), key=lambda x: -x[1]):
        method_name = "规则分类" if method == "rule" else "VLM兜底"
        print(f"  {method_name}: {count}")

    # 错误统计
    all_errors = []
    for r in results:
        all_errors.extend(r.get('errors', []))

    if all_errors:
        print(f"\n❌ 错误 ({len(all_errors)}个):")
        for error in all_errors[:5]:
            print(f"  - {error[:100]}")
        if len(all_errors) > 5:
            print(f"  ... 还有 {len(all_errors) - 5} 个错误")


def compare_vlm_engines(
    stock_results: List[Dict[str, Any]],
    new_results: List[Dict[str, Any]],
    engine_name: str
):
    """对比两个业务分类在指定VLM引擎下的表现"""
    print(f"\n{'='*70}")
    print(f"VLM引擎: {engine_name}")
    print(f"{'='*70}")

    all_results = stock_results + new_results

    total_images = sum(r['processed_images'] for r in all_results)
    total_fields = sum(r['fields_extracted'] for r in all_results)
    total_time = sum(r['total_time'] for r in all_results)

    # 合并统计
    all_doc_types = defaultdict(int)
    all_layers = defaultdict(int)
    all_methods = defaultdict(int)

    for r in all_results:
        for doc_type, count in r['doc_types'].items():
            all_doc_types[doc_type] += count
        for layer, count in r['layers_used'].items():
            all_layers[layer] += count
        for method, count in r['classification_methods'].items():
            all_methods[method] += count

    print(f"\n总体统计:")
    print(f"  处理图片数: {total_images}")
    print(f"  提取字段数: {total_fields}")
    print(f"  平均字段数: {total_fields/total_images:.1f}/张" if total_images > 0 else "N/A")
    print(f"  总耗时: {total_time:.1f}s")
    print(f"  平均耗时: {total_time/total_images:.1f}s/张" if total_images > 0 else "N/A")

    print(f"\n文档类型分布:")
    for doc_type, count in sorted(all_doc_types.items(), key=lambda x: -x[1]):
        print(f"  {doc_type}: {count}")

    print(f"\n提取层分布:")
    for layer, count in sorted(all_layers.items(), key=lambda x: -x[1]):
        print(f"  {layer}: {count}")

    print(f"\n分类方法分布:")
    rule_count = all_methods.get('rule', 0)
    vlm_count = all_methods.get('vlm_fallback', 0)
    total_classified = rule_count + vlm_count
    if total_classified > 0:
        print(f"  规则分类: {rule_count} ({rule_count/total_classified*100:.1f}%)")
        print(f"  VLM兜底: {vlm_count} ({vlm_count/total_classified*100:.1f}%)")


def main():
    print("="*70)
    print("VLM 模型定向评测 - 按业务分类测试")
    print("="*70)

    # 配置
    sample_path = "/Users/dongsun/Github/sample-OCR"
    stock_path = os.path.join(sample_path, "存量房图片资料")
    new_path = os.path.join(sample_path, "增量房图片资料")

    # 每个业务分类只测试1个子目录
    sample_count = 1

    # 评测 GLM-OCR
    print(f"\n{'='*70}")
    print("评测 VLM 引擎: GLM-OCR (端口8080)")
    print(f"{'='*70}")

    config_glm = OCRConfig()
    config_glm.vlm_extraction_engine = "glm_ocr"
    config_glm.enable_vlm_fallback = True
    config_glm.enable_position_extraction = True
    config_glm.enable_vlm_field_fallback = True

    service_glm = OCRService(config=config_glm)
    print(f"✅ GLM-OCR 服务初始化完成")

    stock_results_glm = evaluate_business_category(stock_path, "存量房", service_glm, sample_count)
    new_results_glm = evaluate_business_category(new_path, "增量房", service_glm, sample_count)

    print_business_summary(stock_results_glm, "存量房 - GLM-OCR")
    print_business_summary(new_results_glm, "增量房 - GLM-OCR")
    compare_vlm_engines(stock_results_glm, new_results_glm, "GLM-OCR")

    # 评测 Qwen2.5-VL-7B
    print(f"\n{'='*70}")
    print("评测 VLM 引擎: Qwen2.5-VL-7B (端口8082)")
    print(f"{'='*70}")

    config_qwen = OCRConfig()
    config_qwen.vlm_extraction_engine = "qwen2_5_vl_7b"
    config_qwen.enable_vlm_fallback = True
    config_qwen.enable_position_extraction = True
    config_qwen.enable_vlm_field_fallback = True

    service_qwen = OCRService(config=config_qwen)
    print(f"✅ Qwen2.5-VL-7B 服务初始化完成")

    stock_results_qwen = evaluate_business_category(stock_path, "存量房", service_qwen, sample_count)
    new_results_qwen = evaluate_business_category(new_path, "增量房", service_qwen, sample_count)

    print_business_summary(stock_results_qwen, "存量房 - Qwen2.5-VL-7B")
    print_business_summary(new_results_qwen, "增量房 - Qwen2.5-VL-7B")
    compare_vlm_engines(stock_results_qwen, new_results_qwen, "Qwen2.5-VL-7B")

    # 对比两个VLM引擎
    print(f"\n{'='*70}")
    print("VLM 引擎对比")
    print(f"{'='*70}")

    glm_total_images = sum(r['processed_images'] for r in stock_results_glm + new_results_glm)
    glm_total_fields = sum(r['fields_extracted'] for r in stock_results_glm + new_results_glm)
    glm_total_time = sum(r['total_time'] for r in stock_results_glm + new_results_glm)

    qwen_total_images = sum(r['processed_images'] for r in stock_results_qwen + new_results_qwen)
    qwen_total_fields = sum(r['fields_extracted'] for r in stock_results_qwen + new_results_qwen)
    qwen_total_time = sum(r['total_time'] for r in stock_results_qwen + new_results_qwen)

    print(f"\n{'指标':<20} {'GLM-OCR':>15} {'Qwen2.5-VL-7B':>15} {'差异':>15}")
    print(f"{'-'*70}")

    print(f"{'处理图片数':<20} {glm_total_images:>15} {qwen_total_images:>15} {qwen_total_images - glm_total_images:>15}")
    print(f"{'提取字段数':<20} {glm_total_fields:>15} {qwen_total_fields:>15} {qwen_total_fields - glm_total_fields:>15}")

    glm_avg_fields = glm_total_fields / glm_total_images if glm_total_images > 0 else 0
    qwen_avg_fields = qwen_total_fields / qwen_total_images if qwen_total_images > 0 else 0
    print(f"{'平均字段数/张':<20} {glm_avg_fields:>14.1f} {qwen_avg_fields:>14.1f} {qwen_avg_fields - glm_avg_fields:>+14.1f}")

    glm_avg_time = glm_total_time / glm_total_images if glm_total_images > 0 else 0
    qwen_avg_time = qwen_total_time / qwen_total_images if qwen_total_images > 0 else 0
    time_diff_symbol = "✅" if qwen_avg_time < glm_avg_time else "❌"
    print(f"{'平均耗时/张':<20} {glm_avg_time:>13.1f}s {qwen_avg_time:>13.1f}s {time_diff_symbol} {qwen_avg_time - glm_avg_time:>+10.1f}s")

    # VLM 分类兜底使用统计
    glm_vlm_count = sum(r['classification_methods'].get('vlm_fallback', 0) for r in stock_results_glm + new_results_glm)
    qwen_vlm_count = sum(r['classification_methods'].get('vlm_fallback', 0) for r in stock_results_qwen + new_results_qwen)

    print(f"\n{'VLM分类兜底次数':<20} {glm_vlm_count:>15} {qwen_vlm_count:>15}")
    print(f"{'(验证修复效果)':<20} {'(应>0)':>15} {'(应>0)':>15}")

    print(f"\n{'='*70}")
    print("✅ 定向评测完成")
    print(f"{'='*70}")

    # 关键验证点
    print(f"\n关键验证点:")
    print(f"1. VLM分类兜底功能: {'✅ 正常' if glm_vlm_count > 0 or qwen_vlm_count > 0 else '❌ 未触发'}")
    print(f"   - GLM-OCR 触发 {glm_vlm_count} 次")
    print(f"   - Qwen2.5-VL-7B 触发 {qwen_vlm_count} 次")
    print(f"2. 推荐VLM引擎: {'Qwen2.5-VL-7B' if qwen_avg_time < glm_avg_time else 'GLM-OCR'} (速度优势)")


if __name__ == "__main__":
    main()
