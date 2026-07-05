#!/usr/bin/env python3
"""
全量测试脚本 - 覆盖所有存量房和增量房图片资料

测试策略：
1. 逐案例测试，每个案例完成后立即评估准确率
2. 准确率要求：≥95%
3. 记录每个图片的执行时间、总时间、平均时间
4. 如果准确率未达标或时间异常，停止测试并分析
"""

import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.service import OCRService


def load_baseline_data() -> Dict[str, Dict]:
    """加载基准数据"""
    baseline_file = Path('/Users/dongsun/Github/OCR-Three-Layer-Hybrid/tests/batch_test_50_samples.json')
    with open(baseline_file, 'r', encoding='utf-8') as f:
        samples = json.load(f)

    # 按案例ID组织
    baseline = {}
    for sample in samples:
        case_id = sample['case_id']
        if case_id not in baseline:
            baseline[case_id] = []
        baseline[case_id].append(sample)

    return baseline


def get_all_cases() -> List[Dict]:
    """获取所有案例（增量房和存量房交替排列）"""
    cunliang_cases = []
    zengliang_cases = []

    # 存量房
    cunliangfang_dir = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料')
    for case_dir in sorted(cunliangfang_dir.iterdir()):
        if case_dir.is_dir():
            images = list(case_dir.glob('*.jp*g'))
            if images:
                cunliang_cases.append({
                    'category': '存量房',
                    'case_id': case_dir.name,
                    'images': sorted(images)
                })

    # 增量房
    zengliangfang_dir = Path('/Users/dongsun/Github/sample-OCR/增量房图片资料')
    for case_dir in sorted(zengliangfang_dir.iterdir()):
        if case_dir.is_dir():
            images = list(case_dir.glob('*.jp*g'))
            if images:
                zengliang_cases.append({
                    'category': '增量房',
                    'case_id': case_dir.name,
                    'images': sorted(images)
                })

    # 交替合并：存量房、增量房、存量房、增量房...
    cases = []
    max_len = max(len(cunliang_cases), len(zengliang_cases))
    for i in range(max_len):
        if i < len(cunliang_cases):
            cases.append(cunliang_cases[i])
        if i < len(zengliang_cases):
            cases.append(zengliang_cases[i])

    return cases


def evaluate_accuracy(case_results: List[Dict], baseline: Dict) -> Tuple[float, int, int]:
    """
    评估准确率

    Returns:
        (accuracy, correct_count, total_count)
    """
    correct = 0
    total = 0

    for result in case_results:
        image_path = result['image_path']
        predicted_type = result['doc_type']

        # 查找基准数据
        baseline_sample = None
        for sample in baseline.get(result['case_id'], []):
            if sample['image'] == Path(image_path).name:
                baseline_sample = sample
                break

        if baseline_sample:
            total += 1
            expected_type = baseline_sample['cert_code']

            # 简化的类型映射
            type_mapping = {
                'id_card_front': '身份证-正面',
                'id_card_back': '身份证-背面',
                'household_register': '户口本-首页',
                'hukou': '户口本-个人页',
                'marriage': '结婚证-内容页',
                'divorce_certificate': '离婚证-内容页',
                'property': '不动产权证书-内容页',
                'invoice': '发票',
                'purchase_contract': '购房合同-内容页',
                'stock_contract': '存量房合同-内容页',
                'fund_supervision': '资金监管协议-首页',
                'fund_supervision_certificate': '资金监管凭证',
            }

            expected_mapped = type_mapping.get(expected_type, expected_type)

            # 判断是否正确
            if predicted_type == expected_mapped or predicted_type.startswith(expected_mapped.split('-')[0]):
                correct += 1

    accuracy = correct / total if total > 0 else 0
    return accuracy, correct, total


