#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui_metadata 单元测试"""

import pytest

from ocr_three_layer_hybrid.ui_metadata import (
    ROUTE_NAMES,
    PIPELINE_STAGES,
    LAYER_COLORS,
)


class TestRouteNames:
    """ROUTE_NAMES 测试"""

    def test_is_dict(self):
        assert isinstance(ROUTE_NAMES, dict)

    def test_has_vlm_fallback(self):
        assert "vlm_fallback_required" in ROUTE_NAMES

    def test_has_multi_doc_conflict(self):
        assert "multi_doc_conflict_resolution" in ROUTE_NAMES

    def test_all_values_are_strings(self):
        for key, value in ROUTE_NAMES.items():
            assert isinstance(key, str)
            assert isinstance(value, str)
            assert len(value) > 0


class TestPipelineStages:
    """PIPELINE_STAGES 测试"""

    def test_is_list(self):
        assert isinstance(PIPELINE_STAGES, list)

    def test_not_empty(self):
        assert len(PIPELINE_STAGES) > 0

    def test_each_stage_has_required_keys(self):
        for stage in PIPELINE_STAGES:
            assert "id" in stage, f"缺少 id: {stage}"
            assert "name" in stage, f"缺少 name: {stage}"
            assert "title" in stage, f"缺少 title: {stage}"
            assert "keywords" in stage, f"缺少 keywords: {stage}"

    def test_stage_ids_unique(self):
        ids = [s["id"] for s in PIPELINE_STAGES]
        assert len(ids) == len(set(ids)), "存在重复的 stage id"


class TestLayerColors:
    """LAYER_COLORS 测试"""

    def test_has_rule(self):
        assert "rule" in LAYER_COLORS

    def test_has_vlm(self):
        assert "vlm" in LAYER_COLORS

    def test_has_position(self):
        assert "position" in LAYER_COLORS

    def test_colors_are_hex(self):
        import re
        hex_pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
        for key, color in LAYER_COLORS.items():
            assert hex_pattern.match(color), f"{key} 颜色不是有效的 HEX: {color}"
