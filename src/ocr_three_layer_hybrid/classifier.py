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

from typing import Any, Dict, List, Optional, Tuple
from ocr_three_layer_hybrid.interfaces import (
    DocumentType,
    DocumentInfo,
    PageType,
    IDocumentClassifier,
)


class KeywordDocumentClassifier(IDocumentClassifier):
    """基于关键词的文档分类器（三阶段路由）"""

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
        # === 离婚证页面类型识别 ===
        if doc_type in [
            DocumentType.DIVORCE_CERTIFICATE,
            DocumentType.DIVORCE_CERTIFICATE_COVER,
            DocumentType.DIVORCE_CERTIFICATE_CONTENT,
            DocumentType.DIVORCE_CERTIFICATE_STAMP,
        ]:
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

        # === 结婚证页面类型识别 ===
        if doc_type in [
            DocumentType.MARRIAGE_CERTIFICATE,
            DocumentType.MARRIAGE_CERTIFICATE_COVER,
            DocumentType.MARRIAGE_CERTIFICATE_CONTENT,
            DocumentType.MARRIAGE_CERTIFICATE_STAMP,
        ]:
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

        # === 户口本页面类型识别 ===
        if doc_type in [
            DocumentType.HOUSEHOLD_REGISTER,
            DocumentType.HOUSEHOLD_REGISTER_COVER,
            DocumentType.HOUSEHOLD_REGISTER_CONTENT,
        ]:
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

        # === 不动产权证书页面类型识别 ===
        if doc_type in [
            DocumentType.PROPERTY_CERTIFICATE,
            DocumentType.PROPERTY_CERTIFICATE_CONTENT,
            DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT,
            DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE,
        ]:
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

        # === 身份证页面类型识别 ===
        if doc_type in [
            DocumentType.ID_CARD,
            DocumentType.ID_CARD_FRONT,
            DocumentType.ID_CARD_BACK,
        ]:
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

        # === 资金监管协议页面类型识别 ===
        if doc_type in [
            DocumentType.FUND_SUPERVISION,
            DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE,
            DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE,
            DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP,
        ]:
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

        # === 合同页面类型识别（购房合同/存量房合同）===
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
            # 签署页特征：合同签订日期、合同签订地址、签字/盖章
            has_stamp_signals = any(
                kw in full_text
                for kw in ["合同签订日期", "合同签订地址", "签字", "盖章", "签章"]
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

            # 签署页优先（但要排除监管协议）
            if has_stamp_signals and not is_fund_supervision:
                return PageType.STAMP
            elif has_contract_title and has_first_page_fields:
                return PageType.FIRST_PAGE
            elif has_content_fields:
                return PageType.CONTENT
            else:
                return PageType.UNKNOWN

        # 默认返回内容页（对于合同、协议等）
        return PageType.CONTENT

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
        """
        # 去除空格以修复破碎OCR文本的关键词匹配问题（如"结 婚" → "结婚"）
        full_text = "".join(ocr_texts).replace(" ", "")

        # === 阶段0: 多文档冲突检测 ===
        # 当合同级强信号（买受人+出卖人+房屋类型）同时存在时，优先分类为合同
        # 防止多文档混合扫描时，合同页面中的身份证号码误触发身份证分类
        # 注意：仅用"买受人/出卖人"，不用"甲方/乙方"（后者在资金监管协议中也出现）
        has_buyer = "买受人" in full_text
        has_seller = "出卖人" in full_text
        has_property_type = any(kw in full_text for kw in ["商品房", "存量房"])
        if has_buyer and has_seller and has_property_type:
            if "商品房" in full_text:
                contract_type = DocumentType.PURCHASE_CONTRACT
            else:
                contract_type = DocumentType.STOCK_CONTRACT
            return DocumentInfo(
                image_path=image_path,
                doc_type=contract_type,
                page_type=PageType.CONTENT,  # 合同页默认为内容页
                ocr_texts=ocr_texts,
                confidence=0.90,
                metadata={
                    "route": "multi_doc_conflict_resolution",
                    "signal": "buyer+seller+property_type",
                },
            )

        # === 阶段1: 标准证件强信号 ===
        for doc_type, signals in self.STANDARD_CERTIFICATE_SIGNALS.items():
            for signal in signals:
                if signal in full_text:
                    # 特殊处理：资金监管凭证需要额外检查
                    if doc_type == DocumentType.FUND_SUPERVISION_CERTIFICATE:
                        # 检查是否真的是凭证（有实际字段）
                        has_cert_fields = any(
                            kw in full_text
                            for kw in [
                                "协议编号",
                                "买房人",
                                "卖房人",
                                "监管总额",
                                "建筑面积",
                                "房屋坐落",
                            ]
                        )
                        # 检查是否是协议信息页（有甲乙丙方+银行账号）
                        has_agreement_info = any(
                            kw in full_text for kw in ["甲方", "乙方", "丙方"]
                        ) and any(kw in full_text for kw in ["银行", "账号"])

                        # 如果有凭证字段且不是协议信息页，才是真正的凭证
                        if has_cert_fields and not has_agreement_info:
                            return DocumentInfo(
                                image_path=image_path,
                                doc_type=doc_type,
                                ocr_texts=ocr_texts,
                                confidence=0.95,
                                metadata={
                                    "route": "standard_certificate",
                                    "signal": signal,
                                },
                            )
                        else:
                            # 否则分类为资金监管协议（信息页）
                            return DocumentInfo(
                                image_path=image_path,
                                doc_type=DocumentType.FUND_SUPERVISION,
                                ocr_texts=ocr_texts,
                                confidence=0.90,
                                metadata={
                                    "route": "fund_supervision_info_page",
                                    "reason": "mentioned_cert_but_has_agreement_info",
                                },
                            )
                    else:
                        # 其他证件类型直接返回
                        return DocumentInfo(
                            image_path=image_path,
                            doc_type=doc_type,
                            ocr_texts=ocr_texts,
                            confidence=0.95,
                            metadata={
                                "route": "standard_certificate",
                                "signal": signal,
                            },
                        )

        # === 阶段1.5: 标准证件备选强信号 ===
        for doc_type, signal_config in self.BACKUP_CERTIFICATE_SIGNALS.items():
            primary_signals = signal_config["primary"]
            required_signals = signal_config.get("required", [])
            secondary_signals = signal_config.get("secondary", [])
            tertiary_signals = signal_config.get("tertiary", [])
            min_secondary = signal_config.get("min_secondary", 0)
            min_tertiary = signal_config.get("min_tertiary", 0)
            id_pattern_required = signal_config.get("id_pattern", False)

            # 检查主信号（任一匹配）
            has_primary = any(kw in full_text for kw in primary_signals)
            if not has_primary:
                continue

            # 检查必需信号（全部匹配）
            has_required = all(kw in full_text for kw in required_signals)
            if not has_required:
                continue

            # 检查是否需要18位身份证号模式（身份证专用）
            if id_pattern_required:
                import re

                if not re.search(r"\d{17}[\dXx]", full_text):
                    continue

            # 检查次要信号（如果有定义）
            if secondary_signals:
                secondary_count = sum(1 for kw in secondary_signals if kw in full_text)
                if secondary_count < min_secondary:
                    continue

            # 检查三级信号（如果有定义）
            if tertiary_signals:
                tertiary_count = sum(1 for kw in tertiary_signals if kw in full_text)
                if tertiary_count < min_tertiary:
                    continue

            return DocumentInfo(
                image_path=image_path,
                doc_type=doc_type,
                ocr_texts=ocr_texts,
                confidence=0.90,  # 备选强信号，置信度略低
                metadata={
                    "route": "backup_certificate",
                    "primary": [kw for kw in primary_signals if kw in full_text],
                    "required": [kw for kw in required_signals if kw in full_text],
                },
            )

        # === 阶段1.6: 更多备选信号（针对特殊页面） ===
        for doc_type, signal_config in self.ADDITIONAL_BACKUP_SIGNALS.items():
            primary_signals = signal_config["primary"]
            secondary_signals = signal_config.get("secondary", [])
            tertiary_signals = signal_config.get("tertiary", [])
            min_tertiary = signal_config.get("min_tertiary", 1)
            min_secondary = signal_config.get("min_secondary", 1)

            # 检查primary信号（任一匹配）
            has_primary = any(kw in full_text for kw in primary_signals)
            if not has_primary:
                continue

            # 检查secondary信号
            secondary_count = sum(1 for kw in secondary_signals if kw in full_text)
            if secondary_count < min_secondary:
                continue

            # 检查tertiary信号（如果有定义）
            if tertiary_signals:
                tertiary_count = sum(1 for kw in tertiary_signals if kw in full_text)
                if tertiary_count < min_tertiary:
                    continue

            return DocumentInfo(
                image_path=image_path,
                doc_type=doc_type,
                ocr_texts=ocr_texts,
                confidence=0.85,  # 更多备选信号，置信度再略低
                metadata={
                    "route": "additional_backup",
                    "primary": [kw for kw in primary_signals if kw in full_text],
                },
            )

        # === 阶段2: 标准单证强信号 ===
        # 发票：发票代码 + 发票号码同时存在
        invoice_signals = self.STANDARD_DOCUMENT_SIGNALS[DocumentType.INVOICE]
        if all(signal in full_text for signal in invoice_signals):
            return DocumentInfo(
                image_path=image_path,
                doc_type=DocumentType.INVOICE,
                ocr_texts=ocr_texts,
                confidence=0.95,
                metadata={
                    "route": "standard_document",
                    "signal": "invoice_code+number",
                },
            )

        # 发票弱信号：税额 + 不含税金额
        if any(signal in full_text for signal in self.INVOICE_WEAK_SIGNALS):
            weak_signal_count = sum(
                1 for s in self.INVOICE_WEAK_SIGNALS if s in full_text
            )
            if weak_signal_count >= 2:
                return DocumentInfo(
                    image_path=image_path,
                    doc_type=DocumentType.INVOICE,
                    ocr_texts=ocr_texts,
                    confidence=0.7,
                    metadata={
                        "route": "standard_document_weak",
                        "weak_signals": weak_signal_count,
                    },
                )

        # === 阶段3: 合同/协议字段组合 ===
        for doc_type, signal_config in self.CONTRACT_SIGNALS.items():
            property_type_keywords = signal_config.get("property_type", [])

            # 根据文档类型检查不同的字段组合
            if doc_type in (
                DocumentType.PURCHASE_CONTRACT,
                DocumentType.STOCK_CONTRACT,
            ):
                # 买卖合同：买受人 + 出卖人 + (价款 或 房屋类型关键词)
                has_buyer = any(kw in full_text for kw in signal_config["buyer"])
                has_seller = any(kw in full_text for kw in signal_config["seller"])
                has_property_type = (
                    any(kw in full_text for kw in property_type_keywords)
                    if property_type_keywords
                    else False
                )

                # 基本条件：必须有买受人+出卖人
                if not has_buyer or not has_seller:
                    continue

                # 方案B：部分匹配回退（仅适用于购房合同）
                # 当有买受人+出卖人但没有明确的房屋类型关键词时，分类为购房合同（默认）
                # 场景：签名页有买方卖方但无"商品房"/"存量房"字样
                if doc_type == DocumentType.PURCHASE_CONTRACT:
                    if property_type_keywords and not has_property_type:
                        # 有买受人+出卖人，但没有"商品房" → 部分匹配，分类为购房合同
                        confidence = 0.6
                        return DocumentInfo(
                            image_path=image_path,
                            doc_type=DocumentType.PURCHASE_CONTRACT,
                            ocr_texts=ocr_texts,
                            confidence=confidence,
                            metadata={
                                "route": "contract_partial_match",
                                "has_property_type": False,
                                "signal": "buyer+seller_fallback",
                            },
                        )
                    else:
                        # 完整匹配：有买受人+出卖人+商品房
                        confidence = 0.9
                        return DocumentInfo(
                            image_path=image_path,
                            doc_type=doc_type,
                            ocr_texts=ocr_texts,
                            confidence=confidence,
                            metadata={
                                "route": "contract_field_combination",
                                "has_property_type": bool(property_type_keywords),
                            },
                        )
                else:
                    # 存量房合同：必须有"存量房"关键词（完整匹配）
                    if property_type_keywords and not has_property_type:
                        continue  # 没有"存量房"关键词，跳过
                    confidence = 0.85
                    return DocumentInfo(
                        image_path=image_path,
                        doc_type=doc_type,
                        ocr_texts=ocr_texts,
                        confidence=confidence,
                        metadata={
                            "route": "contract_field_combination",
                            "has_property_type": bool(property_type_keywords),
                        },
                    )

            elif doc_type == DocumentType.FUND_SUPERVISION:
                # 资金监管协议：放宽条件
                has_资金监管 = "资金监管" in full_text
                has_监管协议 = "监管协议" in full_text
                has_amount = any(kw in full_text for kw in signal_config["amount"])
                has_alternative = any(
                    kw in full_text for kw in self.SUPERVISION_ALTERNATIVE
                )
                has_clause_signal = any(
                    kw in full_text for kw in self.SUPERVISION_CLAUSE_SIGNALS
                )
                # 签章页特殊处理：丙方 + 签章 + (签约日期 或 第X页)
                has_丙方 = "丙方" in full_text
                has_签章 = "签章" in full_text
                has_签约日期 = "签约日期" in full_text
                has_第x页 = any(f"第{i}页" in full_text for i in range(1, 10))
                is_stamp_page = has_丙方 and has_签章 and (has_签约日期 or has_第x页)

                # 条件1：资金监管 + 监管协议 → 直接识别
                # 条件2：监管凭证/监管专用章 → 直接识别
                # 条件3：资金监管 + 金额 → 识别
                # 条件4：条款页信号 + 协议/监管 → 识别
                # 条件5：签章页特殊信号（丙方+签章+签约日期/页码）→ 识别
                if has_资金监管 and has_监管协议:
                    pass  # 满足条件1
                elif has_alternative:
                    pass  # 满足条件2
                elif has_资金监管 and has_amount:
                    pass  # 满足条件3
                elif has_clause_signal and (
                    has_资金监管 or has_监管协议 or "协议" in full_text
                ):
                    pass  # 满足条件4：条款页
                elif is_stamp_page:
                    pass  # 满足条件5：签章页特殊处理
                else:
                    continue

            elif doc_type == DocumentType.DIVORCE_AGREEMENT:
                # 离婚协议：离婚 + 财产分割/抚养
                has_divorce = any(kw in full_text for kw in signal_config["divorce"])
                has_property = any(kw in full_text for kw in signal_config["property"])
                if not (has_divorce and has_property):
                    continue

            # 计算置信度（仅资金监管和离婚协议走这里，合同类已在上面提前返回）
            confidence = 0.85

            return DocumentInfo(
                image_path=image_path,
                doc_type=doc_type,
                ocr_texts=ocr_texts,
                confidence=confidence,
                metadata={
                    "route": "contract_field_combination",
                    "has_property_type": bool(property_type_keywords),
                },
            )

        # === 阶段4: VLM兜底 ===
        return DocumentInfo(
            image_path=image_path,
            doc_type=DocumentType.UNKNOWN,
            ocr_texts=ocr_texts,
            confidence=0.0,
            metadata={"route": "vlm_fallback_required"},
        )

    def _group_keywords(self, keywords: List[str]) -> List[List[str]]:
        """
        将关键词按语义分组（用于"或"逻辑）

        例如: ["买受人", "买方", "出卖人", "卖方"]
        → [["买受人", "买方"], ["出卖人", "卖方"]]
        """
        # 简单实现：每个关键词作为独立组
        # 后续可以优化为语义分组
        return [[kw] for kw in keywords]

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