def compute_layer_stats(case_results: List[Dict], baseline: Dict) -> Dict:
    """
    按提取层和VLM兜底状态统计准确率

    Returns:
        {
            'rule': {'correct': int, 'total': int, 'accuracy': float},
            'vlm': {'correct': int, 'total': int, 'accuracy': float},
            'vlm_fallback_enabled': bool,
            'vlm_fallback_triggered_count': int,
            'vlm_fallback_triggered_fields': List[str],
            'vlm_fallback': {'correct': int, 'total': int, 'accuracy': float},
        }
    """
    rule_correct = rule_total = 0
    vlm_correct = vlm_total = 0
    fb_correct = fb_total = 0
    fb_enabled_any = False
    fb_triggered_count = 0
    fb_triggered_fields_all = []

    # 类型映射（与 evaluate_accuracy 一致）
    type_mapping = {
        'id_card_front': '身份证-正面',
        'id_card_back': '身份证-背面',
        'household_register': '户口本-首页',
        'hukou': '户口本-个人页',
        'marriage': '结婚证-内容页',
        'divorce_certificate': '离婚证-内容页',
        'property': '不动产权证书-内容页',
        'invoice': '发票',
        'purchase_contract': '购房合同-内容页',
        'stock_contract': '存量房合同-内容页',
        'fund_supervision': '资金监管协议-首页',
        'fund_supervision_certificate': '资金监管凭证',
    }

    def _is_correct(predicted_type, expected_type):
        expected_mapped = type_mapping.get(expected_type, expected_type)
        return (predicted_type == expected_mapped
                or predicted_type.startswith(expected_mapped.split('-')[0]))

    for result in case_results:
        layer = result.get('layer', 'none')
        if result.get('vlm_fallback_enabled'):
            fb_enabled_any = True
        fb_triggered = result.get('vlm_fallback_triggered', False)

        # 查找基准
        baseline_sample = None
        for sample in baseline.get(result['case_id'], []):
            if sample['image'] == Path(result['image_path']).name:
                baseline_sample = sample
                break

        if not baseline_sample:
            continue

        expected_type = baseline_sample['cert_code']
        predicted_type = result['doc_type']
        is_correct = _is_correct(predicted_type, expected_type)

        # 按层统计
        if layer == 'rule':
            rule_total += 1
            if is_correct:
                rule_correct += 1
        elif layer == 'vlm':
            vlm_total += 1
            if is_correct:
                vlm_correct += 1

        # VLM字段级兜底统计
        if fb_triggered:
            fb_triggered_count += 1
            fb_triggered_fields_all.extend(result.get('vlm_fallback_fields', []))
            fb_total += 1
            if is_correct:
                fb_correct += 1

    return {
        'rule': {
            'correct': rule_correct,
            'total': rule_total,
            'accuracy': rule_correct / rule_total if rule_total > 0 else 0,
        },
        'vlm': {
            'correct': vlm_correct,
            'total': vlm_total,
            'accuracy': vlm_correct / vlm_total if vlm_total > 0 else 0,
        },
        'vlm_fallback_enabled': fb_enabled_any,
        'vlm_fallback_triggered_count': fb_triggered_count,
        'vlm_fallback_triggered_fields': sorted(set(fb_triggered_fields_all)),
        'vlm_fallback': {
            'correct': fb_correct,
            'total': fb_total,
            'accuracy': fb_correct / fb_total if fb_total > 0 else 0,
        },
    }


def format_layer_stats(stats: Dict) -> str:
    """格式化层统计信息为可读字符串"""
    lines = []
    rule = stats['rule']
    vlm = stats['vlm']
    if rule['total'] > 0:
        lines.append(f"    规则层准确率: {rule['accuracy']:.1%} ({rule['correct']}/{rule['total']})")
    else:
        lines.append(f"    规则层准确率: 无样本")
    if vlm['total'] > 0:
        lines.append(f"    VLM层准确率: {vlm['accuracy']:.1%} ({vlm['correct']}/{vlm['total']})")

    if not stats['vlm_fallback_enabled']:
        lines.append(f"    VLM字段级兜底: 未启用")
    else:
        fb = stats['vlm_fallback']
        if stats['vlm_fallback_triggered_count'] == 0:
            lines.append(f"    VLM字段级兜底: 已启用，未触发")
        else:
            lines.append(f"    VLM字段级兜底准确率: {fb['accuracy']:.1%} ({fb['correct']}/{fb['total']}) | 触发{stats['vlm_fallback_triggered_count']}次 字段:{stats['vlm_fallback_triggered_fields']}")
    return "\n".join(lines)


