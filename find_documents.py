#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查找身份证和结婚证图片
"""

import os
import sys
from pathlib import Path
from paddleocr import PaddleOCR

def find_id_cards_and_marriage_certs():
    """查找身份证和结婚证图片"""

    print("初始化PaddleOCR引擎...")
    ocr = PaddleOCR(use_angle_cls=True, lang='ch')
    print("✅ 引擎初始化完成\n")

    sample_dirs = [
        '/Users/dongsun/Github/sample-OCR/存量房图片资料',
        '/Users/dongsun/Github/sample-OCR/增量房图片资料'
    ]

    id_card_images = []
    marriage_cert_images = []

    for sample_dir in sample_dirs:
        if not os.path.exists(sample_dir):
            continue

        print(f"扫描目录: {sample_dir}")

        # 遍历所有子目录
        for root, dirs, files in os.walk(sample_dir):
            for file in files:
                if not file.lower().endswith(('.jpg', '.jpeg')):
                    continue

                image_path = os.path.join(root, file)

                try:
                    result = ocr.ocr(image_path)
                    if not result or len(result) == 0:
                        continue

                    texts = result[0].rec_texts if hasattr(result[0], 'rec_texts') else []
                    full_text = ' '.join(texts)

                    # 检查是否是身份证
                    if '公民身份号码' in full_text or '居民身份证' in full_text:
                        id_card_images.append(image_path)
                        print(f"  ✅ 身份证: {file}")

                    # 检查是否是结婚证
                    elif '结婚证' in full_text or '登记日期' in full_text:
                        marriage_cert_images.append(image_path)
                        print(f"  ✅ 结婚证: {file}")

                except Exception as e:
                    print(f"  ❌ 错误: {file} - {e}")
                    continue

    print("\n" + "="*60)
    print("扫描结果")
    print("="*60)
    print(f"身份证图片: {len(id_card_images)}张")
    for img in id_card_images[:10]:
        print(f"  - {img}")

    print(f"\n结婚证图片: {len(marriage_cert_images)}张")
    for img in marriage_cert_images[:10]:
        print(f"  - {img}")

    # 保存结果
    result = {
        'id_card_images': id_card_images,
        'marriage_cert_images': marriage_cert_images
    }

    import json
    with open('/Users/dongsun/github/OCR-Three-Layer-Hybrid/document_scan_results.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 结果已保存到: document_scan_results.json")

if __name__ == '__main__':
    find_id_cards_and_marriage_certs()
