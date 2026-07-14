#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回归测试：对真实业务样本跑分类+提取，验证分类器修复无回归

样本来源：
- 增量房图片资料/202406240010（58张，购房合同为主）
- 增量房图片资料/202411070032（5张，身份证）
- 存量房图片资料/BBJZ-2026-0121076（32张，不动产权证书+其他）
- 存量房图片资料/BBJZ-2026-0129058（27张，不动产权证书+资金监管）

用法:
    python3 scripts/regression_test_samples.py
"""
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ocr_three_layer_hybrid.service import OCRService

SAMPLE_DIRS = [
    "/Users/dongsun/Github/sample-OCR/增量房图片资料/202406240010",
    "/Users/dongsun/Github/sample-OCR/增量房图片资料/202411070032",
    "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0121076",
    "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0129058",
]

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def main():
    print("初始化 OCRService（首次调用会懒加载 PaddleOCR 模型，约 30-60 秒）...")
    service = OCRService()

    total = 0
    type_counts = defaultdict(int)
    errors = []
    per_image_results = []
    start_total = time.time()

    for sample_dir in SAMPLE_DIRS:
        dir_name = Path(sample_dir).name
        print(f"\n=== 样本目录: {dir_name} ===")
        images = sorted(
            f for f in Path(sample_dir).iterdir() if f.suffix.lower() in IMAGE_EXTS
        )
        print(f"共 {len(images)} 张图片")

        for img in images:
            try:
                start = time.time()
                result = service.process_single(str(img))
                elapsed = time.time() - start

                doc_type = result["classification"]["doc_type"]
                confidence = result["classification"]["confidence"]
                fields = result["extraction"]["fields"]
                fields_count = len([v for v in fields.values() if v and v.strip()])
                success = result["extraction"]["success"]

                type_counts[doc_type] += 1
                total += 1

                per_image_results.append({
                    "image": img.name,
                    "directory": dir_name,
                    "doc_type": doc_type,
                    "confidence": confidence,
                    "fields_count": fields_count,
                    "success": success,
                    "elapsed_s": round(elapsed, 2),
                })

                status = "✅" if success else "⚠️"
                print(
                    f"  [{total:3d}] {status} {img.name[:35]:<35} "
                    f"-> {doc_type:<15} conf={confidence:.2f} "
                    f"fields={fields_count:2d}  {elapsed:.1f}s"
                )
            except Exception as e:
                errors.append({"image": img.name, "directory": dir_name, "error": str(e)})
                print(f"  [ERR] {img.name[:35]}: {e}")

    total_time = time.time() - start_total

    # 汇总
    print(f"\n{'=' * 70}")
    print(f"=== 回归测试汇总 ===")
    print(f"总处理: {total} 张 | 错误: {len(errors)} | 总耗时: {total_time:.1f}s ({total_time/60:.1f}min)")
    print(f"\n按类型分布:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t:<20} {c:3d} ({c/total*100:.1f}%)")

    if errors:
        print(f"\n错误详情:")
        for e in errors:
            print(f"  {e['directory']}/{e['image']}: {e['error'][:100]}")

    # 保存结果
    out_path = (
        Path(__file__).resolve().parent.parent
        / "tests"
        / "results"
        / "regression_test_20260714.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sample_dirs": [Path(d).name for d in SAMPLE_DIRS],
        "total": total,
        "errors": errors,
        "type_counts": dict(type_counts),
        "total_time_s": round(total_time, 1),
        "per_image": per_image_results,
    }
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n结果已保存: {out_path}")


if __name__ == "__main__":
    main()