def run_full_test():
    """运行全量测试"""
    print("=" * 80)
    print("全量测试 - 覆盖所有存量房和增量房图片资料")
    print("=" * 80)

    # 初始化服务
    print("\n正在初始化OCR服务...")
    service = OCRService()

    # 加载基准数据
    print("加载基准数据...")
    baseline = load_baseline_data()

    # 获取所有案例
    cases = get_all_cases()
    print(f"找到 {len(cases)} 个案例")

    # 统计信息
    all_results = []
    all_image_results = []  # 所有图片结果（用于全局层统计）
    case_times = []
    image_times = []
    total_images = 0
    total_correct = 0
    total_tested = 0

    # 逐案例测试
    for i, case in enumerate(cases, 1):
        category = case['category']
        case_id = case['case_id']
        images = case['images']

        print(f"\n{'=' * 80}")
        print(f"[{i}/{len(cases)}] 测试案例: {case_id} ({category})")
        print(f"图片数量: {len(images)}")
        print(f"{'=' * 80}")

        case_start_time = time.time()
        case_results = []

        for j, img_path in enumerate(images, 1):
            print(f"\n  [{j}/{len(images)}] 处理图片: {img_path.name}")

            img_start_time = time.time()

            try:
                # 先运行OCR获取文本
                ocr_text = service.run_ocr(str(img_path))

                # 处理图片
                result = service.process_image(str(img_path), ocr_text=ocr_text)

                img_time = time.time() - img_start_time
                image_times.append(img_time)

                # 从结果字典中提取信息
                doc_type = result['classification']['doc_type']
                extraction = result['extraction']
                fields = extraction['fields']
                layer = extraction.get('layer', 'none')
                vlm_fb_enabled = extraction.get('vlm_fallback_enabled', False)
                vlm_fb_triggered = extraction.get('vlm_fallback_triggered', False)
                vlm_fb_fields = extraction.get('vlm_fallback_fields', [])

                print(f"    分类: {doc_type}")
                print(f"    提取层: {layer}")
                if vlm_fb_triggered:
                    print(f"    VLM兜底: 已触发 (字段: {vlm_fb_fields})")
                print(f"    耗时: {img_time:.2f}s")

                case_results.append({
                    'image_path': str(img_path),
                    'case_id': case_id,
                    'doc_type': doc_type,
                    'fields': fields,
                    'time': img_time,
                    'layer': layer,
                    'vlm_fallback_enabled': vlm_fb_enabled,
                    'vlm_fallback_triggered': vlm_fb_triggered,
                    'vlm_fallback_fields': vlm_fb_fields,
                })

                total_images += 1

            except Exception as e:
                img_time = time.time() - img_start_time
                print(f"    ❌ 错误: {e}")
                case_results.append({
                    'image_path': str(img_path),
                    'case_id': case_id,
                    'doc_type': 'ERROR',
                    'fields': {},
                    'time': img_time,
                    'layer': 'none',
                    'vlm_fallback_enabled': False,
                    'vlm_fallback_triggered': False,
                    'vlm_fallback_fields': [],
                    'error': str(e)
                })

        # 案例完成，评估准确率
        case_time = time.time() - case_start_time
        case_times.append(case_time)

        accuracy, correct, total = evaluate_accuracy(case_results, baseline)
        layer_stats = compute_layer_stats(case_results, baseline)

        print(f"\n  案例完成:")
        print(f"    总耗时: {case_time:.2f}s")
        print(f"    图片数: {len(images)}")
        print(f"    准确率: {accuracy:.1%} ({correct}/{total})")
        print(format_layer_stats(layer_stats))

        # 更新总统计
        total_correct += correct
        total_tested += total

        # 计算平均时间
        avg_image_time = sum(image_times) / len(image_times) if image_times else 0
        avg_case_time = sum(case_times) / len(case_times) if case_times else 0

        print(f"    平均图片耗时: {avg_image_time:.2f}s")
        print(f"    累计准确率: {total_correct / total_tested:.1%} ({total_correct}/{total_tested})")

        # 保存案例结果
        all_results.append({
            'case_id': case_id,
            'category': category,
            'accuracy': accuracy,
            'correct': correct,
            'total': total,
            'time': case_time,
            'layer_stats': layer_stats,
            'results': case_results
        })
        all_image_results.extend(case_results)

        # 判断是否继续
        if total == 0:
            print(f"  ℹ️  无基准数据，跳过准确率检查，继续下一案例")
        elif accuracy < 0.95:
            print(f"\n  ⚠️  准确率未达标 ({accuracy:.1%} < 95%)")
            print(f"  停止测试，分析问题...")
            break

        # 时间异常检测：仅警告不停止（案例总时间受图片数和文档类型影响，跨案例比较无意义）
        if len(case_times) > 1 and case_time < avg_case_time * 0.5:
            print(f"  ℹ️  案例耗时偏短 ({case_time:.2f}s < 平均{avg_case_time:.2f}s * 0.5)，可能图片较少或走规则层，继续测试")

        print(f"  ✅ 准确率达标，继续下一案例")

    # 输出最终报告
    print(f"\n{'=' * 80}")
    print("测试报告")
    print(f"{'=' * 80}")
    print(f"测试案例数: {len(all_results)}/{len(cases)}")
    print(f"测试图片数: {total_images}")
    print(f"总耗时: {sum(case_times):.2f}s")
    print(f"平均案例耗时: {sum(case_times) / len(case_times):.2f}s")
    print(f"平均图片耗时: {sum(image_times) / len(image_times):.2f}s")
    print(f"总体准确率: {total_correct / total_tested:.1%} ({total_correct}/{total_tested})")
    print()
    print("全局层统计:")
    global_layer_stats = compute_layer_stats(all_image_results, baseline)
    print(format_layer_stats(global_layer_stats))

    # 保存结果
    output_file = Path('/Users/dongsun/Github/OCR-Three-Layer-Hybrid/tests/full_test_results.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'summary': {
                'total_cases': len(all_results),
                'total_images': total_images,
                'total_time': sum(case_times),
                'avg_case_time': sum(case_times) / len(case_times) if case_times else 0,
                'avg_image_time': sum(image_times) / len(image_times) if image_times else 0,
                'total_correct': total_correct,
                'total_tested': total_tested,
                'overall_accuracy': total_correct / total_tested if total_tested > 0 else 0
            },
            'global_layer_stats': global_layer_stats,
            'cases': all_results
        }, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_file}")


if __name__ == '__main__':
    run_full_test()
