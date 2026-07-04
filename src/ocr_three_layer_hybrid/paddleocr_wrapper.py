"""
PaddleOCR 包装器模块

提供统一的 PaddleOCR 接口，支持：
1. PP-OCRv6 引擎（快速、稳定，适合 A/B 级文档，11.88秒/张）
2. PaddleOCR-VL 视觉语言模型引擎（精度高，适合 C/D 级文档，151秒/张）
3. 自动根据文档类型选择最佳引擎

分层策略（Phase 1 调整后）：
- A 级文档（身份证、结婚证等）→ PP-OCRv6（11.88秒）
- B 级文档（户口本、发票等）→ PP-OCRv6（11.88秒）
- C 级文档（合同、协议等）→ PaddleOCR-VL（151秒）
- D 级文档（病历、处方等）→ PaddleOCR-VL（151秒）

注意：PP-StructureV3 已弃用（性能不稳定，某些图片 692秒）

模型路径：
- 默认使用 ~/.paddlex/official_models/ 中的模型
- 可通过 /Users/dongsun/Github/models-OCR/official_models/ 访问（软链接）

作者: Claude
日期: 2026-07-01
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Optional, Union, List, Dict
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

# ============== 模型路径配置 ==============

# 默认模型路径（PaddleX 官方模型目录）
_DEFAULT_MODELS_DIR = os.path.expanduser("~/.paddlex/official_models")

# 文本检测模型
_DEFAULT_DET_MODEL = os.path.join(_DEFAULT_MODELS_DIR, "PP-OCRv6_medium_det")

# 文本识别模型
_DEFAULT_REC_MODEL = os.path.join(_DEFAULT_MODELS_DIR, "PP-OCRv6_medium_rec")

# 版面分析模型
_DEFAULT_LAYOUT_MODEL = os.path.join(_DEFAULT_MODELS_DIR, "PP-DocLayoutV3")

# PaddleOCR-VL 模型路径
_DEFAULT_VLM_MODEL = os.path.expanduser(
    "~/Github/models-OCR/PaddleOCR-VL-0.9B"
)

# ============== 版面分析标签 ==============

LAYOUT_LABELS = {
    "text",           # 普通文本
    "title",          # 标题
    "table",          # 表格
    "figure",         # 图片
    "image",          # 图片
    "seal",           # 印章
    "header",         # 页眉
    "footer",         # 页脚
    "header_image",   # 页眉图片
    "footer_image",   # 页脚图片
}

# 需要 OCR 的区域
OCR_REGION_LABELS = {"text", "title", "table", "header", "footer"}

# 跳过的区域（印章、图片等）
SKIP_REGION_LABELS = {"seal", "figure", "image", "header_image", "footer_image"}


# ============== 数据结构 ==============

@dataclass
class LayoutRegion:
    """版面分析检测到的区域"""
    label: str              # 区域类型
    score: float            # 检测置信度
    coordinate: list        # 边界框 [x1, y1, x2, y2]
    order: Optional[int]    # 阅读顺序
    polygon_points: list    # 多边形顶点

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "score": round(self.score, 4),
            "coordinate": self.coordinate,
            "order": self.order,
        }


@dataclass
class OCRResult:
    """OCR 识别结果"""
    input_path: str
    # 识别文本列表
    rec_texts: List[str] = field(default_factory=list)
    # 识别置信度列表
    rec_scores: List[float] = field(default_factory=list)
    # 文本检测框坐标（四边形）
    rec_polys: List = field(default_factory=list)
    # 检测框矩形（x1,y1,x2,y2）
    rec_boxes: Optional[np.ndarray] = None
    # 版面分析区域列表
    layout_regions: Optional[List[LayoutRegion]] = None
    # 按版面区域分组的文本块
    grouped_blocks: Optional[List[dict]] = None
    # 原始完整结果
    raw_result: Optional[dict] = None

    @property
    def full_text(self) -> str:
        """获取按阅读顺序拼接的纯文本"""
        if self.grouped_blocks:
            parts = []
            for block in self.grouped_blocks:
                region = block.get("region")
                # 跳过印章、图片等非文本区域
                if region and region.label in SKIP_REGION_LABELS:
                    continue
                parts.extend(block.get("texts", []))
            return "\n".join(parts)
        return "\n".join(self.rec_texts)

    @property
    def blocks(self) -> List[dict]:
        """获取文本块列表（含坐标和置信度）"""
        result = []
        for i, text in enumerate(self.rec_texts):
            poly = self.rec_polys[i] if i < len(self.rec_polys) else None
            score = self.rec_scores[i] if i < len(self.rec_scores) else 0.0
            bbox = None
            region_label = None

            if poly is not None:
                poly_arr = np.array(poly)
                x1, y1 = poly_arr.min(axis=0)
                x2, y2 = poly_arr.max(axis=0)
                bbox = [float(x1), float(y1), float(x2), float(y2)]

                # 如果有版面分析，找到文本块所属的区域
                if self.layout_regions:
                    region_label = self._find_region_for_bbox(
                        [float(x1), float(y1), float(x2), float(y2)]
                    )

            result.append({
                "text": text,
                "score": float(score),
                "poly": poly.tolist() if poly is not None else [],
                "bbox": bbox or [],
                "region_label": region_label,
            })
        return result

    def _find_region_for_bbox(self, text_bbox: List[float]) -> Optional[str]:
        """找到文本框所属的版面区域标签"""
        if not self.layout_regions:
            return None
        tx1, ty1, tx2, ty2 = text_bbox
        tcx = (tx1 + tx2) / 2
        tcy = (ty1 + ty2) / 2

        best_region = None
        best_iou = 0.0

        for region in self.layout_regions:
            rx1, ry1, rx2, ry2 = region.coordinate
            # 检查文本框中心点是否在区域内
            if rx1 <= tcx <= rx2 and ry1 <= tcy <= ry2:
                # 计算 IoU
                ix1 = max(tx1, rx1)
                iy1 = max(ty1, ry1)
                ix2 = min(tx2, rx2)
                iy2 = min(ty2, ry2)
                if ix1 < ix2 and iy1 < iy2:
                    inter = (ix2 - ix1) * (iy2 - iy1)
                    area_t = (tx2 - tx1) * (ty2 - ty1)
                    area_r = (rx2 - rx1) * (ry2 - ry1)
                    iou = inter / max(area_t + area_r - inter, 1e-6)
                    if iou > best_iou:
                        best_iou = iou
                        best_region = region.label

        return best_region

    def get_text_by_region(self, label: str) -> List[str]:
        """获取指定区域类型的所有文本"""
        return [
            b["text"] for b in self.blocks
            if b.get("region_label") == label
        ]

    def to_dict(self) -> dict:
        """转换为字典"""
        d = {
            "input_path": self.input_path,
            "full_text": self.full_text,
            "texts": self.rec_texts,
            "scores": [round(s, 4) for s in self.rec_scores],
            "blocks": self.blocks,
        }
        if self.layout_regions:
            d["layout_regions"] = [r.to_dict() for r in self.layout_regions]
            d["layout_summary"] = {
                label: len([r for r in self.layout_regions if r.label == label])
                for label in set(r.label for r in self.layout_regions)
            }
        if self.grouped_blocks:
            d["grouped_blocks"] = [
                {
                    "region": b["region"].to_dict(),
                    "texts": b["texts"],
                    "avg_score": round(
                        sum(b["scores"]) / max(len(b["scores"]), 1), 4
                    ),
                }
                for b in self.grouped_blocks
            ]
        return d

    def to_json(self, indent: int = 2, ensure_ascii: bool = False) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=ensure_ascii)


# ============== PP-StructureV3 引擎 ==============

class PPStructureV3Engine:
    """
    PP-StructureV3 引擎（技术方案推荐）

    一次调用完成：
    - 版面分析（PP-DocLayoutV3）
    - 文本检测 + 识别（PP-OCRv6）
    - 表格识别（SLANet_plus）
    - 公式识别（PP-FormulaNet）

    优势：
    - 速度快（0.5-2秒/张）
    - 支持复杂文档（表格、多栏、公式）
    - 输出结构化结果（HTML/Markdown）

    适用场景：
    - A 级文档（身份证、结婚证等）
    - B 级文档（户口本、发票等）

    参数：
        device: 推理设备（默认 "cpu"）
        use_layout: 是否启用版面分析
        use_table: 是否启用表格识别
        use_formula: 是否启用公式识别
    """

    def __init__(
        self,
        device: str = "cpu",
        use_layout: bool = True,
        use_table: bool = True,
        use_formula: bool = False,
    ):
        self.device = device
        self.use_layout = use_layout
        self.use_table = use_table
        self.use_formula = use_formula
        self._pipeline = None

    def _ensure_pipeline(self):
        """延迟加载 PP-StructureV3 pipeline"""
        if self._pipeline is None:
            from paddlex import create_pipeline
            logger.info(f"初始化 PP-StructureV3 pipeline (device={self.device})...")
            start = time.time()
            self._pipeline = create_pipeline(
                pipeline="PP-StructureV3",
                device=self.device,
                use_layout_detection=self.use_layout,
                use_table_recognition=self.use_table,
                use_formula_recognition=self.use_formula,
            )
            logger.info(f"PP-StructureV3 pipeline 初始化完成，耗时: {time.time()-start:.1f}s")

    def predict(
        self,
        input_data: Union[str, np.ndarray],
    ) -> List[OCRResult]:
        """
        识别图片/PDF

        Args:
            input_data: 图片/PDF 文件路径或 ndarray

        Returns:
            OCRResult 列表
        """
        self._ensure_pipeline()

        input_desc = input_data if isinstance(input_data, str) else "ndarray"
        logger.info(f"PP-StructureV3 开始推理: {input_desc}")
        start = time.time()

        # 图片预处理：缩放到 2000px 以内（经测试为准确率与性能的最佳平衡点）
        processed_input = input_data
        if isinstance(input_data, str) and os.path.exists(input_data):
            from ocr_three_layer_hybrid.image_preprocessor import ensure_max_size
            processed_input = ensure_max_size(input_data, max_side=2000)
            if processed_input != input_data:
                logger.info(f"图片已预处理（缩放）")

        output = self._pipeline.predict(processed_input)
        results = []

        for res in output:
            j = res.json
            inner = j.get("res", j) if isinstance(j, dict) else {}

            # 提取文本（PP-StructureV3 的输出结构）
            rec_texts = []
            rec_scores = []
            rec_polys = []

            # 从 parsing_res_list 中提取文本（PP-StructureV3 的主要输出）
            parsing_res_list = inner.get("parsing_res_list", [])
            if parsing_res_list:
                for block in parsing_res_list:
                    block_content = block.get("block_content", "")
                    block_label = block.get("block_label", "")

                    # 只提取文本类型的块
                    if block_content and block_label in ["text", "title", "table"]:
                        rec_texts.append(block_content)
                        rec_scores.append(1.0)  # PP-StructureV3 没有单块置信度
                        # PP-StructureV3 没有提供多边形坐标
                        rec_polys.append([])

            input_path = inner.get(
                "input_path",
                str(input_data) if isinstance(input_data, str) else "ndarray"
            )

            ocr_result = OCRResult(
                input_path=input_path,
                rec_texts=rec_texts,
                rec_scores=rec_scores,
                rec_polys=rec_polys,
                raw_result=inner,
            )
            results.append(ocr_result)

        elapsed = time.time() - start
        logger.info(f"PP-StructureV3 推理完成，耗时: {elapsed:.1f}s，共{len(results)}页")

        return results

    def predict_to_json(
        self,
        input_data: Union[str, np.ndarray],
        save_path: Optional[str] = None,
    ) -> dict:
        """识别并返回 JSON 格式结果"""
        results = self.predict(input_data)

        output = {
            "success": True,
            "input": str(input_data) if isinstance(input_data, str) else "ndarray",
            "total_pages": len(results),
            "pages": [r.to_dict() for r in results],
        }

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            logger.info(f"结果已保存到: {save_path}")

        return output

    def close(self):
        """关闭引擎，释放资源"""
        if self._pipeline is not None:
            try:
                self._pipeline.close()
            except Exception:
                pass
            self._pipeline = None


# ============== OCR 引擎（标准 PP-OCRv6） ==============

class PaddleOCREngine:
    """
    PaddleOCR 标准产线引擎

    流程：
    - 基础模式: PP-OCRv6 文本检测 → PP-OCRv6 文本识别
    - 增强模式: PP-DocLayoutV3 版面分析 → PP-OCRv6 文本检测+识别 → 按区域分组

    适用场景：
    - A/B 级文档（身份证、结婚证、户口本、发票等）
    - 需要快速识别（0.5-2 秒/张）

    参数：
        device: 推理设备，Apple Silicon 使用 "cpu"
        cpu_threads: CPU 推理线程数
        use_layout: 是否启用版面分析（PP-DocLayoutV3）
        det_model_dir: 文本检测模型目录
        rec_model_dir: 文本识别模型目录
        layout_model_dir: 版面分析模型目录
    """

    def __init__(
        self,
        device: str = "cpu",
        cpu_threads: int = 10,
        use_layout: bool = False,
        det_model_dir: Optional[str] = None,
        rec_model_dir: Optional[str] = None,
        layout_model_dir: Optional[str] = None,
        use_doc_orientation_classify: bool = False,
        use_doc_unwarping: bool = False,
        use_textline_orientation: bool = False,
        text_det_limit_side_len: int = 64,
        text_det_thresh: float = 0.3,
        text_det_box_thresh: float = 0.6,
        text_det_unclip_ratio: float = 1.5,
    ):
        self.device = device
        self.use_layout = use_layout
        self._ocr_pipeline = None
        self._layout_model = None
        self._init_kwargs = {
            "use_doc_orientation_classify": use_doc_orientation_classify,
            "use_doc_unwarping": use_doc_unwarping,
            "use_textline_orientation": use_textline_orientation,
            "text_det_limit_side_len": text_det_limit_side_len,
            "text_det_thresh": text_det_thresh,
            "text_det_box_thresh": text_det_box_thresh,
            "text_det_unclip_ratio": text_det_unclip_ratio,
        }
        # 模型路径
        self.det_model_dir = det_model_dir or _DEFAULT_DET_MODEL
        self.rec_model_dir = rec_model_dir or _DEFAULT_REC_MODEL
        self.layout_model_dir = layout_model_dir or _DEFAULT_LAYOUT_MODEL

    def _ensure_pipeline(self):
        """延迟加载 OCR pipeline"""
        if self._ocr_pipeline is None:
            from paddleocr import PaddleOCR
            logger.info(f"初始化 PaddleOCR pipeline (device={self.device})...")
            logger.info(f"  检测模型: {self.det_model_dir}")
            logger.info(f"  识别模型: {self.rec_model_dir}")
            start = time.time()
            self._ocr_pipeline = PaddleOCR(
                text_detection_model_dir=self.det_model_dir,
                text_recognition_model_dir=self.rec_model_dir,
                **self._init_kwargs,
            )
            logger.info(f"PaddleOCR pipeline 初始化完成，耗时: {time.time()-start:.1f}s")

    def _ensure_layout_model(self):
        """延迟加载版面分析模型"""
        if self.use_layout and self._layout_model is None:
            from paddlex import create_pipeline
            logger.info(f"初始化 PP-DocLayoutV3 版面分析模型...")
            logger.info(f"  模型路径: {self.layout_model_dir}")
            start = time.time()
            self._layout_model = create_pipeline(
                pipeline="PP-StructureV3",
                layout_model_dir=self.layout_model_dir,
            )
            logger.info(f"版面分析模型初始化完成，耗时: {time.time()-start:.1f}s")

    def _run_layout_analysis(self, image_path: str) -> List[LayoutRegion]:
        """运行版面分析"""
        self._ensure_layout_model()
        start = time.time()
        results = self._layout_model.predict(image_path)
        regions = []
        for r in results:
            j = r.json
            inner = j.get("res", j) if isinstance(j, dict) else {}
            boxes = inner.get("boxes", [])
            for b in boxes:
                regions.append(LayoutRegion(
                    label=b.get("label", "unknown"),
                    score=b.get("score", 0.0),
                    coordinate=b.get("coordinate", []),
                    order=b.get("order"),
                    polygon_points=b.get("polygon_points", []),
                ))
        logger.info(f"版面分析完成，耗时: {time.time()-start:.1f}s，检测到 {len(regions)} 个区域")
        return regions

    def _group_texts_by_regions(
        self,
        rec_texts: List[str],
        rec_scores: List[float],
        rec_polys: List,
        regions: List[LayoutRegion],
    ) -> List[dict]:
        """将文本块按版面区域分组"""
        # 为每个文本块找到所属区域
        block_to_region = {}
        for i, text in enumerate(rec_texts):
            if i >= len(rec_polys):
                break
            poly = rec_polys[i]
            poly_arr = np.array(poly)
            x1, y1 = poly_arr.min(axis=0)
            x2, y2 = poly_arr.max(axis=0)
            tcx = (float(x1) + float(x2)) / 2
            tcy = (float(y1) + float(y2)) / 2

            best_region_idx = None
            best_iou = 0.0
            for j, region in enumerate(regions):
                rx1, ry1, rx2, ry2 = region.coordinate
                if rx1 <= tcx <= rx2 and ry1 <= tcy <= ry2:
                    ix1 = max(float(x1), rx1)
                    iy1 = max(float(y1), ry1)
                    ix2 = min(float(x2), rx2)
                    iy2 = min(float(y2), ry2)
                    if ix1 < ix2 and iy1 < iy2:
                        inter = (ix2 - ix1) * (iy2 - iy1)
                        area_t = (float(x2) - float(x1)) * (float(y2) - float(y1))
                        area_r = (rx2 - rx1) * (ry2 - ry1)
                        iou = inter / max(area_t + area_r - inter, 1e-6)
                        if iou > best_iou:
                            best_iou = iou
                            best_region_idx = j

            if best_region_idx is not None:
                block_to_region[i] = best_region_idx

        # 按区域分组
        grouped = {}
        for region_idx in set(block_to_region.values()):
            region = regions[region_idx]
            indices = [i for i, ri in block_to_region.items() if ri == region_idx]
            # 按 y 坐标排序
            def y_position(i):
                if i < len(rec_polys):
                    return np.array(rec_polys[i]).min(axis=0)[1]
                return 0
            indices.sort(key=y_position)
            grouped[region_idx] = {
                "region": region,
                "texts": [rec_texts[i] for i in indices if i < len(rec_texts)],
                "scores": [rec_scores[i] for i in indices if i < len(rec_scores)],
            }

        # 按区域 order 排序输出
        result = sorted(
            grouped.values(),
            key=lambda g: (0, g["region"].coordinate[1]) if g["region"].order is None else (1, g["region"].order),
        )
        return result

    def predict(
        self,
        input_data: Union[str, np.ndarray, list],
        **predict_kwargs,
    ) -> List[OCRResult]:
        """
        识别图片/PDF

        Args:
            input_data: 输入数据，支持：
                - str: 图片/PDF 文件路径或 URL
                - np.ndarray: 图像数据
                - list: 多个文件路径的列表

        Returns:
            OCRResult 列表
        """
        self._ensure_pipeline()

        input_desc = input_data if isinstance(input_data, str) else (
            f"{len(input_data)}张" if isinstance(input_data, list) else "ndarray"
        )
        logger.info(f"开始推理: {input_desc}")
        start = time.time()

        # 版面分析（如果启用）
        layout_regions = None
        if self.use_layout and isinstance(input_data, str) and os.path.exists(input_data):
            try:
                layout_regions = self._run_layout_analysis(input_data)
            except Exception as e:
                logger.warning(f"版面分析失败，回退到无版面分析模式: {e}")
                layout_regions = None

        # OCR 识别
        output = self._ocr_pipeline.predict(input_data, **predict_kwargs)
        results = []

        for res in output:
            input_path = res.get(
                "input_path",
                str(input_data) if isinstance(input_data, str) else "ndarray"
            )
            rec_texts = res.get("rec_texts", []) or []
            rec_scores = res.get("rec_scores", []) or []
            rec_polys = res.get("rec_polys", []) or []

            # 文本块按区域分组
            grouped_blocks = None
            if layout_regions:
                grouped_blocks = self._group_texts_by_regions(
                    rec_texts, rec_scores, rec_polys, layout_regions
                )

            ocr_result = OCRResult(
                input_path=input_path,
                rec_texts=rec_texts,
                rec_scores=rec_scores,
                rec_polys=rec_polys,
                rec_boxes=res.get("rec_boxes"),
                layout_regions=layout_regions,
                grouped_blocks=grouped_blocks,
                raw_result={
                    "input_path": input_path,
                    "rec_texts": rec_texts,
                    "rec_scores": rec_scores,
                    "rec_polys": rec_polys,
                },
            )
            results.append(ocr_result)

        elapsed = time.time() - start
        logger.info(f"推理完成，耗时: {elapsed:.1f}s，共{len(results)}页")

        return results

    def predict_to_json(
        self,
        input_data: Union[str, np.ndarray],
        save_path: Optional[str] = None,
        **predict_kwargs,
    ) -> dict:
        """识别并返回 JSON 格式结果"""
        results = self.predict(input_data, **predict_kwargs)

        output = {
            "success": True,
            "input": str(input_data) if isinstance(input_data, str) else "ndarray",
            "total_pages": len(results),
            "pages": [r.to_dict() for r in results],
        }

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            logger.info(f"结果已保存到: {save_path}")

        return output

    def close(self):
        """关闭引擎，释放资源"""
        if self._ocr_pipeline is not None:
            try:
                self._ocr_pipeline.close()
            except Exception:
                pass
            self._ocr_pipeline = None
        self._layout_model = None


# ============== VLM 引擎 ==============

class PaddleOCRVLLEngine:
    """
    PaddleOCR-VL 视觉语言模型引擎

    使用 VLM 直接对文档图片进行解析，输出 Markdown 格式的结构化内容。

    优势：
    - 能理解文档语义
    - 可处理复杂排版
    - 精度高（96.3% on OmniDocBench）

    劣势：
    - CPU 推理较慢（5-8 秒/张）
    - 输出非结构化 JSON

    适用场景：
    - C/D 级文档（合同、协议、病历等）
    - 复杂文档（多栏、嵌套表格、印章覆盖）
    - 需要语义理解的提取任务

    参数：
        device: 推理设备（默认 "cpu"）
        pipeline_version: VLM 产线版本（"v1" 对应 0.9B 模型）
        vl_rec_model_dir: VLM 模型目录
    """

    def __init__(
        self,
        device: str = "cpu",
        pipeline_version: str = "v1",
        vl_rec_model_dir: Optional[str] = None,
        use_layout_detection: bool = True,
    ):
        self.device = device
        self.pipeline_version = pipeline_version
        self.vl_rec_model_dir = vl_rec_model_dir or _DEFAULT_VLM_MODEL
        self.use_layout_detection = use_layout_detection
        self._pipeline = None

    def _ensure_pipeline(self):
        """延迟加载 VLM pipeline"""
        if self._pipeline is None:
            from paddleocr import PaddleOCRVL
            logger.info(f"初始化 PaddleOCR-VL pipeline (version={self.pipeline_version})...")
            logger.info(f"  VLM 模型: {self.vl_rec_model_dir}")
            start = time.time()
            self._pipeline = PaddleOCRVL(
                device=self.device,
                pipeline_version=self.pipeline_version,
                vl_rec_model_dir=self.vl_rec_model_dir,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_layout_detection=self.use_layout_detection,
            )
            logger.info(f"VLM pipeline 初始化完成，耗时: {time.time()-start:.1f}s")

    def predict(self, input_data: Union[str, np.ndarray]) -> List[OCRResult]:
        """
        用 VLM 识别文档图片

        Args:
            input_data: 图片文件路径或 ndarray

        Returns:
            OCRResult 列表（full_text 为 Markdown 格式）
        """
        self._ensure_pipeline()

        logger.info(f"VLM 推理开始: {input_data if isinstance(input_data, str) else 'ndarray'}")
        start = time.time()

        output = self._pipeline.predict(input_data)
        results = []

        for res in output:
            j = res.json
            inner = j.get("res", j) if isinstance(j, dict) else {}

            # 从 parsing_res_list 提取 Markdown 内容
            parsing_list = inner.get("parsing_res_list", [])
            texts = []
            for block in parsing_list:
                content = block.get("block_content", "").strip()
                if content:
                    texts.append(content)

            input_path = inner.get(
                "input_path",
                str(input_data) if isinstance(input_data, str) else "ndarray"
            )

            ocr_result = OCRResult(
                input_path=input_path,
                rec_texts=texts,
                rec_scores=[1.0] * len(texts),  # VLM 没有单块置信度
                rec_polys=[],
                raw_result=inner,
            )
            results.append(ocr_result)

        elapsed = time.time() - start
        logger.info(f"VLM 推理完成，耗时: {elapsed:.1f}s，共{len(results)}页")

        return results

    def close(self):
        """关闭引擎"""
        if self._pipeline is not None:
            try:
                self._pipeline.close()
            except Exception:
                pass
            self._pipeline = None


# ============== 统一包装器 ==============

class PaddleOCRWrapper:
    """
    PaddleOCR 统一包装器

    提供统一的接口，自动根据文档类型选择最佳引擎：
    - A/B 级文档 → PP-StructureV3（快速，0.5-2秒/张）
    - C/D 级文档 → PaddleOCR-VL（精度高，5-8秒/张）

    使用示例：
        wrapper = PaddleOCRWrapper()

        # 方式1：自动选择引擎
        result = wrapper.run_ocr("id_card.jpg", doc_type="身份证")

        # 方式2：指定引擎
        result = wrapper.run_ocr("contract.jpg", engine="vlm")

        # 方式3：获取纯文本
        text = wrapper.run_ocr_text("invoice.jpg")
    """

    # 文档类型分类
    FAST_DOC_TYPES = {
        "身份证", "结婚证", "离婚证", "户口本", "发票",
        "不动产权证书", "营业执照", "驾驶证", "行驶证"
    }

    def __init__(
        self,
        device: str = "cpu",
        default_engine: str = "auto",  # "auto", "structure_v3", "ppocr", "vlm"
    ):
        """
        初始化包装器

        Args:
            device: 推理设备（"cpu" 或 "gpu"）
            default_engine: 默认引擎（"auto" 根据文档类型自动选择）
        """
        self.device = device
        self.default_engine = default_engine

        # 延迟初始化引擎
        self._structure_v3_engine = None
        self._ppocr_engine = None
        self._vlm_engine = None

    def _get_structure_v3_engine(self) -> PPStructureV3Engine:
        """获取 PP-StructureV3 引擎（延迟初始化）"""
        if self._structure_v3_engine is None:
            self._structure_v3_engine = PPStructureV3Engine(
                device=self.device,
            )
        return self._structure_v3_engine

    def _get_ppocr_engine(self) -> PaddleOCREngine:
        """获取 PP-OCR 引擎（延迟初始化，备选）"""
        if self._ppocr_engine is None:
            self._ppocr_engine = PaddleOCREngine(
                device=self.device,
            )
        return self._ppocr_engine

    def _get_vlm_engine(self) -> PaddleOCRVLLEngine:
        """获取 VLM 引擎（延迟初始化）"""
        if self._vlm_engine is None:
            self._vlm_engine = PaddleOCRVLLEngine(
                device=self.device,
            )
        return self._vlm_engine

    def _select_engine(self, doc_type: Optional[str] = None) -> str:
        """
        选择引擎（Phase 1 调整后的分层策略）

        Args:
            doc_type: 文档类型

        Returns:
            引擎名称："ppocr", "vlm", 或 "structure_v3"
        """
        if self.default_engine != "auto":
            return self.default_engine

        # 根据文档类型选择（Phase 1 调整后的分层策略）
        if doc_type and doc_type in self.FAST_DOC_TYPES:
            # A/B 级文档 → PP-OCRv6（快速、稳定）
            # 注意：PP-StructureV3 性能不稳定，已弃用
            return "ppocr"
        else:
            # C/D 级文档 → PaddleOCR-VL（精度高）
            return "vlm"

    def run_ocr(
        self,
        image_path: str,
        doc_type: Optional[str] = None,
        engine: Optional[str] = None,
    ) -> OCRResult:
        """
        运行 OCR

        Args:
            image_path: 图片路径
            doc_type: 文档类型（用于自动选择引擎）
            engine: 指定引擎（"structure_v3", "ppocr", "vlm"），None 表示自动选择

        Returns:
            OCRResult
        """
        engine_name = engine or self._select_engine(doc_type)

        if engine_name == "structure_v3":
            ocr_engine = self._get_structure_v3_engine()
        elif engine_name == "ppocr":
            ocr_engine = self._get_ppocr_engine()
        else:  # vlm
            ocr_engine = self._get_vlm_engine()

        results = ocr_engine.predict(image_path)
        return results[0] if results else OCRResult(input_path=image_path)

    def run_ocr_text(
        self,
        image_path: str,
        doc_type: Optional[str] = None,
        engine: Optional[str] = None,
    ) -> str:
        """
        运行 OCR 并返回纯文本

        Args:
            image_path: 图片路径
            doc_type: 文档类型
            engine: 指定引擎

        Returns:
            识别的纯文本
        """
        result = self.run_ocr(image_path, doc_type, engine)
        return result.full_text

    def close(self):
        """关闭所有引擎，释放资源"""
        if self._structure_v3_engine:
            self._structure_v3_engine.close()
            self._structure_v3_engine = None
        if self._ppocr_engine:
            self._ppocr_engine.close()
            self._ppocr_engine = None
        if self._vlm_engine:
            self._vlm_engine.close()
            self._vlm_engine = None
