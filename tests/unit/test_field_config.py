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

    def test_required_property_true(self):
        """测试 required 属性：必须字段"""
        field = FieldConfig(name="姓名", priority=FieldPriority.REQUIRED)
        assert field.required is True

    def test_required_property_false(self):
        """测试 required 属性：可选字段"""
        field = FieldConfig(name="备注", priority=FieldPriority.OPTIONAL)
        assert field.required is False

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


class TestDocumentFieldConfigSkip:
    """测试 DocumentFieldConfig 的 skip 属性"""

    def test_skip_default_false(self):
        """测试 skip 默认为 False"""
        config = DocumentFieldConfig()
        assert config.skip is False

    def test_skip_true(self):
        """测试设置 skip=True"""
        config = DocumentFieldConfig(skip=True)
        assert config.skip is True

    def test_skip_with_fields_ignored(self):
        """测试 skip=True 时即使有字段也不影响 skip 语义"""
        config = DocumentFieldConfig(
            required_fields=[FieldConfig(name="字段A", priority=FieldPriority.REQUIRED)],
            skip=True,
        )
        assert config.skip is True
        assert len(config.required_fields) == 1


class TestGetMissingRequiredFields:
    """测试 get_missing_required_fields 方法"""

    def test_all_required_present(self):
        """所有必填字段都有值 → 返回空列表"""
        config = DocumentFieldConfig(
            required_fields=[
                FieldConfig(name="姓名", priority=FieldPriority.REQUIRED),
                FieldConfig(name="身份证号", priority=FieldPriority.REQUIRED),
            ],
        )
        extracted = {"姓名": "张三", "身份证号": "340123199001011234"}
        assert config.get_missing_required_fields(extracted) == []

    def test_one_required_missing(self):
        """一个必填字段缺失 → 返回该字段名"""
        config = DocumentFieldConfig(
            required_fields=[
                FieldConfig(name="姓名", priority=FieldPriority.REQUIRED),
                FieldConfig(name="身份证号", priority=FieldPriority.REQUIRED),
            ],
        )
        extracted = {"姓名": "张三", "身份证号": ""}
        missing = config.get_missing_required_fields(extracted)
        assert missing == ["身份证号"]

    def test_all_required_missing(self):
        """所有必填字段都缺失 → 返回所有字段名"""
        config = DocumentFieldConfig(
            required_fields=[
                FieldConfig(name="姓名", priority=FieldPriority.REQUIRED),
                FieldConfig(name="身份证号", priority=FieldPriority.REQUIRED),
            ],
        )
        extracted = {"姓名": "", "身份证号": ""}
        missing = config.get_missing_required_fields(extracted)
        assert set(missing) == {"姓名", "身份证号"}

    def test_field_not_in_extracted_dict(self):
        """必填字段不在提取结果字典中 → 视为缺失"""
        config = DocumentFieldConfig(
            required_fields=[
                FieldConfig(name="姓名", priority=FieldPriority.REQUIRED),
                FieldConfig(name="编号", priority=FieldPriority.REQUIRED),
            ],
        )
        extracted = {"姓名": "张三"}  # 编号 不在字典中
        missing = config.get_missing_required_fields(extracted)
        assert missing == ["编号"]

    def test_whitespace_only_treated_as_empty(self):
        """值只有空白字符 → 视为缺失"""
        config = DocumentFieldConfig(
            required_fields=[
                FieldConfig(name="姓名", priority=FieldPriority.REQUIRED),
            ],
        )
        extracted = {"姓名": "   "}
        missing = config.get_missing_required_fields(extracted)
        assert missing == ["姓名"]

    def test_no_required_fields(self):
        """没有必填字段 → 返回空列表"""
        config = DocumentFieldConfig(
            optional_fields=[
                FieldConfig(name="备注", priority=FieldPriority.OPTIONAL),
            ],
        )
        extracted = {}
        assert config.get_missing_required_fields(extracted) == []


