#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第1层：文档分类器（重构版）

路由逻辑：
1. 标准证件强信号 → 直接路由
2. 标准单证强信号 → 直接路由
3. 合同/协议字段组合 → 路由到对应提取器
4. 无法判定 → VLM兜底（返回UNKNOWN）
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from ocr_three_layer_hybrid.interfaces import (
    DocumentType,
    DocumentInfo,
    PageType,
    IDocumentClassifier,
)


class KeywordDocumentClassifier(IDocumentClassifier):
    """基于关键词的文档分类器（三阶段路由）"""

    # === 置信度阈值 ===
    CONFIDENCE_PARTIAL_MATCH = 0.6  # 部分匹配（有买卖双方但无房屋类型）
    CONFIDENCE_STRONG_SIGNAL = 0.9  # 强信号匹配
    CONFIDENCE_COMBINATION = 0.85  # 组合信号匹配
    CONFIDENCE_BACKUP = 0.85  # 备选信号匹配

    # === 阶段1: 标准证件强信号 ===
    # 这些关键词几乎只出现在对应证件上，误判率极低
    # 注意：字典顺序决定优先级，户口本在身份证之前（避免"公民身份号码"误判户口本）
    STANDARD_CERTIFICATE_SIGNALS: Dict[DocumentType, List[str]] = {
        DocumentType.HOUSEHOLD_REGISTER: [
            "常住人口登记卡",  # 户口本个人页独有（优先级最高）
        ],
        DocumentType.DIVORCE_CERTIFICATE: [
            "离婚证字号",  # 离婚证独有
            "离婚证",  # 离婚证标题
        ],
        DocumentType.NOTARY_CERTIFICATE: [
            "公证书",  # 公证书标题
            "公证字第",  # 公证书编号特征
        ],
        DocumentType.POWER_OF_ATTORNEY: [
            "委托书",  # 委托书标题
            "委托人",  # 委托书特征
            "受托人",  # 委托书特征
        ],
        DocumentType.DIVORCE_AGREEMENT: [
            "离婚协议书",  # 离婚协议书标题
        ],
        DocumentType.ID_CARD: [
            "公民身份号码",  # 身份证独有
            "签发机关",  # 身份证反面独有
        ],
        DocumentType.MARRIAGE_CERTIFICATE: [
            "结婚证字号",  # 结婚证独有
        ],
        DocumentType.PROPERTY_CERTIFICATE: [
            "不动产权证书",  # 房产证独有
            "BDCQZ",  # 房产证编号前缀
            "房产分户图",  # 房产证附图页
            "宗地图",  # 房产证附图页
            "所在图幅编号",  # 房产证附图页
            "制图日期",  # 房产证附图页
            "制图者",  # 房产证附图页
            "宗地代码",  # 房产证附图页
        ],
        DocumentType.FUND_SUPERVISION_CERTIFICATE: [
            "存量房交易资金监管凭证",  # 资金监管凭证独有标题
            "资金监管凭证",  # 简写
        ],
    }

    # === 阶段1.5: 标准证件备选强信号（需要组合匹配） ===
    # 当主强信号未命中时，使用备选强信号
    BACKUP_CERTIFICATE_SIGNALS: Dict[DocumentType, Dict[str, Any]] = {
        DocumentType.MARRIAGE_CERTIFICATE: {
            # 持证人 + 登记日期 → 结婚证
            "primary": ["持证人"],
            "required": ["登记日期"],
        },
        DocumentType.HOUSEHOLD_REGISTER: {
            # 户口簿/户口本 + 户主 → 户口本
            "primary": ["户口簿", "户口本", "居民户口簿"],
            "required": ["户主"],
        },
        DocumentType.ID_CARD: {
            # 身份证备选信号：公民身份（不含"号码"）+ 18位身份证号
            "primary": ["公民身份"],
            "required": [],
            "id_pattern": True,  # 需要匹配18位身份证号
        },
    }

    # === 阶段1.6: 更多备选信号 ===
    # 针对特殊页面的备选信号
    ADDITIONAL_BACKUP_SIGNALS: Dict[DocumentType, Dict[str, Any]] = {
        DocumentType.HOUSEHOLD_REGISTER: {
            # 户别 + 户主姓名 + (住址 或 户口专用章) → 户口本首页
            "primary": ["户别", "户 别"],  # 处理OCR空格问题
            "secondary": ["户主姓名"],
            "tertiary": ["住址", "户口专用章", "家庭住址"],
            "min_tertiary": 1,  # 至少需要1个tertiary信号
        },
        DocumentType.MARRIAGE_CERTIFICATE: {
            # 结婚证 + 登记机关 → 结婚证盖章页
            # 支持多种表述：结婚证、结婚申请、结婚登记
            "primary": ["结婚证", "结婚申请", "结婚登记"],
            "secondary": ["登记机关", "婚姻登记专用章", "予以登记", "民政部监制"],
            "min_secondary": 1,
        },
        DocumentType.DIVORCE_CERTIFICATE: {
            # 离婚证 + 印章 → 离婚证盖章页
            # 支持多种表述：离婚证、离婚申请、离婚登记
            "primary": ["离婚证", "离婚申请", "离婚登记"],
            "secondary": ["婚姻登记专用章", "予以登记", "民政部监制", "登记机关"],
            "min_secondary": 1,
        },
        DocumentType.PROPERTY_CERTIFICATE: {
            # 不动产权 + 权利人 + 不动产单元号 → 房产证附记页
            "primary": ["不动产权"],
            "secondary": ["权利人"],
            "tertiary": ["不动产单元号"],
            "min_tertiary": 1,
        },
    }

    # === 阶段2: 标准单证强信号 ===
    STANDARD_DOCUMENT_SIGNALS: Dict[DocumentType, List[str]] = {
        DocumentType.INVOICE: [
            # 发票代码 + 发票号码同时存在 → 高置信度
            "发票代码",
            "发票号码",
        ],
    }

    # 发票的弱信号（需要组合判定）
    INVOICE_WEAK_SIGNALS = [
        "税额",
        "不含税金额",
        "价税合计",
    ]

    # === 阶段3: 合同/协议字段组合 ===
    # 买卖合同的字段组合特征
    CONTRACT_BUYER_KEYWORDS = ["买受人", "买方", "乙方"]
    CONTRACT_SELLER_KEYWORDS = ["出卖人", "卖方", "甲方"]
    CONTRACT_PRICE_KEYWORDS = ["总价款", "价款", "合同金额"]

    # 资金监管协议的字段组合特征
    SUPERVISION_KEYWORDS = ["资金监管", "监管协议"]
    SUPERVISION_AMOUNT_KEYWORDS = ["监管金额", "监管价款"]
    # 资金监管的备选信号
    SUPERVISION_ALTERNATIVE = ["监管凭证", "监管专用章"]
    # 资金监管条款页信号
    SUPERVISION_CLAUSE_SIGNALS = ["监管资金", "丙方免费监管", "暂停支付监管资金"]

    # 离婚协议的字段组合特征
    DIVORCE_KEYWORDS = ["离婚"]
    DIVORCE_PROPERTY_KEYWORDS = ["财产分割", "抚养"]

    # 合同/协议类型到字段组合的映射
    # 注意：顺序决定优先级，存量房在购房合同之前（避免"存量房买卖合同"被误判）
    # 但部分匹配时，购房合同作为默认（更常见）
    CONTRACT_SIGNALS: Dict[DocumentType, Dict[str, List[str]]] = {
        DocumentType.FUND_SUPERVISION: {
            "supervision": SUPERVISION_KEYWORDS,
            "amount": SUPERVISION_AMOUNT_KEYWORDS,
            "property_type": [],
        },
        DocumentType.STOCK_CONTRACT: {
            "buyer": CONTRACT_BUYER_KEYWORDS,
            "seller": CONTRACT_SELLER_KEYWORDS,
            "price": CONTRACT_PRICE_KEYWORDS,
            "property_type": ["存量房"],  # 存量房 → 存量房合同
        },
        DocumentType.PURCHASE_CONTRACT: {
            "buyer": CONTRACT_BUYER_KEYWORDS,
            "seller": CONTRACT_SELLER_KEYWORDS,
            "price": CONTRACT_PRICE_KEYWORDS,
            "property_type": ["商品房"],  # 商品房 → 购房合同
        },
        DocumentType.DIVORCE_AGREEMENT: {
            "divorce": DIVORCE_KEYWORDS,
            "property": DIVORCE_PROPERTY_KEYWORDS,
            "property_type": [],
        },
    }

    def __init__(self, custom_rules: Optional[Dict] = None):
        """
        初始化分类器

        Args:
            custom_rules: 自定义关键词规则（保留兼容性，暂不使用）
        """
        pass

    def _detect_page_type(self, doc_type: DocumentType, full_text: str) -> PageType:
        """
        识别页面类型

        Args:
            doc_type: 文档类型
            full_text: 完整OCR文本

        Returns:
            PageType枚举值
        """
        # 离婚证页面类型识别
        if doc_type in [
            DocumentType.DIVORCE_CERTIFICATE,
            DocumentType.DIVORCE_CERTIFICATE_COVER,
            DocumentType.DIVORCE_CERTIFICATE_CONTENT,
            DocumentType.DIVORCE_CERTIFICATE_STAMP,
        ]:
            return self._detect_divorce_certificate_page_type(full_text)

        # 结婚证页面类型识别
        if doc_type in [
            DocumentType.MARRIAGE_CERTIFICATE,
            DocumentType.MARRIAGE_CERTIFICATE_COVER,
            DocumentType.MARRIAGE_CERTIFICATE_CONTENT,
            DocumentType.MARRIAGE_CERTIFICATE_STAMP,
        ]:
            return self._detect_marriage_certificate_page_type(full_text)

        # 户口本页面类型识别
        if doc_type in [
            DocumentType.HOUSEHOLD_REGISTER,
            DocumentType.HOUSEHOLD_REGISTER_COVER,
            DocumentType.HOUSEHOLD_REGISTER_CONTENT,
        ]:
            return self._detect_household_register_page_type(full_text)

        # 不动产权证书页面类型识别
        if doc_type in [
            DocumentType.PROPERTY_CERTIFICATE,
            DocumentType.PROPERTY_CERTIFICATE_CONTENT,
            DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT,
            DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE,
        ]:
            return self._detect_property_certificate_page_type(full_text)

        # 身份证页面类型识别
        if doc_type in [
            DocumentType.ID_CARD,
            DocumentType.ID_CARD_FRONT,
            DocumentType.ID_CARD_BACK,
        ]:
            return self._detect_id_card_page_type(full_text)

        # 资金监管协议页面类型识别
        if doc_type in [
            DocumentType.FUND_SUPERVISION,
            DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE,
            DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE,
            DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP,
        ]:
            return self._detect_fund_supervision_page_type(full_text)

        # 合同页面类型识别（购房合同/存量房合同）
        if doc_type in [
            DocumentType.PURCHASE_CONTRACT,
            DocumentType.STOCK_CONTRACT,
            DocumentType.PURCHASE_CONTRACT_FIRST_PAGE,
            DocumentType.PURCHASE_CONTRACT_CONTENT,
            DocumentType.PURCHASE_CONTRACT_STAMP,
            DocumentType.STOCK_CONTRACT_FIRST_PAGE,
            DocumentType.STOCK_CONTRACT_CONTENT,
            DocumentType.STOCK_CONTRACT_STAMP,
        ]:
            return self._detect_contract_page_type(full_text)

        # 默认返回内容页（对于合同、协议等）
        return PageType.CONTENT

    def _detect_divorce_certificate_page_type(self, full_text: str) -> PageType:
        """离婚证页面类型识别"""
        # 内容页特征：有离婚证字号 + 登记日期 + 持证人信息
        has_cert_no = "离婚证字号" in full_text
        has_date = "登记日期" in full_text

        if has_cert_no and has_date:
            return PageType.CONTENT
        # 盖章页特征：有印章相关词（优先于封面页检测）
        elif (
            "登记机关" in full_text
            or "婚姻登记专用章" in full_text
            or "予以登记" in full_text
        ):
            return PageType.STAMP
        # 封面页特征：有"离婚证"但无内容页特征
        elif "离婚证" in full_text and not has_cert_no:
            return PageType.COVER
        else:
            return PageType.UNKNOWN

    def _detect_marriage_certificate_page_type(self, full_text: str) -> PageType:
        """结婚证页面类型识别"""
        # 内容页特征：有结婚证字号 + 持证人 + 登记日期
        has_cert_no = "结婚证字号" in full_text
        has_holder = "持证人" in full_text
        has_date = "登记日期" in full_text

        if has_cert_no or (has_holder and has_date):
            return PageType.CONTENT
        # 盖章页特征：有印章相关词（优先于封面页检测）
        elif (
            "登记机关" in full_text
            or "婚姻登记专用章" in full_text
            or "予以登记" in full_text
        ):
            return PageType.STAMP
        # 封面页特征：有"结婚证"但无内容页特征
        elif "结婚证" in full_text and not has_cert_no:
            return PageType.COVER
        else:
            return PageType.UNKNOWN

    def _detect_household_register_page_type(self, full_text: str) -> PageType:
        """户口本页面类型识别"""
        # 首页特征：户别 + 户主姓名 + 住址
        has_hubie = "户别" in full_text or "户 别" in full_text
        has_holder_name = "户主姓名" in full_text

        # 个人页特征：常住人口登记卡
        has_personal_card = "常住人口登记卡" in full_text

        if has_personal_card:
            return PageType.PERSONAL_PAGE
        elif has_hubie or has_holder_name:
            return PageType.FIRST_PAGE
        else:
            return PageType.UNKNOWN

    def _detect_property_certificate_page_type(self, full_text: str) -> PageType:
        """不动产权证书页面类型识别"""
        # 附图页特征：房产分户图、宗地图、所在图幅编号
        attachment_signals = [
            "房产分户图",
            "宗地图",
            "所在图幅编号",
            "制图日期",
            "制图者",
            "宗地代码",
        ]
        if any(signal in full_text for signal in attachment_signals):
            return PageType.ATTACHMENT
        # 内容页特征：有共有情况、不动产单元号、坐落、权利类型等多个字段
        content_signals = [
            "共有情况",
            "不动产单元号",
            "坐落",
            "权利类型",
            "权利性质",
            "使用期限",
        ]
        content_count = sum(1 for signal in content_signals if signal in full_text)
        if content_count >= 3:
            return PageType.CONTENT
        # 首页特征：有登记机构、编号，但没有内容页的字段
        first_page_signals = ["登记机构", "编号"]
        if any(signal in full_text for signal in first_page_signals):
            # 且不包含内容页的明确特征
            if not any(
                signal in full_text
                for signal in ["共有情况", "不动产单元号", "权利类型", "权利性质"]
            ):
                return PageType.FIRST_PAGE
        else:
            return PageType.UNKNOWN
        return PageType.UNKNOWN

    def _detect_id_card_page_type(self, full_text: str) -> PageType:
        """身份证页面类型识别"""
        # 正面特征：有姓名、性别、民族、出生、住址
        has_front_fields = any(
            kw in full_text for kw in ["姓名", "性别", "民族", "出生", "住址"]
        )
        # 背面特征：有签发机关、有效期限
        has_back_fields = any(kw in full_text for kw in ["签发机关", "有效期限"])

        if has_front_fields and "公民身份号码" in full_text:
            return PageType.CONTENT  # 正面
        elif has_back_fields:
            return PageType.BACK  # 背面（用BACK表示）
        else:
            return PageType.UNKNOWN

    def _detect_fund_supervision_page_type(self, full_text: str) -> PageType:
        """资金监管协议页面类型识别"""
        # 首页特征：有"存量房交易资金监管协议"标题 + 编号/甲方/乙方
        has_title = "存量房交易资金监管协议" in full_text
        has_first_page_fields = any(
            kw in full_text for kw in ["编号", "甲方", "乙方", "丙方", "签署日期"]
        )
        # 信息页特征：有甲方/乙方 + 身份证号/银行/账号（但没有协议标题）
        has_party_info = any(kw in full_text for kw in ["身份证号", "银行", "账号"])
        # 签章页特征：有"签章"/"签字"/"盖章" + 有甲乙丙方签章标记
        has_stamp_signals = any(
            kw in full_text
            for kw in [
                "甲方（签章）",
                "乙方（签章）",
                "丙方（签章）",
                "甲方签章",
                "乙方签章",
                "丙方签章",
            ]
        )
        has_sign_signals = any(kw in full_text for kw in ["签字", "盖章"])

        # 签章页优先检测（签章标记是强信号）
        if has_stamp_signals or (has_sign_signals and not has_first_page_fields):
            return PageType.STAMP
        elif has_title and has_first_page_fields:
            return PageType.FIRST_PAGE
        elif has_party_info:
            return PageType.PERSONAL_PAGE  # 复用个人页表示信息页
        elif has_title:
            # 有标题但没有首页字段，可能是信息页
            return PageType.PERSONAL_PAGE
        else:
            return PageType.UNKNOWN

    def _detect_contract_page_type(self, full_text: str) -> PageType:
        """合同页面类型识别（购房合同/存量房合同）"""
        # 强信号：签署页独有特征（内容页/首页一般没有）
        has_strong_stamp = any(
            kw in full_text for kw in ["合同签订日期", "合同签订地址"]
        )
        # 弱信号：通用词（内容页/首页也可能有"签字盖章"条款，不可单独判定 STAMP）
        has_weak_stamp = any(
            kw in full_text for kw in ["签字", "盖章", "签章"]
        )
        # 注意：监管协议的签章页也有这些特征，需要排除
        is_fund_supervision = any(
            kw in full_text
            for kw in ["资金监管", "监管协议", "监管凭证", "监管资金"]
        )

        # 首页特征：买卖合同、合同编号 + 卖方/买方/房屋坐落
        has_contract_title = any(
            kw in full_text for kw in ["买卖合同", "存量房买卖合同"]
        )
        has_first_page_fields = any(
            kw in full_text for kw in ["卖方", "买方", "房屋坐落"]
        )

        # 内容页特征：房屋基本情况、付款方式、装修价款
        has_content_fields = any(
            kw in full_text for kw in ["房屋基本情况", "付款方式", "装修价款"]
        )

        # STAMP 判定：需签署信号且无内容页/首页强特征（避免误伤内容页/首页致数据丢失）
        # 宁可漏判 STAMP（签署页走提取，不丢数据），不可误判内容页（数据丢失）
        has_stamp_signals = (has_strong_stamp or has_weak_stamp) and not is_fund_supervision
        if has_stamp_signals and not (has_content_fields or (has_contract_title and has_first_page_fields)):
            return PageType.STAMP
        elif has_contract_title and has_first_page_fields:
            return PageType.FIRST_PAGE
        elif has_content_fields:
            return PageType.CONTENT
        else:
            return PageType.UNKNOWN

    def _get_refined_doc_type(
        self, doc_type: DocumentType, page_type: PageType
    ) -> DocumentType:
        """
        根据页面类型细化文档类型

        Args:
            doc_type: 原始文档类型
            page_type: 页面类型

        Returns:
            细化后的文档类型
        """
        # 离婚证细化
        if doc_type == DocumentType.DIVORCE_CERTIFICATE:
            if page_type == PageType.COVER:
                return DocumentType.DIVORCE_CERTIFICATE_COVER
            elif page_type == PageType.CONTENT:
                return DocumentType.DIVORCE_CERTIFICATE_CONTENT
            elif page_type == PageType.STAMP:
                return DocumentType.DIVORCE_CERTIFICATE_STAMP

        # 结婚证细化
        elif doc_type == DocumentType.MARRIAGE_CERTIFICATE:
            if page_type == PageType.COVER:
                return DocumentType.MARRIAGE_CERTIFICATE_COVER
            elif page_type == PageType.CONTENT:
                return DocumentType.MARRIAGE_CERTIFICATE_CONTENT
            elif page_type == PageType.STAMP:
                return DocumentType.MARRIAGE_CERTIFICATE_STAMP

        # 户口本细化
        elif doc_type == DocumentType.HOUSEHOLD_REGISTER:
            if page_type == PageType.FIRST_PAGE:
                return DocumentType.HOUSEHOLD_REGISTER_COVER
            elif page_type == PageType.PERSONAL_PAGE:
                return DocumentType.HOUSEHOLD_REGISTER_CONTENT

        # 不动产权证书细化
        elif doc_type == DocumentType.PROPERTY_CERTIFICATE:
            if page_type == PageType.FIRST_PAGE:
                return DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE
            elif page_type == PageType.ATTACHMENT:
                return DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT
            elif page_type == PageType.CONTENT:
                return DocumentType.PROPERTY_CERTIFICATE_CONTENT

        # 身份证细化
        elif doc_type == DocumentType.ID_CARD:
            if page_type == PageType.CONTENT:
                return DocumentType.ID_CARD_FRONT
            elif page_type == PageType.BACK:
                return DocumentType.ID_CARD_BACK

        # 资金监管协议细化
        elif doc_type == DocumentType.FUND_SUPERVISION:
            if page_type == PageType.FIRST_PAGE:
                return DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE
            elif page_type == PageType.PERSONAL_PAGE:
                return DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE
            elif page_type == PageType.STAMP:
                return DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP

        # 购房合同细化
        elif doc_type == DocumentType.PURCHASE_CONTRACT:
            if page_type == PageType.FIRST_PAGE:
                return DocumentType.PURCHASE_CONTRACT_FIRST_PAGE
            elif page_type == PageType.CONTENT:
                return DocumentType.PURCHASE_CONTRACT_CONTENT
            elif page_type == PageType.STAMP:
                return DocumentType.PURCHASE_CONTRACT_STAMP

        # 存量房合同细化
        elif doc_type == DocumentType.STOCK_CONTRACT:
            if page_type == PageType.FIRST_PAGE:
                return DocumentType.STOCK_CONTRACT_FIRST_PAGE
            elif page_type == PageType.CONTENT:
                return DocumentType.STOCK_CONTRACT_CONTENT
            elif page_type == PageType.STAMP:
                return DocumentType.STOCK_CONTRACT_STAMP

        return doc_type

    def classify(self, image_path: str, ocr_texts: List[str]) -> DocumentInfo:
        """
        根据OCR文本分类文档（三阶段路由 + 页面类型识别）

        Args:
            image_path: 图片路径
            ocr_texts: OCR识别文本列表

        Returns:
            DocumentInfo对象（包含doc_type和page_type）
        """
        # 先进行基础分类
        doc_info = self._classify_base(image_path, ocr_texts)

        # 然后识别页面类型并细化文档类型
        # 去除空格以修复破碎OCR文本的关键词匹配问题（如"结 婚" → "结婚"）
        full_text = "".join(ocr_texts).replace(" ", "")
        page_type = self._detect_page_type(doc_info.doc_type, full_text)
        refined_doc_type = self._get_refined_doc_type(doc_info.doc_type, page_type)

        # 更新文档信息
        doc_info.page_type = page_type
        doc_info.doc_type = refined_doc_type

        return doc_info

    def _classify_base(self, image_path: str, ocr_texts: List[str]) -> DocumentInfo:
        """
        基础分类方法（不含页面类型识别）

        这是原始的分类逻辑，返回基础的文档类型。
        拆分为多个阶段方法以降低复杂度。
        """
        # 去除空格以修复破碎OCR文本的关键词匹配问题（如"结 婚" → "结婚"）
        full_text = "".join(ocr_texts).replace(" ", "")

        # 阶段0: 多文档冲突检测
        result = self._check_multi_doc_conflict(image_path, full_text, ocr_texts)
        if result:
            return result

        # 阶段1: 标准证件强信号
        result = self._check_standard_certificates(image_path, full_text, ocr_texts)
        if result:
            return result

        # 阶段1.5+1.6: 备选信号（数据驱动方式）
        result = self._check_backup_signals(image_path, full_text, ocr_texts)
        if result:
            return result

        # 阶段2: 标准单证强信号
        result = self._check_standard_documents(image_path, full_text, ocr_texts)
        if result:
            return result

        # 阶段3: 合同/协议字段组合
        result = self._check_contracts(image_path, full_text, ocr_texts)
        if result:
            return result

        # 阶段4: VLM兜底
        return DocumentInfo(
            image_path=image_path,
            doc_type=DocumentType.UNKNOWN,
            ocr_texts=ocr_texts,
            confidence=0.0,
            metadata={"route": "vlm_fallback_required"},
        )

    # === 通用辅助方法（数据驱动分类基础设施） ===

    def _keywords_match(self, text: str, keywords: List[str], match_type: str = "any") -> Tuple[bool, int]:
        """
        通用关键词匹配辅助方法

        Args:
            text: 待匹配文本
            keywords: 关键词列表
            match_type: 匹配类型
                - "any": 任一关键词匹配即返回True
                - "all": 所有关键词都匹配才返回True
                - "count": 返回匹配的数量

        Returns:
            (是否匹配, 匹配数量)
        """
        if not keywords:
            if match_type == "all":
                return True, 0
            return False, 0

        count = sum(1 for kw in keywords if kw in text)
        if match_type == "any":
            return count > 0, count
        elif match_type == "all":
            return count == len(keywords), count
        else:  # count
            return True, count

    def _run_stage(
        self,
        image_path: str,
        full_text: str,
        ocr_texts: List[str],
        stage_config: List[Tuple],
    ) -> Optional[DocumentInfo]:
        """
        通用阶段执行器（数据驱动）

        将重复的"遍历配置→匹配关键词→构建DocumentInfo"模式提取为通用方法。

        Args:
            image_path: 图片路径
            full_text: 完整文本
            ocr_texts: OCR文本列表
            stage_config: 阶段配置列表，每项为元组:
                (doc_type, match_func, confidence, metadata)
                - match_func(full_text) -> Optional[DocumentInfo] 或 bool
                  如果返回 DocumentInfo，直接作为结果
                  如果返回 True，使用提供的 confidence 和 metadata 构建结果
                  如果返回 False/None，跳过该项

        Returns:
            匹配结果或 None
        """
        for entry in stage_config:
            doc_type, match_func, confidence, metadata = entry
            result = match_func(full_text)
            if isinstance(result, DocumentInfo):
                return result
            if result:
                return DocumentInfo(
                    image_path=image_path,
                    doc_type=doc_type,
                    ocr_texts=ocr_texts,
                    confidence=confidence,
                    metadata=metadata,
                )
        return None

    def _check_multi_doc_conflict(
        self, image_path: str, full_text: str, ocr_texts: List[str]
    ) -> Optional[DocumentInfo]:
        """
        阶段0: 多文档冲突检测（数据驱动）

        当合同级强信号（买受人+出卖人+房屋类型）同时存在时，优先分类为合同
        防止多文档混合扫描时，合同页面中的身份证号码误触发身份证分类
        """
        def match(text):
            has_buyer = "买受人" in text
            has_seller = "出卖人" in text
            has_property_type = any(kw in text for kw in ["商品房", "存量房"])
            if not (has_buyer and has_seller and has_property_type):
                return False
            contract_type = (
                DocumentType.PURCHASE_CONTRACT if "商品房" in text
                else DocumentType.STOCK_CONTRACT
            )
            return DocumentInfo(
                image_path=image_path,
                doc_type=contract_type,
                page_type=PageType.CONTENT,
                ocr_texts=ocr_texts,
                confidence=0.90,
                metadata={
                    "route": "multi_doc_conflict_resolution",
                    "signal": "buyer+seller+property_type",
                },
            )

        return self._run_stage(image_path, full_text, ocr_texts, [
            (None, match, 0, None),
        ])

    def _check_standard_certificates(
        self, image_path: str, full_text: str, ocr_texts: List[str]
    ) -> Optional[DocumentInfo]:
        """
        阶段1: 标准证件强信号（数据驱动）
        """
        stage_config = []

        for doc_type, signals in self.STANDARD_CERTIFICATE_SIGNALS.items():
            if doc_type == DocumentType.FUND_SUPERVISION_CERTIFICATE:
                # 资金监管凭证：特殊匹配逻辑（区分凭证 vs 协议信息页）
                def make_fund_cert_matcher(dt, sig):
                    def match(text):
                        if sig not in text:
                            return False
                        cert_field_kws = [
                            "协议编号", "买房人", "卖房人",
                            "监管总额", "建筑面积", "房屋坐落",
                        ]
                        agreement_party_kws = ["甲方", "乙方", "丙方"]
                        agreement_account_kws = ["银行", "账号"]
                        has_cert_fields = any(kw in text for kw in cert_field_kws)
                        has_agreement_info = (
                            any(kw in text for kw in agreement_party_kws)
                            and any(kw in text for kw in agreement_account_kws)
                        )
                        if has_cert_fields and not has_agreement_info:
                            return DocumentInfo(
                                image_path=image_path, doc_type=dt,
                                ocr_texts=ocr_texts, confidence=0.95,
                                metadata={"route": "standard_certificate", "signal": sig},
                            )
                        else:
                            return DocumentInfo(
                                image_path=image_path,
                                doc_type=DocumentType.FUND_SUPERVISION,
                                ocr_texts=ocr_texts, confidence=0.90,
                                metadata={
                                    "route": "fund_supervision_info_page",
                                    "reason": "mentioned_cert_but_has_agreement_info",
                                },
                            )
                    return match
                stage_config.append((doc_type, make_fund_cert_matcher(doc_type, signals[0]), 0, None))
            else:
                # 其他证件类型：任一信号匹配即可
                def make_cert_matcher(dt, sigs):
                    def match(text):
                        matched, _ = self._keywords_match(text, sigs)
                        if not matched:
                            return False
                        first_match = next(s for s in sigs if s in text)
                        return DocumentInfo(
                            image_path=image_path, doc_type=dt,
                            ocr_texts=ocr_texts, confidence=0.95,
                            metadata={"route": "standard_certificate", "signal": first_match},
                        )
                    return match
                stage_config.append((doc_type, make_cert_matcher(doc_type, signals), 0, None))

        return self._run_stage(image_path, full_text, ocr_texts, stage_config)

    def _check_backup_signals(
        self, image_path: str, full_text: str, ocr_texts: List[str]
    ) -> Optional[DocumentInfo]:
        """
        阶段1.5+1.6: 备选信号统一检查（数据驱动）

        合并原 _check_backup_certificates（阶段1.5）和 _check_additional_backup（阶段1.6），
        使用统一的配置表 + 通用匹配逻辑，消除重复代码。
        """
        # 统一备选信号配置表（顺序决定优先级）
        BACKUP_SIGNALS_CONFIG = [
            # 阶段1.5: 标准证件备选强信号
            (DocumentType.MARRIAGE_CERTIFICATE, {
                "primary": ["持证人"], "required": ["登记日期"],
                "route": "backup_certificate", "confidence": 0.90,
            }),
            (DocumentType.HOUSEHOLD_REGISTER, {
                "primary": ["户口簿", "户口本", "居民户口簿"], "required": ["户主"],
                "route": "backup_certificate", "confidence": 0.90,
            }),
            (DocumentType.ID_CARD, {
                "primary": ["公民身份"], "required": [],
                "id_pattern": True,
                "route": "backup_certificate", "confidence": 0.90,
            }),
            # 阶段1.6: 更多备选信号（针对特殊页面）
            (DocumentType.HOUSEHOLD_REGISTER, {
                "primary": ["户别", "户 别"],
                "secondary": ["户主姓名"], "min_secondary": 1,
                "tertiary": ["住址", "户口专用章", "家庭住址"], "min_tertiary": 1,
                "route": "additional_backup", "confidence": 0.85,
            }),
            # 户口本个人页字段组合兜底：
            # OCR 把"常住人口登记卡"识别成乱码（如"居民家党庄人口登记卡"）导致标题信号失效时，
            # 靠个人页独有字段组合识别（承办人签章/籍贯 + 多个登记项字段，min_secondary=3 保严格）。
            (DocumentType.HOUSEHOLD_REGISTER, {
                "primary": ["承办人签章", "籍贯"],
                "secondary": ["婚姻状况", "兵役状况", "服务处所", "户主或与",
                              "户主关系", "迁来本", "其他住址", "何时由何地",
                              "宗教信仰", "文化程度"],
                "min_secondary": 3,
                "route": "household_personal_page_combination", "confidence": 0.85,
            }),
            (DocumentType.MARRIAGE_CERTIFICATE, {
                "primary": ["结婚证", "结婚申请", "结婚登记"],
                "secondary": ["登记机关", "婚姻登记专用章", "予以登记", "民政部监制"],
                "min_secondary": 1,
                "route": "additional_backup", "confidence": 0.85,
            }),
            # 结婚登记申请表字段组合兜底：
            # OCR 把结婚证标题识别成乱码（如"员民2记机品一"）导致标题信号失效时，
            # 靠申请表"双人+国籍"特征识别（国籍 + 多个申请人信息字段，min_secondary=4 保严格）。
            (DocumentType.MARRIAGE_CERTIFICATE, {
                "primary": ["国籍"],
                "secondary": ["身份证件号", "出生日", "姓名", "性别", "男", "女"],
                "min_secondary": 4,
                "route": "marriage_application_combination", "confidence": 0.85,
            }),
            (DocumentType.DIVORCE_CERTIFICATE, {
                "primary": ["离婚证", "离婚申请", "离婚登记"],
                "secondary": ["婚姻登记专用章", "予以登记", "民政部监制", "登记机关"],
                "min_secondary": 1,
                "route": "additional_backup", "confidence": 0.85,
            }),
            (DocumentType.PROPERTY_CERTIFICATE, {
                "primary": ["不动产权"],
                "secondary": ["权利人"],
                "tertiary": ["不动产单元号"], "min_tertiary": 1,
                "route": "additional_backup", "confidence": 0.85,
            }),
            # 不动产权证书内容页字段组合兜底：
            # 当 OCR 把标题"不动产权证书"识别成乱码（如"明念老念费"）导致
            # "不动产权"关键词完全缺失时，靠内容页特有字段组合识别。
            # primary="权利人"（房产证独有，购房合同用"买方/卖方"），
            # secondary 命中≥4 即判定为不动产权证书，后续走页面识别细化为内容页。
            (DocumentType.PROPERTY_CERTIFICATE, {
                "primary": ["权利人"],
                "secondary": ["共有情况", "不动产单元号", "权利类型",
                              "权利性质", "使用期限", "坐落"],
                "min_secondary": 4,
                "route": "property_content_field_combination", "confidence": 0.85,
            }),
            # 身份证字段组合兜底：OCR 文本没有"公民身份"但含"身份"+18位身份证号+多个身份证字段
            # 比备选信号1（primary=公民身份）更宽松，能命中部分 OCR 识别不完整的情况
            (DocumentType.ID_CARD, {
                "primary": ["身份"],
                "secondary": ["姓名", "性别", "民族", "出生", "住址"],
                "min_secondary": 3,
                "id_pattern": True,
                "route": "id_card_field_combination", "confidence": 0.85,
            }),
            # 户口本字段组合兜底：OCR 文本没有"户别/户口本/常住人口登记卡"但有"户主"+多个户口本字段
            # 比备选信号2（primary=户别）更宽松，能命中部分 OCR 识别不完整的情况
            (DocumentType.HOUSEHOLD_REGISTER, {
                "primary": ["户主"],
                "secondary": ["籍贯", "婚姻状况", "民族", "出生日期", "承办人签章"],
                "min_secondary": 3,
                "route": "household_register_field_combination", "confidence": 0.85,
            }),
        ]

        def make_matcher(config):
            primary = config["primary"]
            required = config.get("required", [])
            secondary = config.get("secondary", [])
            tertiary = config.get("tertiary", [])
            min_secondary = config.get("min_secondary", 0)
            min_tertiary = config.get("min_tertiary", 0)
            id_pattern = config.get("id_pattern", False)

            def match(text):
                # 1. 主信号（任一匹配）
                has_primary, _ = self._keywords_match(text, primary)
                if not has_primary:
                    return False
                # 2. 必需信号（全部匹配）
                if required:
                    has_req, _ = self._keywords_match(text, required, "all")
                    if not has_req:
                        return False
                # 3. 身份证号模式（身份证专用）
                if id_pattern and not re.search(r"\d{17}[\dXx]", text):
                    return False
                # 4. 次要信号计数
                if secondary:
                    _, sec_count = self._keywords_match(text, secondary, "count")
                    if sec_count < min_secondary:
                        return False
                # 5. 三级信号计数
                if tertiary:
                    _, tert_count = self._keywords_match(text, tertiary, "count")
                    if tert_count < min_tertiary:
                        return False
                return True

            return match

        stage_config = []
        for doc_type, config in BACKUP_SIGNALS_CONFIG:
            metadata = {
                "route": config["route"],
                "primary": [kw for kw in config["primary"] if kw in full_text],
            }
            if "required" in config:
                metadata["required"] = [kw for kw in config["required"] if kw in full_text]
            stage_config.append((
                doc_type,
                make_matcher(config),
                config["confidence"],
                metadata,
            ))

        return self._run_stage(image_path, full_text, ocr_texts, stage_config)

    def _check_standard_documents(
        self, image_path: str, full_text: str, ocr_texts: List[str]
    ) -> Optional[DocumentInfo]:
        """
        阶段2: 标准单证强信号（数据驱动）
        """
        invoice_signals = self.STANDARD_DOCUMENT_SIGNALS[DocumentType.INVOICE]

        def match_invoice(text):
            if all(s in text for s in invoice_signals):
                return DocumentInfo(
                    image_path=image_path, doc_type=DocumentType.INVOICE,
                    ocr_texts=ocr_texts, confidence=0.95,
                    metadata={"route": "standard_document", "signal": "invoice_code+number"},
                )
            return False

        def match_invoice_weak(text):
            _, weak_count = self._keywords_match(text, self.INVOICE_WEAK_SIGNALS, "count")
            if weak_count >= 2:
                return DocumentInfo(
                    image_path=image_path, doc_type=DocumentType.INVOICE,
                    ocr_texts=ocr_texts, confidence=0.7,
                    metadata={"route": "standard_document_weak", "weak_signals": weak_count},
                )
            return False

        return self._run_stage(image_path, full_text, ocr_texts, [
            (DocumentType.INVOICE, match_invoice, 0, None),
            (DocumentType.INVOICE, match_invoice_weak, 0, None),
        ])

    def _check_contracts(
        self, image_path: str, full_text: str, ocr_texts: List[str]
    ) -> Optional[DocumentInfo]:
        """
        阶段3: 合同/协议字段组合（数据驱动）
        """
        stage_config = []

        for doc_type, signal_config in self.CONTRACT_SIGNALS.items():
            property_type_keywords = signal_config.get("property_type", [])

            if doc_type in (DocumentType.PURCHASE_CONTRACT, DocumentType.STOCK_CONTRACT):
                def make_contract_matcher(dt, cfg, ptk):
                    def match(text):
                        has_buyer, _ = self._keywords_match(text, cfg["buyer"])
                        has_seller, _ = self._keywords_match(text, cfg["seller"])
                        if not has_buyer or not has_seller:
                            return False
                        has_pt, _ = self._keywords_match(text, ptk) if ptk else (False, 0)

                        if dt == DocumentType.PURCHASE_CONTRACT:
                            if ptk and not has_pt:
                                return DocumentInfo(
                                    image_path=image_path,
                                    doc_type=DocumentType.PURCHASE_CONTRACT,
                                    ocr_texts=ocr_texts,
                                    confidence=self.CONFIDENCE_PARTIAL_MATCH,
                                    metadata={
                                        "route": "contract_partial_match",
                                        "has_property_type": False,
                                        "signal": "buyer+seller_fallback",
                                    },
                                )
                            return DocumentInfo(
                                image_path=image_path, doc_type=dt,
                                ocr_texts=ocr_texts,
                                confidence=self.CONFIDENCE_STRONG_SIGNAL,
                                metadata={
                                    "route": "contract_field_combination",
                                    "has_property_type": bool(ptk),
                                },
                            )
                        else:  # STOCK_CONTRACT
                            if ptk and not has_pt:
                                return False
                            return DocumentInfo(
                                image_path=image_path, doc_type=dt,
                                ocr_texts=ocr_texts,
                                confidence=self.CONFIDENCE_COMBINATION,
                                metadata={
                                    "route": "contract_field_combination",
                                    "has_property_type": bool(ptk),
                                },
                            )
                    return match
                stage_config.append((
                    doc_type,
                    make_contract_matcher(doc_type, signal_config, property_type_keywords),
                    0, None,
                ))

            elif doc_type == DocumentType.FUND_SUPERVISION:
                def make_supervision_matcher(cfg):
                    def match(text):
                        has_监管, _ = self._keywords_match(text, ["资金监管"])
                        has_协议, _ = self._keywords_match(text, ["监管协议"])
                        has_amount, _ = self._keywords_match(text, cfg["amount"])
                        has_alt, _ = self._keywords_match(text, self.SUPERVISION_ALTERNATIVE)
                        has_clause, _ = self._keywords_match(text, self.SUPERVISION_CLAUSE_SIGNALS)
                        has_丙方 = "丙方" in text
                        has_签章 = "签章" in text
                        has_签约日期 = "签约日期" in text
                        has_第x页 = any(f"第{i}页" in text for i in range(1, 10))
                        is_stamp = has_丙方 and has_签章 and (has_签约日期 or has_第x页)
                        # 5个条件任一满足即可
                        if (has_监管 and has_协议) or has_alt \
                                or (has_监管 and has_amount) \
                                or (has_clause and (has_监管 or has_协议 or "协议" in text)) \
                                or is_stamp:
                            return True
                        return False
                    return match
                stage_config.append((
                    doc_type, make_supervision_matcher(signal_config),
                    self.CONFIDENCE_COMBINATION,
                    {"route": "contract_field_combination", "has_property_type": False},
                ))

            elif doc_type == DocumentType.DIVORCE_AGREEMENT:
                def make_divorce_matcher(cfg):
                    def match(text):
                        has_div, _ = self._keywords_match(text, cfg["divorce"])
                        has_prop, _ = self._keywords_match(text, cfg["property"])
                        return has_div and has_prop
                    return match
                stage_config.append((
                    doc_type, make_divorce_matcher(signal_config),
                    self.CONFIDENCE_COMBINATION,
                    {"route": "contract_field_combination", "has_property_type": False},
                ))

        return self._run_stage(image_path, full_text, ocr_texts, stage_config)

    def classify_from_text(self, image_path: str, text: str) -> DocumentInfo:
        """
        直接从文本分类（便捷方法）

        Args:
            image_path: 图片路径
            text: OCR合并文本

        Returns:
            DocumentInfo对象
        """
        return self.classify(image_path, [text])
