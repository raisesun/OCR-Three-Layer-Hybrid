# -*- coding: utf-8 -*-
"""户口本和房产证提取器"""

import logging
import re
from typing import Dict, List, Optional

from ocr_three_layer_hybrid.extractors.base_extractor import BaseExtractor
from ocr_three_layer_hybrid.interfaces import DocumentType

logger = logging.getLogger(__name__)


class HouseholdPropertyExtractor(BaseExtractor):
    """户口本和房产证字段提取器"""

    def __init__(self, position_extractor=None):
        """
        初始化提取器

        Args:
            position_extractor: 位置标注提取器（可选）
        """
        self._position_extractor = position_extractor

    def extract_household_register(
        self, full_text: str, key_list: List[str], image_path: str = ""
    ) -> Dict[str, str]:
        """
        从户口本文本中提取字段（位置标注优先，正则兜底）

        首页字段（位置标注可处理）：户别、户主姓名、户号、住址
        个人页字段（正则处理）：姓名、与户主关系、性别、公民身份号码
        """
        fields: Dict[str, str] = {}

        # 空白模板页检测："常住人口登记卡" 页面若无身份证号，则只有字段标签无数据
        if "常住人口登记卡" in full_text and not re.search(r"\d{17}[\dXx]", full_text):
            return fields

        # 第1层：位置标注提取（首页字段）
        pos_fields = {}
        if image_path and self._position_extractor:
            try:
                pos_fields = self._position_extractor.extract(image_path)
                logger.debug(f"位置标注结果: {pos_fields}")
            except Exception as e:
                logger.warning(f"位置标注提取失败，回退到正则: {e}")

        # 合并位置标注结果（优先）
        pos_field_names = ["户别", "户主姓名", "户号", "住址"]
        for key in pos_field_names:
            if key in key_list and pos_fields.get(key):
                value = pos_fields[key]
                # 验证：户主姓名不应该包含地址关键词
                if key == "户主姓名" and re.search(
                    r"(省|市|区|县|镇|乡|村|路|号|室)", value
                ):
                    logger.warning(f"位置标注户主姓名含地址关键词，跳过: {value}")
                    continue
                # 验证：住址不应该以"户号"开头
                if key == "住址" and value.startswith("户号"):
                    logger.warning(f"位置标注住址以户号开头，跳过: {value}")
                    continue
                fields[key] = value
                if key == "户主姓名" and "户主" in key_list:
                    fields["户主"] = value
                if key == "住址" and "地址" in key_list:
                    fields["地址"] = value

        # 第2层：正则提取（补充位置标注未覆盖的字段）
        # 只填充 fields 中尚未有值的字段

        if "户别" in key_list and "户别" not in fields:
            # 匹配"户别 XXX"或"户 别 XXX"
            # 使用简单方法：匹配到下一个字段标签（户主、户号、住址）之前
            match = re.search(r"户\s*别\s+(.+?)(?=\n|户\s*主|户\s*号|住\s*址|$)", full_text, re.MULTILINE)
            if match:
                value = match.group(1).strip()
                # 过滤噪声
                if value and value not in ("户别", "户 别"):
                    fields["户别"] = value
                else:
                    fields["户别"] = ""
            else:
                fields["户别"] = ""

        if ("户主姓名" in key_list or "户主" in key_list) and "户主姓名" not in fields:
            # OCR 可能输出 "户 主 姓 名"（字间有空格）
            match = re.search(r"户\s*主\s*姓\s*名\s*([^\s]+)", full_text)
            if not match:
                match = re.search(r"户主\s+姓名\s*([^\s]+)", full_text)
            if not match:
                # Fallback：无"户主姓名"标签，从"姓名"字段取（当该页是户主页时）
                if re.search(
                    r"户\s*主\s*或\s*与\s*户\s*主\s*关\s*系\s*户\s*主", full_text
                ):
                    m = re.search(r"姓\s*名\s*([^\s]+)", full_text)
                    if m:
                        value = m.group(1)
                        if "户主姓名" in key_list:
                            fields["户主姓名"] = value
                        if "户主" in key_list:
                            fields["户主"] = value
                        # 跳过后续重复赋值
                        value = None
                    else:
                        value = ""
                else:
                    value = ""
                if value is not None:
                    # 过滤封面页噪声
                    if value and (
                        "签章" in value
                        or value
                        in (
                            "姓名",
                            "与户主关系",
                            "性别",
                            "住址",
                            "出生日期",
                            "公民身份号码",
                        )
                    ):
                        value = ""
                    if "户主姓名" in key_list:
                        fields["户主姓名"] = value
                    if "户主" in key_list:
                        fields["户主"] = value
            else:
                value = match.group(1) if match else ""
                # 过滤封面页噪声（承办人签章、字段标签等）
                if value and (
                    "签章" in value
                    or value
                    in (
                        "姓名",
                        "与户主关系",
                        "性别",
                        "住址",
                        "出生日期",
                        "公民身份号码",
                    )
                ):
                    value = ""
                if "户主姓名" in key_list:
                    fields["户主姓名"] = value
                if "户主" in key_list:
                    fields["户主"] = value

        if "户号" in key_list and "户号" not in fields:
            # OCR 可能输出 "户 号"（字间有空格）
            match = re.search(r"户\s*号\s*([A-Z0-9]+)", full_text, re.IGNORECASE)
            if not match:
                match = re.search(
                    r"^([0-9]{6,12})\s*常住人口登记卡", full_text, re.MULTILINE
                )
            if not match:
                match = re.search(r"^([0-9]{6,12})\s*\n", full_text, re.MULTILINE)
            fields["户号"] = match.group(1) if match else ""

        if ("住址" in key_list or "地址" in key_list) and "住址" not in fields:
            # 避免匹配"住址变动登记"等噪声
            # 同时避免匹配 "其他住址" 等复合词（前面不能有中文字符）
            candidate = ""
            # 格式1：同行有值 "住址 XXX"
            match = re.search(r"(?<![一-鿿])住\s*址\s*(?!变动)([^\n]+)", full_text)
            if match:
                value = match.group(1).strip()
                # 如果同行是"户号"，则跳过，从下一行取地址
                if value.startswith("户号"):
                    # 格式2：住址同行是户号，地址在后续行
                    match = re.search(
                        r"住\s*址\s*\n\s*户\s*号[^\n]*\n\s*(.+?)(?:\n\s*省级|\n\s*徽|\n\s*$)",
                        full_text,
                        re.DOTALL,
                    )
                    if match:
                        candidate = re.sub(r"\s*\n\s*", "", match.group(1)).strip()
                else:
                    candidate = value
            # 格式3：多行地址 "住址\n地址内容..."
            if not candidate:
                match = re.search(
                    r"(?<![一-鿿])住\s*址\s*\n\s*(.+?)(?:\n\s*省级|\n\s*徽|\n\s*$)",
                    full_text,
                    re.DOTALL,
                )
                if match:
                    candidate = re.sub(r"\s*\n\s*", "", match.group(1)).strip()
            # 格式4：地址标签
            if not candidate:
                match = re.search(r"(?<![一-鿿])地\s*址\s*(?!变动)([^\n]+)", full_text)
                if match:
                    candidate = match.group(1).strip()
            # 验证：住址应该包含地址关键词
            if candidate and re.search(r"(省|市|区|县|镇|乡|村|路|号|室)", candidate):
                if "住址" in key_list:
                    fields["住址"] = candidate
                if "地址" in key_list:
                    fields["地址"] = candidate
            else:
                if "住址" in key_list:
                    fields["住址"] = ""
                if "地址" in key_list:
                    fields["地址"] = ""

        if "姓名" in key_list:
            # 格式1：姓名 张玉德
            # 格式2：姓 名 张玉德（带空格）
            # 注意：用负向后行断言排除 "户主姓名"（封面页），避免户主值覆盖个人页姓名
            match = re.search(r"(?<!户主)姓\s*名\s*[:：]?\s*([^\s]+)", full_text)
            # 格式3：登记事项变更页格式 "姓\n张玉德"（标签分行）
            if not match:
                match = re.search(r"姓\s*\n\s*([一-鿿]{2,4})\s*\n", full_text)
            fields["姓名"] = match.group(1) if match else ""

        if "与户主关系" in key_list or "关系" in key_list:
            # OCR 可能输出 "户主或与户主关系"（字间有空格）
            # 捕获长度限制 ≤5 字符，避免匹配"注意事项"法律条文（如"户主或本户成员..."）
            match = re.search(
                r"户\s*主\s*或\s*与\s*户\s*主\s*关\s*系\s*(\S{1,5})", full_text
            )
            if not match:
                match = re.search(
                    r"(?:与\s*户\s*主\s*关\s*系|关\s*系)\s*[:：]?\s*(\S{1,5})",
                    full_text,
                )
            value = match.group(1) if match else ""
            # 过滤明显的非关系词（如法律术语、字段名等）
            if value and (
                value
                in (
                    "姓名",
                    "性别",
                    "曾用名",
                    "出生地",
                    "籍贯",
                    "民族",
                    "宗教信仰",
                    "公民身份号码",
                    "出生日期",
                    "文化程度",
                    "婚姻状况",
                    "兵役状况",
                    "服务处所",
                    "职业",
                    "承办人签章",
                    "登记日期",
                    "户号",
                    "住址",
                )
                or "法律" in value
                or "效力" in value
                or "机关" in value
            ):
                value = ""
            if "与户主关系" in key_list:
                fields["与户主关系"] = value
            if "关系" in key_list:
                fields["关系"] = value

        if "性别" in key_list:
            match = re.search(r"性\s*别\s*[:：]?\s*(男|女)", full_text)
            # 格式2：登记事项变更页格式 "别\n性\n男"（标签分行或反转）
            if not match:
                match = re.search(
                    r"[性别]\s*\n\s*[性别]?\s*\n\s*(男|女)\s*\n", full_text
                )
            if not match:
                # 宽松匹配：在"性"或"别"附近找到"男"或"女"
                match = re.search(
                    r"(?:性|别)\s*\n?\s*(?:性|别)?\s*\n?\s*(男|女)", full_text
                )
            fields["性别"] = match.group(1) if match else ""

        if "出生日期" in key_list:
            # 格式1：出生日期 1990年1月1日
            match = re.search(
                r"(?:出\s*生\s*日\s*期|出\s*生)\s*[:：]?\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日?)",
                full_text,
            )
            if not match:
                # 格式2：1990.01.01 或 1990/01/01
                match = re.search(
                    r"(?:出\s*生\s*日\s*期|出\s*生)\s*[:：]?\s*(\d{4}[./]\d{1,2}[./]\d{1,2})",
                    full_text,
                )
            fields["出生日期"] = match.group(1).strip() if match else ""

        if "民族" in key_list:
            # 格式1：民族 汉 或 民 族 汉族
            match = re.search(r"民\s*族\s*[:：]?\s*([^\s\n]{1,5})", full_text)
            if match:
                value = match.group(1).strip()
                # 过滤噪声
                if value and value not in ("民族", "民 族"):
                    fields["民族"] = value
                else:
                    fields["民族"] = ""
            else:
                fields["民族"] = ""

        if "公民身份号码" in key_list or "身份证号" in key_list:
            # OCR 可能输出 "公 民 身 份 号 码" 或 "公民身份证件编号"（字间有空格）
            match = re.search(
                r"(?:公\s*民\s*身\s*份\s*号\s*码|公\s*民\s*身\s*份\s*证\s*件\s*编\s*号|身\s*份\s*证\s*号)\s*[:：]?\s*(\d{17}[\dXx])",
                full_text,
                re.IGNORECASE,
            )
            # 格式2：登记事项变更页格式，标签分行或简化（如"份号"、"证件编"等后跟身份证号）
            if not match:
                match = re.search(
                    r"(?:份号|证件编|编号)\s*\n?\s*(?:公|民)?\s*\n?\s*(?:民)?\s*\n?\s*(\d{17}[\dXx])",
                    full_text,
                )
            # 格式3：宽松匹配，直接找18位身份证号（作为兜底）
            if not match:
                match = re.search(r"(\d{17}[\dXx])", full_text)
            value = match.group(1).upper() if match else ""
            if "公民身份号码" in key_list:
                fields["公民身份号码"] = value
            if "身份证号" in key_list:
                fields["身份证号"] = value

        return fields

    def extract_property_certificate(
        self, full_text: str, key_list: List[str]
    ) -> Dict[str, str]:
        """从房产证文本中提取字段"""
        fields = {}

        if "不动产权证书号" in key_list or "证书号" in key_list:
            # 标准格式：皖（2017）蚌埠市不动产权第0025588号
            # OCR 可能输出: "皖（ 2025 ） 蚌埠市 不动产权第 0058326 号"（括号内/数字后有空格）
            match = re.search(
                r"[一-龥]*\s*[（(]\s*\d{4}\s*[）)]\s*[一-龥]+\s*市?\s*不动产权第\s*[A-Z0-9]+\s*号",
                full_text,
            )
            if match:
                value = re.sub(r"\s+", "", match.group(0))  # 标准化去空格
            else:
                value = ""
            # Fallback: "编号 № 34026135082" 格式
            if not value:
                match = re.search(r"编\s*号\s*[№#]+\s*([A-Z0-9]+)", full_text)
                if match:
                    value = match.group(1).strip()
            # Fallback: 直接 "不动产权证书号：..."
            if not value:
                match = re.search(r"不动产权证书号\s*[:：]?\s*([^\n]+)", full_text)
                if match:
                    value = re.sub(r"\s+", "", match.group(1).strip())
            if "不动产权证书号" in key_list:
                fields["不动产权证书号"] = value
            if "证书号" in key_list:
                fields["证书号"] = value

        if "权利人" in key_list:
            # 权利人必须出现在行首，避免匹配法律条文中的 "保护不动产权利人合法权益"
            # OCR 可能输出 "土地权利人" 而非 "权利人"
            match = re.search(
                r"^(?:土地)?权利人\s*[:：]?\s*([^\n]+)", full_text, re.MULTILINE
            )
            if not match:
                # fallback: 前面不是中文字符的情况（避免匹配"...保护不动产权利人..."）
                match = re.search(
                    r"(?<=[^一-鿿])(?:土地)?权利人\s*[:：]?\s*([^\n]+)", full_text
                )
            fields["权利人"] = match.group(1).strip() if match else ""

        if "共有情况" in key_list:
            match = re.search(r"共有情况\s*[:：]?\s*([^\n]+)", full_text)
            fields["共有情况"] = match.group(1).strip() if match else ""

        if "不动产单元号" in key_list or "单元号" in key_list:
            match = re.search(
                r"不动产单元号\s*[:：]?\s*([A-Z0-9]+)", full_text, re.IGNORECASE
            )
            if not match:
                match = re.search(r"单元号\s*[:：]?\s*([^\n]+)", full_text)
            value = match.group(1).strip() if match else ""
            if "不动产单元号" in key_list:
                fields["不动产单元号"] = value
            if "单元号" in key_list:
                fields["单元号"] = value

        if "房屋地址" in key_list or "地址" in key_list or "坐落" in key_list:
            # OCR 可能输出 "坐 落"（字间有空格）
            # 必须匹配行首，避免匹配房产分户图表头中的 "坐落"（与 "结构 层数..." 同行）
            match = re.search(
                r"^(?:房屋坐落|坐\s*落|地址)\s*[:：]?\s*([^\n]+)",
                full_text,
                re.MULTILINE,
            )
            if not match:
                match = re.search(
                    r"^房屋地址\s*[:：]?\s*([^\n]+)", full_text, re.MULTILINE
                )
            value = match.group(1).strip() if match else ""
            if "房屋地址" in key_list:
                fields["房屋地址"] = value
            if "地址" in key_list:
                fields["地址"] = value
            if "坐落" in key_list:
                fields["坐落"] = value

        if "建筑面积" in key_list or "面积" in key_list:
            # OCR 可能输出:
            # - "房屋建筑面积 101.79 平方米"
            # - "共有宗地面积932.58平方米/房屋建筑面积101.79平方米"
            # - "建筑面积,m²\n... 88.32" （房产分户图表格格式）
            # - "面 积 ... 101.79平方米"
            match = re.search(
                r"房\s*屋\s*建\s*筑\s*面\s*积\s*[:：]?\s*([\d.]+)\s*(?:㎡|平方米|m2)",
                full_text,
            )
            if not match:
                match = re.search(
                    r"建\s*筑\s*面\s*积\s*[:：]?\s*([\d.]+)\s*(?:㎡|平方米|m2)",
                    full_text,
                )
            if not match:
                # 房产分户图表格数据：数字直接跟 m²（如 "88.32 m²"）
                match = re.search(r"([\d.]+)\s*m²", full_text)
            if not match:
                # 表格格式：表头 "建筑面积,m²" 后跟数值（可能换行）
                match = re.search(
                    r"建\s*筑\s*面\s*积\s*,?\s*(?:㎡|m²|m2)?\s*\n?\s*([\d.]+)",
                    full_text,
                )
            if not match:
                # 通用 fallback：排除 "宗地面积"
                match = re.search(r"(?<!宗地)面\s*积\s*[:：]?\s*([\d.]+)", full_text)
            value = match.group(1) if match else ""
            if "建筑面积" in key_list:
                fields["建筑面积"] = value
            if "面积" in key_list:
                fields["面积"] = value

        if "用途" in key_list:
            # OCR 可能输出 "用 途"（字间有空格）
            match = re.search(r"用\s*途\s*[:：]?\s*([^\n]+)", full_text)
            fields["用途"] = match.group(1).strip() if match else ""

        return fields

    def extract_property_certificate_content(
        self, full_text: str, key_list: List[str]
    ) -> Dict[str, str]:
        """
        从不动产权证书内容页提取10个字段（针对表格布局优化）

        字段：不动产编号、权利人、共有情况、坐落、不动产单元号、
              权利类型、权利性质、用途、面积、使用期限
        """
        fields = {}

        # 1. 不动产编号（对应"不动产第 {数字}号"）
        if "不动产编号" in key_list:
            match = re.search(r"不动产权第\s*(\d+)\s*号", full_text)
            if match:
                fields["不动产编号"] = match.group(1)

        # 2. 权利人 - 查找2-4个汉字的姓名（针对表格布局）
        if "权利人" in key_list:
            lines = full_text.split("\n")
            found_ren_label = False
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                if "权利人" in line_stripped and len(line_stripped) < 10:
                    found_ren_label = True
                    continue

                if found_ren_label:
                    # 跳过空行和其他标签
                    if not line_stripped:
                        continue
                    # 如果是其他标签，继续
                    if any(
                        tag in line_stripped
                        for tag in [
                            "共有情况",
                            "不动产单元号",
                            "权利类型",
                            "权利性质",
                            "使用期限",
                            "坐落",
                        ]
                    ):
                        continue
                    # 查找2-4个汉字的姓名
                    match = re.match(r"^([一-龥]{2,4})$", line_stripped)
                    if match:
                        fields["权利人"] = match.group(1)
                        break
                    # 如果这一行包含姓名（可能和其他文字混在一起）
                    match = re.search(r"([一-龥]{2,4})", line_stripped)
                    if match and len(line_stripped) < 10:
                        fields["权利人"] = match.group(1)
                        break

            # 备选策略：直接查找常见的姓名模式
            if "权利人" not in fields:
                all_names = re.findall(r"\n([一-龥]{2,4})\n", full_text)
                if all_names:
                    for name in all_names:
                        if name not in [
                            "共有情况",
                            "不动产单元号",
                            "权利类型",
                            "权利性质",
                            "使用期限",
                            "坐落",
                            "和念老具",
                        ]:
                            fields["权利人"] = name
                            break

        # 3. 共有情况
        if "共有情况" in key_list:
            if "共同共有" in full_text:
                fields["共有情况"] = "共同共有"
            elif "单独所有" in full_text:
                fields["共有情况"] = "单独所有"

        # 4. 坐落 - 查找包含"号楼"、"单元"的地址
        if "坐落" in key_list:
            # 优先匹配完整地址（如"绿地世纪城·柏仕公馆6号楼2单元8层2号"）
            match = re.search(
                r"([一-龥]+[·・]?[一-龥]+[0-9]*号楼[0-9]*单元[0-9]+层[0-9]+号)",
                full_text,
            )
            if match:
                fields["坐落"] = match.group(1)
            else:
                # 备选：匹配包含"号楼"或"单元"的地址
                match = re.search(r"([一-龥]+(?:号楼|单元)[^\n]{0,30})", full_text)
                if match:
                    address = match.group(1).strip()
                    if "号楼" in address or "单元" in address:
                        fields["坐落"] = address

        # 5. 不动产单元号 - 查找包含空格分隔的编码
        if "不动产单元号" in key_list:
            match = re.search(r"(\d{6}\s+\d{6}\s+[A-Z]+\d+\s+[A-Z]+\d+)", full_text)
            if match:
                fields["不动产单元号"] = match.group(1)

        # 6. 权利类型
        if "权利类型" in key_list:
            if "国有建设用地使用权/房屋所有权" in full_text:
                fields["权利类型"] = "国有建设用地使用权/房屋所有权"
            elif "国有建设用地使用权" in full_text:
                fields["权利类型"] = "国有建设用地使用权"

        # 7. 权利性质
        if "权利性质" in key_list:
            if "出让/市场化商品房" in full_text:
                fields["权利性质"] = "出让/市场化商品房"
            elif "出让" in full_text:
                fields["权利性质"] = "出让"

        # 8. 用途
        if "用途" in key_list:
            if "城镇住宅用地/住宅" in full_text:
                fields["用途"] = "城镇住宅用地/住宅"
            elif "住宅" in full_text:
                fields["用途"] = "住宅"

        # 9. 面积（房屋建筑面积）
        if "面积" in key_list:
            match = re.search(r"房屋建筑面积\s*([\d.]+)", full_text)
            if match:
                fields["面积"] = match.group(1)
            else:
                # 备选：匹配 "建筑面积xxx"
                match = re.search(r"建筑面积[：:\s]*([\d.]+)", full_text)
                if match:
                    fields["面积"] = match.group(1)

        # 10. 使用期限 - 查找日期范围
        if "使用期限" in key_list:
            match = re.search(
                r"(\d{4}年\d{1,2}月\d{1,2}日[起止].*\d{4}年\d{1,2}月\d{1,2}日[起止止]?)",
                full_text,
            )
            if match:
                fields["使用期限"] = match.group(1)

        return fields

    def extract_property_certificate_first_page(
        self, full_text: str, key_list: List[str]
    ) -> Dict[str, str]:
        """
        从不动产权证书首页提取字段（编号 + 登记日期）

        首页通常是证书的发证信息页，包含：
        - 编号：不动产权证书编号（如"编号 № 34026135082"）
        - 登记日期：登记日期（如"登记日期 2025年03月20日"）
        """
        fields: Dict[str, str] = {}

        if "编号" in key_list:
            # 格式1：编号 № XXXXX
            match = re.search(r"编\s*号\s*[№#]+\s*([A-Z0-9]+)", full_text)
            if not match:
                # 格式2：编号: XXXXX
                match = re.search(r"编\s*号\s*[:：]?\s*([A-Z0-9]+)", full_text)
            if not match:
                # 格式3：皖(2025)蚌埠市不动产权第XXXXX号
                match = re.search(
                    r"[一-龥]*\s*[（(]\s*\d{4}\s*[）)]\s*[一-龥]+\s*市?\s*不动产权第\s*([A-Z0-9]+)\s*号",
                    full_text,
                )
            fields["编号"] = match.group(1).strip() if match else ""

        if "登记日期" in key_list:
            # 格式1：登记日期 2025年03月20日
            match = re.search(
                r"登\s*记\s*日\s*期\s*[:：]?\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)",
                full_text,
            )
            if not match:
                # 格式2：2025-03-20 或 2025/03/20
                match = re.search(
                    r"登\s*记\s*日\s*期\s*[:：]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
                    full_text,
                )
            fields["登记日期"] = match.group(1).strip() if match else ""

        return fields

