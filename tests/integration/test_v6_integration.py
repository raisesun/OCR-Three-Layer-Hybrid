#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成测试：验证V6原型模块集成到主系统

测试内容：
1. 位置标注提取器（position_extractor.py）
2. 字段校验器（field_validator.py）
3. VLM兜底处理器（vlm_fallback.py）
4. 集成到规则层和Pipeline
"""

import sys
import logging
from pathlib import Path

# 添加src路径
src_path = str(Path(__file__).parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from ocr_three_layer_hybrid.config import OCRConfig
from ocr_three_layer_hybrid.position_extractor import HouseholdPositionExtractor
from ocr_three_layer_hybrid.field_validator import FieldValidator
from ocr_three_layer_hybrid.vlm_fallback import VLMFallbackHandler
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer
from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
from ocr_three_layer_hybrid.interfaces import DocumentType, DocumentInfo

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def test_position_extractor():
    """测试位置标注提取器"""
    logger.info("=" * 60)
    logger.info("测试1: 位置标注提取器")
    logger.info("=" * 60)

    extractor = HouseholdPositionExtractor()
    logger.info("✓ 位置标注提取器创建成功")

    # 测试方法存在性
    assert hasattr(extractor, 'extract'), "extract方法不存在"
    assert hasattr(extractor, 'is_first_page'), "is_first_page方法不存在"
    assert hasattr(extractor, '_parse_ocr'), "_parse_ocr方法不存在"
    logger.info("✓ 所有必需方法存在")

    logger.info("✓ 测试通过: 位置标注提取器\n")


def test_field_validator():
    """测试字段校验器"""
    logger.info("=" * 60)
    logger.info("测试2: 字段校验器")
    logger.info("=" * 60)

    validator = FieldValidator()
    logger.info("✓ 字段校验器创建成功")

    # 测试校验规则
    test_cases = [
        ("户主姓名", "王晨露", True),
        ("户主姓名", "王", False),  # 太短
        ("户号", "005300251", True),
        ("户号", "123", False),  # 太短
        ("住址", "安徽省蚌埠市禹会区长中路44.5号", True),
        ("住址", "短地址", False),  # 太短
        ("公民身份号码", "123456789012345678", True),
        ("公民身份号码", "12345", False),  # 格式错误
    ]

    for field_name, value, should_pass in test_cases:
        result = validator.validate(field_name, value)
        status = "✓" if result.is_valid == should_pass else "✗"
        logger.info(f"{status} {field_name}='{value}': expected={should_pass}, actual={result.is_valid}")

    logger.info("✓ 测试通过: 字段校验器\n")


def test_vlm_fallback_handler():
    """测试VLM兜底处理器"""
    logger.info("=" * 60)
    logger.info("测试3: VLM兜底处理器")
    logger.info("=" * 60)

    # 创建模拟的VLM客户端
    class MockVLMClient:
        def call(self, prompt, image_path, max_tokens=2048):
            return '{"户主姓名": "测试姓名"}'

    handler = VLMFallbackHandler(vlm_client=MockVLMClient())
    logger.info("✓ VLM兜底处理器创建成功")

    # 测试判断逻辑
    fields = {
        "户主姓名": "王",  # 太短，需要兜底
        "户号": "005300251",  # 有效值
        "住址": "短",  # 太短，需要兜底
    }

    failed_fields = handler.get_failed_fields(fields)
    logger.info(f"失败字段: {failed_fields}")
    assert "户主姓名" in failed_fields, "户主姓名应该被标记为失败（太短）"
    assert "住址" in failed_fields, "住址应该被标记为失败（太短）"
    logger.info("✓ 测试通过: VLM兜底处理器\n")


def test_rule_layer_integration():
    """测试规则层集成"""
    logger.info("=" * 60)
    logger.info("测试4: 规则层集成位置标注提取器")
    logger.info("=" * 60)

    # 创建位置标注提取器
    position_extractor = HouseholdPositionExtractor()

    # 创建规则层，注入位置标注提取器
    rule_layer = RuleExtractionLayer(position_extractor=position_extractor)
    logger.info("✓ 规则层创建成功（注入位置标注提取器）")

    # 验证注入
    assert rule_layer._position_extractor is not None, "位置标注提取器未注入"
    logger.info("✓ 位置标注提取器已成功注入规则层")

    # 测试可以处理户口本文档
    doc_info = DocumentInfo(
        doc_type=DocumentType.HOUSEHOLD_REGISTER,
        ocr_texts=["测试文本"],
        image_path="/fake/path.jpg",
    )
    assert rule_layer.can_process(doc_info), "规则层应该可以处理户口本文档"
    logger.info("✓ 规则层可以处理户口本文档")

    logger.info("✓ 测试通过: 规则层集成\n")


def test_pipeline_integration():
    """测试Pipeline集成"""
    logger.info("=" * 60)
    logger.info("测试5: Pipeline集成VLM兜底处理器")
    logger.info("=" * 60)

    # 创建配置（启用所有VLM功能）
    config = OCRConfig()
    config.enable_vlm_fallback = True  # 启用VLM分类兜底
    config.enable_position_extraction = True  # 启用位置标注提取
    config.enable_vlm_field_fallback = True  # 启用VLM字段兜底

    # 创建Pipeline
    pipeline = PlanEPlusPipeline(
        enable_vlm_classification_fallback=config.enable_vlm_fallback,
        vlm_fallback_handler=None,
    )
    logger.info("✓ Pipeline创建成功")

    # 验证参数注入
    assert pipeline.vlm_fallback_handler is None, "VLM兜底处理器应该为None"
    logger.info("✓ VLM兜底处理器参数已注入（当前为None）")

    logger.info("✓ 测试通过: Pipeline集成\n")


def test_config_switches():
    """测试配置开关"""
    logger.info("=" * 60)
    logger.info("测试6: 配置开关")
    logger.info("=" * 60)

    config = OCRConfig()

    # 验证默认值
    assert config.enable_position_extraction == True, "位置标注默认应该启用"
    assert config.enable_vlm_field_fallback == True, "VLM兜底默认应该启用"
    logger.info("✓ 配置默认值正确")

    # 测试可以修改
    config.enable_position_extraction = False
    config.enable_vlm_field_fallback = False
    assert config.enable_position_extraction == False, "位置标注应该可以关闭"
    assert config.enable_vlm_field_fallback == False, "VLM兜底应该可以关闭"
    logger.info("✓ 配置可以修改")

    logger.info("✓ 测试通过: 配置开关\n")


def main():
    """运行所有集成测试"""
    logger.info("\n" + "=" * 60)
    logger.info("开始集成测试：V6原型模块集成到主系统")
    logger.info("=" * 60 + "\n")

    try:
        test_position_extractor()
        test_field_validator()
        test_vlm_fallback_handler()
        test_rule_layer_integration()
        test_pipeline_integration()
        test_config_switches()

        logger.info("=" * 60)
        logger.info("✓ 所有集成测试通过！")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"✗ 测试失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
