#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""image_preprocessor 单元测试"""

import os
import tempfile
import pytest
import numpy as np
from PIL import Image

from ocr_three_layer_hybrid.image_preprocessor import (
    resize_image,
    ensure_max_size,
    get_image_info,
    ImageEnhancer,
    enhance_image,
    CV2_AVAILABLE,
)

skip_no_cv2 = pytest.mark.skipif(not CV2_AVAILABLE, reason="OpenCV not available")


class TestResizeImage:
    """resize_image 测试"""

    def _create_test_image(self, width, height, suffix=".jpg"):
        """创建测试图片"""
        f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        img = Image.new("RGB", (width, height), color=(255, 255, 255))
        img.save(f.name)
        f.close()
        return f.name

    def test_small_image_not_resized(self):
        """小图片不缩放"""
        path = self._create_test_image(100, 100)
        try:
            result_path, resized = resize_image(path, max_side=2000)
            assert resized is False
            assert result_path == path
        finally:
            os.unlink(path)

    def test_large_image_resized(self):
        """大图片缩放"""
        path = self._create_test_image(4000, 3000)
        try:
            result_path, resized = resize_image(path, max_side=2000)
            assert resized is True
            # 验证缩放后尺寸
            with Image.open(result_path) as img:
                assert max(img.size) <= 2000
            # 清理输出文件
            if result_path != path:
                os.unlink(result_path)
        finally:
            os.unlink(path)

    def test_output_path_specified(self):
        """指定输出路径"""
        path = self._create_test_image(4000, 3000)
        output = tempfile.mktemp(suffix=".jpg")
        try:
            result_path, resized = resize_image(path, max_side=2000, output_path=output)
            assert resized is True
            assert result_path == output
            assert os.path.exists(output)
        finally:
            os.unlink(path)
            if os.path.exists(output):
                os.unlink(output)

    def test_quality_parameter(self):
        """质量参数"""
        path = self._create_test_image(4000, 3000)
        try:
            result_path, resized = resize_image(path, max_side=2000, quality=50)
            assert resized is True
            if result_path != path:
                os.unlink(result_path)
        finally:
            os.unlink(path)


class TestEnsureMaxSize:
    """ensure_max_size 测试"""

    def _create_test_image(self, width, height):
        f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        img = Image.new("RGB", (width, height), color=(255, 255, 255))
        img.save(f.name)
        f.close()
        return f.name

    def test_small_image_returns_original(self):
        """小图片返回原路径"""
        path = self._create_test_image(100, 100)
        try:
            result = ensure_max_size(path, max_side=2000)
            assert result == path
        finally:
            os.unlink(path)

    def test_large_image_returns_processed(self):
        """大图片返回处理后路径"""
        path = self._create_test_image(4000, 3000)
        try:
            result = ensure_max_size(path, max_side=2000)
            assert os.path.exists(result)
            with Image.open(result) as img:
                assert max(img.size) <= 2000
            if result != path:
                os.unlink(result)
        finally:
            os.unlink(path)


class TestGetImageInfo:
    """get_image_info 测试"""

    def test_valid_image(self):
        """有效图片"""
        f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        img = Image.new("RGB", (800, 600), color=(255, 0, 0))
        img.save(f.name)
        f.close()

        try:
            info = get_image_info(f.name)
            assert info["width"] == 800
            assert info["height"] == 600
            assert info["mode"] == "RGB"
            assert info["max_side"] == 800
        finally:
            os.unlink(f.name)

    def test_invalid_path(self):
        """无效路径返回空字典"""
        info = get_image_info("/nonexistent/image.jpg")
        assert info == {}


class TestResizeAspectRatio:
    """缩放保持宽高比测试"""

    def test_landscape_preserved(self):
        """横向图片保持比例"""
        f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        img = Image.new("RGB", (4000, 2000), color=(255, 255, 255))
        img.save(f.name)
        f.close()

        try:
            result_path, resized = resize_image(f.name, max_side=2000)
            assert resized is True
            with Image.open(result_path) as result_img:
                w, h = result_img.size
                # 宽高比应约为 2:1
                assert abs(w / h - 2.0) < 0.1
            if result_path != f.name:
                os.unlink(result_path)
        finally:
            os.unlink(f.name)


