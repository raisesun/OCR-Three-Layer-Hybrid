#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLM字段提取能力测试脚本

直接测试VLM模型的字段提取能力，不依赖主流程
"""

import json
import time
import argparse
import base64
from pathlib import Path
from typing import List, Dict
import requests


def load_samples(samples_file: str, limit: int = None) -> List[Dict]:
    """加载测试样本"""
    with open(samples_file, 'r', encoding='utf-8') as f:
        samples = json.load(f)

    if limit:
        samples = samples[:limit]

    return samples


def load_ocr_texts(image_path: str) -> List[str]:
    """加载OCR文本（从基准数据中）"""
    with open('tests/batch_test_50_samples.json', 'r', encoding='utf-8') as f:
        samples = json.load(f)

    for sample in samples:
        if sample['image_path'].endswith(Path(image_path).name):
            return sample.get('ocr_texts', [])

    return []


def extract_fields_with_vlm(
    model_name: str,
    base_url: str,
    image_path: str,
    ocr_texts: List[str],
    doc_type: str,
    key_list: List[str]
) -> tuple[Dict[str, str], float]:
    """
    使用VLM提取字段

    Returns:
        (提取的字段字典, 耗时秒数)
    """
    # 构造提示词
    ocr_text = "\n".join(ocr_texts[:30])  # 限制OCR文本长度

    keys_str = "\n".join([f"- {key}" for key in key_list])

    prompt = f"""请从以下文档中提取指定字段。

文档类型: {doc_type}

需要提取的字段:
{keys_str}

OCR识别文本:
{ocr_text}

请以JSON格式返回提取结果，格式如下:
{{
  "字段1": "值1",
  "字段2": "值2",
  ...
}}

