#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第2B层：VLM层
使用GLM-OCR多模态模型处理半固定文档（户口本等）
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
    ProcessingLayer,
)
from ocr_three_layer_hybrid.config import VLMServiceConfig
from ocr_three_layer_hybrid.external_services import VLMClient


class VLMExtractionLayer(IExtractionLayer):
    """基于GLM-OCR的VLM提取层"""

    # 默认支持的文档类型（所有类型均可处理，有专用Prompt的用专用，无的用通用模板）
    DEFAULT_SUPPORTED_TYPES = [
        DocumentType.ID_CARD,
        DocumentType.MARRIAGE_CERTIFICATE,
        DocumentType.DIVORCE_CERTIFICATE,
        DocumentType.HOUSEHOLD_REGISTER,
        DocumentType.PROPERTY_CERTIFICATE,
        DocumentType.INVOICE,
        DocumentType.PURCHASE_CONTRACT,
        DocumentType.STOCK_CONTRACT,
        DocumentType.FUND_SUPERVISION,
        DocumentType.DIVORCE_AGREEMENT,
        DocumentType.UNKNOWN,
    ]

    # 默认配置
    DEFAULT_MODEL_NAME = "GLM-OCR-Q8_0.gguf"
    DEFAULT_BASE_URL = "http://localhost:8080/v1"  # 使用llama-server
    DEFAULT_TIMEOUT = 120.0
    DEFAULT_API_KEY = "not-needed"

    # 各文档类型的默认Prompt模板
    PROMPT_TEMPLATES: Dict[DocumentType, str] = {
        DocumentType.HOUSEHOLD_REGISTER: (
            "你是一名专业的户口本页页信息提取专家。请仔细识别图片中的「常住人口登记卡」表格，"
            "按以下JSON格式输出所有可识别的字段信息。\n\n"
            "## 输出JSON格式（必须严格使用以下键名）\n"
            "{\n"
            '  "姓名": "",\n'
            '  "户主": "",\n'
            '  "与户主关系": "",\n'
            '  "性别": "",\n'
            '  "出生日期": "",\n'
            '  "民族": "",\n'
            '  "户籍地址": "",\n'
            '  "公民身份号码": ""\n'
            "}\n\n"
            "## 字段提取说明\n"
            "1. **姓名**：从「姓 名」或「姓名」栏中提取\n"
            "2. **户主**：从「户主姓名」栏中提取（通常在页面顶部的户信息区域），或者从「户主或与户主关系」栏中值为「户主」时对应的姓名\n"
            "3. **与户主关系**：从「户主或与户主关系」栏中提取，常见值有：户主、妻、夫、子、女、长子、长女、次子、二女、孙子、孙女等。**注意：JSON键名必须是\"与户主关系\"，不要使用\"户主或与户主关系\"**\n"
            "4. **性别**：从「性 别」或「性别」栏中提取，值为「男」或「女」\n"
            "5. **出生日期**：从「出生日期」栏中提取，保持原始格式（如：2004年08月03日 或 2004.08.03）\n"
            "6. **民族**：从「民 族」或「民族」栏中提取，如：汉、汉族、回族等\n"
            "7. **户籍地址**：从「住 址」栏中提取（通常在页面顶部的户信息区域，格式如：安徽省蚌埠市蚌山区燕山乡定安村张庄219号）\n"
            "8. **公民身份号码**：从「公民身份证件编号」或「公民身份号码」栏中提取\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记（如```json）\n"
            "- 不要输出任何其他解释文字\n"
            "- JSON键名必须严格按照上面定义的格式，不要添加或修改键名\n"
            "- 如果某个字段在图片中不存在或无法识别，该字段值保留为空字符串\n"
            "- 仔细检查表格中的每个单元格，确保不遗漏任何字段\n"
            "- 户口本页通常包含两个部分：顶部是户基本信息（户别、户号、户主姓名、住址），下方是个人登记卡\n"
            "- 「户主或与户主关系」表示本人与户主的关系，不是户主的姓名\n"
        ),
        DocumentType.UNKNOWN: (
            "你是一名专业的文档信息提取专家。这张图片无法自动分类，请仔细识别图片内容，"
            "提取所有可能与不动产交易税务验证相关的字段信息。\n\n"
            "## 输出JSON格式（只提取存在的字段，不要添加不存在的字段）\n"
            "{\n"
            '  "文档类型": "",\n'
            '  "姓名": "",\n'
            '  "身份证号": "",\n'
            '  "金额": "",\n'
            '  "日期": "",\n'
            '  "地址": "",\n'
            '  "编号": ""\n'
            "}\n\n"
            "## 字段提取说明\n"
            "1. **文档类型**：判断这是什么类型的文档（如：合同、协议、发票、证明等）\n"
            "2. **姓名**：提取文档中的人名（买方、卖方、当事人等）\n"
            "3. **身份证号**：提取18位身份证号码\n"
            "4. **金额**：提取文档中的金额数字（价格、价款、监管金额等）\n"
            "5. **日期**：提取文档中的日期（签订日期、登记日期等）\n"
            "6. **地址**：提取房屋地址或当事人地址\n"
            "7. **编号**：提取合同编号、证书编号等\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记（如```json）\n"
            "- 不要输出任何其他解释文字\n"
            "- 只提取图片中实际存在的字段，不存在的字段不要出现在JSON中\n"
            "- 如果图片模糊或无法识别，相关字段值保留为空字符串\n"
            "- 优先提取与不动产交易税务验证相关的信息\n"
        ),
    }

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
        初始化VLM层

        Args:
            model_name: GLM-OCR模型名称
            base_url: GLM-OCR API地址
            api_key: API密钥
            timeout: 请求超时时间（秒）
            supported_doc_types: 支持的文档类型
            vlm_client: 外部注入的VLM客户端（优先使用）
        """
        self.model_name = model_name
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.supported_types = supported_doc_types or self.DEFAULT_SUPPORTED_TYPES.copy()
        # 使用注入的客户端，或根据参数创建默认客户端
        self._client = vlm_client or VLMClient(VLMServiceConfig(
            base_url=base_url,
            model_name=model_name,
            timeout=timeout,
        ))

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
            prompt = self._build_prompt(doc_info.doc_type, key_list)

            # 调用VLM（直接传递图片路径）
            vlm_response = self._call_vlm(prompt, doc_info.image_path)

            # 解析响应
            fields = self._parse_json_response(vlm_response, key_list)

            return ExtractionResult(
                doc_type=doc_info.doc_type,
                layer=ProcessingLayer.VLM,
                fields=fields,
                success=True,
                time_cost=time.time() - start_time,
                raw_text=str(vlm_response)[:500],
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

    def _encode_image_base64(self, image_path: str) -> str:
        """将图片编码为base64字符串（已迁移到 external_services.encode_image_base64）"""
        from ocr_three_layer_hybrid.external_services import encode_image_base64
        return encode_image_base64(image_path)

    def _build_prompt(self, doc_type: DocumentType, key_list: List[str]) -> str:
        """构建Prompt"""
        template = self.PROMPT_TEMPLATES.get(doc_type)
        if template is None:
            # 通用模板
            keys_str = "、".join(key_list)
            template = (
                "请从图片中提取以下字段，以JSON格式返回，不要包含markdown标记：{keys}\n"
                "不存在的字段返回空字符串。"
            )
            return template.format(keys=keys_str)
        return template

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

    def _parse_json_response(self, response: Any, key_list: List[str]) -> Dict[str, str]:
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
            clean_response = response.strip()

            # 去除markdown代码块标记
            if clean_response.startswith("```"):
                lines = clean_response.split("\n")
                # 去除第一行和最后一行（如果是```）
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                clean_response = "\n".join(lines).strip()

            # 尝试直接解析
            try:
                parsed = json.loads(clean_response)
                if not isinstance(parsed, dict):
                    return fields
            except json.JSONDecodeError:
                # 尝试用正则提取JSON块
                json_match = re.search(r"\{[^{}]*\}", clean_response, re.DOTALL)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group())
                        if not isinstance(parsed, dict):
                            return fields
                    except json.JSONDecodeError:
                        return fields
                else:
                    return fields
        else:
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
