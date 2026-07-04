#!/usr/bin/env python3
"""
快速查找凭证
"""

import sys
from pathlib import Path
import subprocess

def quick_find_certificates():
    """快速查找包含'凭证'的图片"""
    sample_dir = Path('/Users/dongsun/Github/sample-OCR/存量房图片资料')
    test_cases = ['BBJZ-2026-0112065', 'BBJZ-2026-0113059', 'BBJZ-2026-0114007']

    results = []

    for case_name in test_cases:
        case_dir = sample_dir / case_name
        if not case_dir.exists():
            continue

        print(f"\n{'='*80}")
        print(f"案例: {case_name}")
        print(f"{'='*80}")

        # 对每个图片运行OCR并检查
        for img_path in sorted(case_dir.glob("*.jpg"))[:10]:  # 只检查前10个
            print(f"\n检查: {img_path.name}")

            # 使用Python脚本运行OCR
            result = subprocess.run(
                ['python3', '-c', f'''
import sys
sys.path.insert(0, 'src')
from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
ocr = PaddleOCRWrapper(device="cpu", default_engine="ppocr")
result = ocr.run_ocr("{img_path}")
print(result.full_text[:500])
                '''],
                capture_output=True,
                text=True,
                timeout=60
            )

            ocr_text = result.stdout
            if "凭证" in ocr_text[:100]:
                print(f"  ✓ 找到凭证！")
                print(f"\n完整OCR文本:\n{ocr_text}")
                results.append({
                    'case': case_name,
                    'image': img_path.name,
                    'text': ocr_text
                })

    return results


if __name__ == '__main__':
    results = quick_find_certificates()
    print(f"\n{'='*80}")
    print(f"共找到 {len(results)} 个凭证")
    print(f"{'='*80}")
