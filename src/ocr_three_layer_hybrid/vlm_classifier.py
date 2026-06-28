#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLM分类器：使用视觉语言模型进行文档分类

当规则分类器无法确定文档类型时，使用VLM进行兜底分类
"""

import base64
import json
import requests
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from ocr_three_layer_hybrid.interfaces import DocumentType, DocumentInfo, IDocumentClassifier


class VLMDocumentClassifier:
    """基于VLM的文档分类器"""

    # VLM服务配置
    DEFAULT_BASE_URL = "http://localhost:8081/v1"
    DEFAULT_MODEL = "Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"
    DEFAULT_TIMEOUT = 120.0

    # 文档类型列表（与VLM prompt中保持一致）
    DOC_TYPES = [
        "身份证",
        "结婚证",
        "离婚证",
        "户口本",
        "不动产权证书",
        "发票",
        "购房合同",
        "存量房合同",
        "资金监管协议",
        "离婚协议",
        "附属页面",  # 宗地图、附图等
        "其他",      # 无法判断
    ]

    # 文档类型到DocumentType的映射
    TYPE_MAPPING: Dict[str, DocumentType] = {
        "身份证": DocumentType.ID_CARD,
        "结婚证": DocumentType.MARRIAGE_CERTIFICATE,
        "离婚证": DocumentType.DIVORCE_CERTIFICATE,
        "户口本": DocumentType.HOUSEHOLD_REGISTER,
        "不动产权证书": DocumentType.PROPERTY_CERTIFICATE,
        "发票": DocumentType.INVOICE,
        "购房合同": DocumentType.PURCHASE_CONTRACT,
        "存量房合同": DocumentType.STOCK_CONTRACT,
        "资金监管协议": DocumentType.FUND_SUPERVISION,
        "离婚协议": DocumentType.DIVORCE_AGREEMENT,
        "附属页面": DocumentType.UNKNOWN,  # 附属页面作为UNKNOWN处理，但metadata标记
        "其他": DocumentType.UNKNOWN,
    }

    # 分类prompt
    CLASSIFICATION_PROMPT = """这张图片是什么文档类型？从以下选项中选择：
身份证、结婚证、离婚证、户口本、不动产权证书、发票、购房合同、存量房合同、资金监管协议、离婚协议、附属页面、其他

只输出类型名称，不要解释。"""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.base_url = base_url
        self.model = model
        self.timeout = timeout

    def classify(self, image_path: str) -> Tuple[DocumentType, float, Dict]:
        """
        使用VLM对图片进行分类

        Args:
            image_path: 图片路径

        Returns:
            (文档类型, 置信度, 元数据)
        """
        if not Path(image_path).exists():
            return DocumentType.UNKNOWN, 0.0, {"error": f"图片不存在: {image_path}"}

        try:
            # 编码图片
            with open(image_path, 'rb') as f:
                image_b64 = base64.b64encode(f.read()).decode('utf-8')

            # 构建请求
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self.CLASSIFICATION_PROMPT},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                        ]
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 50,
            }

            # 调用API
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()

            result = response.json()
            content = result['choices'][0]['message'].get('content', '').strip()

            # 解析结果
            doc_type_str = self._parse_response(content)
            doc_type = self.TYPE_MAPPING.get(doc_type_str, DocumentType.UNKNOWN)

            # 构建元数据
            metadata = {
                "route": "vlm_classification",
                "vlm_result": doc_type_str,
                "vlm_raw": content,
            }

            # 附属页面特殊标记
            if doc_type_str == "附属页面":
                metadata["is_attachment"] = True

            # 置信度：VLM分类给0.8（低于规则分类的0.9-0.95）
            confidence = 0.8 if doc_type != DocumentType.UNKNOWN else 0.5

            return doc_type, confidence, metadata

        except Exception as e:
            return DocumentType.UNKNOWN, 0.0, {"error": str(e)}

    def _parse_response(self, content: str) -> str:
        """解析VLM返回的文本为文档类型"""
        content = content.strip()

        # 直接匹配
        for doc_type in self.DOC_TYPES:
            if doc_type in content:
                return doc_type

        # 模糊匹配
        content_lower = content.lower()
        if "身份证" in content_lower:
            return "身份证"
        if "结婚证" in content_lower:
            return "结婚证"
        if "离婚证" in content_lower:
            return "离婚证"
        if "户口" in content_lower:
            return "户口本"
        if "房产" in content_lower or "不动产" in content_lower:
            return "不动产权证书"
        if "发票" in content_lower:
            return "发票"
        if "购房" in content_lower or "商品房" in content_lower:
            return "购房合同"
        if "存量房" in content_lower:
            return "存量房合同"
        if "监管" in content_lower:
            return "资金监管协议"
        if "离婚协议" in content_lower:
            return "离婚协议"
        if "附图" in content_lower or "宗地" in content_lower or "附属" in content_lower:
            return "附属页面"

        return "其他"


class HybridDocumentClassifier(IDocumentClassifier):
    """
    混合文档分类器：规则优先，VLM兜底

    工作流程：
    1. 先使用规则分类器（关键词匹配）
    2. 如果规则分类器返回UNKNOWN，调用VLM分类器
    """

    def __init__(
        self,
        rule_classifier: IDocumentClassifier,
        vlm_classifier: Optional[VLMDocumentClassifier] = None,
        enable_vlm_fallback: bool = True,
    ):
        """
        初始化混合分类器

        Args:
            rule_classifier: 规则分类器
            vlm_classifier: VLM分类器（可选）
            enable_vlm_fallback: 是否启用VLM兜底
        """
        self.rule_classifier = rule_classifier
        self.vlm_classifier = vlm_classifier or VLMDocumentClassifier()
        self.enable_vlm_fallback = enable_vlm_fallback

    def classify(self, image_path: str, ocr_texts: List[str]) -> DocumentInfo:
        """
        分类文档（规则优先，VLM兜底）

        Args:
            image_path: 图片路径
            ocr_texts: OCR文本列表

        Returns:
            DocumentInfo对象
        """
        # 第一步：使用规则分类器
        rule_result = self.rule_classifier.classify(image_path, ocr_texts)

        # 如果规则分类器已经确定了类型（不是UNKNOWN），直接返回
        if rule_result.doc_type != DocumentType.UNKNOWN:
            return rule_result

        # 第二步：规则分类器返回UNKNOWN，尝试VLM兜底
        if not self.enable_vlm_fallback:
            return rule_result

        # 调用VLM分类器
        vlm_type, vlm_confidence, vlm_metadata = self.vlm_classifier.classify(image_path)

        # 如果VLM也无法确定，返回原始的UNKNOWN结果
        if vlm_type == DocumentType.UNKNOWN and not vlm_metadata.get("is_attachment"):
            # 合并元数据
            merged_metadata = {**rule_result.metadata, **vlm_metadata}
            return DocumentInfo(
                image_path=image_path,
                doc_type=DocumentType.UNKNOWN,
                ocr_texts=ocr_texts,
                confidence=0.0,
                metadata=merged_metadata,
            )

        # VLM确定了类型，返回VLM的结果
        return DocumentInfo(
            image_path=image_path,
            doc_type=vlm_type,
            ocr_texts=ocr_texts,
            confidence=vlm_confidence,
            metadata=vlm_metadata,
        )
