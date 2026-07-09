# -*- coding: utf-8 -*-
"""
字段配置模块

定义字段的优先级（必须/可选）和来源信息，用于指导多页文档的字段提取和合并策略。

核心概念：
- FieldConfig: 单个字段的配置（名称、优先级）
- DocumentFieldConfig: 某个文档类型的完整字段配置（必须字段 + 可选字段 + 是否跳过）
- get_default_document_field_configs(): 所有文档类型的默认字段配置

RULE 层失败判定：
- 任一 required 字段值为空 → RULE 层失败 → 触发 VLM 兜底
- skip=True 的类型不提取任何数据，明确定义"不需要读取"
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class FieldPriority(str, Enum):
    """字段优先级"""
    REQUIRED = "required"  # 必须字段，提取失败会影响整体成功率
    OPTIONAL = "optional"  # 可选字段，提取失败不影响整体成功率


@dataclass
class FieldConfig:
    """单个字段的配置"""
    name: str  # 字段名称
    priority: FieldPriority  # 优先级（必须/可选）
    sources: List[str] = field(default_factory=list)  # 预期来源页面（如 ["first_page", "content"]）

    @property
    def required(self) -> bool:
        """是否为必须提取的字段"""
        return self.priority == FieldPriority.REQUIRED

    def __hash__(self):
        return hash((self.name, self.priority))

    def __eq__(self, other):
        if not isinstance(other, FieldConfig):
            return False
        return self.name == other.name and self.priority == other.priority


@dataclass
class DocumentFieldConfig:
    """文档类型的字段配置集合

    Attributes:
        required_fields: 必须提取的字段列表（任一为空 → RULE 层失败）
        optional_fields: 允许提取不到的字段列表
        skip: 是否明确定义不提取任何数据（如封面页、盖章页、附图页）
    """
    required_fields: List[FieldConfig] = field(default_factory=list)
    optional_fields: List[FieldConfig] = field(default_factory=list)
    skip: bool = False

    def get_all_field_names(self) -> List[str]:
        """获取所有字段名称"""
        return [f.name for f in self.required_fields] + [f.name for f in self.optional_fields]

    def get_field_by_name(self, name: str) -> Optional[FieldConfig]:
        """根据字段名查找配置"""
        for f in self.required_fields + self.optional_fields:
            if f.name == name:
                return f
        return None

    def is_optional_field(self, name: str) -> bool:
        """判断是否是可选字段"""
        return any(f.name == name and f.priority == FieldPriority.OPTIONAL
                   for f in self.optional_fields)

    def is_required_field(self, name: str) -> bool:
        """判断是否是必须字段"""
        return any(f.name == name and f.priority == FieldPriority.REQUIRED
                   for f in self.required_fields)

    def get_all_fields(self) -> List[FieldConfig]:
        """获取所有字段配置"""
        return self.required_fields + self.optional_fields

    def get_missing_required_fields(self, extracted_fields: Dict[str, str]) -> List[str]:
        """获取未提取到值的必须字段名称列表

        Args:
            extracted_fields: 已提取的字段字典 {字段名: 值}

        Returns:
            值为空的必须字段名称列表
        """
        missing = []
        for f in self.required_fields:
            value = extracted_fields.get(f.name, "")
            if not value or not value.strip():
                missing.append(f.name)
        return missing


def get_default_key_lists() -> Dict:
    """获取所有文档类型的默认字段列表（字段名列表）

    返回 Dict[DocumentType, List[str]]，避免循环导入。
    从 get_default_document_field_configs() 动态生成，
    将 required_fields 和 optional_fields 合并为完整的字段名列表。

    这样避免了在 pipeline.py 中硬编码 ~250 行的 DEFAULT_KEY_LISTS。
    """
    field_configs = get_default_document_field_configs()
    key_lists = {}
    for doc_type, config in field_configs.items():
        key_lists[doc_type] = config.get_all_field_names()
    return key_lists


def _r(name: str) -> FieldConfig:
    """快捷方法：创建必须字段配置"""
    return FieldConfig(name=name, priority=FieldPriority.REQUIRED)


def _o(name: str) -> FieldConfig:
    """快捷方法：创建可选字段配置"""
    return FieldConfig(name=name, priority=FieldPriority.OPTIONAL)


def get_default_document_field_configs() -> Dict:
    """所有文档类型的默认字段配置

    返回 Dict[DocumentType, DocumentFieldConfig]，避免循环导入。

    设计原则：
    - 每个文档类型/子类型必须明确定义提取哪些字段
    - required=True 的字段未提取到 → RULE 层失败 → 触发 VLM 兜底
    - skip=True → 明确定义不提取任何数据（封面页、盖章页、附图页）
    - 用户可直接修改 required/optional 来调整提取策略
    """
    from ocr_three_layer_hybrid.interfaces import DocumentType

    return {
        # ==================== 身份证 ====================
        DocumentType.ID_CARD: DocumentFieldConfig(
            required_fields=[_r("姓名"), _r("公民身份号码")],
            optional_fields=[_o("性别"), _o("民族"), _o("出生"), _o("住址")],
        ),
        DocumentType.ID_CARD_FRONT: DocumentFieldConfig(
            required_fields=[_r("姓名"), _r("公民身份号码")],
            optional_fields=[_o("性别"), _o("民族"), _o("出生"), _o("住址")],
        ),
        DocumentType.ID_CARD_BACK: DocumentFieldConfig(
            required_fields=[_r("签发机关")],
            optional_fields=[_o("有效期限")],
        ),

        # ==================== 户口本 ====================
        # 首页（户信息）：户别/户主姓名/户号/住址
        DocumentType.HOUSEHOLD_REGISTER_COVER: DocumentFieldConfig(
            required_fields=[_r("户主姓名"), _r("户号")],
            optional_fields=[_o("户别"), _o("住址")],
        ),
        # 个人页：姓名/与户主关系/性别/出生日期/民族/公民身份号码
        DocumentType.HOUSEHOLD_REGISTER_CONTENT: DocumentFieldConfig(
            required_fields=[_r("姓名"), _r("公民身份号码")],
            optional_fields=[_o("与户主关系"), _o("性别"), _o("出生日期"), _o("民族")],
        ),

        # ==================== 结婚证 ====================
        DocumentType.MARRIAGE_CERTIFICATE: DocumentFieldConfig(
            required_fields=[_r("结婚证字号"), _r("男方身份证号"), _r("女方身份证号")],
            optional_fields=[_o("登记日期"), _o("持证人"), _o("男方姓名"), _o("女方姓名")],
        ),
        DocumentType.MARRIAGE_CERTIFICATE_COVER: DocumentFieldConfig(skip=True),
        DocumentType.MARRIAGE_CERTIFICATE_CONTENT: DocumentFieldConfig(
            required_fields=[_r("结婚证字号"), _r("男方身份证号"), _r("女方身份证号")],
            optional_fields=[_o("登记日期"), _o("持证人"), _o("男方姓名"), _o("女方姓名")],
        ),
        DocumentType.MARRIAGE_CERTIFICATE_STAMP: DocumentFieldConfig(skip=True),

        # ==================== 离婚证 ====================
        DocumentType.DIVORCE_CERTIFICATE: DocumentFieldConfig(
            required_fields=[_r("离婚证字号"), _r("持证人身份证件号"), _r("原配偶身份证件号")],
            optional_fields=[
                _o("登记日期"), _o("持证人"), _o("持证人性别"), _o("持证人民族"),
                _o("持证人出生日期"), _o("原配偶姓名"), _o("原配偶性别"),
                _o("原配偶民族"), _o("原配偶出生日期"), _o("备注"),
            ],
        ),
        DocumentType.DIVORCE_CERTIFICATE_COVER: DocumentFieldConfig(skip=True),
        DocumentType.DIVORCE_CERTIFICATE_CONTENT: DocumentFieldConfig(
            required_fields=[_r("离婚证字号"), _r("持证人身份证件号"), _r("原配偶身份证件号")],
            optional_fields=[
                _o("登记日期"), _o("持证人"), _o("持证人性别"), _o("持证人民族"),
                _o("持证人出生日期"), _o("原配偶姓名"), _o("原配偶性别"),
                _o("原配偶民族"), _o("原配偶出生日期"), _o("备注"),
            ],
        ),
        DocumentType.DIVORCE_CERTIFICATE_STAMP: DocumentFieldConfig(skip=True),

        # ==================== 不动产权证书 ====================
        # 首页：编号和登记日期（均允许提取不到）
        DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE: DocumentFieldConfig(
            required_fields=[],
            optional_fields=[_o("编号"), _o("登记日期")],
        ),
        # 内容页：核心数据
        DocumentType.PROPERTY_CERTIFICATE_CONTENT: DocumentFieldConfig(
            required_fields=[_r("证书号"), _r("权利人")],
            optional_fields=[
                _o("共有情况"), _o("不动产单元号"), _o("房屋地址"),
                _o("建筑面积"), _o("用途"),
            ],
        ),
        # 附图页：明确定义不提取
        DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT: DocumentFieldConfig(skip=True),

        # ==================== 发票 ====================
        DocumentType.INVOICE: DocumentFieldConfig(
            required_fields=[_r("发票代码"), _r("发票号码")],
            optional_fields=[
                _o("开票日期"), _o("价税合计"), _o("购买方名称"),
                _o("购买方纳税人识别号"), _o("销售方名称"), _o("销售方纳税人识别号"),
            ],
        ),

        # ==================== 购房合同 ====================
        # 首页：合同编号/买受人/出卖人（必须），房屋坐落（可选）
        DocumentType.PURCHASE_CONTRACT: DocumentFieldConfig(
            required_fields=[_r("合同编号"), _r("买受人"), _r("出卖人")],
            optional_fields=[_o("总价款"), _o("签订日期"), _o("房屋地址"), _o("建筑面积")],
        ),
        DocumentType.PURCHASE_CONTRACT_FIRST_PAGE: DocumentFieldConfig(
            required_fields=[_r("合同编号"), _r("买受人"), _r("出卖人")],
            optional_fields=[_o("房屋坐落")],
        ),
        DocumentType.PURCHASE_CONTRACT_CONTENT: DocumentFieldConfig(
            required_fields=[_r("总价款"), _r("签订日期")],
            optional_fields=[_o("建筑面积"), _o("房屋地址")],
        ),
        DocumentType.PURCHASE_CONTRACT_STAMP: DocumentFieldConfig(skip=True),

        # ==================== 存量房合同 ====================
        DocumentType.STOCK_CONTRACT: DocumentFieldConfig(
            required_fields=[_r("合同编号"), _r("买受人"), _r("出卖人")],
            optional_fields=[_o("总价款"), _o("签订日期"), _o("房屋地址"), _o("建筑面积")],
        ),
        DocumentType.STOCK_CONTRACT_FIRST_PAGE: DocumentFieldConfig(
            required_fields=[_r("合同编号"), _r("买受人"), _r("出卖人")],
            optional_fields=[_o("房屋坐落")],
        ),
        DocumentType.STOCK_CONTRACT_CONTENT: DocumentFieldConfig(
            required_fields=[_r("总价款"), _r("签订日期")],
            optional_fields=[_o("建筑面积"), _o("房屋地址")],
        ),
        DocumentType.STOCK_CONTRACT_STAMP: DocumentFieldConfig(skip=True),

        # ==================== 资金监管协议 ====================
        # 首页：编号（必须），其余 13 字段（可选）
        DocumentType.FUND_SUPERVISION: DocumentFieldConfig(
            required_fields=[_r("编号")],
            optional_fields=[
                _o("甲方"), _o("乙方"), _o("丙方"), _o("签署日期"),
                _o("网上签约备案合同号"), _o("房屋地址"), _o("建筑面积"), _o("不动产权证号"),
                _o("购房款"), _o("购房款(大写)"), _o("购房款(小写)"),
                _o("贷款(大写)"), _o("贷款(小写)"),
                _o("甲方姓名"), _o("甲方身份证号"), _o("甲方银行"), _o("甲方账号"),
                _o("乙方姓名"), _o("乙方身份证号"), _o("乙方银行"), _o("乙方账号"),
            ],
        ),
        DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE: DocumentFieldConfig(
            required_fields=[_r("编号")],
            optional_fields=[
                _o("甲方"), _o("乙方"), _o("丙方"), _o("签署日期"),
                _o("网上签约备案合同号"), _o("房屋地址"), _o("建筑面积"), _o("不动产权证号"),
                _o("购房款"), _o("购房款(大写)"), _o("购房款(小写)"),
                _o("贷款(大写)"), _o("贷款(小写)"),
            ],
        ),
        DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE: DocumentFieldConfig(
            required_fields=[_r("甲方姓名"), _r("乙方姓名")],
            optional_fields=[
                _o("甲方身份证号"), _o("甲方银行"), _o("甲方账号"),
                _o("乙方身份证号"), _o("乙方银行"), _o("乙方账号"),
            ],
        ),
        DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP: DocumentFieldConfig(skip=True),
        # 凭证：协议编号/买房人姓名（必须），其余（可选）
        DocumentType.FUND_SUPERVISION_CERTIFICATE: DocumentFieldConfig(
            required_fields=[_r("协议编号"), _r("买房人姓名")],
            optional_fields=[
                _o("日期"), _o("买房人"), _o("身份证号"), _o("房屋坐落"),
                _o("建筑面积"), _o("监管总额"), _o("收款单位"),
            ],
        ),

        # ==================== 离婚协议 ====================
        DocumentType.DIVORCE_AGREEMENT: DocumentFieldConfig(
            required_fields=[_r("男方姓名"), _r("女方姓名")],
            optional_fields=[
                _o("男方身份证号"), _o("女方身份证号"), _o("离婚日期"),
                _o("财产分割约定"), _o("子女抚养"), _o("债务处理"), _o("其他约定"),
            ],
        ),

        # ==================== 公证书 ====================
        DocumentType.NOTARY_CERTIFICATE: DocumentFieldConfig(
            required_fields=[_r("公证书编号")],
            optional_fields=[_o("公证日期"), _o("公证事项")],
        ),

        # ==================== 委托书 ====================
        DocumentType.POWER_OF_ATTORNEY: DocumentFieldConfig(
            required_fields=[_r("委托人"), _r("受托人")],
            optional_fields=[_o("委托事项"), _o("委托日期")],
        ),

        # ==================== 未知类型 ====================
        DocumentType.UNKNOWN: DocumentFieldConfig(
            required_fields=[],
            optional_fields=[
                _o("文档类型"), _o("编号"), _o("日期"), _o("金额"),
                _o("姓名"), _o("身份证号"), _o("买方"), _o("卖方"), _o("权利人"),
                _o("房屋地址"), _o("建筑面积"), _o("用途"),
            ],
        ),
    }
