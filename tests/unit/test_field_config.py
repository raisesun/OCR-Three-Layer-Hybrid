# -*- coding: utf-8 -*-
"""
field_config 模块的单元测试
"""

import pytest
from ocr_three_layer_hybrid.field_config import (
    FieldPriority,
    FieldConfig,
    DocumentFieldConfig,
)


class TestFieldPriority:
    """测试 FieldPriority 枚举"""

    def test_priority_values(self):
        """测试优先级枚举值"""
        assert FieldPriority.REQUIRED.value == "required"
        assert FieldPriority.OPTIONAL.value == "optional"

    def test_priority_comparison(self):
        """测试优先级比较"""
        assert FieldPriority.REQUIRED != FieldPriority.OPTIONAL
        assert FieldPriority.REQUIRED == FieldPriority.REQUIRED


class TestFieldConfig:
    """测试 FieldConfig 数据类"""

    def test_create_required_field(self):
        """测试创建必须字段"""
        field = FieldConfig(
            name="合同编号",
            priority=FieldPriority.REQUIRED
        )
        assert field.name == "合同编号"
        assert field.priority == FieldPriority.REQUIRED
        assert field.sources == []

    def test_create_optional_field(self):
        """测试创建可选字段"""
        field = FieldConfig(
            name="买受人",
            priority=FieldPriority.OPTIONAL,
            sources=["first_page", "content"]
        )
        assert field.name == "买受人"
        assert field.priority == FieldPriority.OPTIONAL
        assert field.sources == ["first_page", "content"]

    def test_field_equality(self):
        """测试字段相等性"""
        field1 = FieldConfig(name="合同编号", priority=FieldPriority.REQUIRED)
        field2 = FieldConfig(name="合同编号", priority=FieldPriority.REQUIRED)
        field3 = FieldConfig(name="合同编号", priority=FieldPriority.OPTIONAL)

        assert field1 == field2
        assert field1 != field3

    def test_field_hash(self):
        """测试字段哈希"""
        field1 = FieldConfig(name="合同编号", priority=FieldPriority.REQUIRED)
        field2 = FieldConfig(name="合同编号", priority=FieldPriority.REQUIRED)

        # 相同字段应该有相同的哈希
        assert hash(field1) == hash(field2)

        # 可以用作字典键
        d = {field1: "value"}
        assert d[field2] == "value"


