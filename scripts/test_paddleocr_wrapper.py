#!/usr/bin/env python3
"""
测试 PaddleOCR 包装器

验证：
1. 模型路径是否正确
2. PP-OCRv6 引擎是否可以正常工作
3. PaddleOCR-VL 引擎是否可以正常工作
4. 速度和精度是否符合预期
"""

import sys
import time
import logging
from pathlib import Path

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ocr_three_layer_hybrid.paddleocr_wrapper import (
    PaddleOCRWrapper,
    PaddleOCREngine,
    PaddleOCRVLLEngine,
    _DEFAULT_DET_MODEL,
    _DEFAULT_REC_MODEL,
    _DEFAULT_LAYOUT_MODEL,
    _DEFAULT_VLM_MODEL,
)


def check_model_paths():
    """检查模型路径是否存在"""
    print("\n" + "="*70)
    print("检查模型路径")
    print("="*70)

    models = {
        "PP-OCRv6 检测模型": _DEFAULT_DET_MODEL,
        "PP-OCRv6 识别模型": _DEFAULT_REC_MODEL,
        "PP-DocLayoutV3 版面分析": _DEFAULT_LAYOUT_MODEL,
        "PaddleOCR-VL 0.9B": _DEFAULT_VLM_MODEL,
    }

    all_exist = True
    for name, path in models.items():
        exists = Path(path).exists()
        status = "✅" if exists else "❌"
        print(f"{status} {name}: {path}")
        if not exists:
            all_exist = False

    return all_exist


def test_ppocr_engine(image_path: str):
    """测试 PP-OCRv6 引擎"""
    print("\n" + "="*70)
    print("测试 PP-OCRv6 引擎")
    print("="*70)

    print(f"测试图片: {image_path}")
    print("初始化引擎...")

    engine = PaddleOCREngine(
        device="cpu",
        use_layout=False,
    )

    print("开始推理...")
    start = time.time()

    try:
        results = engine.predict(image_path)
        elapsed = time.time() - start

        if results:
            result = results[0]
            print(f"\n✅ 推理成功！")
            print(f"耗时: {elapsed:.2f}秒")
            print(f"识别文本块数: {len(result.rec_texts)}")
            print(f"文本长度: {len(result.full_text)} 字符")
            print(f"\n前 200 字符:")
            print(result.full_text[:200])

            return True, elapsed
        else:
            print(f"❌ 推理失败：无结果")
            return False, elapsed

    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ 推理失败: {e}")
        import traceback
        traceback.print_exc()
        return False, elapsed


def test_vlm_engine(image_path: str):
    """测试 PaddleOCR-VL 引擎"""
    print("\n" + "="*70)
    print("测试 PaddleOCR-VL 引擎")
    print("="*70)

    print(f"测试图片: {image_path}")
    print("初始化引擎...")

    engine = PaddleOCRVLLEngine(
        device="cpu",
    )

    print("开始推理...")
    start = time.time()

    try:
        results = engine.predict(image_path)
        elapsed = time.time() - start

        if results:
            result = results[0]
            print(f"\n✅ 推理成功！")
            print(f"耗时: {elapsed:.2f}秒")
            print(f"识别文本块数: {len(result.rec_texts)}")
            print(f"文本长度: {len(result.full_text)} 字符")
            print(f"\n前 200 字符:")
            print(result.full_text[:200])

            return True, elapsed
        else:
            print(f"❌ 推理失败：无结果")
            return False, elapsed

    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ 推理失败: {e}")
        import traceback
        traceback.print_exc()
        return False, elapsed


def test_wrapper(image_path: str):
    """测试统一包装器"""
    print("\n" + "="*70)
    print("测试统一包装器")
    print("="*70)

    print(f"测试图片: {image_path}")

    wrapper = PaddleOCRWrapper(
        device="cpu",
        use_layout=False,
        default_engine="auto",
    )

    # 测试自动选择引擎（身份证 → PP-OCR）
    print("\n测试1: 自动选择引擎（身份证 → PP-OCR）")
    start = time.time()
    try:
        result = wrapper.run_ocr(image_path, doc_type="身份证")
        elapsed = time.time() - start
        print(f"✅ 成功！耗时: {elapsed:.2f}秒")
        print(f"文本长度: {len(result.full_text)} 字符")
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ 失败: {e}")

    # 测试强制使用 VLM
    print("\n测试2: 强制使用 VLM 引擎")
    start = time.time()
    try:
        result = wrapper.run_ocr(image_path, engine="vlm")
        elapsed = time.time() - start
        print(f"✅ 成功！耗时: {elapsed:.2f}秒")
        print(f"文本长度: {len(result.full_text)} 字符")
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ 失败: {e}")

    wrapper.close()


def find_test_image():
    """查找测试图片"""
    # 尝试查找测试图片
    test_dirs = [
        Path(__file__).parent.parent / "tests" / "samples",
        Path(__file__).parent.parent / "tests" / "images",
        Path(__file__).parent.parent / "data" / "samples",
    ]

    for test_dir in test_dirs:
        if test_dir.exists():
            images = list(test_dir.glob("*.jpg")) + list(test_dir.glob("*.png"))
            if images:
                return str(images[0])

    # 如果找不到，使用默认路径
    return "/Users/dongsun/Github/OCR-Three-Layer-Hybrid/tests/samples/hukou/hukou_001.jpg"


def main():
    """主函数"""
    print("\n" + "="*70)
    print("PaddleOCR 包装器测试")
    print("="*70)

    # 1. 检查模型路径
    if not check_model_paths():
        print("\n⚠️  警告：部分模型路径不存在，测试可能失败")

    # 2. 查找测试图片（支持命令行参数）
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        image_path = find_test_image()

    if not Path(image_path).exists():
        print(f"\n❌ 找不到测试图片: {image_path}")
        print("请指定一个有效的图片路径")
        return

    print(f"\n使用测试图片: {image_path}")

    # 3. 测试 PP-OCRv6 引擎
    success_ppocr, time_ppocr = test_ppocr_engine(image_path)

    # 4. 测试 VLM 引擎（可选，可能较慢）
    # success_vlm, time_vlm = test_vlm_engine(image_path)

    # 5. 测试统一包装器
    test_wrapper(image_path)

    # 6. 输出总结
    print("\n" + "="*70)
    print("测试总结")
    print("="*70)

    if success_ppocr:
        print(f"✅ PP-OCRv6 引擎: 正常 ({time_ppocr:.2f}秒)")
    else:
        print(f"❌ PP-OCRv6 引擎: 失败")

    # if success_vlm:
    #     print(f"✅ PaddleOCR-VL 引擎: 正常 ({time_vlm:.2f}秒)")
    # else:
    #     print(f"❌ PaddleOCR-VL 引擎: 失败")

    print("\n测试完成！")


if __name__ == "__main__":
    main()
