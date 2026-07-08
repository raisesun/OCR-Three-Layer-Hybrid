# -*- coding: utf-8 -*-
"""文档字段提取器模块

按文档类型组织的字段提取器集合。
"""

from ocr_three_layer_hybrid.extractors.personal_id_extractor import PersonalIdExtractor
from ocr_three_layer_hybrid.extractors.household_property_extractor import HouseholdPropertyExtractor
from ocr_three_layer_hybrid.extractors.financial_extractor import FinancialExtractor
from ocr_three_layer_hybrid.extractors.agreement_extractor import AgreementExtractor
from ocr_three_layer_hybrid.extractors.regex_patterns import (
    # 常量模式
    ID_CARD_NUMBER_PATTERN,
    GENDER_PATTERN,
    ISSUING_AUTHORITY_PATTERN,
    HOUSEHOLDER_NAME_PATTERN,
    NAME_PATTERN,
    ETHNICITY_PATTERN,
    BIRTH_DATE_PATTERN,
    VALIDITY_PERIOD_RANGE_PATTERN,
    VALIDITY_PERIOD_LONG_TERM_PATTERN,
    ADDRESS_PATTERN,
    # 提取函数
    extract_id_card_number,
    extract_gender,
    extract_name,
    extract_ethnicity,
    extract_issuing_authority,
    extract_validity_period,
    extract_householder_name,
    extract_address,
    extract_birth_date,
    extract_household_type,
    extract_household_number,
)

__all__ = [
    # Extractor classes
    'PersonalIdExtractor',
    'HouseholdPropertyExtractor',
    'FinancialExtractor',
    'AgreementExtractor',
    # Regex patterns
    'ID_CARD_NUMBER_PATTERN',
    'GENDER_PATTERN',
    'ISSUING_AUTHORITY_PATTERN',
    'HOUSEHOLDER_NAME_PATTERN',
    'NAME_PATTERN',
    'ETHNICITY_PATTERN',
    'BIRTH_DATE_PATTERN',
    'VALIDITY_PERIOD_RANGE_PATTERN',
    'VALIDITY_PERIOD_LONG_TERM_PATTERN',
    'ADDRESS_PATTERN',
    # Extraction functions
    'extract_id_card_number',
    'extract_gender',
    'extract_name',
    'extract_ethnicity',
    'extract_issuing_authority',
    'extract_validity_period',
    'extract_householder_name',
    'extract_address',
    'extract_birth_date',
    'extract_household_type',
    'extract_household_number',
]
