#!/usr/bin/env python3
"""
不动产权证书内容页字段提取测试
测试10个字段的提取效果
"""

import sys
import re
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper


def extract_property_certificate_content(ocr_text: str) -> dict:
    """
    提取不动产权证书内容页的10个字段

    针对OCR表格布局优化：标签和值分开显示
    """
    fields = {}

    # 1. 不动产编号（对应"不动产第 {数字}号"）
    match = re.search(r'不动产权第\s*(\d+)\s*号', ocr_text)
    if match:
        fields["不动产编号"] = match.group(1)

    # 2. 权利人 - 查找2-4个汉字的姓名
    # 策略：找到"权利人"标签后，在后面的文本中找到第一个2-4汉字的词
    lines = ocr_text.split('\n')
    found_ren_label = False
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if '权利人' in line_stripped and len(line_stripped) < 10:
            found_ren_label = True
            continue

        if found_ren_label:
            # 跳过空行和其他标签
            if not line_stripped:
                continue
            # 如果是其他标签，继续
            if any(tag in line_stripped for tag in ['共有情况', '不动产单元号', '权利类型', '权利性质', '使用期限', '坐落']):
                continue
            # 查找2-4个汉字的姓名
            match = re.match(r'^([一-龥]{2,4})$', line_stripped)
            if match:
                fields["权利人"] = match.group(1)
                break
            # 如果这一行包含姓名（可能和其他文字混在一起）
            match = re.search(r'([一-龥]{2,4})', line_stripped)
            if match and len(line_stripped) < 10:
                fields["权利人"] = match.group(1)
                break

    # 备选策略：直接查找常见的姓名模式（如"周保根"）
    # 假设姓名在"权利人"标签后面，且是2-4个汉字
    if "权利人" not in fields:
        # 查找文本中所有2-4汉字的词
        all_names = re.findall(r'\n([一-龥]{2,4})\n', ocr_text)
        if all_names:
            # 选择第一个看起来像姓名的（排除常见标签）
            for name in all_names:
                if name not in ['共有情况', '不动产单元号', '权利类型', '权利性质', '使用期限', '坐落', '和念老具']:
                    fields["权利人"] = name
                    break

    # 3. 共有情况
    if '共同共有' in ocr_text:
        fields["共有情况"] = "共同共有"
    elif '单独所有' in ocr_text:
        fields["共有情况"] = "单独所有"

    # 4. 坐落 - 查找包含"号楼"、"单元"的地址
    # 优先匹配"绿地世纪城·柏仕公馆6号楼2单元8层2号"这样的完整地址
    match = re.search(r'([一-龥]+[·・]?[一-龥]+[0-9]*号楼[0-9]*单元[0-9]+层[0-9]+号)', ocr_text)
    if match:
        fields["坐落"] = match.group(1)
    else:
        # 备选：匹配包含"号楼"或"单元"的地址
        match = re.search(r'([一-龥]+(?:号楼|单元)[^\n]{0,30})', ocr_text)
        if match:
            address = match.group(1).strip()
            if '号楼' in address or '单元' in address:
                fields["坐落"] = address

    # 5. 不动产单元号 - 查找包含空格分隔的编码（如"340304 014005 GB00065 F00060095"）
    match = re.search(r'(\d{6}\s+\d{6}\s+[A-Z]+\d+\s+[A-Z]+\d+)', ocr_text)
    if match:
        fields["不动产单元号"] = match.group(1)

    # 6. 权利类型
    if '国有建设用地使用权/房屋所有权' in ocr_text:
        fields["权利类型"] = "国有建设用地使用权/房屋所有权"
    elif '国有建设用地使用权' in ocr_text:
        fields["权利类型"] = "国有建设用地使用权"

    # 7. 权利性质
    if '出让/市场化商品房' in ocr_text:
        fields["权利性质"] = "出让/市场化商品房"
    elif '出让' in ocr_text:
        fields["权利性质"] = "出让"

    # 8. 用途
    if '城镇住宅用地/住宅' in ocr_text:
        fields["用途"] = "城镇住宅用地/住宅"
    elif '住宅' in ocr_text:
        fields["用途"] = "住宅"

    # 9. 面积（房屋建筑面积）
    match = re.search(r'房屋建筑面积\s*([\d.]+)', ocr_text)
    if match:
        fields["面积"] = match.group(1)
    else:
        # 备选：匹配 "建筑面积xxx"
        match = re.search(r'建筑面积[：:\s]*([\d.]+)', ocr_text)
        if match:
            fields["面积"] = match.group(1)

    # 10. 使用期限 - 查找日期范围（如"2011年07月23日起2081年07月22日止"）
    match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日[起止].*\d{4}年\d{1,2}月\d{1,2}日[起止止]?)', ocr_text)
    if match:
        fields["使用期限"] = match.group(1)

    return fields


def test_extraction():
    """测试内容页字段提取"""

    # 测试样本：正确的内容页图片
    test_image = "/Users/dongsun/Github/sample-OCR/demo-不动产权证书/存量/BBJZ-2026-0129058/0d7b511c1e7144f4bad4f60335aa1226.jpg"

    if not Path(test_image).exists():
        print(f"❌ 图片不存在: {test_image}")
        return

    print("=" * 80)
    print("不动产权证书内容页字段提取测试")
    print("=" * 80)
    print(f"\n测试图片: {Path(test_image).name}")
    print(f"案例: BBJZ-2026-0129058")

    # 初始化OCR
    print("\n正在初始化OCR引擎...")
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")

    # OCR识别
    print("正在进行OCR识别...")
    ocr_result = ocr.run_ocr(test_image)
    text = ocr_result.full_text

    print(f"\nOCR文本长度: {len(text)} 字符")

    # 提取字段
    print("\n正在提取字段...")
    fields = extract_property_certificate_content(text)

    # 定义期望的字段
    expected_fields = [
        "不动产编号", "权利人", "共有情况", "坐落",
        "不动产单元号", "权利类型", "权利性质", "用途", "面积", "使用期限"
    ]

    # 显示提取结果
    print("\n" + "=" * 80)
    print("提取结果")
    print("=" * 80)

    total_fields = len(expected_fields)
    extracted_count = 0

    for field in expected_fields:
        value = fields.get(field, "")
        if value:
            extracted_count += 1
            print(f"✅ {field}: {value}")
        else:
            print(f"❌ {field}: [缺失]")

    # 统计
    completion_rate = extracted_count / total_fields * 100

    print(f"\n{'=' * 80}")
    print("统计")
    print(f"{'=' * 80}")
    print(f"总字段数: {total_fields}")
    print(f"已提取: {extracted_count}")
    print(f"完成率: {completion_rate:.1f}%")

    # 显示完整OCR文本（用于调试）
    print(f"\n{'=' * 80}")
    print("完整OCR文本")
    print(f"{'=' * 80}")
    print(text)

    return fields


if __name__ == "__main__":
    test_extraction()
