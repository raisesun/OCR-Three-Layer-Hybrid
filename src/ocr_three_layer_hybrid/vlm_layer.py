#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Layer 2B：VLM提取层

使用视觉语言模型（默认 Qwen2.5-VL-7B）处理未知文档类型或纯文本提取。
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ocr_three_layer_hybrid.interfaces import (
    DocumentType,
    DocumentInfo,
    ExtractionResult,
    IExtractionLayer,
    PageType,
    ProcessingLayer,
)
from ocr_three_layer_hybrid.config import VLMServiceConfig
from ocr_three_layer_hybrid.external_services import VLMClient
from ocr_three_layer_hybrid.prompt_templates import build_prompt, COMMON_SUFFIX, PROMPT_TEMPLATES
from ocr_three_layer_hybrid.json_utils import parse_json_from_response


class VLMExtractionLayer(IExtractionLayer):
    """VLM 视觉模型提取层（默认使用 Qwen2.5-VL-7B）"""

    # 默认支持的文档类型（所有类型均可处理，有专用Prompt的用专用，无的用通用模板）
    # 直接使用 DocumentType 枚举的所有值，避免重复维护
    DEFAULT_SUPPORTED_TYPES = list(DocumentType)

    # 默认配置（Qwen2.5-VL-7B，端口 8082）
    DEFAULT_MODEL_NAME = "qwen2.5-vl-7b"
    DEFAULT_BASE_URL = "http://localhost:8082/v1"  # 使用llama-server
    DEFAULT_TIMEOUT = 120.0
    DEFAULT_API_KEY = "not-needed"


    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = DEFAULT_API_KEY,
        timeout: float = DEFAULT_TIMEOUT,
        supported_doc_types: Optional[List[DocumentType]] = None,
        vlm_client: Optional[VLMClient] = None,
    ):
        """
        初始化VLM提取层

        Args:
            model_name: VLM模型名称
            base_url: VLM API地址
            api_key: API密钥
            timeout: 请求超时时间（秒）
            supported_doc_types: 支持的文档类型
            vlm_client: 外部注入的VLM客户端（优先使用）
        """
        self.model_name = model_name
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.supported_types = (
            supported_doc_types or self.DEFAULT_SUPPORTED_TYPES.copy()
        )
        # 使用注入的客户端，或根据参数创建默认客户端
        self._client = vlm_client or VLMClient(
            VLMServiceConfig(
                base_url=base_url,
                model_name=model_name,
                timeout=timeout,
            )
        )

    @property
    def supported_doc_types(self) -> List[DocumentType]:
        return self.supported_types

    def can_process(self, doc_info: DocumentInfo) -> bool:
        return doc_info.doc_type in self.supported_types

    def extract(self, doc_info: DocumentInfo, key_list: List[str]) -> ExtractionResult:
        start_time = time.time()

        # 检查图片是否存在
        if not Path(doc_info.image_path).exists():
            return ExtractionResult(
                doc_type=doc_info.doc_type,
                layer=ProcessingLayer.VLM,
                fields={k: "" for k in key_list},
                success=False,
                time_cost=time.time() - start_time,
                error_message=f"图片不存在: {doc_info.image_path}",
            )

        try:
            # 构建Prompt
            prompt = self._build_prompt(doc_info, key_list)

            # 调用VLM（直接传递图片路径）
            vlm_response = self._call_vlm(prompt, doc_info.image_path)

            # 解析响应（解析一次，复用给 fields 提取和分类逻辑，避免双重解析 H6）
            if isinstance(vlm_response, dict):
                parsed_response = vlm_response
            elif isinstance(vlm_response, str):
                from ocr_three_layer_hybrid.json_utils import parse_json_from_response
                parsed_response = parse_json_from_response(vlm_response)
            else:
                parsed_response = None
            fields = self._parse_json_response(
                parsed_response if parsed_response is not None else vlm_response, key_list
            )

            # 轻量修复：让UNKNOWN文档的VLM分类结果反馈回系统
            # 当前UNKNOWN prompt让VLM同时做分类+提取，但VLM返回的doc_type被丢弃。
            # 这里提取VLM识别的doc_type，记录到结果中（用于日志/监控/后续优化）。
            # 支持两种格式：枚举名（"PROPERTY_CERTIFICATE"）和中文value（"不动产权证书"）
            vlm_classified_type = None
            if isinstance(parsed_response, dict) and "doc_type" in parsed_response:
                vlm_doc_type_str = parsed_response["doc_type"]
                # 尝试用枚举名匹配（如 "PROPERTY_CERTIFICATE"）
                if vlm_doc_type_str in DocumentType.__members__:
                    vlm_classified_type = DocumentType[vlm_doc_type_str]
                else:
                    # VLM 常用名称别名（日常语言 → DocumentType 正式名）
                    VLM_ALIASES = {
                        "房产证": DocumentType.PROPERTY_CERTIFICATE,
                        "不动产权证": DocumentType.PROPERTY_CERTIFICATE,
                        "附图页": DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT,
                        "房产分户图": DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT,
                        "宗地图": DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT,
                        "身份证正面": DocumentType.ID_CARD_FRONT,
                        "身份证背面": DocumentType.ID_CARD_BACK,
                        "身份证反面": DocumentType.ID_CARD_BACK,
                        "户口本": DocumentType.HOUSEHOLD_REGISTER,
                        "户口簿": DocumentType.HOUSEHOLD_REGISTER,
                        "结婚证": DocumentType.MARRIAGE_CERTIFICATE,
                        "离婚证": DocumentType.DIVORCE_CERTIFICATE,
                        "购房合同": DocumentType.PURCHASE_CONTRACT,
                        "商品房合同": DocumentType.PURCHASE_CONTRACT,
                        "存量房合同": DocumentType.STOCK_CONTRACT,
                        "二手房合同": DocumentType.STOCK_CONTRACT,
                        "发票": DocumentType.INVOICE,
                        "增值税发票": DocumentType.INVOICE,
                        "资金监管协议": DocumentType.FUND_SUPERVISION,
                        "监管协议": DocumentType.FUND_SUPERVISION,
                        "离婚协议": DocumentType.DIVORCE_AGREEMENT,
                    }
                    if vlm_doc_type_str in VLM_ALIASES:
                        vlm_classified_type = VLM_ALIASES[vlm_doc_type_str]
                    else:
                        # startswith 匹配（VLM 可能返回带括号说明的长字符串，如"附图页（房产证...）"）
                        for alias, dt in VLM_ALIASES.items():
                            if vlm_doc_type_str.startswith(alias):
                                vlm_classified_type = dt
                                break
                    if vlm_classified_type is None:
                        # 精确匹配 DocumentType 的中文 value（去掉模糊包含匹配 H6：VLM 返回完整名，精确+别名+startswith 已足够）
                        for dt in DocumentType:
                            if dt.value == vlm_doc_type_str:
                                vlm_classified_type = dt
                                break

            return ExtractionResult(
                doc_type=doc_info.doc_type,
                layer=ProcessingLayer.VLM,
                fields=fields,
                success=True,
                time_cost=time.time() - start_time,
                raw_text=str(vlm_response)[:500],
                vlm_classified_type=vlm_classified_type,
            )
        except Exception as e:
            return ExtractionResult(
                doc_type=doc_info.doc_type,
                layer=ProcessingLayer.VLM,
                fields={k: "" for k in key_list},
                success=False,
                time_cost=time.time() - start_time,
                error_message=str(e),
                raw_text="",
            )

    def extract_multi_page(
        self,
        image_paths: List[str],
        key_list: List[str],
        doc_type: DocumentType,
        max_pages: int = 15,
    ) -> ExtractionResult:
        """
        多页文档提取：逐页提取 + 字段合并

        适用于购房合同、存量房合同、房产证等多页文档。
        逐页调用VLM提取固定字段列表，合并所有页面的提取结果（取第一个非空值）。

        Args:
            image_paths: 图片路径列表
            key_list: 目标字段列表
            doc_type: 文档类型
            max_pages: 最大处理页数（性能优化，默认15页）

        Returns:
            合并后的提取结果
        """
        import logging

        logger = logging.getLogger(__name__)

        start_time = time.time()

        # 获取文档类型的 Prompt（创建一个临时DocumentInfo用于prompt构建）
        temp_doc_info = DocumentInfo(
            image_path="",
            doc_type=doc_type,
            page_type=PageType.CONTENT,  # 多页文档默认使用内容页
        )
        prompt = self._build_prompt(temp_doc_info, key_list)

        # 定义单页提取函数
        def extract_page(img_path: str, page_idx: int) -> Optional[Dict[str, str]]:
            page_start = time.time()
            vlm_response = self._call_vlm(prompt, img_path)
            page_time = time.time() - page_start

            page_fields = self._parse_json_response(vlm_response, key_list)

            non_empty_count = len(
                [v for v in page_fields.values() if v and v.strip()]
            )
            logger.info(
                f"[VLM层] 多页提取 | 页 {page_idx + 1}/{min(len(image_paths), max_pages)} | "
                f"耗时 {page_time:.1f}s | 提取字段 {non_empty_count}"
            )
            return page_fields

        # 使用公共的多页迭代+合并工具函数
        from ocr_three_layer_hybrid.multi_page_utils import (
            iterate_extract_merge,
            determine_extraction_success,
        )

        merged_fields, pages_processed = iterate_extract_merge(
            image_paths,
            extract_page,
            max_pages=max_pages,
            log_context="VLM层多页提取",
        )

        # 判断是否成功
        success = determine_extraction_success(merged_fields)

        total_time_cost = time.time() - start_time
        non_empty_fields = len([v for v in merged_fields.values() if v and v.strip()])

        logger.info(
            f"[VLM层] 多页提取完成 | 文档类型={doc_type.value} | "
            f"处理页数={pages_processed} | 成功字段={non_empty_fields} | "
            f"总耗时={total_time_cost:.1f}s"
        )

        return ExtractionResult(
            doc_type=doc_type,
            layer=ProcessingLayer.VLM,
            fields=merged_fields,
            success=success,
            time_cost=total_time_cost,
            raw_text=f"Processed {pages_processed} pages",
        )

    def _encode_image_base64(self, image_path: str) -> str:
        """将图片编码为base64字符串（已迁移到 external_services.encode_image_base64）"""
        from ocr_three_layer_hybrid.external_services import encode_image_base64

        return encode_image_base64(image_path)

    def _build_prompt(self, doc_info: DocumentInfo, key_list: List[str]) -> str:
        """构建Prompt（考虑文档类型和页面类型）

        优先使用文档类型+页面类型的专用Prompt，回退到文档类型的通用Prompt。
        Prompt 模板和公共后缀由 prompt_templates 模块统一管理。
        """
        doc_type_key = doc_info.doc_type.name

        # 优先使用精确类型的 Prompt
        if doc_type_key in PROMPT_TEMPLATES:
            return build_prompt(doc_type_key, key_list)

        # 回退到基础文档类型的 Prompt
        base_key = self._get_base_doc_type(doc_info.doc_type).name
        if base_key in PROMPT_TEMPLATES:
            return build_prompt(base_key, key_list)

        # 最终回退：通用模板（由 build_prompt 自动拼接 COMMON_SUFFIX）
        return build_prompt("", key_list)

    def _get_base_doc_type(self, doc_type: DocumentType) -> DocumentType:
        """获取基础文档类型（去除页面类型后缀）

        例如：HOUSEHOLD_REGISTER_CONTENT -> HOUSEHOLD_REGISTER
              DIVORCE_CERTIFICATE_COVER -> DIVORCE_CERTIFICATE
        """
        base_mapping = {
            DocumentType.ID_CARD_FRONT: DocumentType.ID_CARD,
            DocumentType.ID_CARD_BACK: DocumentType.ID_CARD,
            DocumentType.MARRIAGE_CERTIFICATE_COVER: DocumentType.MARRIAGE_CERTIFICATE,
            DocumentType.MARRIAGE_CERTIFICATE_CONTENT: DocumentType.MARRIAGE_CERTIFICATE,
            DocumentType.MARRIAGE_CERTIFICATE_STAMP: DocumentType.MARRIAGE_CERTIFICATE,
            DocumentType.DIVORCE_CERTIFICATE_COVER: DocumentType.DIVORCE_CERTIFICATE,
            DocumentType.DIVORCE_CERTIFICATE_CONTENT: DocumentType.DIVORCE_CERTIFICATE,
            DocumentType.DIVORCE_CERTIFICATE_STAMP: DocumentType.DIVORCE_CERTIFICATE,
            DocumentType.HOUSEHOLD_REGISTER_COVER: DocumentType.HOUSEHOLD_REGISTER,
            DocumentType.HOUSEHOLD_REGISTER_CONTENT: DocumentType.HOUSEHOLD_REGISTER,
            DocumentType.PROPERTY_CERTIFICATE_CONTENT: DocumentType.PROPERTY_CERTIFICATE,
            DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT: DocumentType.PROPERTY_CERTIFICATE,
            DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE: DocumentType.FUND_SUPERVISION,
            DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE: DocumentType.FUND_SUPERVISION,
            DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP: DocumentType.FUND_SUPERVISION,
            # FUND_SUPERVISION_CERTIFICATE 不需要映射，它有独立的Prompt
        }
        return base_mapping.get(doc_type, doc_type)

    def _call_vlm(self, prompt: str, image_path: str) -> Any:
        """
        调用VLM API（通过统一的 VLMClient）

        Args:
            prompt: 文本prompt
            image_path: 图片文件路径

        Returns:
            VLM返回的原始响应
        """
        return self._client.call(prompt, image_path, max_tokens=1024)

    # 户口本字段的键名映射（处理VLM可能输出的不同键名）
    HUKOU_KEY_MAPPINGS: Dict[str, List[str]] = {
        "姓名": ["姓名", "名字"],
        "户主": ["户主", "户主姓名"],
        "与户主关系": ["与户主关系", "户主或与户主关系", "关系"],
        "性别": ["性别", "性 别"],
        "出生日期": ["出生日期", "生日"],
        "民族": ["民族", "民 族"],
        "户籍地址": ["户籍地址", "住址", "住 址", "地址"],
        "公民身份号码": ["公民身份号码", "身份证号", "身份证号码", "公民身份证件编号"],
    }

    def _parse_json_response(
        self, response: Any, key_list: List[str]
    ) -> Dict[str, str]:
        """
        解析VLM返回的JSON响应

        Args:
            response: VLM返回的原始响应（可能是dict、str等）
            key_list: 需要提取的字段列表

        Returns:
            字段字典
        """
        fields = {k: "" for k in key_list}

        # 如果是dict，直接提取
        if isinstance(response, dict):
            parsed = response
        elif isinstance(response, str):
            # 使用公共工具函数解析 JSON
            parsed = parse_json_from_response(response)
            if parsed is None:
                return fields
        else:
            return fields

        # 处理UNKNOWN文档的嵌套格式：{"doc_type": "...", "fields": {...}}
        if "fields" in parsed and isinstance(parsed["fields"], dict):
            # UNKNOWN文档：VLM返回嵌套格式，直接使用所有字段
            nested_fields = parsed["fields"]
            for key, value in nested_fields.items():
                if value and str(value).strip():
                    fields[key] = str(value)
            return fields

        # 使用键名映射来提取字段
        for target_key in key_list:
            if target_key in self.HUKOU_KEY_MAPPINGS:
                # 尝试所有可能的键名
                for possible_key in self.HUKOU_KEY_MAPPINGS[target_key]:
                    if possible_key in parsed:
                        fields[target_key] = str(parsed[possible_key])
                        break
            elif target_key in parsed:
                fields[target_key] = str(parsed[target_key])

        return fields
