#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLM分类能力测试脚本

直接测试VLM模型的文档分类能力，不依赖主流程
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
    # 从batch_test_50_samples.json中读取OCR文本
    with open('tests/batch_test_50_samples.json', 'r', encoding='utf-8') as f:
        samples = json.load(f)

    for sample in samples:
        if sample['image_path'].endswith(Path(image_path).name):
            return sample.get('ocr_texts', [])

    return []


def classify_with_vlm(
    model_name: str,
    base_url: str,
    image_path: str,
    ocr_texts: List[str]
) -> tuple[str, float]:
    """
    使用VLM进行分类

    Returns:
        (分类结果, 耗时秒数)
    """
    # 构造提示词
    ocr_text = "\n".join(ocr_texts[:20])  # 限制OCR文本长度

    prompt = f"""请根据以下信息判断这张图片属于哪种文档类型。

文档类型包括：
- 身份证
- 户口本
- 结婚证
- 离婚证
- 不动产权证书
- 购房合同
- 存量房合同
- 发票
- 公证书
- 委托书
- 离婚协议书
- 资金监管协议

OCR识别文本：
{ocr_text}

请只回答文档类型，不要解释。"""

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
                "max_tokens": 100
            },
            timeout=300
        )

        elapsed = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            classification = result['choices'][0]['message']['content'].strip()
            return classification, elapsed
        else:
            return f"ERROR: {response.status_code}", elapsed

    except Exception as e:
        elapsed = time.time() - start_time
        return f"ERROR: {str(e)}", elapsed


def test_classification(
    model_name: str,
    base_url: str,
    samples: List[Dict]
) -> Dict:
    """测试分类能力"""
    results = []
    total_time = 0.0
    correct_count = 0

    print(f"\n{'='*80}")
    print(f"测试VLM分类能力: {model_name}")
    print(f"{'='*80}\n")

    for i, sample in enumerate(samples, 1):
        image_path = sample['image_path']
        expected_type = sample['cert_code']
        case_id = sample['case_id']

        # 加载OCR文本
        ocr_texts = load_ocr_texts(image_path)

        print(f"[{i}/{len(samples)}] {Path(image_path).name} (case={case_id})")
        print(f"  期望类型: {expected_type}")

        # 调用VLM分类
        predicted_type, elapsed = classify_with_vlm(
            model_name, base_url, image_path, ocr_texts
        )

        total_time += elapsed
        is_correct = (predicted_type == expected_type)

        if is_correct:
            correct_count += 1

        print(f"  预测类型: {predicted_type}")
        print(f"  耗时: {elapsed:.2f}s")
        print(f"  结果: {'✓ 正确' if is_correct else '✗ 错误'}")
        print()

        results.append({
            'index': i,
            'image': Path(image_path).name,
            'case_id': case_id,
            'expected': expected_type,
            'predicted': predicted_type,
            'correct': is_correct,
            'time': elapsed
        })

    # 计算统计
    accuracy = correct_count / len(samples) if samples else 0
    avg_time = total_time / len(samples) if samples else 0

    print(f"{'='*80}")
    print(f"测试完成")
    print(f"{'='*80}")
    print(f"样本数: {len(samples)}")
    print(f"正确数: {correct_count}")
    print(f"准确率: {accuracy:.1%}")
    print(f"总耗时: {total_time:.2f}s")
    print(f"平均耗时: {avg_time:.2f}s/样本")

    return {
        'model_name': model_name,
        'total_samples': len(samples),
        'correct_count': correct_count,
        'accuracy': accuracy,
        'total_time': total_time,
        'avg_time': avg_time,
        'details': results
    }


def main():
    parser = argparse.ArgumentParser(description='VLM分类能力测试')
    parser.add_argument('--model', default='Qwen2.5-VL-3B', help='模型名称')
    parser.add_argument('--port', type=int, default=8083, help='VLM服务端口')
    parser.add_argument('--samples', default='tests/vlm_classification_test_samples.json',
                       help='测试样本文件')
    parser.add_argument('--limit', type=int, default=20, help='样本数量限制')

    args = parser.parse_args()

    # 检查样本文件是否存在
    if not Path(args.samples).exists():
        print(f"错误: 样本文件不存在: {args.samples}")
        print("请先创建测试样本文件，格式：")
        print(json.dumps([
            {
                "image_path": "path/to/image.jpg",
                "case_id": "test001",
                "cert_code": "身份证-正面",
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
    result = test_classification(args.model, base_url, samples)

    # 保存结果
    output_path = f'tests/vlm_classification_results_{args.model.replace("-", "")}.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n详细结果已保存到: {output_path}")


if __name__ == '__main__':
    main()
