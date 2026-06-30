#!/usr/bin/env python3
"""
户口本首页位置标注提取器 v4

核心改进（基于v3的教训）：
1. 文档范围用全部文本计算（稳定）
2. 固定Y范围基于全部文本的文档内坐标（已校准）
3. 数据搜索时只考虑画面左半部分的文本（避免右页干扰）
4. 找标签 → 标签右侧同行找数据（相对定位，不依赖绝对Y）
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Optional


GROUND_TRUTH = {
    "212a6c910a0b4e2da52ee77c496358a2.jpg": {
        "户主姓名": "王晨露",
        "户号": "005300251",
        "住址": "安徽省蚌埠市禹会区长中路44.5号6排8号",
        "户别": "非农业家庭户",
    },
}


@dataclass
class OcrItem:
    text: str
    score: float
    x1: float; y1: float; x2: float; y2: float
    rx1: float = 0.0; ry1: float = 0.0
    rx2: float = 0.0; ry2: float = 0.0
    img_cx: float = 0.0  # 图片内X中心（用于判断左右半）

    @property
    def rcx(self) -> float: return (self.rx1 + self.rx2) / 2
    @property
    def rcy(self) -> float: return (self.ry1 + self.ry2) / 2


@dataclass
class ExtractionResult:
    field_name: str
    value: str
    method: str
    confidence: float
    doc_coords: Optional[tuple] = None


class HouseholdFirstPageExtractor:
    """户口本首页位置标注提取器 v4"""

    LABEL_PATTERNS = {
        '户主姓名': r'户主\s*姓\s*名',
        '户号': r'户\s*号',
        '住址': r'住\s*址',
        '户别': r'户\s*别',
    }

    LABEL_FRAGMENTS = [
        '户主姓名', '户主姓', '户姓名', '户主',
        '户号', '户 号', '住址', '住 址',
        '户别', '户 别', '别',
    ]

    # 固定Y范围（基于全部文本的文档内坐标，已用Image A/B校准）
    ROW1_Y = (0.55, 0.62)
    ROW2_Y = (0.62, 0.70)

    LEFT_COL_X = (0.10, 0.40)
    RIGHT_COL_X = (0.45, 0.95)

    ROW_TOLERANCE = 0.030  # 同行y容差（两行间距约0.04，0.03可区分）
    MERGE_GAP = 0.08
    BIG_GAP_THRESHOLD = 0.25  # 大间隙=跨页/跨列边界，停止合并

    # 地址片段模式：短地址片段（门牌号、排号等）出现在开头时需移到末尾
    ADDR_SUFFIX_PATTERNS = [
        r'^\d+排\d+号',        # 6排8号
        r'^\d+号$',            # 74号
        r'^[一-鿿]{1,4}\d+号',  # 曹台子74号
    ]

    def __init__(self):
        self._ocr = None

    def _get_ocr(self):
        if self._ocr is None:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(lang='ch')
        return self._ocr

    def _parse_ocr(self, image_path: str) -> tuple:
        ocr = self._get_ocr()
        results = list(ocr.predict(input=image_path))
        r = results[0]

        from PIL import Image
        pil_img = Image.open(image_path)
        img_w, img_h = pil_img.size

        # 文档范围：全部文本（保证坐标稳定）
        all_boxes = r['rec_boxes']
        min_x = min(b[0] for b in all_boxes)
        min_y = min(b[1] for b in all_boxes)
        max_x = max(b[2] for b in all_boxes)
        max_y = max(b[3] for b in all_boxes)
        doc_w = max(1, max_x - min_x)
        doc_h = max(1, max_y - min_y)

        items = []
        for text, box, score in zip(r['rec_texts'], r['rec_boxes'], r['rec_scores']):
            x1, y1, x2, y2 = box
            items.append(OcrItem(
                text=text, score=score,
                x1=x1/img_w, y1=y1/img_h, x2=x2/img_w, y2=y2/img_h,
                rx1=(x1-min_x)/doc_w, ry1=(y1-min_y)/doc_h,
                rx2=(x2-min_x)/doc_w, ry2=(y2-min_y)/doc_h,
                img_cx=(x1+x2)/(2*img_w),
            ))

        doc_bounds = (min_x/img_w, min_y/img_h, max_x/img_w, max_y/img_h)
        return items, doc_bounds

    def is_first_page(self, items: list[OcrItem]) -> bool:
        # 检查所有文本（包括右页）
        full_text = ' '.join(item.text for item in items)
        keywords = ['注意事项', '居民户口簿具有', '户口登记机关进行户籍']
        return any(kw in full_text for kw in keywords)

    def _left_half_items(self, items: list[OcrItem]) -> list[OcrItem]:
        """只保留画面左半部分的文本（首页在左侧）"""
        return [item for item in items if item.img_cx < 0.55]

    def _strip_label(self, text: str) -> str:
        for frag in self.LABEL_FRAGMENTS:
            if text.startswith(frag):
                text = text[len(frag):]
                break
        # "非农业家庭户口" → "非农业家庭户" (OCR把标签"户别"的"户"也带入)
        if text.endswith('口') and len(text) > 3 and '户' in text[-3:-1]:
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
                rest = text[len(prefix):]
                # 只有当后面还有较长的地址文本时才调整
                if len(rest) >= 6:
                    return rest + prefix
        return text

    def _find_label(self, items: list[OcrItem], field_name: str, y_range: tuple) -> Optional[OcrItem]:
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
        candidates.sort(key=lambda i: (len(i.text), -i.score))
        return candidates[0]

    def _is_label(self, text: str, exclude_field: str = None) -> bool:
        for fname, pat in self.LABEL_PATTERNS.items():
            if fname == exclude_field:
                continue
            if re.search(pat, text):
                return True
        if exclude_field:
            pat = self.LABEL_PATTERNS.get(exclude_field)
            if pat and re.fullmatch(pat, text):
                return True
        return False

    def _extract_field(self, all_items: list[OcrItem], field_name: str,
                       y_range: tuple, data_x_range: tuple) -> ExtractionResult:
        """
        提取字段（v5）：
        1. 在全部文本中找标签
        2. 在全部文本中找标签右侧同行的数据（不限于左半页，因为长地址可能跨越左右）
        3. 合并时检测大间隙（跨页边界），超过阈值停止合并
        """
        label = self._find_label(all_items, field_name, y_range)

        if label:
            # 策略1a：标签本身包含数据（OCR合并标签+数据，如"户号7314"）
            label_stripped = self._strip_label(label.text)
            if label_stripped and len(label_stripped) >= 1 and not self._is_label(label_stripped):
                return ExtractionResult(
                    field_name, label_stripped, "position", label.score,
                    doc_coords=(label.rcx, label.rcy))

            # 策略1b：标签右侧同行搜索
            data_items = []
            for item in all_items:
                # 用label的rcy做同行判断（而非前一个item的rcy，避免链式断裂）
                if abs(item.rcy - label.rcy) > self.ROW_TOLERANCE:
                    continue
                if item.rcx <= label.rcx + 0.02:
                    continue
                if self._is_label(item.text, exclude_field=field_name):
                    continue
                if data_x_range[0] <= item.rcx <= data_x_range[1]:
                    data_items.append(item)

            if data_items:
                data_items.sort(key=lambda i: i.rcx)
                merged = data_items[0].text
                score = data_items[0].score
                for i in range(1, len(data_items)):
                    prev = data_items[i-1]
                    curr = data_items[i]
                    gap = curr.rx1 - prev.rx2
                    # 大间隙=跨页/跨列边界，停止合并
                    if gap > self.BIG_GAP_THRESHOLD:
                        break
                    # y_diff 用 label.rcy 做基准，避免中间项导致链式断裂
                    if abs(curr.rcy - label.rcy) < self.ROW_TOLERANCE and gap < self.MERGE_GAP:
                        merged += curr.text
                        score = min(score, curr.score)

                merged = self._strip_label(merged)
                # 地址字段：修正短片段顺序（门牌号应排在省市区之后）
                if field_name == '住址':
                    merged = self._fix_address_order(merged)
                if merged:
                    return ExtractionResult(
                        field_name, merged, "position", score,
                        doc_coords=(data_items[0].rcx, data_items[0].rcy))

        # 策略2：在指定Y范围内直接搜索（不依赖标签）
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
            merged = candidates[0].text
            score = candidates[0].score
            for i in range(1, len(candidates)):
                prev = candidates[i-1]
                curr = candidates[i]
                gap = curr.rx1 - prev.rx2
                if gap > self.BIG_GAP_THRESHOLD:
                    break
                if abs(curr.rcy - prev.rcy) < self.ROW_TOLERANCE and gap < self.MERGE_GAP:
                    merged += curr.text
                    score = min(score, curr.score)

            merged = self._strip_label(merged)
            if merged:
                return ExtractionResult(
                    field_name, merged, "position", score,
                    doc_coords=(candidates[0].rcx, candidates[0].rcy))

        return ExtractionResult(field_name, "", "position", 0.0)

    def extract(self, image_path: str) -> dict:
        all_items, doc_bounds = self._parse_ocr(image_path)
        is_first = self.is_first_page(all_items)

        results = {}
        if is_first:
            results['户别'] = self._extract_field(all_items, '户别', self.ROW1_Y, self.LEFT_COL_X)
            results['户主姓名'] = self._extract_field(all_items, '户主姓名', self.ROW1_Y, self.RIGHT_COL_X)
            results['户号'] = self._extract_field(all_items, '户号', self.ROW2_Y, self.LEFT_COL_X)
            results['住址'] = self._extract_field(all_items, '住址', self.ROW2_Y, self.RIGHT_COL_X)

        return {
            'is_first_page': is_first,
            'doc_bounds': doc_bounds,
            'fields': results,
        }


def run_test():
    extractor = HouseholdFirstPageExtractor()

    test_images = [
        ("首页A (王晨露)", "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0107026/212a6c910a0b4e2da52ee77c496358a2.jpg"),
        ("首页B (葛瑞光)", "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0107026/3b9ba8c68af242d9a4751b1b2b3f908b.jpg"),
        ("首页C", "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0112065/1361187da239423b9851912573e4959e.jpg"),
        ("首页D", "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0112065/e925d6b865e34000a8084c7b30d890bc.jpg"),
    ]

    negative_tests = [
        ("个人页", "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0107026/b725d47c747d40ef9119190e63939bb1.jpg"),
        ("个人页2", "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0107026/2bb64043aee84bd7b75587b18ad9575e.jpg"),
    ]

    print("=" * 85)
    print("户口本首页位置标注提取器 v4")
    print("=" * 85)

    all_results = {}
    total_correct = 0
    total_with_gt = 0

    for label, img_path in test_images:
        fname = os.path.basename(img_path)
        gt = GROUND_TRUTH.get(fname, {})

        print(f"\n{'─' * 85}")
        print(f"图片: {label}")
        print(f"文件: {fname}")
        print(f"{'─' * 85}")

        result = extractor.extract(img_path)

        if not result['is_first_page']:
            print(f"  ⚠️ 未检测为首页，跳过")
            continue

        print(f"  ✅ 检测为首页")
        print()

        print(f"  {'字段':<10} {'提取值':<30} {'分数':>5} {'期望值':<20} {'结果':>5}")
        print(f"  {'─' * 80}")

        for field_name, ext in result['fields'].items():
            expected = gt.get(field_name)
            match = ""
            if expected is not None:
                total_with_gt += 1
                if ext.value == expected:
                    match = "✅"
                    total_correct += 1
                elif ext.value and (expected in ext.value or ext.value in expected):
                    match = "~"
            expected_str = expected if expected is not None else "(未设定)"
            print(f"  {field_name:<10} {ext.value:<30} {ext.confidence:>5.2f} {expected_str:<20} {match}")

        all_results[label] = {
            'is_first_page': result['is_first_page'],
            'fields': {k: {'value': v.value, 'score': v.confidence} for k, v in result['fields'].items()},
        }

    print(f"\n{'─' * 85}")
    print("阴性测试:")
    print(f"{'─' * 85}")
    for label, img_path in negative_tests:
        result = extractor.extract(img_path)
        status = "✅ 正确排除" if not result['is_first_page'] else "❌ 误判为首页"
        print(f"  {label}: {status}")

    if total_with_gt > 0:
        print(f"\n{'=' * 85}")
        print(f"准确率: {total_correct}/{total_with_gt} = {total_correct/total_with_gt*100:.0f}%")
        print(f"{'=' * 85}")

    output_path = "/Users/dongsun/Github/OCR-Three-Layer-Hybrid/tests/position_extraction_v4_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {output_path}")


if __name__ == '__main__':
    run_test()
