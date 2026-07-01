#!/usr/bin/env python3
"""
Phase 1: OCR 引擎对比测试

对比三种引擎在 10 张代表性样本上的表现：
1. GLM-OCR（当前基线，27秒/张）
2. PP-StructureV3（技术方案推荐，预期 0.5-2秒/张）
3. PaddleOCR-VL（备选，预期 5-8秒/张）

测试指标：
- 速度（耗时）
- 文本长度
- 识别质量（人工评估）
- 成功率

作者: Claude
日期: 2026-07-01
"""

import sys
import json
import time
import logging
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass, asdict

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@dataclass
class TestResult:
    """测试结果"""
    engine: str
    image_path: str
    doc_type: str
    success: bool
    elapsed_time: float
    text_length: int
    text_preview: str
    error_message: str = ""


def load_test_samples(samples_file: str, count: int = 10) -> List[Dict]:
    """加载测试样本（每种文档类型 1-2 张）"""
    with open(samples_file, 'r', encoding='utf-8') as f:
        samples = json.load(f)

    # 按文档类型分组
    by_type = {}
    for sample in samples:
        cert_code = sample.get('cert_code', 'unknown')
        if cert_code not in by_type:
            by_type[cert_code] = []
        by_type[cert_code].append(sample)

    # 每种类型选择 1-2 张
    selected = []
    for cert_code, type_samples in by_type.items():
        # 优先选择有 ref_fields 的样本（更完整）
        sorted_samples = sorted(
            type_samples,
            key=lambda x: len(x.get('ref_fields', {})),
            reverse=True
        )
        selected.extend(sorted_samples[:2])

    # 限制总数
    selected = selected[:count]

    logger.info(f"选择了 {len(selected)} 张测试样本，涵盖 {len(by_type)} 种文档类型")
    return selected


def test_glm_ocr(image_path: str) -> TestResult:
    """测试 GLM-OCR 引擎"""
    import requests

    start = time.time()
    try:
        # 调用 GLM-OCR（llama-server）
        with open(image_path, 'rb') as f:
            image_data = f.read()

        import base64
        image_b64 = base64.b64encode(image_data).decode('utf-8')

        response = requests.post(
            "http://localhost:8080/v1/chat/completions",
            json={
                "model": "glm-ocr",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                            {"type": "text", "text": "请识别这张图片中的所有文字内容。"}
                        ]
                    }
                ],
                "max_tokens": 2048,
                "temperature": 0.1,
            },
            timeout=60
        )
        response.raise_for_status()

        result = response.json()
        text = result['choices'][0]['message']['content']

        elapsed = time.time() - start
        return TestResult(
            engine="GLM-OCR",
            image_path=image_path,
            doc_type="",
            success=True,
            elapsed_time=elapsed,
            text_length=len(text),
            text_preview=text[:200],
        )

    except Exception as e:
        elapsed = time.time() - start
        return TestResult(
            engine="GLM-OCR",
            image_path=image_path,
            doc_type="",
            success=False,
            elapsed_time=elapsed,
            text_length=0,
            text_preview="",
            error_message=str(e),
        )


def test_ppstructure_v3(image_path: str) -> TestResult:
    """测试 PP-StructureV3 引擎"""
    from ocr_three_layer_hybrid.paddleocr_wrapper import PPStructureV3Engine

    start = time.time()
    try:
        engine = PPStructureV3Engine(device="cpu")
        results = engine.predict(image_path)

        if results:
            result = results[0]
            text = result.full_text
            elapsed = time.time() - start
            return TestResult(
                engine="PP-StructureV3",
                image_path=image_path,
                doc_type="",
                success=True,
                elapsed_time=elapsed,
                text_length=len(text),
                text_preview=text[:200],
            )
        else:
            elapsed = time.time() - start
            return TestResult(
                engine="PP-StructureV3",
                image_path=image_path,
                doc_type="",
                success=False,
                elapsed_time=elapsed,
                text_length=0,
                text_preview="",
                error_message="无结果",
            )

    except Exception as e:
        elapsed = time.time() - start
        return TestResult(
            engine="PP-StructureV3",
            image_path=image_path,
            doc_type="",
            success=False,
            elapsed_time=elapsed,
            text_length=0,
            text_preview="",
            error_message=str(e),
        )


def test_paddleocr_vl(image_path: str) -> TestResult:
    """测试 PaddleOCR-VL 引擎"""
    from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRVLLEngine

    start = time.time()
    try:
        engine = PaddleOCRVLLEngine(device="cpu")
        results = engine.predict(image_path)

        if results:
            result = results[0]
            text = result.full_text
            elapsed = time.time() - start
            return TestResult(
                engine="PaddleOCR-VL",
                image_path=image_path,
                doc_type="",
                success=True,
                elapsed_time=elapsed,
                text_length=len(text),
                text_preview=text[:200],
            )
        else:
            elapsed = time.time() - start
            return TestResult(
                engine="PaddleOCR-VL",
                image_path=image_path,
                doc_type="",
                success=False,
                elapsed_time=elapsed,
                text_length=0,
                text_preview="",
                error_message="无结果",
            )

    except Exception as e:
        elapsed = time.time() - start
        return TestResult(
            engine="PaddleOCR-VL",
            image_path=image_path,
            doc_type="",
            success=False,
            elapsed_time=elapsed,
            text_length=0,
            text_preview="",
            error_message=str(e),
        )


