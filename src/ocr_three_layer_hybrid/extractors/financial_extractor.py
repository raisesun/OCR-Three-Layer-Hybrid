# -*- coding: utf-8 -*-
"""财务文档提取器

发票、合同、资金监管协议字段提取。
"""

import re
from typing import Dict, List

from ocr_three_layer_hybrid.extractors.base_extractor import BaseExtractor
from ocr_three_layer_hybrid.interfaces import DocumentType


class FinancialExtractor(BaseExtractor):
    """财务文档字段提取器"""

    def extract_invoice(self, full_text: str, key_list: List[str]) -> Dict[str, str]:
        """从发票文本中提取字段"""
        fields = {}

        if "发票代码" in key_list:
            match = re.search(r"发票代码\s*[:：]?\s*(\d{10,12})", full_text)
            fields["发票代码"] = match.group(1) if match else ""

        if "发票号码" in key_list:
            match = re.search(r"发票号码\s*[:：]?\s*(\d{8,20})", full_text)
            fields["发票号码"] = match.group(1) if match else ""

        if "开票日期" in key_list or "日期" in key_list:
            match = re.search(
                r"开票日期\s*[:：]?\s*(\d{4}年\d{1,2}月\d{1,2}日)", full_text
            )
            if not match:
                match = re.search(r"(\d{4}年\d{1,2}月\d{1,2}日)", full_text)
            value = match.group(1) if match else ""
            if "开票日期" in key_list:
                fields["开票日期"] = value
            if "日期" in key_list:
                fields["日期"] = value

        if "税额" in key_list:
            match = re.search(r"税额\s*[:：]?\s*([\d,.]+)", full_text)
            if not match:
                match = re.search(r"增值税额\s*[:：]?\s*([\d,.]+)", full_text)
            fields["税额"] = match.group(1) if match else ""

        if "不含税金额" in key_list or "金额" in key_list:
            match = re.search(r"不含税金额\s*[:：]?\s*([\d,.]+)", full_text)
            if not match:
                match = re.search(r"(?:金额|价款)\s*[:：]?\s*([\d,.]+)", full_text)
            value = match.group(1) if match else ""
            if "不含税金额" in key_list:
                fields["不含税金额"] = value
            if "金额" in key_list:
                fields["金额"] = value

        if "价税合计" in key_list or "合计" in key_list:
            # 匹配：价税合计（大写）⊗柒拾玖万伍仟陆佰肆拾圆整 （小写）¥795640.00
            # 或：合计 ¥729944.95
            # 注意：OCR可能输出全角（小写）或半角(小写)，且中间有换行，需要re.DOTALL
            match = re.search(
                r"价税合计.*?[（(]小写[）)]\s*[¥￥]?\s*([\d,.]+)", full_text, re.DOTALL
            )
            if not match:
                match = re.search(r"价税合计\s*[:：]?\s*([\d,.]+)", full_text)
            if not match:
                match = re.search(r"合计\s*[¥￥]?\s*([\d,.]+)", full_text)
            value = match.group(1) if match else ""
            if "价税合计" in key_list:
                fields["价税合计"] = value
            if "合计" in key_list:
                fields["合计"] = value

        if "购买方名称" in key_list or "购买方" in key_list:
            # 格式1：购买方信息 → 名称：张玉德
            # 格式2：购买方名称：张玉德（负向后行断言排除"共同购买方"）
            # 格式3：名称：张铭辉（无"购买方"前缀，出现在发票头部）
            match = re.search(r"购买方信息\s*\n\s*名称\s*[:：]\s*([^\n]+)", full_text)
            if not match:
                match = re.search(
                    r"(?<!共同)购买方\s*名称\s*[:：]?\s*([^\n]+)", full_text
                )
            if not match:
                match = re.search(r"(?<!共同)购买方\s*[:：]\s*([^\n]+)", full_text)
            if not match:
                # 格式3：无"购买方"前缀，匹配第一个非销售方/共同购买方的名称行
                match = re.search(
                    r"(?<!销售方)(?<!卖方信息)(?<!共同购买方)\n\s*名称\s*[:：]\s*([^\n]+)",
                    full_text,
                )
            value = match.group(1).strip() if match else ""
            # 清理可能的噪声
            if value in ("信息", "名称"):
                value = ""
            if "购买方名称" in key_list:
                fields["购买方名称"] = value
            if "购买方" in key_list:
                fields["购买方"] = value

        if "购买方纳税人识别号" in key_list:
            # 购买方信息 → 统一社会信用代码/纳税人识别号：34030320040803351X
            match = re.search(
                r"购买方信息\s*\n.*?纳税人识别号\s*[:：]\s*([A-Z0-9]{15,20})",
                full_text,
                re.DOTALL,
            )
            if not match:
                # 负向后行断言：排除"共同购买方"
                match = re.search(
                    r"(?<!共同)购买方.*?纳税人识别号\s*[:：]?\s*([A-Z0-9]{15,20})",
                    full_text,
                    re.DOTALL,
                )
            if not match:
                # 格式3：名称行直接跟纳税人识别号行（无"购买方"前缀，不跨行匹配）
                match = re.search(
                    r"(?<!共同)名称[^\n]+\n\s*统一社会信用代码/纳税人识别号\s*[:：]\s*([A-Z0-9]{15,20})",
                    full_text,
                )
            fields["购买方纳税人识别号"] = match.group(1) if match else ""

        if "销售方名称" in key_list or "销售方" in key_list:
            # 格式1：销售方信息 → 名称：蚌埠宏翔置业有限公司
            # 格式2：销售方名称：蚌埠宏翔置业有限公司
            match = re.search(r"销售方信息\s*\n\s*名称\s*[:：]\s*([^\n]+)", full_text)
            if not match:
                match = re.search(r"销售方\s*名称\s*[:：]?\s*([^\n]+)", full_text)
            if not match:
                match = re.search(r"销售方\s*[:：]?\s*([^\n]+)", full_text)
            value = match.group(1).strip() if match else ""
            if value in ("信息", "名称"):
                value = ""
            if "销售方名称" in key_list:
                fields["销售方名称"] = value
            if "销售方" in key_list:
                fields["销售方"] = value

        if "销售方纳税人识别号" in key_list:
            match = re.search(
                r"销售方信息\s*\n.*?纳税人识别号\s*[:：]\s*([A-Z0-9]{15,20})",
                full_text,
                re.DOTALL,
            )
            if not match:
                match = re.search(
                    r"销售方.*?纳税人识别号\s*[:：]?\s*([A-Z0-9]{15,20})",
                    full_text,
                    re.DOTALL,
                )
            fields["销售方纳税人识别号"] = match.group(1) if match else ""

        return fields

    def extract_contract(
        self, full_text: str, key_list: List[str], doc_type: DocumentType
    ) -> Dict[str, str]:
        """从买卖合同文本中提取字段（购房合同/存量房合同通用）"""
        fields = {}

        if "合同编号" in key_list:
            match = re.search(
                r"合同编号\s*[:：]?\s*([A-Z0-9\-]+)", full_text, re.IGNORECASE
            )
            fields["合同编号"] = match.group(1) if match else ""

        if "买受人" in key_list:
            # 格式1：乙方/买受人（签章）：张玉煌
            # 格式2：买受人（签章）：张玉煌
            # 避免匹配：买受人已详细阅读...
            # 注意：[ \t]* 只匹配空格/制表符，不匹配换行
            match = re.search(
                r"(?:乙方/)?买受人[（(]签章[）)][ \t]*[:：][ \t]*([^\n]+)", full_text
            )
            if not match:
                match = re.search(
                    r"买受人[ \t]*[:：][ \t]*([^\s,，已详阅]+)", full_text
                )
            if not match:
                # 存量房合同格式：买方： 凡荣，尹笑男
                match = re.search(r"(?:乙方[/／]?)?买方\s*[:：]\s*([^\n]+)", full_text)
            value = match.group(1).strip() if match else ""
            # 清理噪声
            if value.startswith("已") or value in ("签章", "（签章）", "签字"):
                value = ""
            fields["买受人"] = value

        if "出卖人" in key_list:
            # 格式1：甲方/出卖人（签章）：蚌埠宏翔置业有限公司
            # 格式2：甲方/出卖人（签章）：（值在下一行或印章中）
            # 注意：[ \t]* 只匹配空格/制表符，不匹配换行
            match = re.search(
                r"(?:甲方/)?出卖人[（(]签章[）)][ \t]*[:：][ \t]*([^\n]+)", full_text
            )
            value = match.group(1).strip() if match else ""
            # 如果同一行没有值，尝试从下一行获取
            if not value:
                match = re.search(
                    r"(?:甲方/)?出卖人[（(]签章[）)][ \t]*[:：]\n[ \t]*([^\n]+)",
                    full_text,
                )
                next_line = match.group(1).strip() if match else ""
                # 下一行不能是买受人信息
                if next_line and "买受人" not in next_line and "乙方" not in next_line:
                    value = next_line
            # 如果还是没有，尝试从印章中提取
            if not value:
                match = re.search(r"[（(]印章[：:][ \t]*([^\s)）]+)", full_text)
                stamp_value = match.group(1) if match else ""
                # 印章值不能是个人名（通常是公司名）
                if stamp_value and len(stamp_value) > 4:
                    value = stamp_value
            if not value:
                # 简单格式：出卖人：蚌埠宏翔置业有限公司（无签章标记）
                match = re.search(r"出卖人\s*[:：]\s*([^\n]+)", full_text)
                if match:
                    candidate = match.group(1).strip()
                    # 排除法律条文中的匹配
                    if candidate and len(candidate) < 30:
                        value = candidate
            if not value:
                # 存量房合同格式：卖方： 褚作宝
                match = re.search(r"(?:甲方[/／]?)?卖方\s*[:：]\s*([^\n]+)", full_text)
                value = match.group(1).strip() if match else ""
            # 清理噪声
            if value in ("签章", "（签章）", "签字", "：", ""):
                value = ""
            fields["出卖人"] = value

        if "总价款" in key_list or "价款" in key_list or "合同金额" in key_list:
            # 优先匹配带冒号的格式（避免匹配章节标题 "第三章 商品房价款"）
            match = re.search(
                r"(?:总价款|合同金额)\s*[:：]\s*([\d,.]+)\s*(?:元|万元)?", full_text
            )
            if not match:
                # 内联格式：总价款为 人民币 800000 元
                match = re.search(
                    r"总价款\s*为\s*(?:人民币\s*)?(?:（[^）]*）\s*)?([\d,.]+)\s*(?:元|万元)",
                    full_text,
                )
            if not match:
                # 回退匹配（无冒号，但需要至少2位数字以避免匹配 "价款\n1." 噪声）
                match = re.search(
                    r"(?:总价款|合同金额)\s*[:：]?\s*(\d{2,}[,.]?\d*)\s*(?:元|万元)?",
                    full_text,
                )
            value = match.group(1) if match else ""
            # 过滤噪声值
            if value in ("1", "1.", "2", "3", "4"):
                value = ""
            if "总价款" in key_list:
                fields["总价款"] = value
            if "价款" in key_list:
                fields["价款"] = value
            if "合同金额" in key_list:
                fields["合同金额"] = value

        if "签订日期" in key_list or "合同签订日期" in key_list:
            # 格式：签署日期：2024.2.21 或 签订日期：2024年2月21日（数字与年月日间可能有空格）
            match = re.search(
                r"(?:签署日期|签订日期|合同签订日期)\s*[:：]\s*(\d{4}\s*[.年\-]\s*\d{1,2}\s*[.月\-]\s*\d{1,2}\s*[日]?)",
                full_text,
            )
            if not match:
                # 后备：找文本中的日期，排除扫描时间戳
                all_dates = list(
                    re.finditer(
                        r"(\d{4}\s*[.年\-]\s*\d{1,2}\s*[.月\-]\s*\d{1,2}\s*[日]?)",
                        full_text,
                    )
                )
                for dm in all_dates:
                    # 排除扫描时间戳（日期后紧跟 "HH:MM"）
                    after = full_text[dm.end() : dm.end() + 10]
                    if re.match(r"\s*\d{1,2}:\d{2}", after):
                        continue
                    match = dm
                    break
            value = match.group(1) if match else ""
            # 去除日期内的所有空格，统一格式
            value = value.replace(" ", "").replace("　", "")
            if "签订日期" in key_list:
                fields["签订日期"] = value
            if "合同签订日期" in key_list:
                fields["合同签订日期"] = value

        if "房屋地址" in key_list or "房屋坐落" in key_list or "地址" in key_list:
            match = re.search(
                r"(?:房屋坐落|坐落|房屋地址|地址)\s*[:：]?\s*([^\n]+)", full_text
            )
            value = match.group(1).strip() if match else ""
            if "房屋地址" in key_list:
                fields["房屋地址"] = value
            if "房屋坐落" in key_list:
                fields["房屋坐落"] = value
            if "地址" in key_list:
                fields["地址"] = value

        if "建筑面积" in key_list or "面积" in key_list:
            match = re.search(
                r"(?:建筑面积|面积)\s*[:：]?\s*([\d.]+)\s*(?:平方米|㎡|m2)?", full_text
            )
            value = match.group(1) if match else ""
            if "建筑面积" in key_list:
                fields["建筑面积"] = value
            if "面积" in key_list:
                fields["面积"] = value

        return fields

    def extract_fund_supervision(
        self,
        full_text: str,
        key_list: List[str],
        doc_type: DocumentType = DocumentType.FUND_SUPERVISION,
    ) -> Dict[str, str]:
        """从资金监管协议文本中提取字段

        Args:
            full_text: 完整OCR文本
            key_list: 需要提取的字段列表
            doc_type: 文档类型（首页/信息页/通用）
        """
        fields = {}

        # ===== 协议首页字段 =====
        # 编号
        if "编号" in key_list:
            match = re.search(
                r"编\s*号\s*[:：]?\s*([A-Z0-9\-]+)", full_text, re.IGNORECASE
            )
            fields["编号"] = match.group(1) if match else ""

        # 甲方/乙方/丙方
        for party in ["甲方", "乙方", "丙方"]:
            if party in key_list:
                # 模式1: "甲方（卖方）：褚作宝" / "乙方｛买方｝：尹笑男"
                match = re.search(
                    rf"{party}[（(｛{{][^）)）}}｝]*[）)）}}｝]\s*[:：]\s*([一-龥]+)",
                    full_text,
                )
                if not match:
                    # 模式2: "甲方：xxx"
                    match = re.search(rf"{party}\s*[:：]\s*([一-龥]+)", full_text)
                fields[party] = match.group(1) if match else ""

        # 签署日期
        if "签署日期" in key_list or "签订日期" in key_list:
            match = re.search(
                r"(?:签署日期|签订日期)\s*[:：]?\s*(\d{4}年\d{1,2}月\d{1,2}日)",
                full_text,
            )
            if not match:
                # 模式2: "于XXXX年X月X签订" (处理OCR缺少"日"字的情况)
                match = re.search(r"于\s*(\d{4}年\d{1,2}月\d{1,2})\s*签订", full_text)
                if match:
                    # 补充"日"字
                    value = match.group(1) + "日"
                else:
                    value = ""
            else:
                value = match.group(1)

            if "签署日期" in key_list:
                fields["签署日期"] = value
            if "签订日期" in key_list:
                fields["签订日期"] = value

        # 网上签约备案合同号
        if "网上签约备案合同号" in key_list:
            match = re.search(
                r"(?:网上签约备案合同号|备案合同号|合同号)\s*(?:为)?\s*[:：]?\s*([A-Z0-9\-()（）]+)",
                full_text,
                re.IGNORECASE,
            )
            if not match:
                # 模式2: "Y(2024)12345"
                match = re.search(
                    r"([A-Z]\s*[(（]\s*\d{4}\s*[)）]\s*\d+)", full_text, re.IGNORECASE
                )
            fields["网上签约备案合同号"] = match.group(1).strip() if match else ""

        # 房屋地址
        if "房屋地址" in key_list:
            match = re.search(
                r"(?:房屋地址|房屋坐落|坐落)\s*[:：]?\s*([^\n]+)", full_text
            )
            if not match:
                # 模式2: "位于xxx"
                match = re.search(
                    r"位于\s*([^\n，,。]+(?:号|室|栋|楼|单元|层))", full_text
                )
            fields["房屋地址"] = match.group(1).strip() if match else ""

        # 建筑面积
        if "建筑面积" in key_list:
            match = re.search(
                r"建\s*筑\s*面\s*积\s*[:：]?\s*([\d.]+)\s*(?:平方米|㎡|m2)?", full_text
            )
            fields["建筑面积"] = match.group(1) if match else ""

        # 不动产权证号
        if "不动产权证号" in key_list:
            # 模式1: "皖（2024）蚌埠市不动产权第XXXXXXX号"
            match = re.search(
                r"[一-龥]*\s*[（(]\s*\d{4}\s*[）)]\s*[一-龥]+\s*市?\s*不动产权第\s*[A-Z0-9]+\s*号",
                full_text,
                re.DOTALL,  # 允许跨行匹配
            )
            if match:
                value = re.sub(r"\s+", "", match.group(0))
            else:
                # 模式2: "不动产权证号：xxx"
                match = re.search(r"不动产权证号\s*[:：]?\s*([^\n]+)", full_text)
                if not match:
                    # 模式3: "证号为：xxx" (简化版，处理跨行)
                    match = re.search(r"证号为\s*[:：]\s*([^\n]+)", full_text)
                value = match.group(1).strip() if match else ""
            fields["不动产权证号"] = value

        # 购房款（合并字段）
        if "购房款" in key_list:
            # 优先提取小写金额（更精确）
            match = re.search(
                r"购房款\s*[（(]*小写[)）]?\s*[:：]?\s*[¥￥]?\s*([\d,.]+)", full_text
            )
            if not match:
                match = re.search(r"购房款[^\d\n]*?[¥￥]\s*([\d,.]+)", full_text)
            if not match:
                # 模式3: 处理顺序反转 "小写XXX元...购房款" (支持跨行)
                match = re.search(
                    r"[（(]小写\s*([\d,.]+)\s*元[)）][\s\S]*?购房款", full_text
                )
            if match:
                fields["购房款"] = match.group(1)
            else:
                # 如果没有小写，尝试提取大写
                match = re.search(
                    r"购房款\s*[（(]*大写[)）]?\s*[:：]?\s*([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)",
                    full_text,
                )
                if not match:
                    match = re.search(
                        r"购房款[^小\n]*?([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)",
                        full_text,
                    )
                fields["购房款"] = match.group(1) if match else ""

        # 购房款（大写/小写）
        for amount_type in ["购房款(大写)", "购房款(小写)"]:
            if amount_type in key_list:
                if "(大写)" in amount_type:
                    # 匹配中文大写金额
                    match = re.search(
                        r"购房款\s*[（(]*大写[)）]?\s*[:：]?\s*([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)",
                        full_text,
                    )
                    if not match:
                        # 模式2: "购房款（大写）：捌拾万元整"
                        match = re.search(
                            r"购房款[^小\n]*?([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)",
                            full_text,
                        )
                else:
                    # 匹配数字金额
                    match = re.search(
                        r"购房款\s*[（(]*小写[)）]?\s*[:：]?\s*[¥￥]?\s*([\d,.]+)",
                        full_text,
                    )
                    if not match:
                        match = re.search(
                            r"购房款[^\d\n]*?[¥￥]\s*([\d,.]+)", full_text
                        )
                    if not match:
                        # 模式3: 处理顺序反转 "小写XXX元...购房款" (支持跨行)
                        match = re.search(
                            r"[（(]小写\s*([\d,.]+)\s*元[)）][\s\S]*?购房款", full_text
                        )
                fields[amount_type] = match.group(1) if match else ""

        # 贷款（大写/小写）- 可选字段，空值表示无贷款
        for loan_type in ["贷款(大写)", "贷款(小写)"]:
            if loan_type in key_list:
                if "(大写)" in loan_type:
                    match = re.search(
                        r"贷\s*款\s*[（(]*大写[)）]?\s*[:：]?\s*([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)",
                        full_text,
                    )
                    if not match:
                        match = re.search(
                            r"贷\s*款[^小\n]*?([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)",
                            full_text,
                        )
                else:
                    match = re.search(
                        r"贷\s*款\s*[（(]*小写[)）]?\s*[:：]?\s*[¥￥]?\s*([\d,.]+)",
                        full_text,
                    )
                    if not match:
                        match = re.search(
                            r"贷\s*款[^\d\n]*?[¥￥]\s*([\d,.]+)", full_text
                        )
                    # 检查是否为null（表示无贷款）
                    if not match:
                        null_match = re.search(
                            r"贷\s*款\s*[^\n]*?小写\s*null", full_text, re.IGNORECASE
                        )
                        if null_match:
                            # 明确标记为null，表示无贷款
                            fields[loan_type] = ""
                            continue
                # 如果没有匹配到，返回空字符串（表示无贷款）
                fields[loan_type] = match.group(1) if match else ""

        # ===== 协议信息页字段 =====
        # 甲方姓名/身份证号/银行/账号
        for party in ["甲方", "乙方"]:
            for field_suffix in ["姓名", "身份证号", "银行", "账号"]:
                field_name = f"{party}{field_suffix}"
                if field_name in key_list:
                    # 模式1: "甲方姓名：xxx"
                    match = re.search(
                        rf"{party}\s*{field_suffix}\s*[:：]?\s*([^\n]+)", full_text
                    )
                    if not match and field_suffix == "身份证号":
                        # 模式2: 在甲方/乙方后找身份证号
                        match = re.search(rf"{party}[^\n]*?(\d{{17}}[\dXx])", full_text)
                    value = match.group(1).strip() if match else ""
                    if field_suffix == "身份证号" and value:
                        value = value.upper()
                    fields[field_name] = value

        # ===== 兼容旧字段 =====
        # 监管金额
        if "监管金额" in key_list or "监管价款" in key_list:
            match = re.search(
                r"(?:监管总额|监管金额|监管价款)\s*[^\n]*?[¥￥]\s*([\d,.]+)", full_text
            )
            if not match:
                match = re.search(
                    r"(?:监管金额|监管价款)\s*[:：]\s*([\d,.]+)\s*(?:元|万元)?",
                    full_text,
                )
            if not match:
                match = re.search(
                    r"(?:监管总额|监管金额)\s*[:：]?\s*([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+(?:[¥￥][\d,.]+)?)",
                    full_text,
                )
            value = match.group(1) if match else ""
            if "监管金额" in key_list:
                fields["监管金额"] = value
            if "监管价款" in key_list:
                fields["监管价款"] = value

        # 买方/卖方
        if "买方" in key_list or "卖方" in key_list:
            buyer_match = re.search(r"[｛{]买方[}｝]\s*[:：]\s*(\S+)", full_text)
            seller_match = re.search(r"[｛{]卖方[}｝]\s*[:：]\s*(\S+)", full_text)
            if not buyer_match:
                buyer_match = re.search(r"买[房方]人\s+([^\n]+?)(?:\s+卖|$)", full_text)
            if not buyer_match:
                buyer_match = re.search(r"买方\s*[:：]\s*(\S+)", full_text)
            if not seller_match:
                seller_match = re.search(r"卖[房方]人\s+([^\n]+?)(?:\s|$)", full_text)
            if not seller_match:
                seller_match = re.search(r"卖方\s*[:：]\s*(\S+)", full_text)
            buyer_val = buyer_match.group(1).strip() if buyer_match else ""
            seller_val = seller_match.group(1).strip() if seller_match else ""
            if buyer_val:
                buyer_val = re.split(r"卖[房方]人", buyer_val)[0].strip()
                names = buyer_val.split()
                buyer_val = "、".join(names) if names else buyer_val
            if "买方" in key_list:
                fields["买方"] = buyer_val
            if "卖方" in key_list:
                fields["卖方"] = seller_val

        # 监管机构
        if "监管机构" in key_list:
            match = re.search(r"[｛{]监管机构[}｝]\s*[:：]\s*([^\n]+)", full_text)
            if not match:
                match = re.search(r"监管机构\s*[:：]\s*([^\n]+)", full_text)
            if not match:
                match = re.search(r"([^\n]{4,30}公司)\s*\n\s*资金监管专用章", full_text)
            if not match:
                match = re.search(r"印章\s*[:：]\s*([^\s）]+公司)", full_text)
            value = match.group(1).strip() if match else ""
            value = re.sub(r"^[｝}]\s*[:：]?\s*", "", value)
            fields["监管机构"] = value

        # 合同编号
        if "合同编号" in key_list and "合同编号" not in fields:
            match = re.search(
                r"合同编号\s*[:：]?\s*([A-Z0-9\-]+)", full_text, re.IGNORECASE
            )
            fields["合同编号"] = match.group(1) if match else ""

        return fields

    def extract_fund_supervision_certificate(
        self, full_text: str, key_list: List[str]
    ) -> Dict[str, str]:
        """从资金监管凭证文本中提取字段

        资金监管凭证包含表格形式的信息：
        - 协议编号、日期
        - 买房人、买房人姓名、身份证号
        - 房屋坐落（地址）、建筑面积
        - 监管总额
        - 收款单位（红章，忽略）

        注意：凭证格式特殊，标签可能在值后面（如"张新\n买房人"）
        """
        fields = {}

        # 协议编号
        if "协议编号" in key_list:
            match = re.search(
                r"(?:协议编号|编\s*号)\s*[:：]?\s*([A-Z0-9\-]+)",
                full_text,
                re.IGNORECASE,
            )
            if not match:
                # 模式2: "协议编号\n2026011900010627"（标签在前）
                match = re.search(
                    r"协议编号\s*\n\s*([A-Z0-9\-]+)", full_text, re.IGNORECASE
                )
            if not match:
                # 模式3: "2026011600010591\n协议编号"（值在前）
                match = re.search(
                    r"([A-Z0-9\-]+)\s*\n\s*协议编号", full_text, re.IGNORECASE
                )
            fields["协议编号"] = match.group(1) if match else ""

        # 日期
        if "日期" in key_list:
            # 模式1: "年月日"格式
            match = re.search(r"(\d{4}年\d{1,2}月\d{1,2}日)", full_text)
            if not match:
                # 模式2: "YYYY-MM-DD"格式（凭证常用）
                match = re.search(r"(\d{4}-\d{2}-\d{2})", full_text)
            if not match:
                # 模式3: "YYYY/MM/DD"格式
                match = re.search(r"(\d{4}/\d{2}/\d{2})", full_text)
            fields["日期"] = match.group(1) if match else ""

        # 买房人
        if "买房人" in key_list:
            # 模式1: "买房人：xxx"（标准格式）
            match = re.search(r"买[房方]人\s*[:：]\s*([^\n]+)", full_text)
            if match:
                value = match.group(1).strip()
                # 清理可能的后续字段
                value = re.split(r"身份证|姓名", value)[0].strip()
                fields["买房人"] = value
            else:
                # 模式2: "xxx\n买房人"（凭证格式，值在标签前面）
                match = re.search(r"([一-龥]{2,4})\s*\n\s*买房人", full_text)
                if match:
                    fields["买房人"] = match.group(1).strip()
                else:
                    fields["买房人"] = ""

        # 买房人姓名
        if "买房人姓名" in key_list:
            # 模式1: "买房人姓名：xxx"
            match = re.search(
                r"(?:买房人\s*姓名|姓\s*名)\s*[:：]?\s*([一-龥]{2,4})", full_text
            )
            if not match:
                # 模式2: 复用"买房人"字段的值
                fields["买房人姓名"] = fields.get("买房人", "")
            else:
                fields["买房人姓名"] = match.group(1) if match else ""

        # 身份证号
        if "身份证号" in key_list:
            # 找到所有身份证号
            matches = re.findall(r"(\d{17}[\dXx])", full_text)
            if matches:
                # 凭证格式：第一个是卖房人，第二个是买房人
                # 如果有两个，取第二个（买房人）
                if len(matches) >= 2:
                    fields["身份证号"] = matches[1].upper()
                else:
                    fields["身份证号"] = matches[0].upper()
            else:
                fields["身份证号"] = ""

        # 房屋坐落（地址）
        if "房屋坐落" in key_list:
            # 模式1: "房屋坐落：xxx"（标准格式）
            match = re.search(
                r"(?:房屋坐落|坐落|房屋地址)\s*[:：]\s*([^\n]+)", full_text
            )
            if not match:
                # 模式2: "房屋坐落\nxxx"（标签在前）
                match = re.search(r"(?:房屋坐落|坐落)\s*\n\s*([^\n]+)", full_text)
                # 但要排除金额（如"贰拾壹万捌仟元整"）
                if match and re.match(
                    r"[零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+", match.group(1).strip()
                ):
                    match = None
            if not match:
                # 模式3: "xxx\n房屋坐落"（值在前）
                match = re.search(
                    r"([^\n]*(?:号|室|栋|楼|单元|层|座|幢))\s*\n\s*(?:房屋坐落|坐落)",
                    full_text,
                )
            fields["房屋坐落"] = match.group(1).strip() if match else ""

        # 建筑面积
        if "建筑面积" in key_list:
            # 模式1: "建筑面积：xxx"（标准格式）
            match = re.search(
                r"建\s*筑\s*面\s*积\s*[:：]\s*([\d.]+)\s*(?:平方米|㎡|m2|m²)?",
                full_text,
            )
            if not match:
                # 模式2: "建筑面积\nxxx m²"（标签在前）
                match = re.search(
                    r"建筑面积\s*\n\s*([\d.]+)\s*(?:平方米|㎡|m2|m²)?", full_text
                )
            if not match:
                # 模式3: "xxx m²\n建筑面积"（值在前，紧接着）
                match = re.search(
                    r"([\d.]+)\s*(?:平方米|㎡|m2|m²)\s*\n\s*建筑面积", full_text
                )
            if not match:
                # 模式4: 找到"建筑面积"，然后往前找最近的数字+单位
                # 分割文本为行
                lines = full_text.split("\n")
                for i, line in enumerate(lines):
                    if "建筑面积" in line:
                        # 往前搜索最多5行
                        for j in range(max(0, i - 5), i):
                            area_match = re.search(
                                r"([\d.]+)\s*(?:平方米|㎡|m2|m²)", lines[j]
                            )
                            if area_match:
                                fields["建筑面积"] = area_match.group(1)
                                match = area_match  # 标记为已找到
                                break
                        if match:
                            break
            fields["建筑面积"] = match.group(1) if match else fields.get("建筑面积", "")

        # 监管总额
        if "监管总额" in key_list:
            # 模式1: "监管总额：xxx"（标准格式）
            match = re.search(r"监管总额\s*[:：]\s*[¥￥]?\s*([\d,.]+)", full_text)
            if not match:
                # 模式2: "监管总额\n￥40000.00"（凭证格式，值在标签前面）
                match = re.search(r"[¥￥]\s*([\d,.]+)\s*\n\s*监管总额", full_text)
            if not match:
                # 模式3: 中文大写金额在监管总额前面
                match = re.search(
                    r"([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)\s*\n\s*监管总额",
                    full_text,
                )
            if not match:
                # 模式4: "监管总额：xxx元"
                match = re.search(
                    r"监管总额\s*[:：]?\s*([\d,.]+)\s*(?:元|万元)?", full_text
                )
            if not match:
                # 模式5: 中文大写金额
                match = re.search(
                    r"监管总额\s*[:：]?\s*([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)",
                    full_text,
                )
            fields["监管总额"] = match.group(1) if match else ""

        # 收款单位（忽略红章，只提取文字）
        if "收款单位" in key_list:
            # 模式1: "收款单位：xxx公司"
            match = re.search(
                r"收款单位\s*[:：]\s*([一-龥]+(?:公司|集团|中心))", full_text
            )
            if not match:
                # 模式2: "收款单位签章：xxx"
                match = re.search(
                    r"收款单位签章\s*[:：]?\s*([一-龥]+(?:公司|集团|中心))", full_text
                )
            if not match:
                # 模式3: 在"资金监管专用章"前的公司名
                match = re.search(
                    r"([一-龥]+(?:公司|集团|中心))\s*\n?\s*(?:资金监管)?专用章",
                    full_text,
                )
            if not match:
                # 模式4: 在"收款单位"附近的公司名
                match = re.search(
                    r"收款单位[^一-龥]*([一-龥]+(?:公司|集团|中心))", full_text
                )
            fields["收款单位"] = match.group(1) if match else ""

        return fields

