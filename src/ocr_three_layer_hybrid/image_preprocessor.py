"""
图片预处理模块

提供图片缩放、增强等预处理功能，用于优化 OCR 引擎的输入质量。

主要功能：
1. 图片缩放到指定尺寸（保持宽高比）
2. 图片格式转换
3. 图片质量优化
4. 图像增强（去噪、纠偏、对比度增强、二值化）

作者: Claude
日期: 2026-07-01 / 2026-07-02 (增强)
"""

import os
import logging
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image
import numpy as np

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

logger = logging.getLogger(__name__)

if not CV2_AVAILABLE:
    logger.warning("OpenCV 不可用，图像增强功能将被禁用。请安装: pip install opencv-python")


def resize_image(
    image_path: str,
    max_side: int = 2000,
    output_path: Optional[str] = None,
    quality: int = 75,
) -> Tuple[str, bool]:
    """
    缩放图片，使最大边不超过 max_side

    Args:
        image_path: 输入图片路径
        max_side: 最大边长（像素），默认2000px（经测试为准确率与性能的最佳平衡点）
        output_path: 输出图片路径（None 则覆盖原图）
        quality: JPEG 质量（1-100），默认75%（经测试为文件大小与准确率的最佳平衡点）

    Returns:
        (输出路径, 是否缩放)
    """
    try:
        with Image.open(image_path) as img:
            # 转换为 RGB（如果是 RGBA 或其他模式）
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')

            width, height = img.size

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
    max_side: int = 2000,
    temp_dir: Optional[str] = None,
) -> str:
    """
    确保图片最大边不超过 max_side，如果需要缩放则保存到临时目录

    Args:
        image_path: 输入图片路径
        max_side: 最大边长（像素），默认2000px（经测试为准确率与性能的最佳平衡点）
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


# =============================================================================
# 高级图像增强功能
# =============================================================================

class ImageEnhancer:
    """
    图像增强处理器

    提供去噪、纠偏、对比度增强、二值化等功能，用于改善 OCR 识别质量。

    参考: AI-OCR 项目的 image_enhancer.py
    """

    def __init__(
        self,
        enable_denoise: bool = True,
        enable_deskew: bool = True,
        enable_contrast: bool = True,
        enable_binarize: bool = False,
        binarize_method: str = "adaptive",
    ):
        """
        初始化图像增强器

        Args:
            enable_denoise: 是否启用去噪
            enable_deskew: 是否启用纠偏
            enable_contrast: 是否启用对比度增强
            enable_binarize: 是否启用二值化（默认关闭，会丢失灰度信息）
            binarize_method: 二值化方法 ("adaptive" 或 "otsu")
        """
        if not CV2_AVAILABLE:
            raise RuntimeError("OpenCV 不可用，无法使用图像增强功能")

        self.enable_denoise = enable_denoise
        self.enable_deskew = enable_deskew
        self.enable_contrast = enable_contrast
        self.enable_binarize = enable_binarize
        self.binarize_method = binarize_method

    def enhance(self, image: np.ndarray) -> np.ndarray:
        """
        图像增强流水线

        Args:
            image: 输入图像（BGR numpy array）

        Returns:
            增强后的图像
        """
        result = image.copy()

        if self.enable_denoise:
            result = self.denoise(result)

        if self.enable_deskew:
            result = self.deskew(result)

        if self.enable_contrast:
            result = self.enhance_contrast(result)

        if self.enable_binarize:
            result = self.binarize(result, method=self.binarize_method)
            # 二值化后转为 BGR 三通道（保持格式一致）
            if len(result.shape) == 2:
                result = cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)

        return result

    def denoise(self, image: np.ndarray) -> np.ndarray:
        """
        去噪

        使用 fastNlMeansDenoisingColored 算法，在去除噪声的同时保留文字边缘。

        Args:
            image: 输入图像（BGR）

        Returns:
            去噪后的图像
        """
        return cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)

    def deskew(self, image: np.ndarray) -> np.ndarray:
        """
        纠偏

        使用 OTSU 阈值自动判断前景/背景，计算最小面积矩形，旋转纠偏。
        对于白底黑字文档，前景是灰度值较低的像素（深色文字）。

        Args:
            image: 输入图像（BGR）

        Returns:
            纠偏后的图像
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # 使用 OTSU 阈值自动判断前景/背景
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # 获取前景像素坐标（白色部分，即原始图像中的深色文字）
        coords = np.column_stack(np.where(binary > 0))

        if len(coords) < 100:
            # 前景像素太少，可能是纯色图像，跳过纠偏
            return image

        # 计算最小面积矩形
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]

        # 调整角度
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        # 小角度偏差不纠偏（< 1.0度，更保守）
        if abs(angle) < 1.0:
            logger.debug(f"纠偏角度 {angle:.2f}° < 1.0°，跳过纠偏")
            return image

        logger.debug(f"纠偏角度: {angle:.2f}°")

        # 旋转图像
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(
            image, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )

    def enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """
        增强对比度（CLAHE）

        使用自适应直方图均衡化（CLAHE），增强文字与背景的对比度。

        Args:
            image: 输入图像（BGR）

        Returns:
            对比度增强后的图像
        """
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)

    def binarize(self, image: np.ndarray, method: str = "adaptive") -> np.ndarray:
        """
        二值化

        Args:
            image: 输入图像（BGR）
            method: 二值化方法
                - "adaptive": 自适应阈值（适合光照不均匀）
                - "otsu": OTSU 自动阈值（适合光照均匀）

        Returns:
            二值化后的图像（单通道灰度）
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        if method == "adaptive":
            return cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                11, 2
            )
        elif method == "otsu":
            _, binary = cv2.threshold(
                gray, 0, 255,
                cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
            return binary
        else:
            raise ValueError(f"未知的二值化方法: {method}，支持 adaptive / otsu")


def enhance_image(
    image_path: str,
    output_path: Optional[str] = None,
    enable_denoise: bool = True,
    enable_deskew: bool = True,
    enable_contrast: bool = True,
    enable_binarize: bool = False,
) -> str:
    """
    对图片进行增强处理

    便捷函数，封装 ImageEnhancer 的使用。

    Args:
        image_path: 输入图片路径
        output_path: 输出图片路径（None 则生成临时文件）
        enable_denoise: 是否启用去噪
        enable_deskew: 是否启用纠偏
        enable_contrast: 是否启用对比度增强
        enable_binarize: 是否启用二值化

    Returns:
        处理后的图片路径
    """
    if not CV2_AVAILABLE:
        logger.warning("OpenCV 不可用，跳过图像增强")
        return image_path

    try:
        # 读取图片
        image = cv2.imread(image_path)
        if image is None:
            logger.error(f"无法读取图片: {image_path}")
            return image_path

        # 创建增强器并处理
        enhancer = ImageEnhancer(
            enable_denoise=enable_denoise,
            enable_deskew=enable_deskew,
            enable_contrast=enable_contrast,
            enable_binarize=enable_binarize,
        )
        enhanced = enhancer.enhance(image)

        # 确定输出路径
        if output_path is None:
            import tempfile
            temp_dir = tempfile.gettempdir()
            Path(temp_dir).mkdir(parents=True, exist_ok=True)
            filename = Path(image_path).name
            output_path = os.path.join(temp_dir, f"enhanced_{filename}")

        # 保存处理后的图片
        cv2.imwrite(output_path, enhanced)
        logger.info(f"图像增强完成: {output_path}")

        return output_path

    except Exception as e:
        logger.error(f"图像增强失败: {e}")
        return image_path