def run_comparison_test(samples: List[Dict], engines: List[str]) -> List[TestResult]:
    """运行对比测试"""
    results = []

    for i, sample in enumerate(samples):
        image_path = sample['image_path']
        cert_code = sample['cert_code']

        if not Path(image_path).exists():
            logger.warning(f"图片不存在: {image_path}")
            continue

        logger.info(f"\n[{i+1}/{len(samples)}] 测试图片: {cert_code}")
        logger.info(f"  路径: {image_path}")

        for engine_name in engines:
            logger.info(f"  测试引擎: {engine_name}")

            if engine_name == "GLM-OCR":
                result = test_glm_ocr(image_path)
            elif engine_name == "PP-StructureV3":
                result = test_ppstructure_v3(image_path)
            elif engine_name == "PaddleOCR-VL":
                result = test_paddleocr_vl(image_path)
            else:
                continue

            result.doc_type = cert_code
            results.append(result)

            status = "✅" if result.success else "❌"
            logger.info(f"    {status} {result.engine}: {result.elapsed_time:.2f}秒, {result.text_length}字符")

    return results


def generate_report(results: List[TestResult], output_file: str):
    """生成对比报告"""
    # 按引擎分组
    by_engine = {}
    for result in results:
        if result.engine not in by_engine:
            by_engine[result.engine] = []
        by_engine[result.engine].append(result)

    # 计算统计
    stats = {}
    for engine, engine_results in by_engine.items():
        success_results = [r for r in engine_results if r.success]
        if success_results:
            avg_time = sum(r.elapsed_time for r in success_results) / len(success_results)
            avg_length = sum(r.text_length for r in success_results) / len(success_results)
            success_rate = len(success_results) / len(engine_results) * 100
        else:
            avg_time = 0
            avg_length = 0
            success_rate = 0

        stats[engine] = {
            "total": len(engine_results),
            "success": len(success_results),
            "success_rate": success_rate,
            "avg_time": avg_time,
            "avg_length": avg_length,
        }

    # 生成 Markdown 报告
    report = []
    report.append("# Phase 1: OCR 引擎对比测试报告\n")
    report.append(f"**测试时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.append(f"**测试样本数**: {len(results) // len(by_engine)}\n")
    report.append(f"**测试引擎**: {', '.join(by_engine.keys())}\n")

    report.append("\n## 1. 总体对比\n")
    report.append("| 引擎 | 测试数 | 成功数 | 成功率 | 平均耗时 | 平均文本长度 |")
    report.append("|------|--------|--------|--------|----------|--------------|")
    for engine, stat in stats.items():
        report.append(f"| {engine} | {stat['total']} | {stat['success']} | {stat['success_rate']:.1f}% | {stat['avg_time']:.2f}秒 | {stat['avg_length']:.0f}字符 |")

    report.append("\n## 2. 详细结果\n")
    for engine, engine_results in by_engine.items():
        report.append(f"\n### {engine}\n")
        report.append("| 文档类型 | 耗时 | 文本长度 | 状态 |")
        report.append("|---------|------|---------|------|")
        for result in engine_results:
            status = "✅" if result.success else "❌"
            report.append(f"| {result.doc_type} | {result.elapsed_time:.2f}秒 | {result.text_length}字符 | {status} |")

    report.append("\n## 3. 文本预览\n")
    for result in results[:5]:  # 只显示前 5 个
        if result.success:
            report.append(f"\n### {result.engine} - {result.doc_type}\n")
            report.append(f"耗时: {result.elapsed_time:.2f}秒\n")
            report.append(f"文本长度: {result.text_length}字符\n")
            report.append(f"前 200 字符:\n```\n{result.text_preview}\n```\n")

    # 写入文件
    report_text = "\n".join(report)
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_text)

    logger.info(f"\n报告已保存到: {output_file}")

    # 打印摘要
    print("\n" + "="*70)
    print("Phase 1 对比测试完成")
    print("="*70)
    for engine, stat in stats.items():
        print(f"{engine}: 成功率 {stat['success_rate']:.1f}%, 平均耗时 {stat['avg_time']:.2f}秒")


def main():
    """主函数"""
    print("\n" + "="*70)
    print("Phase 1: OCR 引擎对比测试")
    print("="*70)

    # 配置
    samples_file = Path(__file__).parent.parent / "tests" / "batch_test_50_samples.json"
    output_file = Path(__file__).parent.parent / "analysis" / "phase1_ocr_engine_comparison.md"

    # 测试的引擎（可以先测试 PP-StructureV3，GLM-OCR 可能不稳定）
    engines = ["PP-StructureV3"]  # , "PaddleOCR-VL", "GLM-OCR"]

    # 加载测试样本（先测试 3 张验证）
    if not samples_file.exists():
        logger.error(f"找不到样本文件: {samples_file}")
        return

    samples = load_test_samples(str(samples_file), count=3)

    # 运行对比测试
    results = run_comparison_test(samples, engines)

    # 生成报告
    generate_report(results, str(output_file))


if __name__ == "__main__":
    main()