class TestGetDefaultDocumentFieldConfigs:
    """测试 get_default_document_field_configs() 全局配置"""

    def test_returns_dict(self):
        """返回字典类型"""
        from ocr_three_layer_hybrid.field_config import get_default_document_field_configs
        configs = get_default_document_field_configs()
        assert isinstance(configs, dict)

    def test_all_34_types_covered(self):
        """覆盖所有 34 个文档类型"""
        from ocr_three_layer_hybrid.field_config import get_default_document_field_configs
        from ocr_three_layer_hybrid.interfaces import DocumentType
        configs = get_default_document_field_configs()
        # 所有在 field_config 中定义的类型都应该有配置
        expected_types = [
            DocumentType.ID_CARD, DocumentType.ID_CARD_FRONT, DocumentType.ID_CARD_BACK,
            DocumentType.HOUSEHOLD_REGISTER_COVER, DocumentType.HOUSEHOLD_REGISTER_CONTENT,
            DocumentType.MARRIAGE_CERTIFICATE, DocumentType.MARRIAGE_CERTIFICATE_COVER,
            DocumentType.MARRIAGE_CERTIFICATE_CONTENT, DocumentType.MARRIAGE_CERTIFICATE_STAMP,
            DocumentType.DIVORCE_CERTIFICATE, DocumentType.DIVORCE_CERTIFICATE_COVER,
            DocumentType.DIVORCE_CERTIFICATE_CONTENT, DocumentType.DIVORCE_CERTIFICATE_STAMP,
            DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE, DocumentType.PROPERTY_CERTIFICATE_CONTENT,
            DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT,
            DocumentType.INVOICE,
            DocumentType.PURCHASE_CONTRACT, DocumentType.PURCHASE_CONTRACT_FIRST_PAGE,
            DocumentType.PURCHASE_CONTRACT_CONTENT, DocumentType.PURCHASE_CONTRACT_STAMP,
            DocumentType.STOCK_CONTRACT, DocumentType.STOCK_CONTRACT_FIRST_PAGE,
            DocumentType.STOCK_CONTRACT_CONTENT, DocumentType.STOCK_CONTRACT_STAMP,
            DocumentType.FUND_SUPERVISION, DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE,
            DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE,
            DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP,
            DocumentType.FUND_SUPERVISION_CERTIFICATE,
            DocumentType.DIVORCE_AGREEMENT,
            DocumentType.NOTARY_CERTIFICATE, DocumentType.POWER_OF_ATTORNEY,
            DocumentType.UNKNOWN,
        ]
        for dt in expected_types:
            assert dt in configs, f"缺少配置: {dt}"

    def test_skip_types(self):
        """skip=True 的类型：封面页、盖章页、附图页、签署页"""
        from ocr_three_layer_hybrid.field_config import get_default_document_field_configs
        from ocr_three_layer_hybrid.interfaces import DocumentType
        configs = get_default_document_field_configs()

        skip_types = [
            DocumentType.MARRIAGE_CERTIFICATE_COVER,
            DocumentType.MARRIAGE_CERTIFICATE_STAMP,
            DocumentType.DIVORCE_CERTIFICATE_COVER,
            DocumentType.DIVORCE_CERTIFICATE_STAMP,
            DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT,
            DocumentType.PURCHASE_CONTRACT_STAMP,
            DocumentType.STOCK_CONTRACT_STAMP,
            DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP,
        ]
        for dt in skip_types:
            assert configs[dt].skip is True, f"{dt} 应该 skip=True"

    def test_content_types_not_skip(self):
        """内容页类型不应 skip"""
        from ocr_three_layer_hybrid.field_config import get_default_document_field_configs
        from ocr_three_layer_hybrid.interfaces import DocumentType
        configs = get_default_document_field_configs()

        content_types = [
            DocumentType.HOUSEHOLD_REGISTER_COVER,
            DocumentType.HOUSEHOLD_REGISTER_CONTENT,
            DocumentType.DIVORCE_CERTIFICATE_CONTENT,
            DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE,
            DocumentType.PROPERTY_CERTIFICATE_CONTENT,
            DocumentType.PURCHASE_CONTRACT_FIRST_PAGE,
            DocumentType.PURCHASE_CONTRACT_CONTENT,
            DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE,
            DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE,
            DocumentType.FUND_SUPERVISION_CERTIFICATE,
        ]
        for dt in content_types:
            assert configs[dt].skip is False, f"{dt} 应该 skip=False"

    def test_property_first_page_all_optional(self):
        """房产证首页：编号和登记日期都是可选（允许提取不到）"""
        from ocr_three_layer_hybrid.field_config import get_default_document_field_configs
        from ocr_three_layer_hybrid.interfaces import DocumentType
        configs = get_default_document_field_configs()

        config = configs[DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE]
        assert len(config.required_fields) == 0
        assert len(config.optional_fields) == 2
        assert config.is_optional_field("编号")
        assert config.is_optional_field("登记日期")

    def test_fund_supervision_certificate_required_fields(self):
        """资金监管凭证：协议编号和买房人姓名为必填"""
        from ocr_three_layer_hybrid.field_config import get_default_document_field_configs
        from ocr_three_layer_hybrid.interfaces import DocumentType
        configs = get_default_document_field_configs()

        config = configs[DocumentType.FUND_SUPERVISION_CERTIFICATE]
        assert config.is_required_field("协议编号")
        assert config.is_required_field("买房人姓名")
        assert config.is_optional_field("收款单位")


class TestContractFieldConfigs:
    """测试合同字段配置（从 pipeline.py 导入）"""

    def test_purchase_contract_content_config(self):
        """测试购房合同内容页配置"""
        from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
        from ocr_three_layer_hybrid.interfaces import DocumentType

        config = PlanEPlusPipeline.DEFAULT_FIELD_CONFIGS.get(DocumentType.PURCHASE_CONTRACT_CONTENT)

        assert config is not None
        assert len(config.required_fields) == 2  # 总价款、签订日期
        assert len(config.optional_fields) == 2  # 建筑面积、房屋地址

        # 验证必须字段
        assert config.is_required_field("总价款")
        assert config.is_required_field("签订日期")

        # 验证可选字段
        assert config.is_optional_field("建筑面积")
        assert config.is_optional_field("房屋地址")

    def test_stock_contract_content_config(self):
        """测试存量房合同内容页配置"""
        from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
        from ocr_three_layer_hybrid.interfaces import DocumentType

        config = PlanEPlusPipeline.DEFAULT_FIELD_CONFIGS.get(DocumentType.STOCK_CONTRACT_CONTENT)

        assert config is not None
        assert len(config.required_fields) == 2  # 总价款、签订日期
        assert len(config.optional_fields) == 2  # 建筑面积、房屋地址

    def test_purchase_contract_first_page_config(self):
        """测试购房合同首页配置"""
        from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
        from ocr_three_layer_hybrid.interfaces import DocumentType

        config = PlanEPlusPipeline.DEFAULT_FIELD_CONFIGS.get(DocumentType.PURCHASE_CONTRACT_FIRST_PAGE)

        assert config is not None
        # 首页有 3 个必须字段：合同编号、买受人、出卖人
        assert len(config.required_fields) == 3
        assert len(config.optional_fields) == 1  # 房屋坐落
