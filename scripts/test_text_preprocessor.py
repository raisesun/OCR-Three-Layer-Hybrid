#!/usr/bin/env python3
"""
测试OCR文本预处理模块
"""

import sys
sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.text_preprocessor import OCRTextPreprocessor, preprocess_text


def test_cleaning():
    """测试文本清理"""
    print("="*80)
    print("测试1: 文本清理")
    print("="*80)

    preprocessor = OCRTextPreprocessor()

    test_cases = [
        # 多余空格
        ("2026年 1月 14日", "2026年1月14日"),
        ("¥ 40000.00", "¥40000.00"),
        ("房屋 坐落：龙湖 嘉园", "房屋 坐落：龙湖 嘉园"),

        # 全角空格
        ("房屋坐落　龙湖嘉园", "房屋坐落 龙湖嘉园"),

        # 多个空格
        ("房屋  坐落   龙湖嘉园", "房屋 坐落 龙湖嘉园"),

        # 制表符
        ("房屋\t坐落\n龙湖嘉园", "房屋 坐落\n龙湖嘉园"),
    ]

    for i, (input_text, expected) in enumerate(test_cases, 1):
        result = preprocessor.preprocess(input_text)
        status = "✓" if result == expected else "✗"
        print(f"\n测试用例 {i}: {status}")
        print(f"  输入: {repr(input_text)}")
        print(f"  期望: {repr(expected)}")
        print(f"  实际: {repr(result)}")


def test_date_standardization():
    """测试日期标准化"""
    print("\n" + "="*80)
    print("测试2: 日期标准化")
    print("="*80)

    preprocessor = OCRTextPreprocessor()

    test_cases = [
        # 年月日格式
        ("2026年 1月 14日", "2026年1月14日"),
        ("2026 年 1 月 14 日", "2026年1月14日"),

        # YYYY-MM-DD格式
        ("2026- 01- 14", "2026-01-14"),
        ("2026 - 01 - 14", "2026-01-14"),

        # YYYY/MM/DD格式
        ("2026/ 01/ 14", "2026/01/14"),
    ]

    for i, (input_text, expected) in enumerate(test_cases, 1):
        result = preprocessor.preprocess(input_text)
        status = "✓" if result == expected else "✗"
        print(f"\n测试用例 {i}: {status}")
        print(f"  输入: {repr(input_text)}")
        print(f"  期望: {repr(expected)}")
        print(f"  实际: {repr(result)}")


def test_amount_standardization():
    """测试金额标准化"""
    print("\n" + "="*80)
    print("测试3: 金额标准化")
    print("="*80)

    preprocessor = OCRTextPreprocessor()

    test_cases = [
        # 货币符号后的空格
        ("¥ 40000.00", "¥40000.00"),
        ("￥ 40000.00", "¥40000.00"),
        ("¥40000.00", "¥40000.00"),
    ]

    for i, (input_text, expected) in enumerate(test_cases, 1):
        result = preprocessor.preprocess(input_text)
        status = "✓" if result == expected else "✗"
        print(f"\n测试用例 {i}: {status}")
        print(f"  输入: {repr(input_text)}")
        print(f"  期望: {repr(expected)}")
        print(f"  实际: {repr(result)}")


def test_real_certificate():
    """测试真实凭证文本"""
    print("\n" + "="*80)
    print("测试4: 真实凭证文本预处理")
    print("="*80)

    # 模拟一个有OCR问题的凭证文本
    original_text = """蚌埠市存量房交易资金监管凭证
2026- 01- 19
协议编号
2026011900010627
祁杰
卖房人
张新
买房人
证件名称
居民身份证
证件名称
居民身份证
证件号码
340311198508051213
证件号码
34032119830616153X
房屋坐落
龙湖嘉园G29号楼1单元16层3号
肆万元整
￥ 40000.00
监管总额
建筑面积
92.23 m²
收款单位签章：
第1页"""

    print("\n原始文本:")
    print(original_text)

    preprocessed = preprocess_text(original_text)

    print("\n" + "="*80)
    print("预处理后文本:")
    print(preprocessed)

    # 验证关键改进
    print("\n" + "="*80)
    print("关键改进:")
    print("="*80)

    checks = [
        ("日期空格移除", "2026- 01- 19" not in preprocessed and "2026-01-19" in preprocessed),
        ("金额空格移除", "￥ 40000.00" not in preprocessed and "¥40000.00" in preprocessed),
    ]

    for name, passed in checks:
        status = "✓" if passed else "✗"
        print(f"  {status} {name}")


def main():
    """主函数"""
    print("="*80)
    print("OCR文本预处理模块测试")
    print("="*80)

    test_cleaning()
    test_date_standardization()
    test_amount_standardization()
    test_real_certificate()

    print("\n" + "="*80)
    print("测试完成！")
    print("="*80)


if __name__ == '__main__':
    main()
