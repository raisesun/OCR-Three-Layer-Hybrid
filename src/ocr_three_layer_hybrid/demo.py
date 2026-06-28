#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方案E+演示脚本
展示三层混合架构的使用方法
"""

import json
import time
from pathlib import Path

from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
from ocr_three_layer_hybrid.llm_layer import PPChatOCRv4Layer
from ocr_three_layer_hybrid.interfaces import ProcessingLayer


def run_demo_with_mock_data():
    """使用模拟OCR文本演示方案E+"""
    print("=" * 60)
    print("方案E+三层架构演示")
    print("=" * 60)

    # 初始化管道（不带LLM层，只做规则层演示）
    pipeline = PlanEPlusPipeline()

    test_cases = [
        {
            "name": "身份证",
            "path": "/tmp/demo_id_card.jpg",
            "texts": [
                "姓名 张三",
                "性别 男 民族 汉族",
                "出生 1990年1月1日",
                "住址 北京市朝阳区某某路1号",
                "公民身份号码 110101199001011234",
            ],
        },
        {
            "name": "结婚证",
            "path": "/tmp/demo_marriage.jpg",
            "texts": [
                "结婚证",
                "持证人 张三",
                "登记日期 2020年5月20日",
                "结婚证字号 J110101-2020-000123",
            ],
        },
        {
            "name": "购房合同",
            "path": "/tmp/demo_contract.jpg",
            "texts": [
                "商品房买卖合同",
                "买受人 王五",
                "出卖人 赵六",
                "合同编号 2024001",
            ],
        },
    ]

    results = []
    for case in test_cases:
        print(f"\n{'='*60}")
        print(f"处理：{case['name']}")
        print(f"{'='*60}")

        result = pipeline.process(case["path"], case["texts"])

        print(f"文档类型：{result.doc_type.value}")
        print(f"处理层：{result.layer.value}")
        print(f"成功：{result.success}")
        print(f"耗时：{result.time_cost:.4f}秒")
        print(f"提取字段：")
        print(json.dumps(result.fields, ensure_ascii=False, indent=2))

        results.append({
            "name": case["name"],
            "doc_type": result.doc_type.value,
            "layer": result.layer.value,
            "success": result.success,
            "time_cost": result.time_cost,
            "fields": result.fields,
        })

    print("\n" + "=" * 60)
    print("演示完成")
    print("=" * 60)

    return results


def run_demo_with_real_images():
    """使用真实图片和PP-ChatOCRv4演示方案E+"""
    print("=" * 60)
    print("方案E+真实图片演示（需要Ollama服务）")
    print("=" * 60)

    # 初始化LLM层
    llm_layer = PPChatOCRv4Layer()

    # 初始化完整管道
    pipeline = PlanEPlusPipeline(llm_layer=llm_layer)

    test_samples = [
        {
            "name": "购房合同",
            "path": "/Users/dongsun/Github/sample-OCR/增量房图片资料/202403080014/5a99c19b869a4de7a42f2d798d5afde7.jpeg",
            "texts": ["商品房买卖合同", "买受人", "出卖人"],  # 用于分类
        },
        {
            "name": "户口本",
            "path": "/Users/dongsun/Github/sample-OCR/增量房图片资料/202403080014/2bebb1f8eca747d68fdfee98b4456be2.jpeg",
            "texts": ["居民户口簿", "户主"],
        },
        {
            "name": "结婚证",
            "path": "/Users/dongsun/Github/sample-OCR/增量房图片资料/202411060009/fccde46a90d642e79466e101cab848e5.jpeg",
            "texts": ["结婚证", "结婚证字号"],
        },
    ]

    results = []
    for case in test_samples:
        print(f"\n{'='*60}")
        print(f"处理：{case['name']}")
        print(f"{'='*60}")

        if not Path(case["path"]).exists():
            print(f"❌ 图片不存在：{case['path']}")
            continue

        result = pipeline.process(case["path"], case["texts"])

        print(f"文档类型：{result.doc_type.value}")
        print(f"处理层：{result.layer.value}")
        print(f"成功：{result.success}")
        print(f"耗时：{result.time_cost:.4f}秒")
        print(f"提取字段：")
        print(json.dumps(result.fields, ensure_ascii=False, indent=2))

        results.append({
            "name": case["name"],
            "result": result,
        })

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--real":
        run_demo_with_real_images()
    else:
        run_demo_with_mock_data()
