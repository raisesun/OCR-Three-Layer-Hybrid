#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rule层字段级VLM重试（原"第3层"）

当规则层/位置标注层的字段校验失败时，触发VLM聚焦重试。

流程：
1. 规则层/位置标注层提取字段
2. FieldValidator 校验所有字段
3. 校验失败的字段 → 构建VLM Prompt → 调用VLM重新提取
4. 合并VLM结果（只覆盖失败字段）

注意：这不是独立的处理层，而是 Rule 层(2A) 的子步骤。
VLM 服务由 OCRConfig.vlm_fallback_engine 配置决定（生产通过 service 注入 vlm_client）；
直接实例化默认用 VLMServiceConfig(GLM-OCR, port 8080)。
"""

import json
import logging
import re
import time
from typing import Dict, List, Optional

from ocr_three_layer_hybrid.interfaces import DocumentType
from ocr_three_layer_hybrid.field_validator import FieldValidator
from ocr_three_layer_hybrid.external_services import VLMClient
from ocr_three_layer_hybrid.config import VLMServiceConfig, QwenVLServiceConfig
from ocr_three_layer_hybrid.json_utils import parse_json_from_response

logger = logging.getLogger(__name__)


class VLMFieldRetryHandler:
    """Rule层字段级VLM重试处理器

    校验规则层/位置标注层的提取结果，失败字段触发VLM聚焦重试。
    这是 Rule 层(2A)的子步骤，不是独立的处理层。

    Usage:
        handler = VLMFieldRetryHandler(vlm_client)
        failed = handler.get_failed_fields(fields)
        if failed:
            vlm_result = handler.fallback_extract(image_path, failed, doc_type)
            # 合并结果（只覆盖失败字段）
    """

    # 各文档类型的Rule层VLM重试Prompt模板
    FALLBACK_PROMPTS: Dict[DocumentType, str] = {
        DocumentType.HOUSEHOLD_REGISTER: (
            "你是一名专业的户口本信息提取专家。请仔细识别图片中的内容，"
            "提取以下字段的值。\n\n"
            "## 需要提取的字段\n"
            "{fields}\n\n"
            "## 输出格式\n"
            "严格按以下JSON格式输出，不要添加其他字段：\n"
            "{json_template}\n\n"
            "## 注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记\n"
            "- 如果某字段无法识别，值保留为空字符串\n"
            "- 户主姓名在首页的表格区域，注意区分左右列\n"
            "- 身份证号必须为18位（最后一位可能是X）\n"
        ),
        DocumentType.MARRIAGE_CERTIFICATE: (
            "你是一名专业的结婚证信息提取专家。请仔细识别图片中的内容，"
            "提取以下字段的值。\n\n"
            "## 需要提取的字段\n"
            "{fields}\n\n"
            "## 输出格式\n"
            "严格按以下JSON格式输出：\n"
            "{json_template}\n\n"
            "## 注意事项\n"
            "- 只输出纯JSON\n"
            "- 结婚证字号格式如：鄂340321-2022-000122\n"
            "- 身份证号必须为18位\n"
        ),
        DocumentType.ID_CARD: (
            "你是一名专业的身份证信息提取专家。请仔细识别图片中的内容，"
            "提取以下字段的值。\n\n"
            "## 需要提取的字段\n"
            "{fields}\n\n"
            "## 输出格式\n"
            "严格按以下JSON格式输出：\n"
            "{json_template}\n\n"
            "## 注意事项\n"
            "- 只输出纯JSON\n"
            "- 身份证号必须为18位（最后一位可能是X）\n"
            "- 注意区分正面和背面\n"
        ),
    }

    # 通用兜底Prompt（未定义专用模板时使用）
    DEFAULT_FALLBACK_PROMPT = (
        "你是一名专业的文档信息提取专家。请仔细识别图片中的内容，"
        "提取以下字段的值。\n\n"
        "## 需要提取的字段\n"
        "{fields}\n\n"
        "## 输出格式\n"
        "严格按以下JSON格式输出：\n"
        "{json_template}\n\n"
        "## 注意事项\n"
        "- 只输出纯JSON，不要包含markdown代码块标记\n"
        "- 如果某字段无法识别，值保留为空字符串\n"
    )

    def __init__(
        self,
        vlm_client: Optional[VLMClient] = None,
        vlm_config: Optional[VLMServiceConfig] = None,
    ):
        """
        Args:
            vlm_client: VLM客户端（优先使用）
            vlm_config: VLM配置（如无client则用config创建）
        """
        self.validator = FieldValidator()

        if vlm_client:
            self.vlm_client = vlm_client
        elif vlm_config:
            self.vlm_client = VLMClient(vlm_config)
        else:
            self.vlm_client = VLMClient(QwenVLServiceConfig())  # 默认 Qwen2.5-VL-7B（对齐默认 vlm_fallback_engine；GLM-OCR 已不推荐）

        self._call_count = 0
        self._total_time = 0.0

    def get_failed_fields(self, fields: Dict[str, str]) -> List[str]:
        """获取校验失败的字段列表"""
        return self.validator.get_failed_fields(fields)

    def should_fallback(self, fields: Dict[str, str]) -> bool:
        """判断是否需要Rule层VLM重试"""
        failed = self.get_failed_fields(fields)
        return len(failed) > 0

    def fallback_extract(
        self,
        image_path: str,
        failed_fields: List[str],
        doc_type: DocumentType,
    ) -> Dict[str, str]:
        """
        调用VLM重新提取失败字段

        Args:
            image_path: 图片路径
            failed_fields: 需要重新提取的字段名列表
            doc_type: 文档类型

        Returns:
            VLM提取的字段字典
        """
        if not failed_fields:
            return {}

        start_time = time.time()
        self._call_count += 1

        # 构建Prompt
        prompt = self._build_prompt(doc_type, failed_fields)

        try:
            logger.info("[Rule层VLM重试] 调用VLM重新提取: %s", failed_fields)
            response = self.vlm_client.call(
                prompt=prompt,
                image_path=image_path,
                max_tokens=512,
            )

            # 解析响应
            fields = self._parse_response(response, failed_fields)

            call_time = time.time() - start_time
            self._total_time += call_time
            logger.info(
                f"[Rule层VLM重试] 完成 | 字段={failed_fields} | "
                f"结果={fields} | 耗时={call_time:.1f}s"
            )
            return fields

        except Exception as e:
            call_time = time.time() - start_time
            self._total_time += call_time
            logger.error("[Rule层VLM重试] 失败: %s | 耗时=%.1fs", e, call_time)
            return {}

    def _build_prompt(self, doc_type: DocumentType, fields: List[str]) -> str:
        """构建Rule层VLM重试Prompt"""
        # 获取模板
        template = self.FALLBACK_PROMPTS.get(doc_type, self.DEFAULT_FALLBACK_PROMPT)

        # 字段描述
        fields_desc = "\n".join(f"- {f}" for f in fields)

        # JSON模板
        json_obj = {f: "" for f in fields}
        json_template = json.dumps(json_obj, ensure_ascii=False, indent=2)

        return template.format(
            fields=fields_desc,
            json_template=json_template,
        )

    def _parse_response(
        self, response: str, expected_fields: List[str]
    ) -> Dict[str, str]:
        """解析VLM响应JSON"""
        # 使用公共工具函数解析 JSON
        parsed = parse_json_from_response(response)
        if parsed is None:
            logger.warning("[Rule层VLM重试] JSON解析失败: %.200s", response)
            return {}

        # 只保留期望字段
        result = {}
        for field in expected_fields:
            value = parsed.get(field, "")
            if isinstance(value, str):
                result[field] = value.strip()
            else:
                result[field] = str(value).strip()

        return result

    @property
    def stats(self) -> Dict:
        """获取调用统计"""
        return {
            "call_count": self._call_count,
            "total_time_s": round(self._total_time, 2),
            "avg_time_s": round(self._total_time / max(1, self._call_count), 2),
        }
