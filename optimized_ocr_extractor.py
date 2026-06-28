#!/usr/bin/env python3
"""
优化版OCR+LLM提取方案
1. 过滤低置信度OCR结果
2. 使用更简洁的Prompt
3. 增加超时时间
"""

import json
import time
import requests
from pathlib import Path
from paddleocr import PaddleOCR

class OptimizedOCRExtractor:
    """优化版OCR+LLM提取器"""

    def __init__(self):
        """初始化OCR引擎"""
        print("初始化PaddleOCR...")
        self.ocr = PaddleOCR(
            use_textline_orientation=False,
            lang='ch'
        )
        print("✅ PaddleOCR初始化完成")

    def extract_text(self, image_path, min_score=0.8):
        """使用OCR提取文本（过滤低置信度结果）"""
        result = self.ocr.predict(image_path)
        if not result or len(result) == 0:
            return ""

        first_result = result[0]

        if 'rec_texts' in first_result and 'rec_scores' in first_result:
            texts = first_result['rec_texts']
            scores = first_result['rec_scores']

            # 过滤低置信度的文本
            filtered_texts = [
                text for text, score in zip(texts, scores)
                if score >= min_score
            ]

            return '\n'.join(filtered_texts)

        return ""

    def extract_fields_with_llm(self, text, key_list, doc_type="文档"):
        """使用LLM提取关键字段（使用简洁Prompt）"""

        # 构建简洁的Prompt
        keys_str = '、'.join(key_list)
        prompt = f"从以下{doc_type}提取{keys_str}，返回JSON：\n{text}"

        # 调用Ollama（增加超时时间）
        try:
            response = requests.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": "qwen35-4b-test",
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False
                },
                timeout=180  # 增加到180秒
            )

            result = response.json()
            llm_response = result['message']['content']

            # 解析JSON
            clean_response = llm_response.strip()
            if clean_response.startswith('```'):
                lines = clean_response.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines[-1].startswith('```'):
                    lines = lines[:-1]
                clean_response = '\n'.join(lines)

            return json.loads(clean_response)

        except Exception as e:
            print(f"LLM调用失败: {e}")
            return {}

    def extract(self, image_path, key_list, doc_type="文档"):
        """完整的提取流程"""
        start_time = time.time()

        # 步骤1：OCR提取文本（过滤低置信度）
        text = self.extract_text(image_path, min_score=0.8)
        if not text:
            return {"error": "OCR提取失败"}

        # 步骤2：LLM提取字段
        fields = self.extract_fields_with_llm(text, key_list, doc_type)

        total_time = time.time() - start_time

        return {
            "fields": fields,
            "text_length": len(text),
            "time": total_time,
            "extracted_text": text[:200]  # 保存前200字符用于调试
        }


def test_extraction():
    """测试提取效果"""

    # 初始化提取器
    extractor = OptimizedOCRExtractor()

    # 测试样本
    test_samples = [
        {
            "path": "/Users/dongsun/Github/sample-OCR/增量房图片资料/202403080014/5a99c19b869a4de7a42f2d798d5afde7.jpeg",
            "type": "购房合同",
            "keys": ["买受人", "出卖人", "合同编号"]
        },
        {
            "path": "/Users/dongsun/Github/sample-OCR/增量房图片资料/202403080014/2bebb1f8eca747d68fdfee98b4456be2.jpeg",
            "type": "购房合同",
            "keys": ["买受人", "出卖人", "合同编号"]
        },
        {
            "path": "/Users/dongsun/Github/sample-OCR/增量房图片资料/202411060009/fccde46a90d642e79466e101cab848e5.jpeg",
            "type": "存量房合同",
            "keys": ["买受人", "出卖人", "合同编号"]
        }
    ]

    print("\n" + "="*60)
    print("开始测试优化版提取方案")
    print("="*60)

    results = []
    for i, sample in enumerate(test_samples, 1):
        print(f"\n测试 {i}/{len(test_samples)}: {sample['type']}")
        print(f"文件: {Path(sample['path']).name}")

        result = extractor.extract(
            sample['path'],
            sample['keys'],
            sample['type']
        )

        print(f"✅ 提取完成 (耗时: {result['time']:.2f}秒)")
        print(f"提取文本长度: {result['text_length']} 字符")
        print(f"提取文本预览: {result.get('extracted_text', '')[:100]}...")
        print(f"提取字段: {json.dumps(result['fields'], ensure_ascii=False, indent=2)}")

        results.append({
            "type": sample['type'],
            "file": Path(sample['path']).name,
            "result": result
        })

    # 生成报告
    print("\n" + "="*60)
    print("测试报告")
    print("="*60)

    total_time = sum(r['result']['time'] for r in results)
    avg_time = total_time / len(results) if results else 0

    print(f"\n测试样本: {len(results)}")
    print(f"总耗时: {total_time:.2f}秒")
    print(f"平均耗时: {avg_time:.2f}秒")

    # 保存结果
    output_file = Path(__file__).parent / "optimized_ocr_test_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n详细结果已保存: {output_file}")

    return results


if __name__ == "__main__":
    test_extraction()
