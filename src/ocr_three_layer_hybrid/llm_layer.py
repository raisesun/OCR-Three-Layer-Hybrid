#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第2C层：LLM层
使用PP-ChatOCRv4处理复杂文档（购房合同、房产证等）
"""

import time
from typing import Dict, List, Optional, Any
from ocr_three_layer_hybrid.interfaces import (
    DocumentType,
    DocumentInfo,
    ExtractionResult,
    ProcessingLayer,
    IExtractionLayer,
)


class PPChatOCRv4Layer(IExtractionLayer):
    """基于PP-ChatOCRv4的LLM提取层"""

    # 默认支持的文档类型
    DEFAULT_SUPPORTED_TYPES = [
        DocumentType.PURCHASE_CONTRACT,
        DocumentType.STOCK_CONTRACT,
        DocumentType.PROPERTY_CERTIFICATE,
    ]

    # 默认LLM配置
    DEFAULT_CHAT_BOT_CONFIG = {
        "api_type": "openai",
        "model_name": "qwen3.5:4b",  # 默认使用 Qwen3.5-4B
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
    }

    # 默认向量检索配置
    DEFAULT_RETRIEVER_CONFIG = {
        "api_type": "openai",
        "model_name": "nomic-embed-text",
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
    }

    def __init__(
        self,
        chat_bot_config: Optional[Dict[str, Any]] = None,
        retriever_config: Optional[Dict[str, Any]] = None,
        ocr_config: Optional[Dict[str, Any]] = None,
        supported_doc_types: Optional[List[DocumentType]] = None,
        timeout: float = 180.0,
    ):
        """
        初始化PP-ChatOCRv4提取层

        Args:
            chat_bot_config: LLM配置
            retriever_config: 向量检索模型配置
            ocr_config: OCR功能配置
            supported_doc_types: 支持的文档类型
            timeout: 超时时间（秒）
        """
        self.chat_bot_config = chat_bot_config or self.DEFAULT_CHAT_BOT_CONFIG.copy()
        self.retriever_config = retriever_config or self.DEFAULT_RETRIEVER_CONFIG.copy()
        self.ocr_config = ocr_config or self._default_ocr_config()
        self.supported_types = supported_doc_types or self.DEFAULT_SUPPORTED_TYPES.copy()
        self.timeout = timeout

        self._pp_chatocr = None
        self._init_error = None

    def _default_ocr_config(self) -> Dict[str, Any]:
        return {
            "use_doc_orientation_classify": True,
            "use_doc_unwarping": True,
            "use_textline_orientation": True,
            "use_seal_recognition": True,
            "use_table_recognition": True,
        }

    @property
    def supported_doc_types(self) -> List[DocumentType]:
        return self.supported_types

    def can_process(self, doc_info: DocumentInfo) -> bool:
        return doc_info.doc_type in self.supported_types

    def _get_pp_chatocr(self):
        """延迟初始化PP-ChatOCRv4"""
        if self._pp_chatocr is None:
            try:
                from paddleocr import PPChatOCRv4Doc

                self._pp_chatocr = PPChatOCRv4Doc(
                    **self.ocr_config,
                    chat_bot_config=self.chat_bot_config,
                    retriever_config=self.retriever_config,
                )
            except Exception as e:
                self._init_error = str(e)
                raise
        return self._pp_chatocr

    def extract(self, doc_info: DocumentInfo, key_list: List[str]) -> ExtractionResult:
        start_time = time.time()

        try:
            pp_chatocr = self._get_pp_chatocr()

            # 视觉信息提取
            visual_result = pp_chatocr.visual_predict(
                input=doc_info.image_path,
                **self.ocr_config,
            )

            visual_info = visual_result[0]["visual_info"]

            # LLM字段提取
            chat_result = pp_chatocr.chat(
                key_list=key_list,
                visual_info=visual_info,
            )

            # 解析结果
            fields = self._parse_chat_result(chat_result, key_list)

            return ExtractionResult(
                doc_type=doc_info.doc_type,
                layer=ProcessingLayer.LLM,
                fields=fields,
                success=True,
                time_cost=time.time() - start_time,
                raw_text=str(visual_info)[:500],
            )
        except Exception as e:
            return ExtractionResult(
                doc_type=doc_info.doc_type,
                layer=ProcessingLayer.LLM,
                fields={k: "" for k in key_list},
                success=False,
                time_cost=time.time() - start_time,
                error_message=str(e),
                raw_text="",
            )

    def _parse_chat_result(self, chat_result: Any, key_list: List[str]) -> Dict[str, str]:
        """解析chat方法返回结果"""
        import json

        fields = {k: "" for k in key_list}

        if isinstance(chat_result, dict):
            chat_res = chat_result.get("chat_res", {})
        elif isinstance(chat_result, (list, tuple)) and len(chat_result) > 0:
            first = chat_result[0]
            chat_res = first.get("chat_res", {}) if isinstance(first, dict) else {}
        else:
            chat_res = {}

        if isinstance(chat_res, dict):
            for key in key_list:
                if key in chat_res:
                    fields[key] = str(chat_res[key])
        elif isinstance(chat_res, str):
            try:
                parsed = json.loads(chat_res)
                for key in key_list:
                    if key in parsed:
                        fields[key] = str(parsed[key])
            except json.JSONDecodeError:
                pass

        return fields
