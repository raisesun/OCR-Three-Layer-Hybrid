#!/usr/bin/env python3
"""
分析问题凭证
"""

import sys
from pathlib import Path

sys.path.insert(0, 'src')

from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper


def main():
    ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")

    # 问题凭证
    img_path = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0114007/16bb1e492640492c8f3ffbd5a797ff46.jpg')

    print("="*80)
    print(f"问题凭证: {img_path.name}")
    print("="*80)

    # OCR
    ocr_result = ocr.run_ocr(str(img_path))

    print(f"\n完整OCR文本:\n{ocr_result.full_text}")


if __name__ == '__main__':
    main()