class TestDocumentFieldConfig:
    """测试 DocumentFieldConfig 数据类"""

    def test_create_empty_config(self):
        """测试创建空配置"""
        config = DocumentFieldConfig()
        assert config.required_fields == []
        assert config.optional_fields == []
        assert config.get_all_field_names() == []

    def test_create_config_with_fields(self):
        """测试创建带字段的配置"""
        config = DocumentFieldConfig(
            required_fields=[
                FieldConfig(name="总价款", priority=FieldPriority.REQUIRED),
                FieldConfig(name="签订日期", priority=FieldPriority.REQUIRED),
            ],
            optional_fields=[
                FieldConfig(name="合同编号", priority=FieldPriority.OPTIONAL),
                FieldConfig(name="买受人", priority=FieldPriority.OPTIONAL),
            ]
        )
        assert len(config.required_fields) == 2
        assert len(config.optional_fields) == 2
        assert len(config.get_all_field_names()) == 4

    def test_get_all_field_names(self):
        """测试获取所有字段名"""
        config = DocumentFieldConfig(
            required_fields=[
                FieldConfig(name="总价款", priority=FieldPriority.REQUIRED),
            ],
            optional_fields=[
                FieldConfig(name="合同编号", priority=FieldPriority.OPTIONAL),
            ]
        )
        field_names = config.get_all_field_names()
        assert "总价款" in field_names
        assert "合同编号" in field_names
        assert len(field_names) == 2

    def test_get_field_by_name(self):
        """测试根据名称查找字段"""
        config = DocumentFieldConfig(
            required_fields=[
                FieldConfig(name="总价款", priority=FieldPriority.REQUIRED),
            ],
            optional_fields=[
                FieldConfig(name="合同编号", priority=FieldPriority.OPTIONAL),
            ]
        )

        # 查找必须字段
        field = config.get_field_by_name("总价款")
        assert field is not None
        assert field.priority == FieldPriority.REQUIRED

        # 查找可选字段
        field = config.get_field_by_name("合同编号")
        assert field is not None
        assert field.priority == FieldPriority.OPTIONAL

        # 查找不存在的字段
        field = config.get_field_by_name("不存在")
        assert field is None

    def test_is_optional_field(self):
        """测试判断是否可选字段"""
        config = DocumentFieldConfig(
            required_fields=[
                FieldConfig(name="总价款", priority=FieldPriority.REQUIRED),
            ],
            optional_fields=[
                FieldConfig(name="合同编号", priority=FieldPriority.OPTIONAL),
            ]
        )

        assert config.is_optional_field("合同编号") is True
        assert config.is_optional_field("总价款") is False
        assert config.is_optional_field("不存在") is False

    def test_is_required_field(self):
        """测试判断是否必须字段"""
        config = DocumentFieldConfig(
            required_fields=[
                FieldConfig(name="总价款", priority=FieldPriority.REQUIRED),
            ],
            optional_fields=[
                FieldConfig(name="合同编号", priority=FieldPriority.OPTIONAL),
            ]
        )

        assert config.is_required_field("总价款") is True
        assert config.is_required_field("合同编号") is False
        assert config.is_required_field("不存在") is False

    def test_get_all_fields(self):
        """测试获取所有字段配置"""
        config = DocumentFieldConfig(
            required_fields=[
                FieldConfig(name="总价款", priority=FieldPriority.REQUIRED),
            ],
            optional_fields=[
                FieldConfig(name="合同编号", priority=FieldPriority.OPTIONAL),
            ]
        )

        all_fields = config.get_all_fields()
        assert len(all_fields) == 2
        assert all_fields[0].name == "总价款"
        assert all_fields[1].name == "合同编号"


class TestContractFieldConfigs:
    """测试合同字段配置（从 pipeline.py 导入）"""

    def test_purchase_contract_content_config(self):
        """测试购房合同内容页配置"""
        from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline

        config = PlanEPlusPipeline.DEFAULT_FIELD_CONFIGS.get(
            __import__('ocr_three_layer_hybrid.interfaces', fromlist=['DocumentType']).DocumentType.PURCHASE_CONTRACT_CONTENT
        )

        assert config is not None
        assert len(config.required_fields) == 3  # 总价款、签订日期、建筑面积
        assert len(config.optional_fields) == 4  # 合同编号、买受人、出卖人、房屋地址

        # 验证必须字段
        assert config.is_required_field("总价款")
        assert config.is_required_field("签订日期")
        assert config.is_required_field("建筑面积")

        # 验证可选字段
        assert config.is_optional_field("合同编号")
        assert config.is_optional_field("买受人")
        assert config.is_optional_field("出卖人")
        assert config.is_optional_field("房屋地址")

    def test_stock_contract_content_config(self):
        """测试存量房合同内容页配置"""
        from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
        from ocr_three_layer_hybrid.interfaces import DocumentType

        config = PlanEPlusPipeline.DEFAULT_FIELD_CONFIGS.get(DocumentType.STOCK_CONTRACT_CONTENT)

        assert config is not None
        assert len(config.required_fields) == 3
        assert len(config.optional_fields) == 4

    def test_purchase_contract_first_page_config(self):
        """测试购房合同首页配置"""
        from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
        from ocr_three_layer_hybrid.interfaces import DocumentType

        config = PlanEPlusPipeline.DEFAULT_FIELD_CONFIGS.get(DocumentType.PURCHASE_CONTRACT_FIRST_PAGE)

        assert config is not None
        # 首页没有必须字段
        assert len(config.required_fields) == 0
        assert len(config.optional_fields) == 4