class TestResizeImageEdgeCases:
    """resize_image 边界情况测试"""

    def _create_test_image(self, width, height, mode="RGB"):
        f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        if mode == "RGBA":
            # JPEG不支持RGBA，保存为PNG
            f.close()
            os.unlink(f.name)
            f_name = tempfile.mktemp(suffix=".png")
            img = Image.new(mode, (width, height), color=(255, 255, 255, 128))
            img.save(f_name)
            return f_name
        else:
            if mode == "L":
                color = 255  # 灰度图用整数颜色值
            else:
                color = (255, 255, 255)
            img = Image.new(mode, (width, height), color=color)
            img.save(f.name)
            f.close()
            return f.name

    def test_rgba_image_converted(self):
        """RGBA图片转换为RGB后处理"""
        path = self._create_test_image(4000, 3000, mode="RGBA")
        try:
            result_path, resized = resize_image(path, max_side=2000)
            assert resized is True
            with Image.open(result_path) as img:
                assert img.mode == "RGB"
                assert max(img.size) <= 2000
            if result_path != path:
                os.unlink(result_path)
        finally:
            os.unlink(path)

    def test_grayscale_image(self):
        """灰度图片正常处理"""
        path = self._create_test_image(100, 100, mode="L")
        try:
            result_path, resized = resize_image(path, max_side=2000)
            assert resized is False  # 不需要缩放
            assert result_path == path
        finally:
            os.unlink(path)

    def test_corrupt_image_returns_original(self):
        """损坏的图片返回原路径，resized=False"""
        f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        f.write(b"not a valid image")
        f.flush()
        path = f.name
        f.close()

        try:
            result_path, resized = resize_image(path, max_side=2000)
            assert resized is False
            assert result_path == path
        finally:
            os.unlink(path)


class TestEnsureMaxSizeEdgeCases:
    """ensure_max_size 边界情况测试"""

    def _create_test_image(self, width, height):
        f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        img = Image.new("RGB", (width, height), color=(255, 255, 255))
        img.save(f.name)
        f.close()
        return f.name

    def test_custom_temp_dir(self):
        """使用自定义临时目录"""
        path = self._create_test_image(4000, 3000)
        temp_dir = tempfile.mkdtemp()
        try:
            result = ensure_max_size(path, max_side=2000, temp_dir=temp_dir)
            assert os.path.exists(result)
            assert result.startswith(temp_dir)
            with Image.open(result) as img:
                assert max(img.size) <= 2000
            if result != path:
                os.unlink(result)
        finally:
            os.unlink(path)
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_corrupt_image_returns_original(self):
        """无法检查尺寸时返回原路径"""
        f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        f.write(b"not a valid image")
        f.flush()
        path = f.name
        f.close()

        try:
            result = ensure_max_size(path, max_side=2000)
            assert result == path
        finally:
            os.unlink(path)


