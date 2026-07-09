#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第2A+层：位置标注提取器
使用 PaddleOCR 坐标信息做基于空间位置的字段提取

当前支持：
- 户口本首页（户别、户主姓名、户号、住址）

设计原理：
- PP-OCRv6 输出文本+坐标，正则提取在列错位场景下失败
- 位置标注利用坐标信息，在标签右侧同行搜索数据，避免列合并错误
- 文档相对坐标（归一化到文档边界），兼容不同尺寸照片

参考：analysis/analysis_20260628_户口本首页位置标注原型实施报告.md
"""

import logging
import re
import threading
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class OcrItem:
    """OCR识别项（文本+坐标）"""

    text: str
    score: float
    # 图片相对坐标 (0-1)
    x1: float
    y1: float
    x2: float
    y2: float
    # 文档相对坐标 (0-1)
    rx1: float = 0.0
    ry1: float = 0.0
    rx2: float = 0.0
    ry2: float = 0.0

    @property
    def rcx(self) -> float:
        """文档相对X中心"""
        return (self.rx1 + self.rx2) / 2

    @property
    def rcy(self) -> float:
        """文档相对Y中心"""
        return (self.ry1 + self.ry2) / 2


class HouseholdPositionExtractor:
    """户口本首页位置标注提取器

    通过 PaddleOCR 获取文本坐标，利用空间位置关系提取首页字段。
    可修复：列错位、标签+数据合并、长地址跨列等问题。
    不可修复：OCR字符识别错误（如"王龙晨露"列合并），需Rule层VLM重试。

    Usage:
        extractor = HouseholdPositionExtractor()
        fields = extractor.extract(image_path)
        # fields = {"户别": "非农业家庭户", "户主姓名": "王晨露", ...}
    """

    # 字段标签正则模式
    LABEL_PATTERNS = {
        "户主姓名": r"户主\s*姓\s*名",
        "户号": r"户\s*号",
        "住址": r"住\s*址",
        "户别": r"户\s*别",
    }

    # 标签前缀片段（用于从合并文本中剥离标签）
    LABEL_FRAGMENTS = [
        "户主姓名",
        "户主姓",
        "户姓名",
        "户主",
        "户号",
        "户 号",
        "住址",
        "住 址",
        "户别",
        "户 别",
        "别",
    ]

    # 首页表格行Y范围（文档相对坐标，基于PaddleOCR实测校准）
    ROW1_Y = (0.55, 0.62)  # 户别 + 户主姓名
    ROW2_Y = (0.62, 0.70)  # 户号 + 住址

    # 列X范围
    LEFT_COL_X = (0.10, 0.40)  # 左列（户别、户号）
    RIGHT_COL_X = (0.45, 0.95)  # 右列（户主姓名、住址）

    # 合并参数
    ROW_TOLERANCE = 0.030  # 同行Y容差（两行间距约0.04，0.03可区分）
    MERGE_GAP = 0.08  # 小间隙阈值（相邻文本合并）
    BIG_GAP_THRESHOLD = 0.25  # 大间隙阈值（跨页边界，停止合并）

    # 地址后缀模式（短片段在开头时需移到末尾）
    ADDR_SUFFIX_PATTERNS = [
        r"^\d+排\d+号",  # 6排8号
        r"^\d+号$",  # 74号
        r"^[一-鿿]{1,4}\d+号",  # 曹台子74号
    ]

    def __init__(self):
        self._ocr = None  # 延迟初始化
        self._ocr_lock = threading.Lock()  # 线程安全锁

    def _get_ocr(self):
        """获取 PaddleOCR 实例（延迟初始化，首次调用约需10秒）"""
        if self._ocr is None:
            with self._ocr_lock:
                # 双重检查锁定模式
                if self._ocr is None:
                    try:
                        from paddleocr import PaddleOCR

                        logger.info("初始化 PaddleOCR（首次加载需约10秒）...")
                        self._ocr = PaddleOCR(lang="ch")
                        logger.info("PaddleOCR 初始化完成")
                    except Exception as e:
                        logger.error("PaddleOCR 初始化失败: %s", e)
                        raise
        return self._ocr

    def _parse_ocr(
        self, image_path: str
    ) -> Tuple[List[OcrItem], Tuple[float, float, float, float]]:
        """
        运行 PaddleOCR 并解析输出为 OcrItem 列表

        Returns:
            (items, doc_bounds): 文本项列表 + 文档边界 (min_x, min_y, max_x, max_y) 归一化值
        """
        ocr = self._get_ocr()
        results = list(ocr.predict(input=image_path))
        if not results:
            return [], (0, 0, 1, 1)
        r = results[0]

        from PIL import Image

        with Image.open(image_path) as pil_img:
            img_w, img_h = pil_img.size

        # 文档范围：全部文本的边界框
        all_boxes = r["rec_boxes"]
        if len(all_boxes) == 0:
            return [], (0, 0, 1, 1)

        min_x = float(min(b[0] for b in all_boxes))
        min_y = float(min(b[1] for b in all_boxes))
        max_x = float(max(b[2] for b in all_boxes))
        max_y = float(max(b[3] for b in all_boxes))
        doc_w = max(1, max_x - min_x)
        doc_h = max(1, max_y - min_y)

        items = []
        for text, box, score in zip(r["rec_texts"], r["rec_boxes"], r["rec_scores"]):
            x1, y1, x2, y2 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
            items.append(
                OcrItem(
                    text=text,
                    score=float(score),
                    x1=x1 / img_w,
                    y1=y1 / img_h,
                    x2=x2 / img_w,
                    y2=y2 / img_h,
                    rx1=(x1 - min_x) / doc_w,
                    ry1=(y1 - min_y) / doc_h,
                    rx2=(x2 - min_x) / doc_w,
                    ry2=(y2 - min_y) / doc_h,
                )
            )

        # 合并同行相邻文本（修复OCR拆分标签的情况，如"户"+"别"→"户别"）
        items = self._merge_adjacent_items(items)

        doc_bounds = (min_x / img_w, min_y / img_h, max_x / img_w, max_y / img_h)
        return items, doc_bounds

    def _merge_adjacent_items(self, items: List[OcrItem]) -> List[OcrItem]:
        """
        合并同行相邻文本项（gap < 0.05 且同行）

        解决OCR拆分标签的问题，如"户"+"别非农业家庭户"→"户别非农业家庭户"
        """
        if not items:
            return items

        # 按rcx排序
        sorted_items = sorted(items, key=lambda i: i.rcx)
        merged = []
        current = sorted_items[0]

        for next_item in sorted_items[1:]:
            gap = next_item.rx1 - current.rx2
            y_diff = abs(next_item.rcy - current.rcy)

            # 同行（y差 < 0.02）且相邻（gap < 0.05）→ 合并
            if y_diff < 0.02 and gap < 0.05 and gap >= -0.1:
                # 合并文本和坐标
                current = OcrItem(
                    text=current.text + next_item.text,
                    score=min(current.score, next_item.score),
                    x1=min(current.x1, next_item.x1),
                    y1=min(current.y1, next_item.y1),
                    x2=max(current.x2, next_item.x2),
                    y2=max(current.y2, next_item.y2),
                    rx1=min(current.rx1, next_item.rx1),
                    ry1=min(current.ry1, next_item.ry1),
                    rx2=max(current.rx2, next_item.rx2),
                    ry2=max(current.ry2, next_item.ry2),
                )
            else:
                merged.append(current)
                current = next_item

        merged.append(current)
        return merged

    def is_first_page(self, items: List[OcrItem]) -> bool:
        """检测是否为户口本首页（通过关键词判断）"""
        full_text = " ".join(item.text for item in items)
        keywords = ["注意事项", "居民户口簿具有", "户口登记机关进行户籍"]
        return any(kw in full_text for kw in keywords)

    def _strip_label(self, text: str) -> str:
        """剥离标签前缀（处理OCR合并标签+数据的情况）"""
        for frag in self.LABEL_FRAGMENTS:
            if text.startswith(frag):
                text = text[len(frag) :]
                break
        # "非农业家庭户口" → "非农业家庭户"
        if text.endswith("口") and len(text) > 3 and "户" in text[-3:-1]:
            text = text[:-1]
        return text.strip()

    def _fix_address_order(self, text: str) -> str:
        """
        修正地址顺序：中文地址从大到小（省→市→区→街→号）。
        如果短地址片段（门牌号）出现在开头，移到末尾。
        例："曹台子74号安徽省蚌埠市..." → "安徽省蚌埠市...曹台子74号"
        """
        for pat in self.ADDR_SUFFIX_PATTERNS:
            m = re.match(pat, text)
            if m:
                prefix = m.group(0)
                rest = text[len(prefix) :]
                if len(rest) >= 6:
                    return rest + prefix
        return text

    def _find_label(
        self, items: List[OcrItem], field_name: str, y_range: Tuple[float, float]
    ) -> Optional[OcrItem]:
        """在指定Y范围内查找字段标签"""
        pattern = self.LABEL_PATTERNS.get(field_name)
        if not pattern:
            return None

        candidates = []
        for item in items:
            if y_range[0] <= item.rcy <= y_range[1]:
                if re.search(pattern, item.text):
                    candidates.append(item)

        if not candidates:
            return None
        # 优先选择最短匹配（纯标签而非标签+数据）
        candidates.sort(key=lambda i: (len(i.text), -i.score))
        return candidates[0]

    def _is_label(self, text: str, exclude_field: Optional[str] = None) -> bool:
        """判断文本是否为标签（而非数据）"""
        for fname, pat in self.LABEL_PATTERNS.items():
            if fname == exclude_field:
                continue
            if re.search(pat, text):
                return True
        if exclude_field:
            pat2 = self.LABEL_PATTERNS.get(exclude_field)
            if pat2 and re.fullmatch(pat2, text):
                return True
        return False

    def _extract_field(
        self,
        all_items: List[OcrItem],
        field_name: str,
        y_range: Tuple[float, float],
        data_x_range: Tuple[float, float],
    ) -> str:
        """
        提取单个字段

        策略：
        1a. 标签本身包含数据（OCR合并标签+数据，如"户号7314"）
        1b. 标签右侧同行搜索数据项
        2.  在指定Y范围内直接搜索（不依赖标签）
        """
        label = self._find_label(all_items, field_name, y_range)

        if label:
            # 策略1a：标签本身包含数据
            label_stripped = self._strip_label(label.text)
            if (
                label_stripped
                and len(label_stripped) >= 1
                and not self._is_label(label_stripped)
            ):
                logger.debug("[%s] 策略1a: 标签包含数据 '%s'", field_name, label_stripped)
                return label_stripped

            # 策略1b：标签右侧同行搜索
            data_items = []
            for item in all_items:
                # 用label的rcy做同行判断（避免链式断裂）
                if abs(item.rcy - label.rcy) > self.ROW_TOLERANCE:
                    continue
                if item.rcx <= label.rcx + 0.02:
                    continue
                if self._is_label(item.text, exclude_field=field_name):
                    continue
                if data_x_range[0] <= item.rcx <= data_x_range[1]:
                    data_items.append(item)

            if data_items:
                merged = self._merge_items(data_items, label.rcy)
                merged = self._strip_label(merged)
                if field_name == "住址":
                    merged = self._fix_address_order(merged)
                if merged:
                    logger.debug("[%s] 策略1b: 同行搜索 '%s'", field_name, merged)
                    return merged

        # 策略2：直接搜索（不依赖标签）
        candidates = []
        for item in all_items:
            if not (y_range[0] <= item.rcy <= y_range[1]):
                continue
            if not (data_x_range[0] <= item.rcx <= data_x_range[1]):
                continue
            if self._is_label(item.text, exclude_field=field_name):
                continue
            if len(item.text) > 40:
                continue
            candidates.append(item)

        if candidates:
            candidates.sort(key=lambda i: (i.rcy, i.rcx))
            merged = self._merge_items(candidates, candidates[0].rcy)
            merged = self._strip_label(merged)
            if merged:
                logger.debug("[%s] 策略2: 直接搜索 '%s'", field_name, merged)
                return merged

        logger.debug("[%s] 未找到数据", field_name)
        return ""

    def _merge_items(self, items: List[OcrItem], ref_rcy: float) -> str:
        """合并同行相邻文本项"""
        if not items:
            return ""

        sorted_items = sorted(items, key=lambda i: i.rcx)
        merged = sorted_items[0].text

        for i in range(1, len(sorted_items)):
            prev = sorted_items[i - 1]
            curr = sorted_items[i]
            gap = curr.rx1 - prev.rx2

            # 大间隙=跨页边界，停止合并
            if gap > self.BIG_GAP_THRESHOLD:
                break
            # 同行检查（用参考Y，避免链式断裂）
            if abs(curr.rcy - ref_rcy) < self.ROW_TOLERANCE and gap < self.MERGE_GAP:
                merged += curr.text

        return merged

    def extract(self, image_path: str) -> Dict[str, str]:
        """
        主入口：提取户口本首页字段

        Args:
            image_path: 图片路径

        Returns:
            字段字典，如 {"户别": "非农业家庭户", "户主姓名": "王晨露", ...}
            如果不是首页或提取失败，返回空字典
        """
        try:
            if not Path(image_path).exists():
                logger.warning("图片不存在: %s", image_path)
                return {}

            all_items, doc_bounds = self._parse_ocr(image_path)
            if not all_items:
                logger.warning("OCR无结果: %s", image_path)
                return {}

            if not self.is_first_page(all_items):
                logger.debug("非首页，跳过位置标注: %s", Path(image_path).name)
                return {}

            logger.info("检测到首页，执行位置标注提取: %s", Path(image_path).name)

            fields = {}
            for field_name, y_range, x_range in [
                ("户别", self.ROW1_Y, self.LEFT_COL_X),
                ("户主姓名", self.ROW1_Y, self.RIGHT_COL_X),
                ("户号", self.ROW2_Y, self.LEFT_COL_X),
                ("住址", self.ROW2_Y, self.RIGHT_COL_X),
            ]:
                value = self._extract_field(all_items, field_name, y_range, x_range)
                if value:
                    fields[field_name] = value

            logger.info("位置标注提取完成: %s", list(fields.keys()))
            return fields

        except Exception as e:
            logger.error("位置标注提取失败: %s - %s", image_path, e)
            return {}
