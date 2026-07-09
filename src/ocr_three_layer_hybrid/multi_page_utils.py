#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多页文档处理公共工具

提取 service.py 和 vlm_layer.py 中共同的 iterate→extract→merge 逻辑，
避免两处各实现一遍相同的循环+合并模式。

核心函数：
- iterate_extract_merge(): 通用逐页提取+合并循环
- determine_extraction_success(): 判断合并后提取是否成功
"""

import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def iterate_extract_merge(
    image_paths: List[str],
    extract_fn: Callable[[str, int], Optional[Dict[str, str]]],
    max_pages: int = 15,
    log_context: str = "",
) -> Tuple[Dict[str, str], int]:
    """多页文档的通用 iterate→extract→merge 循环

    逐页调用 extract_fn 提取字段，使用"第一个非空值"策略合并。
    被 service.py 和 vlm_layer.py 共同使用，避免重复实现循环+合并逻辑。

    Args:
        image_paths: 图片路径列表
        extract_fn: 单页提取函数，签名 (image_path, page_idx) -> fields_dict。
                    返回 None 表示该页跳过（如封面页、不存在的文件等）。
                    返回空 dict 表示提取了但没有字段值。
        max_pages: 最大处理页数（默认15，性能优化）
        log_context: 日志上下文（用于区分调用来源，如 "VLM层" 或 "多页"）

    Returns:
        (merged_fields, pages_processed)
        - merged_fields: 合并后的字段字典（取第一个非空值）
        - pages_processed: 实际处理的页数（含失败页）
    """
    from ocr_three_layer_hybrid.json_utils import merge_fields_first_nonempty

    merged_fields: Dict[str, str] = {}
    pages_processed = 0

    for page_idx, img_path in enumerate(image_paths[:max_pages]):
        # 检查图片是否存在
        if not Path(img_path).exists():
            logger.warning("[%s] 图片不存在: %s", log_context, img_path)
            continue

        try:
            page_fields = extract_fn(img_path, page_idx)
            pages_processed += 1

            # 合并字段（取第一个非空值）
            if page_fields:
                merge_fields_first_nonempty(merged_fields, page_fields)
        except Exception as e:
            logger.warning("[%s] 页 %d 提取失败 %s: %s", log_context, page_idx, img_path, e)
            pages_processed += 1

    return merged_fields, pages_processed


def determine_extraction_success(
    merged_fields: Dict[str, str],
    required_field_names: Optional[List[str]] = None,
) -> bool:
    """判断多页合并后的提取是否成功

    Args:
        merged_fields: 合并后的字段字典
        required_field_names: 必填字段名称列表。
                              如果提供，则所有必填字段都有非空值才算成功。
                              如果不提供，只要有任一非空字段就算成功。

    Returns:
        是否成功
    """
    if required_field_names:
        return all(
            merged_fields.get(f, "").strip()
            for f in required_field_names
        )
    return any(v and v.strip() for v in merged_fields.values())
