"""
图片预处理模块

提供图片缩放、增强等预处理功能，用于优化 OCR 引擎的输入质量。

主要功能：
1. 图片缩放到指定尺寸（保持宽高比）
2. 图片格式转换
3. 图片质量优化

作者: Claude
日期: 2026-07-01
"""

import os
import logging
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)


def resize_image(
    image_path: str,
    max_side: int = 4000,
    output_path: Optional[str] = None,
    quality: int = 95,
) -> Tuple[str, bool]:
    """
    缩放图片，使最大边不超过 max_side

    Args:
        image_path: 输入图片路径
        max_side: 最大边长（像素）
        output_path: 输出图片路径（None 则覆盖原图）
        quality: JPEG 质量（1-100）

    Returns:
        (输出路径, 是否缩放)
    """
    try:
        with Image.open(image_path) as img:
            # 转换为 RGB（如果是 RGBA 或其他模式）
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')

            width, height = img.size
            original_size = (width, height)

            # 检查是否需要缩放
            if max(width, height) <= max_side:
                logger.debug(f"图片尺寸 {width}x{height} <= {max_side}，无需缩放")
                return image_path, False

            # 计算缩放比例
            scale = max_side / max(width, height)
            new_width = int(width * scale)
            new_height = int(height * scale)

            logger.info(f"缩放图片: {width}x{height} → {new_width}x{new_height} (scale={scale:.2f})")

            # 高质量缩放
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # 确定输出路径
            if output_path is None:
                # 生成临时文件名
                base, ext = os.path.splitext(image_path)
                output_path = f"{base}_resized{ext}"

            # 保存图片
            img_resized.save(output_path, quality=quality, optimize=True)

            logger.info(f"图片已保存到: {output_path}")

            return output_path, True

    except Exception as e:
        logger.error(f"图片缩放失败: {e}")
        return image_path, False


def ensure_max_size(
    image_path: str,
    max_side: int = 4000,
    temp_dir: Optional[str] = None,
) -> str:
    """
    确保图片最大边不超过 max_side，如果需要缩放则保存到临时目录

    Args:
        image_path: 输入图片路径
        max_side: 最大边长（像素）
        temp_dir: 临时目录（None 则使用系统临时目录）

    Returns:
        处理后的图片路径（可能是原图或缩放后的图）
    """
    # 检查是否需要缩放
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            if max(width, height) <= max_side:
                return image_path  # 无需缩放
    except Exception as e:
        logger.warning(f"无法检查图片尺寸: {e}")
        return image_path

    # 需要缩放，创建临时文件
    if temp_dir is None:
        import tempfile
        temp_dir = tempfile.gettempdir()

    Path(temp_dir).mkdir(parents=True, exist_ok=True)

    # 生成临时文件名
    filename = Path(image_path).name
    temp_path = os.path.join(temp_dir, f"resized_{filename}")

    # 缩放图片
    output_path, resized = resize_image(image_path, max_side, temp_path)

    if resized:
        logger.info(f"图片已缩放到临时目录: {output_path}")
        return output_path
    else:
        return image_path


def get_image_info(image_path: str) -> dict:
    """
    获取图片信息

    Args:
        image_path: 图片路径

    Returns:
        包含 width, height, mode, format 的字典
    """
    try:
        with Image.open(image_path) as img:
            return {
                "width": img.width,
                "height": img.height,
                "mode": img.mode,
                "format": img.format,
                "max_side": max(img.width, img.height),
            }
    except Exception as e:
        logger.error(f"获取图片信息失败: {e}")
        return {}
