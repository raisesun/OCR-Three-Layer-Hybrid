# -*- coding: utf-8 -*-
"""
字段配置模块

定义字段的优先级（必须/可选）和来源信息，用于指导多页文档的字段提取和合并策略。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class FieldPriority(str, Enum):
    """字段优先级"""
    REQUIRED = "required"  # 必须字段，提取失败会影响整体成功率
    OPTIONAL = "optional"  # 可选字段，提取失败不影响整体成功率


@dataclass
class FieldConfig:
    """单个字段的配置"""
    name: str  # 字段名称
    priority: FieldPriority  # 优先级（必须/可选）
    sources: List[str] = field(default_factory=list)  # 预期来源页面（如 ["first_page", "content"]）

    def __hash__(self):
        return hash((self.name, self.priority))

    def __eq__(self, other):
        if not isinstance(other, FieldConfig):
            return False
        return self.name == other.name and self.priority == other.priority


@dataclass
class DocumentFieldConfig:
    """文档类型的字段配置集合"""
    required_fields: List[FieldConfig] = field(default_factory=list)  # 必须字段列表
    optional_fields: List[FieldConfig] = field(default_factory=list)  # 可选字段列表

    def get_all_field_names(self) -> List[str]:
        """获取所有字段名称"""
        return [f.name for f in self.required_fields] + [f.name for f in self.optional_fields]

    def get_field_by_name(self, name: str) -> Optional[FieldConfig]:
        """根据字段名查找配置"""
        for f in self.required_fields + self.optional_fields:
            if f.name == name:
                return f
        return None

    def is_optional_field(self, name: str) -> bool:
        """判断是否是可选字段"""
        return any(f.name == name and f.priority == FieldPriority.OPTIONAL
                   for f in self.optional_fields)

    def is_required_field(self, name: str) -> bool:
        """判断是否是必须字段"""
        return any(f.name == name and f.priority == FieldPriority.REQUIRED
                   for f in self.required_fields)

    def get_all_fields(self) -> List[FieldConfig]:
        """获取所有字段配置"""
        return self.required_fields + self.optional_fields
