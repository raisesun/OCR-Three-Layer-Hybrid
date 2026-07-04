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
    PageType,
    ProcessingLayer,
)
from ocr_three_layer_hybrid.config import VLMServiceConfig
from ocr_three_layer_hybrid.external_services import VLMClient


class VLMExtractionLayer(IExtractionLayer):
    """基于GLM-OCR的VLM提取层"""

    # 默认支持的文档类型（所有类型均可处理，有专用Prompt的用专用，无的用通用模板）
    DEFAULT_SUPPORTED_TYPES = [
        DocumentType.ID_CARD,
        DocumentType.ID_CARD_FRONT,
        DocumentType.ID_CARD_BACK,
        DocumentType.MARRIAGE_CERTIFICATE,
        DocumentType.MARRIAGE_CERTIFICATE_COVER,
        DocumentType.MARRIAGE_CERTIFICATE_CONTENT,
        DocumentType.MARRIAGE_CERTIFICATE_STAMP,
        DocumentType.DIVORCE_CERTIFICATE,
        DocumentType.DIVORCE_CERTIFICATE_COVER,
        DocumentType.DIVORCE_CERTIFICATE_CONTENT,
        DocumentType.DIVORCE_CERTIFICATE_STAMP,
        DocumentType.HOUSEHOLD_REGISTER,
        DocumentType.HOUSEHOLD_REGISTER_COVER,
        DocumentType.HOUSEHOLD_REGISTER_CONTENT,
        DocumentType.PROPERTY_CERTIFICATE,
        DocumentType.PROPERTY_CERTIFICATE_CONTENT,
        DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT,
        DocumentType.INVOICE,
        DocumentType.PURCHASE_CONTRACT,
        DocumentType.STOCK_CONTRACT,
        DocumentType.FUND_SUPERVISION,
        DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE,
        DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE,
        DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP,
        DocumentType.FUND_SUPERVISION_CERTIFICATE,
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
        DocumentType.HOUSEHOLD_REGISTER_COVER: (
            "你是一名专业的户口本首页信息提取专家。请仔细识别图片中的户口本首页，"
            "提取户基本信息。\n\n"
            "## 输出JSON格式（必须严格使用以下键名）\n"
            "{\n"
            '  "户别": "",\n'
            '  "户主姓名": "",\n'
            '  "户号": "",\n'
            '  "住址": ""\n'
            "}\n\n"
            "## 字段提取说明\n"
            "1. **户别**：户口类型，如：家庭户、集体户\n"
            "2. **户主姓名**：户主的姓名\n"
            "3. **户号**：户口编号\n"
            "4. **住址**：户籍地址，格式如：安徽省蚌埠市蚌山区燕山乡定安村张庄219号\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记（如```json）\n"
            "- 不要输出任何其他解释文字\n"
            "- 如果某个字段不存在或无法识别，保留为空字符串\n"
            "- 忽略印章信息\n"
        ),
        DocumentType.HOUSEHOLD_REGISTER_CONTENT: (
            "你是一名专业的户口本人页信息提取专家。请仔细识别图片中的「常住人口登记卡」，"
            "提取个人信息。\n\n"
            "## 输出JSON格式（必须严格使用以下键名）\n"
            "{\n"
            '  "姓名": "",\n'
            '  "与户主关系": "",\n'
            '  "性别": "",\n'
            '  "出生日期": "",\n'
            '  "民族": "",\n'
            '  "公民身份号码": ""\n'
            "}\n\n"
            "## 字段提取说明\n"
            "1. **姓名**：从「姓 名」或「姓名」栏中提取\n"
            "2. **与户主关系**：从「户主或与户主关系」栏中提取，常见值有：户主、妻、夫、子、女、长子、长女等。**注意：JSON键名必须是\"与户主关系\"**\n"
            "3. **性别**：从「性 别」或「性别」栏中提取，值为「男」或「女」\n"
            "4. **出生日期**：从「出生日期」栏中提取，保持原始格式\n"
            "5. **民族**：从「民 族」或「民族」栏中提取\n"
            "6. **公民身份号码**：从「公民身份证件编号」或「公民身份号码」栏中提取\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记（如```json）\n"
            "- 不要输出任何其他解释文字\n"
            "- JSON键名必须严格按照上面定义的格式\n"
            "- 如果某个字段不存在或无法识别，保留为空字符串\n"
            "- 注意：常住人口登记卡每个字之间可能没有空格\n"
        ),
        DocumentType.PURCHASE_CONTRACT: (
            "你是一名专业的购房合同信息提取专家。请仔细识别图片中的购房合同内容，"
            "提取以下关键字段。\n\n"
            "## 输出JSON格式（必须严格使用以下键名）\n"
            "{\n"
            '  "合同编号": "",\n'
            '  "买受人": "",\n'
            '  "出卖人": "",\n'
            '  "总价款": "",\n'
            '  "签订日期": "",\n'
            '  "房屋地址": "",\n'
            '  "建筑面积": ""\n'
            "}\n\n"
            "## 字段提取说明\n"
            "1. **合同编号**：通常在合同首页顶部，格式如：Y(2024)XXXXX\n"
            "2. **买受人**：购买房屋的一方，通常在「买受人」「买方」或「乙方」位置\n"
            "3. **出卖人**：出售房屋的一方，通常在「出卖人」「卖方」或「甲方」位置\n"
            "4. **总价款**：房屋总价格，包含单位（如：元、万元），可能在「总价款」「成交价格的」「房屋总价」等位置\n"
            "5. **签订日期**：合同签订日期，保持原始格式（如：2024年01月01日 或 2024-01-01）\n"
            "6. **房屋地址**：房屋的详细地址，通常在「房屋坐落」「房屋地址」「坐落」等位置\n"
            "7. **建筑面积**：房屋的建筑面积，包含单位（如：平方米、㎡），可能在「建筑面积」「面积」等位置\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记（如```json）\n"
            "- 不要输出任何其他解释文字\n"
            "- JSON键名必须严格按照上面定义的格式\n"
            "- 如果某个字段在图片中不存在或无法识别，该字段值保留为空字符串\n"
            "- 仔细识别合同中的关键信息，确保准确提取\n"
            "- 如果本页没有某个字段，该字段值保留为空字符串\n"
        ),
        DocumentType.STOCK_CONTRACT: (
            "你是一名专业的存量房合同信息提取专家。请仔细识别图片中的存量房（二手房）买卖合同内容，"
            "提取以下关键字段。\n\n"
            "## 输出JSON格式（必须严格使用以下键名）\n"
            "{\n"
            '  "合同编号": "",\n'
            '  "买受人": "",\n'
            '  "出卖人": "",\n'
            '  "总价款": "",\n'
            '  "签订日期": "",\n'
            '  "房屋地址": "",\n'
            '  "建筑面积": ""\n'
            "}\n\n"
            "## 字段提取说明\n"
            "1. **合同编号**：通常在合同首页顶部\n"
            "2. **买受人**：购买房屋的一方（买方、乙方）\n"
            "3. **出卖人**：出售房屋的一方（卖方、甲方）\n"
            "4. **总价款**：房屋成交价格，包含单位（元、万元）\n"
            "5. **签订日期**：合同签订日期\n"
            "6. **房屋地址**：房屋的详细地址\n"
            "7. **建筑面积**：房屋建筑面积，包含单位（平方米、㎡）\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记\n"
            "- 不要输出任何其他解释文字\n"
            "- 如果某个字段在图片中不存在或无法识别，保留为空字符串\n"
            "- 如果本页没有某个字段，该字段值保留为空字符串\n"
        ),
        DocumentType.PROPERTY_CERTIFICATE: (
            "你是一名专业的不动产权证书信息提取专家。请仔细识别图片中的不动产权证书内容，"
            "提取以下关键字段。\n\n"
            "## 输出JSON格式（必须严格使用以下键名）\n"
            "{\n"
            '  "证书号": "",\n'
            '  "权利人": "",\n'
            '  "共有情况": "",\n'
            '  "不动产单元号": "",\n'
            '  "房屋地址": "",\n'
            '  "建筑面积": "",\n'
            '  "用途": ""\n'
            "}\n\n"
            "## 字段提取说明\n"
            "1. **证书号**：不动产权证书编号，通常在证书顶部，格式如：皖(2024)蚌埠市不动产权第XXXXXXX号\n"
            "2. **权利人**：房屋所有权人的姓名\n"
            "3. **共有情况**：单独所有、共同共有、按份共有等\n"
            "4. **不动产单元号**：28位不动产单元编号\n"
            "5. **房屋地址**：房屋的详细地址，通常在「坐落」位置\n"
            "6. **建筑面积**：房屋建筑面积，包含单位（平方米、㎡）\n"
            "7. **用途**：房屋用途，如：城镇住宅用地/成套住宅、商业/办公等\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记\n"
            "- 不要输出任何其他解释文字\n"
            "- 如果某个字段在图片中不存在或无法识别，保留为空字符串\n"
            "- 不动产权证书可能有多个页面，仔细识别当前页面的信息\n"
        ),
        DocumentType.DIVORCE_CERTIFICATE: (
            "你是一名专业的离婚证信息提取专家。请仔细识别图片中的离婚证内容页，"
            "提取以下关键字段。注意：离婚证可能有多页，请只提取内容页的信息。\n\n"
            "## 输出JSON格式（必须严格使用以下键名）\n"
            "{\n"
            '  "离婚证字号": "",\n'
            '  "登记日期": "",\n'
            '  "持证人": "",\n'
            '  "持证人性别": "",\n'
            '  "持证人民族": "",\n'
            '  "持证人出生日期": "",\n'
            '  "持证人身份证件号": "",\n'
            '  "原配偶姓名": "",\n'
            '  "原配偶性别": "",\n'
            '  "原配偶民族": "",\n'
            '  "原配偶出生日期": "",\n'
            '  "原配偶身份证件号": "",\n'
            '  "备注": ""\n'
            "}\n\n"
            "## 字段提取说明\n"
            "1. **离婚证字号**：离婚证编号，格式如：L340321-2018-002721\n"
            "2. **登记日期**：离婚登记日期\n"
            "3. **持证人**：离婚证持有人姓名\n"
            "4. **持证人性别**：持证人性别（男/女）\n"
            "5. **持证人民族**：持证人民族（如：汉族）\n"
            "6. **持证人出生日期**：持证人出生日期\n"
            "7. **持证人身份证件号**：持证人身份证号码（18位）\n"
            "8. **原配偶姓名**：原配偶的姓名\n"
            "9. **原配偶性别**：原配偶性别（男/女）\n"
            "10. **原配偶民族**：原配偶民族\n"
            "11. **原配偶出生日期**：原配偶出生日期\n"
            "12. **原配偶身份证件号**：原配偶身份证号码（18位）\n"
            "13. **备注**：离婚证上的备注信息\n\n"
            "## 重要注意事项\n"
            "- 离婚证内容页通常包含两组人员信息（持证人和原配偶），请完整提取\n"
            "- 如果本页是封面页或其他非内容页，无法提取到上述字段，则返回空JSON\n"
            "- 只输出纯JSON，不要包含markdown代码块标记\n"
            "- 如果某个字段不存在或无法识别，保留为空字符串\n"
        ),
        DocumentType.DIVORCE_CERTIFICATE_COVER: (
            "你是一名专业的离婚证信息提取专家。当前页面是离婚证封面页或盖章页，"
            "没有可提取的个人信息。请直接返回空JSON。\n\n"
            "## 输出格式\n"
            "{}\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记\n"
            "- 不要输出任何其他解释文字\n"
        ),
        DocumentType.DIVORCE_CERTIFICATE_CONTENT: (
            "你是一名专业的离婚证信息提取专家。请仔细识别图片中的离婚证内容页，"
            "提取以下关键字段。离婚证内容页包含两组人员信息（持证人和原配偶）。\n\n"
            "## 输出JSON格式（必须严格使用以下键名）\n"
            "{\n"
            '  "离婚证字号": "",\n'
            '  "登记日期": "",\n'
            '  "持证人": "",\n'
            '  "持证人性别": "",\n'
            '  "持证人民族": "",\n'
            '  "持证人出生日期": "",\n'
            '  "持证人身份证件号": "",\n'
            '  "原配偶姓名": "",\n'
            '  "原配偶性别": "",\n'
            '  "原配偶民族": "",\n'
            '  "原配偶出生日期": "",\n'
            '  "原配偶身份证件号": "",\n'
            '  "备注": ""\n'
            "}\n\n"
            "## 字段提取说明\n"
            "1. **离婚证字号**：离婚证编号，格式如：L340321-2018-002721\n"
            "2. **登记日期**：离婚登记日期\n"
            "3. **持证人**：离婚证持有人姓名\n"
            "4-7. **持证人信息**：性别、民族、出生日期、身份证件号\n"
            "8-12. **原配偶信息**：姓名、性别、民族、出生日期、身份证件号\n"
            "13. **备注**：离婚证上的备注信息\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记\n"
            "- 如果某个字段不存在或无法识别，保留为空字符串\n"
            "- 请完整提取两组人员信息\n"
        ),
        DocumentType.MARRIAGE_CERTIFICATE: (
            "你是一名专业的结婚证信息提取专家。请仔细识别图片中的结婚证内容页，"
            "提取以下关键字段。注意：结婚证可能有多页，请只提取内容页的信息。\n\n"
            "## 输出JSON格式（必须严格使用以下键名）\n"
            "{\n"
            '  "结婚证字号": "",\n'
            '  "登记日期": "",\n'
            '  "持证人": "",\n'
            '  "男方姓名": "",\n'
            '  "男方身份证号": "",\n'
            '  "女方姓名": "",\n'
            '  "女方身份证号": ""\n'
            "}\n\n"
            "## 字段提取说明\n"
            "1. **结婚证字号**：结婚证编号，格式如：J340322-2025-000779\n"
            "2. **登记日期**：结婚登记日期\n"
            "3. **持证人**：结婚证持有人姓名\n"
            "4. **男方姓名**：男方姓名\n"
            "5. **男方身份证号**：男方身份证号码（18位）\n"
            "6. **女方姓名**：女方姓名\n"
            "7. **女方身份证号**：女方身份证号码（18位）\n\n"
            "## 重要注意事项\n"
            "- 结婚证内容页通常包含双方人员信息，请完整提取\n"
            "- 如果本页是封面页或其他非内容页，无法提取到上述字段，则返回空JSON\n"
            "- 只输出纯JSON，不要包含markdown代码块标记\n"
            "- 如果某个字段不存在或无法识别，保留为空字符串\n"
        ),
        DocumentType.MARRIAGE_CERTIFICATE_COVER: (
            "你是一名专业的结婚证信息提取专家。当前页面是结婚证封面页或盖章页，"
            "没有可提取的个人信息。请直接返回空JSON。\n\n"
            "## 输出格式\n"
            "{}\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记\n"
            "- 不要输出任何其他解释文字\n"
        ),
        DocumentType.MARRIAGE_CERTIFICATE_CONTENT: (
            "你是一名专业的结婚证信息提取专家。请仔细识别图片中的结婚证内容页，"
            "提取以下关键字段。结婚证内容页包含双方人员信息。\n\n"
            "## 输出JSON格式（必须严格使用以下键名）\n"
            "{\n"
            '  "结婚证字号": "",\n'
            '  "登记日期": "",\n'
            '  "持证人": "",\n'
            '  "男方姓名": "",\n'
            '  "男方身份证号": "",\n'
            '  "女方姓名": "",\n'
            '  "女方身份证号": ""\n'
            "}\n\n"
            "## 字段提取说明\n"
            "1. **结婚证字号**：结婚证编号，格式如：J340322-2025-000779\n"
            "2. **登记日期**：结婚登记日期\n"
            "3. **持证人**：结婚证持有人姓名\n"
            "4. **男方姓名**：男方姓名\n"
            "5. **男方身份证号**：男方身份证号码（18位）\n"
            "6. **女方姓名**：女方姓名\n"
            "7. **女方身份证号**：女方身份证号码（18位）\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记\n"
            "- 如果某个字段不存在或无法识别，保留为空字符串\n"
            "- 请完整提取双方人员信息\n"
        ),
        DocumentType.FUND_SUPERVISION: (
            "你是一名专业的资金监管协议信息提取专家。请仔细识别图片中的资金监管协议内容，"
            "提取以下关键字段。\n\n"
            "## 输出JSON格式（必须严格使用以下键名）\n"
            "{\n"
            '  "监管金额": "",\n'
            '  "监管账户": "",\n'
            '  "买方": "",\n'
            '  "买方身份证号": "",\n'
            '  "卖方": "",\n'
            '  "卖方身份证号": "",\n'
            '  "监管机构": "",\n'
            '  "监管期限": "",\n'
            '  "房屋地址": "",\n'
            '  "合同编号": "",\n'
            '  "签订日期": ""\n'
            "}\n\n"
            "## 字段提取说明\n"
            "1. **监管金额**：监管的资金金额，包含单位（元、万元），通常在「监管金额」「交易资金」等位置\n"
            "2. **监管账户**：监管银行的账户名称或账号\n"
            "3. **买方**：购房人姓名（可能有多个，用逗号分隔）\n"
            "4. **买方身份证号**：购房人的身份证号码\n"
            "5. **卖方**：售房人姓名\n"
            "6. **卖方身份证号**：售房人的身份证号码\n"
            "7. **监管机构**：负责资金监管的机构名称，如：蚌埠市城市开发建设集团有限公司\n"
            "8. **监管期限**：资金监管的期限或起止日期\n"
            "9. **房屋地址**：被交易房屋的详细地址\n"
            "10. **合同编号**：关联的买卖合同编号\n"
            "11. **签订日期**：协议签订日期\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记\n"
            "- 不要输出任何其他解释文字\n"
            "- 如果某个字段在图片中不存在或无法识别，保留为空字符串\n"
            "- 资金监管协议通常包含买方、卖方、监管金额、监管机构等关键信息\n"
            "- 仔细识别协议中的各方当事人信息\n"
        ),
        DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE: (
            "你是一名专业的资金监管协议首页信息提取专家。请仔细识别图片中的「蚌埠市存量房交易资金监管协议」首页，"
            "提取以下关键字段。\n\n"
            "## 输出JSON格式（必须严格使用以下键名）\n"
            "{\n"
            '  "编号": "",\n'
            '  "甲方": "",\n'
            '  "乙方": "",\n'
            '  "丙方": "",\n'
            '  "签署日期": "",\n'
            '  "网上签约备案合同号": "",\n'
            '  "房屋地址": "",\n'
            '  "建筑面积": "",\n'
            '  "不动产权证号": "",\n'
            '  "购房款(大写)": "",\n'
            '  "购房款(小写)": "",\n'
            '  "贷款(大写)": "",\n'
            '  "贷款(小写)": ""\n'
            "}\n\n"
            "## 字段提取说明\n"
            "1. **编号**：协议编号\n"
            "2-4. **甲乙丙方**：立协议人\n"
            "5. **签署日期**：协议签署日期\n"
            "6. **网上签约备案合同号**：关联的备案合同号\n"
            "7-9. **房屋信息**：地址、面积、产权证号\n"
            "10-13. **购房款/贷款**：大写和小写金额\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记\n"
            "- 如果某个字段不存在或无法识别，保留为空字符串\n"
        ),
        DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE: (
            "你是一名专业的资金监管协议信息页提取专家。请仔细识别图片中的协议第二页，"
            "提取甲乙双方的详细信息。\n\n"
            "## 输出JSON格式（必须严格使用以下键名）\n"
            "{\n"
            '  "甲方姓名": "",\n'
            '  "甲方身份证号": "",\n'
            '  "甲方银行": "",\n'
            '  "甲方账号": "",\n'
            '  "乙方姓名": "",\n'
            '  "乙方身份证号": "",\n'
            '  "乙方银行": "",\n'
            '  "乙方账号": ""\n'
            "}\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记\n"
            "- 如果某个字段不存在或无法识别，保留为空字符串\n"
        ),
        DocumentType.FUND_SUPERVISION_CERTIFICATE: (
            "你是一名专业的资金监管凭证信息提取专家。请仔细识别图片中的「蚌埠市存量房交易资金监管凭证」表格，"
            "提取以下关键字段。\n\n"
            "## 输出JSON格式（必须严格使用以下键名）\n"
            "{\n"
            '  "协议编号": "",\n'
            '  "日期": "",\n'
            '  "买房人": "",\n'
            '  "买房人姓名": "",\n'
            '  "身份证号": "",\n'
            '  "房屋坐落": "",\n'
            '  "建筑面积": "",\n'
            '  "监管总额": "",\n'
            '  "收款单位": ""\n'
            "}\n\n"
            "## 字段提取说明\n"
            "1. **协议编号**：关联的监管协议编号\n"
            "2. **日期**：凭证日期\n"
            "3-5. **买房人信息**：姓名、身份证号\n"
            "6-7. **房屋信息**：坐落地址、建筑面积\n"
            "8. **监管总额**：监管金额（忽略红章）\n"
            "9. **收款单位**：收款单位名称（忽略红章）\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记\n"
            "- 忽略印章内容\n"
            "- 如果某个字段不存在或无法识别，保留为空字符串\n"
        ),
        DocumentType.DIVORCE_AGREEMENT: (
            "你是一名专业的离婚协议信息提取专家。请仔细识别图片中的离婚协议内容，"
            "提取以下关键字段。\n\n"
            "## 输出JSON格式（必须严格使用以下键名）\n"
            "{\n"
            '  "男方姓名": "",\n'
            '  "男方身份证号": "",\n'
            '  "女方姓名": "",\n'
            '  "女方身份证号": "",\n'
            '  "离婚日期": "",\n'
            '  "财产分割约定": "",\n'
            '  "子女抚养": "",\n'
            '  "债务处理": "",\n'
            '  "其他约定": ""\n'
            "}\n\n"
            "## 字段提取说明\n"
            "1. **男方姓名**：男方（丈夫）的姓名\n"
            "2. **男方身份证号**：男方的身份证号码（18位）\n"
            "3. **女方姓名**：女方（妻子）的姓名\n"
            "4. **女方身份证号**：女方的身份证号码（18位）\n"
            "5. **离婚日期**：协议离婚的日期，保持原始格式\n"
            "6. **财产分割约定**：关于夫妻共同财产分割的约定内容，简要概括\n"
            "7. **子女抚养**：关于子女抚养权、抚养费等的约定，简要概括\n"
            "8. **债务处理**：关于夫妻共同债务处理的约定，简要概括\n"
            "9. **其他约定**：其他重要约定内容，简要概括\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记\n"
            "- 不要输出任何其他解释文字\n"
            "- 如果某个字段在图片中不存在或无法识别，保留为空字符串\n"
            "- 离婚协议通常包含双方基本信息、离婚意愿、财产分割、子女抚养等内容\n"
            "- 对于长文本字段（如财产分割约定），提取关键内容即可，不需要完整复制\n"
        ),
        DocumentType.UNKNOWN: (
            "你是一名专业的文档信息提取专家。请分析这张图片，完成以下任务：\n\n"
            "## 任务1：识别文档类型\n"
            "判断这是什么类型的文档（从以下类型中选择）：\n"
            "- 身份证、户口本、结婚证、离婚证、房产证\n"
            "- 发票、购房合同、存量房合同、资金监管协议、离婚协议\n"
            "- 其他\n\n"
            "## 任务2：提取关键字段\n"
            "根据识别的文档类型，提取以下字段（如果存在）：\n"
            "- 身份证：姓名、性别、民族、出生、住址、公民身份号码\n"
            "- 户口本：户主姓名、户号、住址、姓名、与户主关系、公民身份号码\n"
            "- 结婚证：持证人、登记日期、结婚证字号、男方姓名、女方姓名\n"
            "- 离婚证：持证人、性别、出生日期、国籍、身份证件号、登记日期、离婚证字号、原配偶姓名\n"
            "- 房产证：证书号、权利人、共有情况、不动产单元号、房屋地址、建筑面积、用途\n"
            "- 发票：发票代码、发票号码、开票日期、价税合计、购买方名称、销售方名称\n"
            "- 购房合同/存量房合同：合同编号、买受人、出卖人、总价款、签订日期、房屋地址、建筑面积\n"
            "- 资金监管协议：监管金额、监管账户、买方、买方身份证号、卖方、卖方身份证号、监管机构、监管期限、房屋地址\n"
            "- 离婚协议：男方姓名、男方身份证号、女方姓名、女方身份证号、离婚日期、财产分割约定、子女抚养\n"
            "- 其他：提取文档中所有可识别的关键信息\n\n"
            "## 输出JSON格式\n"
            "{\n"
            '  "doc_type": "文档类型",\n'
            '  "confidence": 0.95,\n'
            '  "fields": {\n'
            '    "字段1": "值1",\n'
            '    "字段2": "值2"\n'
            '  }\n'
            "}\n\n"
            "## 重要注意事项\n"
            "- 只输出纯JSON，不要包含markdown代码块标记\n"
            "- 不要输出任何其他解释文字\n"
            "- confidence 表示你对文档类型识别的置信度（0-1之间）\n"
            "- 如果某个字段不存在或无法识别，该字段值保留为空字符串\n"
            "- fields 中只包含实际提取到的字段，不要添加不存在的字段\n"
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
            prompt = self._build_prompt(doc_info, key_list)

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
        merged_fields = {k: "" for k in key_list}
        total_time = 0.0
        pages_processed = 0

        # 获取文档类型的 Prompt（创建一个临时DocumentInfo用于prompt构建）
        temp_doc_info = DocumentInfo(
            image_path="",
            doc_type=doc_type,
            page_type=PageType.CONTENT,  # 多页文档默认使用内容页
        )
        prompt = self._build_prompt(temp_doc_info, key_list)

        for img_path in image_paths[:max_pages]:
            # 检查图片是否存在
            if not Path(img_path).exists():
                logger.warning(f"[VLM层] 多页提取 | 图片不存在: {img_path}")
                continue

            try:
                # 单页提取
                page_start = time.time()
                vlm_response = self._call_vlm(prompt, img_path)
                page_time = time.time() - page_start
                total_time += page_time
                pages_processed += 1

                # 解析响应
                page_fields = self._parse_json_response(vlm_response, key_list)

                # 合并字段（取第一个非空值）
                for key, value in page_fields.items():
                    if value and value.strip() and not merged_fields.get(key):
                        merged_fields[key] = value

                # 统计本页提取到的非空字段数
                non_empty_count = len([v for v in page_fields.values() if v and v.strip()])
                logger.info(
                    f"[VLM层] 多页提取 | 页 {pages_processed}/{min(len(image_paths), max_pages)} | "
                    f"耗时 {page_time:.1f}s | 提取字段 {non_empty_count}"
                )
            except Exception as e:
                logger.warning(f"[VLM层] 多页提取 | 页 {pages_processed + 1} 失败: {e}")
                pages_processed += 1
                continue

        # 判断是否成功
        non_empty_fields = {k: v for k, v in merged_fields.items() if v and v.strip()}
        success = len(non_empty_fields) > 0

        total_time_cost = time.time() - start_time

        logger.info(
            f"[VLM层] 多页提取完成 | 文档类型={doc_type.value} | "
            f"处理页数={pages_processed} | 成功字段={len(non_empty_fields)} | "
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
        """
        # 优先使用文档类型（细化后，如 HOUSEHOLD_REGISTER_CONTENT）的Prompt
        template = self.PROMPT_TEMPLATES.get(doc_info.doc_type)

        # 回退到基础文档类型的Prompt
        if template is None:
            template = self.PROMPT_TEMPLATES.get(self._get_base_doc_type(doc_info.doc_type))

        # 最终回退：通用模板
        if template is None:
            keys_str = "、".join(key_list)
            template = (
                "请从图片中提取以下字段，以JSON格式返回，不要包含markdown标记：{keys}\n"
                "不存在的字段返回空字符串。"
            )
            return template.format(keys=keys_str)
        return template

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
