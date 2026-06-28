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

from typing import Dict, List, Optional
from ocr_three_layer_hybrid.interfaces import DocumentType, DocumentInfo, IDocumentClassifier


class KeywordDocumentClassifier(IDocumentClassifier):
    """基于关键词的文档分类器（三阶段路由）"""

    # === 阶段1: 标准证件强信号 ===
    # 这些关键词几乎只出现在对应证件上，误判率极低
    # 注意：字典顺序决定优先级，户口本在身份证之前（避免"公民身份号码"误判户口本）
    STANDARD_CERTIFICATE_SIGNALS: Dict[DocumentType, List[str]] = {
        DocumentType.HOUSEHOLD_REGISTER: [
            "常住人口登记卡",    # 户口本个人页独有（优先级最高）
        ],
        DocumentType.DIVORCE_CERTIFICATE: [
            "离婚证字号",        # 离婚证独有
            "离婚证",            # 离婚证标题
        ],
        DocumentType.ID_CARD: [
            "公民身份号码",      # 身份证独有
            "签发机关",          # 身份证反面独有
        ],
        DocumentType.MARRIAGE_CERTIFICATE: [
            "结婚证字号",        # 结婚证独有
        ],
        DocumentType.PROPERTY_CERTIFICATE: [
            "不动产权证书",      # 房产证独有
            "BDCQZ",            # 房产证编号前缀
        ],
    }

    # === 阶段1.5: 标准证件备选强信号（需要组合匹配） ===
    # 当主强信号未命中时，使用备选强信号
    BACKUP_CERTIFICATE_SIGNALS: Dict[DocumentType, Dict[str, List[str]]] = {
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
    }

    # === 阶段1.6: 更多备选信号 ===
    # 针对特殊页面的备选信号
    ADDITIONAL_BACKUP_SIGNALS: Dict[DocumentType, Dict[str, List[str]]] = {
        DocumentType.HOUSEHOLD_REGISTER: {
            # 户别 + 户主姓名 + (住址 或 户口专用章) → 户口本首页
            "primary": ["户别", "户 别"],  # 处理OCR空格问题
            "secondary": ["户主姓名"],
            "tertiary": ["住址", "户口专用章", "家庭住址"],
            "min_tertiary": 1,  # 至少需要1个tertiary信号
        },
        DocumentType.MARRIAGE_CERTIFICATE: {
            # 结婚证 + 登记机关 → 结婚证盖章页
            "primary": ["结婚证"],
            "secondary": ["登记机关", "婚姻登记专用章", "予以登记"],
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

    def classify(self, image_path: str, ocr_texts: List[str]) -> DocumentInfo:
        """
        根据OCR文本分类文档（三阶段路由）

        Args:
            image_path: 图片路径
            ocr_texts: OCR识别文本列表

        Returns:
            DocumentInfo对象
        """
        full_text = " ".join(ocr_texts)

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
                ocr_texts=ocr_texts,
                confidence=0.90,
                metadata={"route": "multi_doc_conflict_resolution", "signal": "buyer+seller+property_type"},
            )

        # === 阶段1: 标准证件强信号 ===
        for doc_type, signals in self.STANDARD_CERTIFICATE_SIGNALS.items():
            for signal in signals:
                if signal in full_text:
                    return DocumentInfo(
                        image_path=image_path,
                        doc_type=doc_type,
                        ocr_texts=ocr_texts,
                        confidence=0.95,
                        metadata={"route": "standard_certificate", "signal": signal},
                    )

        # === 阶段1.5: 标准证件备选强信号 ===
        for doc_type, signal_config in self.BACKUP_CERTIFICATE_SIGNALS.items():
            primary_signals = signal_config["primary"]
            required_signals = signal_config["required"]

            # 检查主信号（任一匹配）
            has_primary = any(kw in full_text for kw in primary_signals)
            # 检查必需信号（全部匹配）
            has_required = all(kw in full_text for kw in required_signals)

            if has_primary and has_required:
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
                metadata={"route": "standard_document", "signal": "invoice_code+number"},
            )

        # 发票弱信号：税额 + 不含税金额
        if any(signal in full_text for signal in self.INVOICE_WEAK_SIGNALS):
            weak_signal_count = sum(1 for s in self.INVOICE_WEAK_SIGNALS if s in full_text)
            if weak_signal_count >= 2:
                return DocumentInfo(
                    image_path=image_path,
                    doc_type=DocumentType.INVOICE,
                    ocr_texts=ocr_texts,
                    confidence=0.7,
                    metadata={"route": "standard_document_weak", "weak_signals": weak_signal_count},
                )

        # === 阶段3: 合同/协议字段组合 ===
        for doc_type, signal_config in self.CONTRACT_SIGNALS.items():
            property_type_keywords = signal_config.get("property_type", [])

            # 根据文档类型检查不同的字段组合
            if doc_type in (DocumentType.PURCHASE_CONTRACT, DocumentType.STOCK_CONTRACT):
                # 买卖合同：买受人 + 出卖人 + (价款 或 房屋类型关键词)
                has_buyer = any(kw in full_text for kw in signal_config["buyer"])
                has_seller = any(kw in full_text for kw in signal_config["seller"])
                has_price = any(kw in full_text for kw in signal_config["price"])
                has_property_type = any(kw in full_text for kw in property_type_keywords) if property_type_keywords else False

                # 基本条件：有买受人+出卖人
                if not has_buyer or not has_seller:
                    continue

                # 如果有明确的房屋类型关键词，必须匹配
                if property_type_keywords:
                    if not has_property_type:
                        continue  # 要求"商品房"但没有，或要求"存量房"但没有
                    # 有正确的房屋类型，继续检查价款（如果有的话）
                    # 但如果已经有房屋类型，价款不是必须的
                else:
                    # 没有要求房屋类型，则必须有价款
                    if not has_price:
                        continue

            elif doc_type == DocumentType.FUND_SUPERVISION:
                # 资金监管协议：放宽条件
                has_资金监管 = "资金监管" in full_text
                has_监管协议 = "监管协议" in full_text
                has_amount = any(kw in full_text for kw in signal_config["amount"])
                has_alternative = any(kw in full_text for kw in self.SUPERVISION_ALTERNATIVE)
                has_clause_signal = any(kw in full_text for kw in self.SUPERVISION_CLAUSE_SIGNALS)

                # 条件1：资金监管 + 监管协议 → 直接识别
                # 条件2：监管凭证/监管专用章 → 直接识别
                # 条件3：资金监管 + 金额 → 识别
                # 条件4：条款页信号 + 协议/监管 → 识别
                if has_资金监管 and has_监管协议:
                    pass  # 满足条件1
                elif has_alternative:
                    pass  # 满足条件2
                elif has_资金监管 and has_amount:
                    pass  # 满足条件3
                elif has_clause_signal and (has_资金监管 or has_监管协议 or "协议" in full_text):
                    pass  # 满足条件4：条款页
                else:
                    continue

            elif doc_type == DocumentType.DIVORCE_AGREEMENT:
                # 离婚协议：离婚 + 财产分割/抚养
                has_divorce = any(kw in full_text for kw in signal_config["divorce"])
                has_property = any(kw in full_text for kw in signal_config["property"])
                if not (has_divorce and has_property):
                    continue

            # 计算置信度
            confidence = 0.85  # 基础置信度
            if doc_type in (DocumentType.PURCHASE_CONTRACT, DocumentType.STOCK_CONTRACT):
                if has_property_type:
                    confidence = 0.9  # 有房屋类型关键词，提高置信度

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
