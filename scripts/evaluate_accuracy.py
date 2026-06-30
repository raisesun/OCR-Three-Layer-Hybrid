#!/usr/bin/env python3
"""
准确率评估脚本：对比集成V6原型前后的系统表现

评估内容：
1. 分类准确率（是否正确识别文档类型）
2. 提取准确率（是否正确提取字段）
3. 与基线数据对比，检查是否有退化
"""

import json
import sys
import time
import logging
from pathlib import Path
from collections import defaultdict

# 添加src路径
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from ocr_three_layer_hybrid.config import OCRConfig
from ocr_three_layer_hybrid.service import OCRService

# 配置日志
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)

# 测试数据路径
BASELINE_FILE = Path('/Users/dongsun/Github/sample-OCR/test_base_V2.0_full50.json')
SAMPLES_FILE = Path('/Users/dongsun/github/OCR-Three-Layer-Hybrid/tests/batch_test_50_samples.json')


def load_test_data():
    """加载测试数据"""
    if not BASELINE_FILE.exists():
        print(f"基线文件不存在: {BASELINE_FILE}")
        return None, None

    if not SAMPLES_FILE.exists():
        print(f"样本文件不存在: {SAMPLES_FILE}")
        return None, None

    with open(BASELINE_FILE, 'r', encoding='utf-8') as f:
        baseline = json.load(f)

    with open(SAMPLES_FILE, 'r', encoding='utf-8') as f:
        samples = json.load(f)

    return baseline, samples


def normalize_for_compare(value: str) -> str:
    """标准化字段值用于比较"""
    if not value:
        return ""
    v = str(value).strip()
    import re
    v = re.sub(r'[\s ,，.·:：\-_()（）\[\]【】{}]+', '', v)
    v = re.sub(r'(平方米|m2|m²|㎡|元|元整)$', '', v)
    return v


def value_in_text(value: str, text: str) -> bool:
    """检查字段值是否出现在文本中（子串匹配）"""
    if not value:
        return False
    nv = normalize_for_compare(value)
    nt = normalize_for_compare(text)
    if len(nv) < 2:
        return nv == nt
    return nv in nt


def evaluate_extraction(extracted_fields: dict, cloud_text: str) -> dict:
    """评估提取准确率"""
    results = {
        'exact': 0,
        'partial': 0,
        'missed': 0,
        'wrong': 0,
        'total': 0,
    }

    for field_name, extracted_val in extracted_fields.items():
        results['total'] += 1

        if not extracted_val or not extracted_val.strip():
            results['missed'] += 1
            continue

        if value_in_text(extracted_val, cloud_text):
            results['exact'] += 1
        else:
            # 检查部分匹配
            nv = normalize_for_compare(extracted_val)
            nt = normalize_for_compare(cloud_text)

            if len(nv) <= 4:
                if nv in nt:
                    results['exact'] += 1
                else:
                    results['wrong'] += 1
            else:
                # 长字段检查部分匹配
                match_len = 0
                best_match = 0
                for i in range(len(nv)):
                    if i < len(nt) and nv[i] == nt[i]:
                        match_len += 1
                        best_match = max(best_match, match_len)
                    else:
                        match_len = 0

                if best_match >= len(nv) * 0.5:
                    results['partial'] += 1
                else:
                    results['wrong'] += 1

    return results


def main():
    """主函数"""
    print("=" * 70)
    print("准确率评估：集成V6原型前后对比")
    print("=" * 70)
    print()

    # 加载测试数据
    baseline, samples = load_test_data()
    if baseline is None or samples is None:
        return

    print(f"加载测试数据: {len(samples)} 个样本")
    print()

    # 创建服务（启用所有VLM功能）
    config = OCRConfig()
    config.enable_vlm_fallback = True  # 启用VLM分类兜底
    config.enable_position_extraction = True  # 启用位置标注提取
    config.enable_vlm_field_fallback = True  # 启用VLM字段兜底

    service = OCRService(config=config)

    # 统计结果
    classification_results = defaultdict(lambda: {'correct': 0, 'total': 0})
    extraction_results = defaultdict(lambda: {
        'exact': 0, 'partial': 0, 'missed': 0, 'wrong': 0, 'total': 0
    })
    layer_results = defaultdict(lambda: {
        'exact': 0, 'partial': 0, 'missed': 0, 'wrong': 0, 'total': 0
    })

    # 运行测试
    total_samples = len(samples)
    for idx, sample in enumerate(samples, 1):
        image_path = sample.get('image_path', '')
        expected_type = sample.get('cert_code', '')

        if not image_path or not Path(image_path).exists():
            continue

        # 获取云端文本（从baseline中查找）
        case_id = sample.get('case_id', '')
        cloud_text = baseline.get(case_id, {}).get('ocr_text', '')

        try:
            # 处理图片
            result = service.process_single(image_path, "")

            # 分类结果
            actual_type = result['classification']['doc_type']
            is_correct = (actual_type == expected_type) or (
                expected_type == 'DIVORCE_CERTIFICATE' and result['classification'].get('vlm_result') == '附属页面'
            )

            classification_results[expected_type]['total'] += 1
            if is_correct:
                classification_results[expected_type]['correct'] += 1

            # 提取结果
            extracted_fields = result['extraction']['fields']
            layer = result['extraction']['layer']

            eval_result = evaluate_extraction(extracted_fields, cloud_text)

            for key in ['exact', 'partial', 'missed', 'wrong', 'total']:
                extraction_results[expected_type][key] += eval_result[key]
                layer_results[layer][key] += eval_result[key]

            if idx % 10 == 0:
                print(f"进度: {idx}/{total_samples}")

        except Exception as e:
            print(f"处理失败: {Path(image_path).name} - {e}")

    # 输出结果
    print()
    print("=" * 70)
    print("评估结果")
    print("=" * 70)
    print()

    # 分类准确率
    print("分类准确率:")
    total_correct = sum(r['correct'] for r in classification_results.values())
    total_all = sum(r['total'] for r in classification_results.values())

    for doc_type, results in sorted(classification_results.items()):
        accuracy = results['correct'] / results['total'] * 100 if results['total'] > 0 else 0
        print(f"  {doc_type:30s}: {results['correct']:3d}/{results['total']:3d} = {accuracy:5.1f}%")

    print(f"  {'总计':30s}: {total_correct:3d}/{total_all:3d} = {total_correct/total_all*100:5.1f}%")
    print()

    # 提取准确率
    print("提取准确率 (按文档类型):")
    for doc_type, results in sorted(extraction_results.items()):
        if results['total'] == 0:
            continue
        accuracy = (results['exact'] + 0.5 * results['partial']) / results['total'] * 100
        print(f"  {doc_type:30s}: {accuracy:5.1f}% (exact={results['exact']}, partial={results['partial']}, missed={results['missed']}, wrong={results['wrong']})")
    print()

    # 提取准确率 (按层级)
    print("提取准确率 (按层级):")
    for layer, results in sorted(layer_results.items()):
        if results['total'] == 0:
            continue
        accuracy = (results['exact'] + 0.5 * results['partial']) / results['total'] * 100
        print(f"  {layer:30s}: {accuracy:5.1f}% (exact={results['exact']}, partial={results['partial']}, missed={results['missed']}, wrong={results['wrong']})")

    print()
    print("=" * 70)
    print("评估完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
