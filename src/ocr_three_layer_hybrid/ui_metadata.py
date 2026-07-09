#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UI 元数据常量（供前端流程图使用）

注意：这些常量仅用于 API 响应，不属于核心 OCR 逻辑。
API 层可以选择使用或不使用这些常量。
"""

# Pipeline阶段名称映射
ROUTE_NAMES = {
    "multi_doc_conflict_resolution": "阶段0: 多文档冲突检测",
    "standard_certificate": "阶段1: 标准证件强信号",
    "backup_certificate": "阶段1.5: 备选强信号",
    "additional_backup": "阶段1.6: 更多备选信号",
    "standard_document": "阶段2: 标准单证强信号",
    "standard_document_weak": "阶段2: 弱信号组合",
    "contract_field_combination": "阶段3: 合同字段组合",
    "vlm_fallback_required": "Rule层字段级VLM重试",
}

# Pipeline阶段列表（用于流程图显示）
PIPELINE_STAGES = [
    {
        "id": "stage0",
        "name": "阶段0",
        "title": "多文档冲突检测",
        "keywords": "买受人+出卖人+房屋类型",
    },
    {
        "id": "stage1",
        "name": "阶段1",
        "title": "标准证件强信号",
        "keywords": "公民身份号码、常住人口登记卡等",
    },
    {
        "id": "stage1_5",
        "name": "阶段1.5",
        "title": "备选强信号",
        "keywords": "户口簿+户主、持证人+登记日期",
    },
    {
        "id": "stage1_6",
        "name": "阶段1.6",
        "title": "更多备选信号",
        "keywords": "户别+户主姓名、结婚证+登记机关",
    },
    {
        "id": "stage2",
        "name": "阶段2",
        "title": "标准单证强信号",
        "keywords": "发票代码+发票号码",
    },
    {
        "id": "stage3",
        "name": "阶段3",
        "title": "合同字段组合",
        "keywords": "买受人+出卖人+价款",
    },
]

# 提取层颜色映射
LAYER_COLORS = {
    "rule": "#10b981",  # 绿色
    "position": "#8b5cf6",  # 紫色
    "vlm": "#3b82f6",  # 蓝色
    "none": "#6b7280",  # 灰色
}
