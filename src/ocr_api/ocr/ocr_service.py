#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
兼容层 — 实际逻辑已迁移到 src/ocr_three_layer_hybrid/service.py

保留此文件以避免破坏现有 import。
"""

from ocr_three_layer_hybrid.service import (
    OCRService,
    ROUTE_NAMES,
    PIPELINE_STAGES,
    LAYER_COLORS,
)

__all__ = ["OCRService", "ROUTE_NAMES", "PIPELINE_STAGES", "LAYER_COLORS"]
