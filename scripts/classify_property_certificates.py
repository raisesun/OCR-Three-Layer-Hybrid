#!/usr/bin/env python3
"""
不动产权证书图片分类脚本
帮助用户对demo目录中的图片进行细分标注
"""

import sys
import re
from pathlib import Path
import json

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.interfaces import DocumentType


def classify_property_certificate(ocr_text: str) -> tuple[str, list[str]]:
    """
    判断不动产权证书的类型

    Returns:
        (doc_type, reasons): 文档类型和判断依据
    """
    reasons = []

    # 0. 首先检查是否是资金监管凭证（优先级最高）
    if "资金监管凭证" in ocr_text or "监管凭证" in ocr_text:
        reasons.append("包含'资金监管凭证'关键词")
        return "FUND_SUPERVISION_CERTIFICATE", reasons

    # 1. 检查是否是不动产权证书
    property_indicators = [
        "不动产权", "不动产第", "编号", "登记机构",
        "权利人", "共有情况", "不动产单元号", "坐落",
        "权利类型", "权利性质", "用途", "使用期限",
        "图幅", "宗地", "附图"
    ]
    has_property_indicator = any(kw in ocr_text for kw in property_indicators)

    if not has_property_indicator:
        reasons.append("不包含不动产权证书特征，可能不是不动产权证书")
        return "UNKNOWN", reasons

    # 2. 内容页特征（优先级最高，因为特征最明确）
    # 注意：必须是明确的字段标签，而不是出现在法律依据中的文字
    content_keywords = [
        "不动产第", "共有情况", "不动产单元号", "坐落",
        "权利类型", "权利性质", "用途", "使用期限"
    ]
    content_count = sum(1 for kw in content_keywords if kw in ocr_text)

    if content_count >= 3:  # 至少包含3个内容页特征
        reasons.append(f"包含内容页特征关键词（{content_count}个）")
        return "PROPERTY_CERTIFICATE_CONTENT", reasons

    # 3. 附图页特征（扩展关键词）
    attachment_keywords = [
        "附图", "所在图幅编号", "制图日期", "制图者",
        "宗地代码", "房产分户图", "宗地图", "房屋平面图",
        "图幅号", "图幅编号"
    ]
    # 检查明确的附图页关键词
    if any(kw in ocr_text for kw in attachment_keywords):
        reasons.append("包含附图页特征关键词")
        return "PROPERTY_CERTIFICATE_ATTACHMENT", reasons

    # 检查图幅编号模式（如GB0019, J974等）
    pattern_matches = re.findall(r'\b(?:GB|J|G)\d{2,}\b', ocr_text, re.IGNORECASE)
    if len(pattern_matches) >= 3:  # 至少3个图幅编号
        reasons.append(f"包含图幅编号模式（{len(pattern_matches)}个）")
        return "PROPERTY_CERTIFICATE_ATTACHMENT", reasons

    # 4. 首页特征
    # 首页的典型特征：登记机构（章）、编号、日期
    first_page_keywords = [
        "登记机构", "编号", "不动产权证号", "证书号"
    ]
    # 如果包含首页特征
    if any(kw in ocr_text for kw in first_page_keywords):
        # 且不包含内容页的明确特征（共有情况、不动产单元号等）
        content_only_keywords = ["共有情况", "不动产单元号", "权利类型", "权利性质", "使用期限"]
        if not any(kw in ocr_text for kw in content_only_keywords):
            reasons.append("包含首页特征关键词")
            return "PROPERTY_CERTIFICATE_FIRST_PAGE", reasons

    # 5. 基于OCR质量的判断
    # 如果OCR文本很短（<200字符）且包含乱码特征，可能是首页或附图页
    if len(ocr_text) < 200:
        # 检查是否包含乱码特征（大量生僻字组合）
        uncommon_chars = sum(1 for c in ocr_text if '㐀' <= c <= '䶿')
        if uncommon_chars > 5:
            reasons.append("OCR文本短且包含乱码特征，可能是首页或附图页")
            return "PROPERTY_CERTIFICATE_FIRST_PAGE", reasons

    # 默认分类
    reasons.append("无法明确分类，默认为内容页")
    return "PROPERTY_CERTIFICATE_CONTENT", reasons


def analyze_images():
    """分析demo目录中的所有不动产权证书图片"""

    demo_dir = Path("/Users/dongsun/Github/sample-OCR/demo-不动产权证书")

    if not demo_dir.exists():
        print(f"❌ 目录不存在: {demo_dir}")
        return

    # 初始化OCR和分类器
    print("正在初始化OCR引擎...")
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")

    # 收集所有图片
    images = []
    for category in ["存量", "增量"]:
        category_dir = demo_dir / category
        if category_dir.exists():
            for case_dir in category_dir.iterdir():
                if case_dir.is_dir():
                    for img_file in case_dir.glob("*.jp*g"):
                        images.append({
                            "path": img_file,
                            "category": category,
                            "case_id": case_dir.name
                        })

    print(f"\n找到 {len(images)} 张图片\n")

    # 分析每张图片
    results = []
    for i, img_info in enumerate(images, 1):
        img_path = img_info["path"]
        print(f"{'=' * 80}")
        print(f"[{i}/{len(images)}] 分析: {img_path.name}")
        print(f"案例: {img_info['case_id']} ({img_info['category']})")
        print(f"{'=' * 80}")

        # OCR识别
        print("正在进行OCR识别...")
        ocr_result = ocr.run_ocr(str(img_path))
        text = ocr_result.full_text

        # 显示OCR文本（前500字）
        print(f"\nOCR文本（前500字）:")
        print(text[:500])

        # 分类
        doc_type, reasons = classify_property_certificate(text)

        print(f"\n分类结果: {doc_type}")
        print(f"判断依据: {', '.join(reasons)}")

        results.append({
            "image": img_path.name,
            "path": str(img_path),
            "category": img_info["category"],
            "case_id": img_info["case_id"],
            "doc_type": doc_type,
            "reasons": reasons,
            "ocr_text_preview": text[:500]
        })

        print()

    # 生成统计报告
    print(f"\n{'=' * 80}")
    print("统计报告")
    print(f"{'=' * 80}\n")

    type_counts = {}
    for r in results:
        doc_type = r["doc_type"]
        type_counts[doc_type] = type_counts.get(doc_type, 0) + 1

    for doc_type, count in sorted(type_counts.items()):
        print(f"{doc_type}: {count}张")

    # 保存结果到JSON
    output_file = Path("/Users/dongsun/Github/OCR-Three-Layer-Hybrid/data/property_certificate_classification.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 分类结果已保存到: {output_file}")

    return results


if __name__ == "__main__":
    analyze_images()