@skip_no_cv2
class TestImageEnhancer:
    """ImageEnhancer 测试（需要 OpenCV）"""

    def _create_test_image_bgr(self, width=100, height=100):
        """创建 BGR 测试图像"""
        import cv2
        return np.full((height, width, 3), 128, dtype=np.uint8)

    def test_init_default_params(self):
        """默认参数初始化"""
        enhancer = ImageEnhancer()
        assert enhancer.enable_denoise is True
        assert enhancer.enable_deskew is True
        assert enhancer.enable_contrast is True
        assert enhancer.enable_binarize is False

    def test_init_custom_params(self):
        """自定义参数初始化"""
        enhancer = ImageEnhancer(
            enable_denoise=False,
            enable_deskew=False,
            enable_contrast=False,
            enable_binarize=True,
            binarize_method="otsu",
        )
        assert enhancer.enable_denoise is False
        assert enhancer.enable_binarize is True
        assert enhancer.binarize_method == "otsu"

    def test_enhance_pipeline_all_disabled(self):
        """全部禁用时返回原图副本"""
        enhancer = ImageEnhancer(
            enable_denoise=False,
            enable_deskew=False,
            enable_contrast=False,
            enable_binarize=False,
        )
        image = self._create_test_image_bgr()
        result = enhancer.enhance(image)
        np.testing.assert_array_equal(result, image)
        # 确保是副本而非引用
        assert result is not image

    def test_enhance_with_denoise_only(self):
        """仅启用去噪"""
        enhancer = ImageEnhancer(
            enable_denoise=True,
            enable_deskew=False,
            enable_contrast=False,
            enable_binarize=False,
        )
        image = self._create_test_image_bgr()
        result = enhancer.enhance(image)
        assert result.shape == image.shape
        assert result.dtype == np.uint8

    def test_enhance_with_contrast_only(self):
        """仅启用对比度增强"""
        enhancer = ImageEnhancer(
            enable_denoise=False,
            enable_deskew=False,
            enable_contrast=True,
            enable_binarize=False,
        )
        image = self._create_test_image_bgr()
        result = enhancer.enhance(image)
        assert result.shape == image.shape

    def test_enhance_with_binarize_adaptive(self):
        """自适应二值化"""
        # 创建有明显前景/背景的图像
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        image[:50, :] = 255  # 上半部分白色

        enhancer = ImageEnhancer(
            enable_denoise=False,
            enable_deskew=False,
            enable_contrast=False,
            enable_binarize=True,
            binarize_method="adaptive",
        )
        result = enhancer.enhance(image)
        # 二值化后转为BGR三通道
        assert len(result.shape) == 3
        assert result.shape[2] == 3

    def test_enhance_with_binarize_otsu(self):
        """OTSU二值化"""
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        image[:50, :] = 255

        enhancer = ImageEnhancer(
            enable_denoise=False,
            enable_deskew=False,
            enable_contrast=False,
            enable_binarize=True,
            binarize_method="otsu",
        )
        result = enhancer.enhance(image)
        assert len(result.shape) == 3
        assert result.shape[2] == 3

    def test_binarize_unknown_method_raises(self):
        """未知二值化方法抛出 ValueError"""
        enhancer = ImageEnhancer()
        image = self._create_test_image_bgr()
        with pytest.raises(ValueError, match="未知的二值化方法"):
            enhancer.binarize(image, method="unknown")

    def test_deskew_small_angle_skipped(self):
        """小角度（< 1°）不纠偏"""
        import cv2
        # 创建纯白图像（无文字，前景像素极少）
        image = np.full((100, 100, 3), 255, dtype=np.uint8)
        enhancer = ImageEnhancer(enable_deskew=True)
        result = enhancer.deskew(image)
        # 前景太少，应返回原图
        np.testing.assert_array_equal(result, image)

    def test_enhance_full_pipeline(self):
        """完整增强流水线"""
        # 创建测试图像：有文字样式的图案
        image = np.full((200, 200, 3), 255, dtype=np.uint8)
        # 画一些黑色"文字"块
        import cv2
        cv2.rectangle(image, (20, 30), (180, 50), (0, 0, 0), -1)
        cv2.rectangle(image, (20, 70), (150, 90), (0, 0, 0), -1)
        cv2.rectangle(image, (20, 110), (170, 130), (0, 0, 0), -1)

        enhancer = ImageEnhancer(
            enable_denoise=True,
            enable_deskew=True,
            enable_contrast=True,
            enable_binarize=False,
        )
        result = enhancer.enhance(image)
        assert result.shape == image.shape
        assert result.dtype == np.uint8


@skip_no_cv2
class TestEnhanceImageConvenience:
    """enhance_image 便捷函数测试"""

    def _create_test_image(self, width=100, height=100):
        f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        img = Image.new("RGB", (width, height), color=(200, 200, 200))
        img.save(f.name)
        f.close()
        return f.name

    def test_enhance_image_basic(self):
        """基本增强处理"""
        path = self._create_test_image()
        try:
            result = enhance_image(path)
            assert os.path.exists(result)
            if result != path:
                os.unlink(result)
        finally:
            os.unlink(path)

    def test_enhance_image_custom_output(self):
        """指定输出路径"""
        path = self._create_test_image()
        output = tempfile.mktemp(suffix=".jpg")
        try:
            result = enhance_image(path, output_path=output)
            assert result == output
            assert os.path.exists(output)
        finally:
            os.unlink(path)
            if os.path.exists(output):
                os.unlink(output)

    def test_enhance_image_invalid_input(self):
        """无效输入返回原路径"""
        result = enhance_image("/nonexistent/image.jpg")
        assert result == "/nonexistent/image.jpg"

    def test_enhance_image_custom_params(self):
        """自定义参数"""
        path = self._create_test_image()
        try:
            result = enhance_image(
                path,
                enable_denoise=False,
                enable_deskew=False,
                enable_contrast=True,
                enable_binarize=False,
            )
            assert os.path.exists(result)
            if result != path:
                os.unlink(result)
        finally:
            os.unlink(path)
