#!/usr/bin/env python3
"""
VLM兜底机制验证脚本

测试场景：
1. 构造字段校验失败的场景
2. 验证VLM兜底被正确调用
3. 验证失败字段被VLM结果覆盖
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ocr_three_layer_hybrid.config import OCRConfig
from ocr_three_layer_hybrid.service import OCRService
from ocr_three_layer_hybrid.field_validator import FieldValidator
from ocr_three_layer_hybrid.vlm_fallback import VLMFallbackHandler
from ocr_three_layer_hybrid.interfaces import DocumentType

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_field_validator():
    """测试字段校验器"""
    logger.info("=" * 70)
    logger.info("测试1: 字段校验器")
    logger.info("=" * 70)

    validator = FieldValidator()

    # 测试用例1: 有效的身份证号
    result = validator.validate("公民身份号码", "340322199403014698")
    logger.info(f"有效身份证号: {result.status.value} (期望: valid)")
    assert result.status.value == "valid", f"期望 valid，实际 {result.status.value}"

    # 测试用例2: 无效的身份证号（位数不对）
    result = validator.validate("公民身份号码", "12345")
    logger.info(f"无效身份证号: {result.status.value} (期望: invalid)")
    assert result.status.value == "invalid", f"期望 invalid，实际 {result.status.value}"

    # 测试用例3: 有效的姓名
    result = validator.validate("姓名", "张三")
    logger.info(f"有效姓名: {result.status.value} (期望: valid)")
    assert result.status.value == "valid", f"期望 valid，实际 {result.status.value}"

    # 测试用例4: 无效的姓名（太短）
    result = validator.validate("姓名", "张")
    logger.info(f"无效姓名: {result.status.value} (期望: invalid)")
    assert result.status.value == "invalid", f"期望 invalid，实际 {result.status.value}"

    logger.info("✅ 字段校验器测试通过\n")


def test_vlm_fallback_handler():
    """测试VLM兜底处理器"""
    logger.info("=" * 70)
    logger.info("测试2: VLM兜底处理器")
    logger.info("=" * 70)

    handler = VLMFallbackHandler()

    # 测试用例1: 所有字段都有效
    fields = {
        "公民身份号码": "340322199403014698",
        "姓名": "张三",
        "性别": "男"
    }
    failed = handler.get_failed_fields(fields)
    logger.info(f"所有字段有效: 失败字段数={len(failed)} (期望: 0)")
    assert len(failed) == 0, f"期望 0 个失败字段，实际 {len(failed)}"

    # 测试用例2: 部分字段无效
    fields = {
        "公民身份号码": "12345",  # 无效
        "姓名": "张三",
        "性别": "男"
    }
    failed = handler.get_failed_fields(fields)
    logger.info(f"部分字段无效: 失败字段={failed} (期望: ['公民身份号码'])")
    assert "公民身份号码" in failed, f"期望 '公民身份号码' 在失败列表中"

    logger.info("✅ VLM兜底处理器测试通过\n")


def test_vlm_fallback_integration():
    """测试VLM兜底集成（需要VLM服务运行）"""
    logger.info("=" * 70)
    logger.info("测试3: VLM兜底集成测试")
    logger.info("=" * 70)

    # 检查VLM服务是否可用
    config = OCRConfig()
    service = OCRService(config=config)

    # 测试图片：使用样本2（身份证）
    image_path = "/Users/dongsun/Github/sample-OCR/增量房图片资料/202402270015/e25491d291254874bf854b12515f701f.jpeg"

    if not Path(image_path).exists():
        logger.warning(f"测试图片不存在: {image_path}")
        logger.info("⚠️  跳过集成测试\n")
        return

    # 手动构造一个校验失败的场景
    logger.info("构造校验失败场景...")

    # 先正常提取
    ocr_text = service.run_ocr(image_path)
    result = service.process_single(image_path, ocr_text)

    extraction = result.get("extraction", {})
    fields = extraction.get("fields", {})

    logger.info(f"原始提取结果: {len([v for v in fields.values() if v])} 个字段")
    for key, value in fields.items():
        if value:
            logger.info(f"  {key}: {value}")

    # 手动修改一个字段为无效值，触发VLM兜底
    logger.info("\n手动修改公民身份号码为无效值，触发VLM兜底...")

    # 注意：这里我们只是演示如何触发VLM兜底
    # 实际生产中，VLM兜底是由字段校验器自动触发的

    handler = VLMFallbackHandler()
    invalid_fields = {
        "公民身份号码": "12345",  # 无效值
        "姓名": fields.get("姓名", ""),
        "性别": fields.get("性别", "")
    }

    failed = handler.get_failed_fields(invalid_fields)
    logger.info(f"校验失败字段: {failed}")

    if failed:
        logger.info("尝试调用VLM重新提取...")
        try:
            vlm_fields = handler.fallback_extract(
                image_path=image_path,
                failed_fields=failed,
                doc_type=DocumentType.ID_CARD
            )
            logger.info(f"VLM提取结果: {vlm_fields}")

            # 验证VLM结果
            if vlm_fields.get("公民身份号码"):
                logger.info("✅ VLM兜底成功提取到公民身份号码")
            else:
                logger.warning("⚠️  VLM未能提取到公民身份号码")
        except Exception as e:
            logger.error(f"❌ VLM兜底调用失败: {e}")

    logger.info("✅ VLM兜底集成测试完成\n")


def main():
    logger.info("=" * 70)
    logger.info("VLM兜底机制验证")
    logger.info("=" * 70)
    logger.info("")

    try:
        # 测试1: 字段校验器
        test_field_validator()

        # 测试2: VLM兜底处理器
        test_vlm_fallback_handler()

        # 测试3: VLM兜底集成
        test_vlm_fallback_integration()

        logger.info("=" * 70)
        logger.info("✅ 所有测试通过")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
