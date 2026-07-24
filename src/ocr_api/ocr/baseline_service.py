#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基线数据服务：加载和管理基线标注数据
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional


# 默认基线文件路径（支持环境变量覆盖）
DEFAULT_BASELINE_FILE = os.getenv("OCR_BASELINE_FILE", "/Users/dongsun/Github/sample-OCR/baseline_v3/baseline_8cases.json")


class BaselineService:
    """基线数据服务"""

    def __init__(self, baseline_file: str = DEFAULT_BASELINE_FILE):
        self.baseline_file = Path(baseline_file)
        self._data: Optional[Dict] = None

    def _load(self) -> Dict:
        """加载基线数据（带缓存）"""
        if self._data is None:
            with open(self.baseline_file, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        return self._data

    def reload(self):
        """强制重新加载"""
        self._data = None
        return self._load()

    def list_cases(self) -> List[Dict[str, Any]]:
        """
        获取所有业务Case的摘要列表

        Returns:
            [{"case_id": "...", "category": "...", "image_count": N}, ...]
        """
        data = self._load()
        cases = []
        for case in data.get("cases", []):
            case_id = case.get("case_id", "")
            category = case.get("category", "")
            images = case.get("images", [])
            image_count = len(images)
            cases.append({
                "case_id": case_id,
                "category": category,
                "image_count": image_count,
            })
        return cases

    def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定Case的详细信息

        Returns:
            {
                "case_id": "...",
                "category": "...",
                "images": [
                    {
                        "file_path": "...",
                        "file_name": "...",
                        "doc_type": "...",
                        "page_status": "...",
                        "text": "...",
                    },
                    ...
                ]
            }
        """
        data = self._load()
        for case in data.get("cases", []):
            if case.get("case_id") == case_id:
                images = []
                for img in case.get("images", []):
                    parsed = img.get("ocr_result", {}).get("parsed")
                    if not parsed:
                        continue
                    doc_type = parsed.get("doc_type", "")
                    if doc_type == "未知":
                        continue
                    images.append({
                        "file_path": img.get("file_path", ""),
                        "file_name": Path(img.get("file_path", "")).name,
                        "doc_type": doc_type,
                        "expected_type": doc_type,  # alias for process_batch compatibility
                        "page_status": parsed.get("page_status", ""),
                        "text": parsed.get("text", ""),
                        "confidence": parsed.get("confidence", 0),
                    })
                return {
                    "case_id": case.get("case_id", ""),
                    "category": case.get("category", ""),
                    "images": images,
                }
        return None

    def get_all_images(self) -> List[Dict[str, Any]]:
        """
        获取所有可测试的图片（排除未知类型）

        Returns:
            [{"file_path", "file_name", "expected_type", "page_status", "text", "case_id"}, ...]
        """
        data = self._load()
        images = []
        for case in data.get("cases", []):
            case_id = case.get("case_id", "")
            for img in case.get("images", []):
                parsed = img.get("ocr_result", {}).get("parsed")
                if not parsed:
                    continue
                doc_type = parsed.get("doc_type", "")
                if doc_type == "未知" or not doc_type:
                    continue
                images.append({
                    "file_path": img.get("file_path", ""),
                    "file_name": Path(img.get("file_path", "")).name,
                    "expected_type": doc_type,
                    "page_status": parsed.get("page_status", ""),
                    "text": parsed.get("text", ""),
                    "case_id": case_id,
                })
        return images

    def get_stats(self) -> Dict[str, Any]:
        """
        获取基线数据统计

        Returns:
            {
                "total_cases": N,
                "total_images": N,
                "testable_images": N,
                "type_distribution": {"身份证": N, ...},
                "page_status_distribution": {"完整": N, ...},
            }
        """
        data = self._load()
        total_cases = len(data.get("cases", []))
        total_images = 0
        testable_images = 0
        type_dist = {}
        status_dist = {}

        for case in data.get("cases", []):
            for img in case.get("images", []):
                total_images += 1
                parsed = img.get("ocr_result", {}).get("parsed")
                if not parsed:
                    continue
                doc_type = parsed.get("doc_type", "")
                page_status = parsed.get("page_status", "")

                if doc_type and doc_type != "未知":
                    testable_images += 1
                    type_dist[doc_type] = type_dist.get(doc_type, 0) + 1

                if page_status:
                    status_dist[page_status] = status_dist.get(page_status, 0) + 1

        return {
            "total_cases": total_cases,
            "total_images": total_images,
            "testable_images": testable_images,
            "type_distribution": dict(sorted(type_dist.items(), key=lambda x: -x[1])),
            "page_status_distribution": status_dist,
        }
