#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试特定字段的正则表达式
"""

import re

# OCR文本片段
text = """原产权证或不动产权证证号为：皖(2025)蚌埠市不动产权第0081745号"""

print("=" * 80)
print("测试不动产权证号正则")
print("=" * 80)
print(f"\n文本: {text}")

# 当前正则
pattern1 = r'[一-龥]*\s*[（(]\s*\d{4}\s*[）)]\s*[一-龥]+\s*市?\s*不动产权第\s*[A-Z0-9]+\s*号'
match1 = re.search(pattern1, text)
print(f"\n模式1: {pattern1}")
print(f"匹配结果: {match1.group(0) if match1 else '无匹配'}")

# 简化版正则
pattern2 = r'皖\s*[(（]\s*\d{4}\s*[)）]\s*蚌埠市\s*不动产权第\s*\d+\s*号'
match2 = re.search(pattern2, text)
print(f"\n模式2: {pattern2}")
print(f"匹配结果: {match2.group(0) if match2 else '无匹配'}")

# 更灵活的正则
pattern3 = r'[(（]\s*\d{4}\s*[)）][^\n]*?不动产权第\s*[A-Z0-9]+\s*号'
match3 = re.search(pattern3, text)
print(f"\n模式3: {pattern3}")
print(f"匹配结果: {match3.group(0) if match3 else '无匹配'}")

# 测试购房款(小写)
print("\n" + "=" * 80)
print("测试购房款(小写)正则")
print("=" * 80)

text2 = """元（小写450000.00元）存入以 乙方将购房款人民币肆拾伍万元整"""
print(f"\n文本: {text2}")

# 模式1: 正常顺序
pattern4 = r'购房款\s*[（(]*小写[)）]?\s*[:：]?\s*[¥￥]?\s*([\d,.]+)'
match4 = re.search(pattern4, text2)
print(f"\n模式1 (正常顺序): {pattern4}")
print(f"匹配结果: {match4.group(1) if match4 else '无匹配'}")

# 模式2: 反转顺序
pattern5 = r'[（(]小写\s*([\d,.]+)\s*元[)）][^\n]*?购房款'
match5 = re.search(pattern5, text2)
print(f"\n模式2 (反转顺序): {pattern5}")
print(f"匹配结果: {match5.group(1) if match5 else '无匹配'}")

# 模式3: 更灵活
pattern6 = r'小写\s*([\d,.]+)\s*元'
match6 = re.search(pattern6, text2)
print(f"\n模式3 (灵活): {pattern6}")
print(f"匹配结果: {match6.group(1) if match6 else '无匹配'}")
