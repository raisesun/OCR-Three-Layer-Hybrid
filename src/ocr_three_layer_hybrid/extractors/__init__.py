# -*- coding: utf-8 -*-
"""文档字段提取器模块

按文档类型组织的字段提取器集合。
"""

from ocr_three_layer_hybrid.extractors.personal_id_extractor import PersonalIdExtractor
from ocr_three_layer_hybrid.extractors.household_property_extractor import HouseholdPropertyExtractor
from ocr_three_layer_hybrid.extractors.financial_extractor import FinancialExtractor
from ocr_three_layer_hybrid.extractors.agreement_extractor import AgreementExtractor

__all__ = [
    'PersonalIdExtractor',
    'HouseholdPropertyExtractor',
    'FinancialExtractor',
    'AgreementExtractor',
]