如果某个字段在文档中不存在或无法识别，请将其值设为空字符串""。
只返回JSON，不要其他解释。"""

    # 读取图片并编码为base64
    with open(image_path, 'rb') as f:
        image_data = base64.b64encode(f.read()).decode('utf-8')

    # 调用VLM API
    start_time = time.time()

    try:
        response = requests.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
                        ]
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 1000
            },
            timeout=300
        )

        elapsed = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content'].strip()

            # 解析JSON响应
            try:
                # 尝试提取JSON部分
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                extracted_fields = json.loads(content)
                return extracted_fields, elapsed
            except json.JSONDecodeError:
                return {"ERROR": f"JSON解析失败: {content[:100]}"}, elapsed
        else:
            return {"ERROR": f"HTTP {response.status_code}"}, elapsed

    except Exception as e:
        elapsed = time.time() - start_time
        return {"ERROR": str(e)}, elapsed


def compute_accuracy(extracted_fields: Dict, ref_fields: Dict) -> Dict:
    """计算准确率（基于实际提取）"""
    # 过滤掉空值和错误
    non_empty_extracted = {
        k: v for k, v in extracted_fields.items()
        if v and not k.startswith("ERROR")
    }

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
            # 清理空格后比较
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


def test_extraction(
    model_name: str,
    base_url: str,
    samples: List[Dict]
) -> Dict:
    """测试字段提取能力"""
    results = []
    total_time = 0.0
    total_fields = 0
    total_matched = 0

    print(f"\n{'='*80}")
    print(f"测试VLM字段提取能力: {model_name}")
    print(f"{'='*80}\n")

    for i, sample in enumerate(samples, 1):
        image_path = sample['image_path']
        doc_type = sample.get('doc_type', '未知')
        key_list = sample.get('key_list', [])
        ref_fields = sample.get('ref_fields', {})
        case_id = sample['case_id']

        # 加载OCR文本
        ocr_texts = load_ocr_texts(image_path)

        print(f"[{i}/{len(samples)}] {Path(image_path).name} (case={case_id})")
        print(f"  文档类型: {doc_type}")
        print(f"  提取字段: {', '.join(key_list)}")

        # 调用VLM提取
        extracted_fields, elapsed = extract_fields_with_vlm(
            model_name, base_url, image_path, ocr_texts, doc_type, key_list
        )

        total_time += elapsed

        # 计算准确率
        accuracy_result = compute_accuracy(extracted_fields, ref_fields)

        if accuracy_result['total_extracted'] > 0:
            total_fields += accuracy_result['total_extracted']
            total_matched += accuracy_result['matched']

        # 打印结果
        acc_str = f"{accuracy_result['accuracy']:.0%}" if accuracy_result['accuracy'] else "N/A"
        print(f"  提取结果: {accuracy_result['total_extracted']}个字段")
        print(f"  匹配结果: {accuracy_result['matched']}/{accuracy_result['total_extracted']} = {acc_str}")
        print(f"  耗时: {elapsed:.2f}s")

        if accuracy_result['matched_fields']:
            print(f"  匹配字段: {', '.join(accuracy_result['matched_fields'])}")
        if accuracy_result['missing_in_ref']:
            print(f"  基线缺失: {', '.join(accuracy_result['missing_in_ref'])}")

        print()

        results.append({
            'index': i,
            'image': Path(image_path).name,
            'case_id': case_id,
            'doc_type': doc_type,
            'extracted_fields': {k: v for k, v in extracted_fields.items() if v},
            'accuracy': accuracy_result['accuracy'],
            'matched': accuracy_result['matched'],
            'total_extracted': accuracy_result['total_extracted'],
            'time': elapsed
        })

    # 计算统计
    overall_accuracy = total_matched / total_fields if total_fields > 0 else 0
    avg_time = total_time / len(samples) if samples else 0

    print(f"{'='*80}")
    print(f"测试完成")
    print(f"{'='*80}")
    print(f"样本数: {len(samples)}")
    print(f"总提取字段: {total_fields}")
    print(f"总匹配字段: {total_matched}")
    print(f"平均准确率: {overall_accuracy:.1%}")
    print(f"总耗时: {total_time:.2f}s")
    print(f"平均耗时: {avg_time:.2f}s/样本")

    return {
        'model_name': model_name,
        'total_samples': len(samples),
        'total_fields': total_fields,
        'total_matched': total_matched,
        'accuracy': overall_accuracy,
        'total_time': total_time,
        'avg_time': avg_time,
        'details': results
    }


def main():
    parser = argparse.ArgumentParser(description='VLM字段提取能力测试')
    parser.add_argument('--model', default='Qwen2.5-VL-3B', help='模型名称')
    parser.add_argument('--port', type=int, default=8083, help='VLM服务端口')
    parser.add_argument('--samples', default='tests/vlm_extraction_test_samples.json',
                       help='测试样本文件')
    parser.add_argument('--limit', type=int, default=10, help='样本数量限制')

    args = parser.parse_args()

    # 检查样本文件是否存在
    if not Path(args.samples).exists():
        print(f"错误: 样本文件不存在: {args.samples}")
        print("请先创建测试样本文件，格式：")
        print(json.dumps([
            {
                "image_path": "path/to/image.jpg",
                "case_id": "test001",
                "doc_type": "身份证-正面",
                "key_list": ["姓名", "性别", "公民身份号码"],
                "ref_fields": {
                    "姓名": "张三",
                    "性别": "男",
                    "公民身份号码": "110101199001011234"
                },
                "ocr_texts": ["OCR文本1", "OCR文本2"]
            }
        ], indent=2, ensure_ascii=False))
        return

    # 加载样本
    samples = load_samples(args.samples, args.limit)
    print(f"加载了 {len(samples)} 个测试样本")

    # 检查VLM服务
    base_url = f"http://localhost:{args.port}"
    try:
        resp = requests.get(f"{base_url}/v1/models", timeout=5)
        if resp.status_code != 200:
            print(f"错误: VLM服务异常 (端口 {args.port})")
            return
        print(f"✓ VLM服务运行中: {args.model} (端口 {args.port})")
    except Exception as e:
        print(f"错误: VLM服务未启动 (端口 {args.port}): {e}")
        return

    # 运行测试
    result = test_extraction(args.model, base_url, samples)

    # 保存结果
    output_path = f'tests/vlm_extraction_results_{args.model.replace("-", "")}.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n详细结果已保存到: {output_path}")


if __name__ == '__main__':
    main()
