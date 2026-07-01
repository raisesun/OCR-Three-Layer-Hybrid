#!/usr/bin/env python3
"""
Phase 2 集成测试

验证 PP-OCRv6 集成到主系统的效果：
1. 测试 run_ocr() 方法是否正常工作
2. 对比不同引擎的速度
3. 验证文本提取质量
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

from ocr_three_layer_hybrid.config import OCRConfig
from ocr_three_layer_hybrid.service import OCRService


def test_ocr_engine(engine_name: str, image_path: str):
    """测试指定 OCR 引擎"""
    print(f"\n{'='*70}")
    print(f"测试引擎: {engine_name}")
    print(f"{'='*70}")

    # 创建配置
    config = OCRConfig()
    config.ocr_engine = engine_name

    # 创建服务
    service = OCRService(config=config)

    # 测试 run_ocr()
    start = time.time()
    text = service.run_ocr(image_path)
    elapsed = time.time() - start

    print(f"耗时: {elapsed:.2f}秒")
    print(f"文本长度: {len(text)}字符")
    print(f"前 200 字符:")
    print(text[:200])

    return {
        "engine": engine_name,
        "elapsed": elapsed,
        "text_length": len(text),
        "success": len(text) > 0,
    }


def main():
    """主函数"""
    print("\n" + "="*70)
    print("Phase 2 集成测试")
    print("="*70)

    # 测试图片
    image_path = "/Users/dongsun/Github/OCR-Three-Layer-Hybrid/demo-single-image.png"

    if not Path(image_path).exists():
        logger.error(f"找不到测试图片: {image_path}")
        return

    # 测试的引擎
    engines = ["ppocr", "glm_ocr"]  # 先测试这两个

    results = []
    for engine in engines:
        try:
            result = test_ocr_engine(engine, image_path)
            results.append(result)
        except Exception as e:
            logger.error(f"测试 {engine} 失败: {e}")
            results.append({
                "engine": engine,
                "elapsed": 0,
                "text_length": 0,
                "success": False,
            })

    # 输出总结
    print("\n" + "="*70)
    print("测试总结")
    print("="*70)

    for result in results:
        status = "✅" if result["success"] else "❌"
        print(f"{status} {result['engine']}: {result['elapsed']:.2f}秒, {result['text_length']}字符")

    print("\n测试完成！")


if __name__ == "__main__":
    main()
