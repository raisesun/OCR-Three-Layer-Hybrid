# 50张样本批量测试报告 V2（基于云端基线 + 子串匹配）

> Ground Truth: doubao-seed-2.0-pro 云端模型
> 评估方法: 将系统提取的字段值与云端OCR文本做子串匹配
> 评估时间: 2026-06-28

## 一、总体结果

### 分类器: 38.0% (19/50)

| 文档类型 | 正确 | 总数 | 准确率 |
|---------|------|------|--------|
| hukou | 10 | 12 | 83% |
| id_card_back | 5 | 5 | 100% |
| id_card_front | 1 | 10 | 10% |
| marriage | 2 | 8 | 25% |
| property | 1 | 7 | 14% |
| purchase_contract | 0 | 8 | 0% |

### 提取层准确率

| 层级 | 完全匹配 | 部分匹配 | 遗漏 | 错误 | 综合准确率 |
|------|---------|---------|------|------|-----------|
| RULE | 66 | 1 | 91 | 2 | **96.4%** |
| VLM | 35 | 0 | 22 | 3 | **92.1%** |
| LLM | 20 | 0 | 68 | 2 | **90.9%** |

### 按文档类型统计

| 文档类型 | 字段总数 | 完全匹配 | 部分匹配 | 遗漏 | 错误 | 准确率 |
|---------|---------|---------|---------|------|------|--------|
| hukou | 38 | 35 | 0 | 22 | 3 | 92.1% |
| id_card_back | 16 | 15 | 0 | 24 | 1 | 93.8% |
| id_card_front | 45 | 45 | 0 | 35 | 0 | 100.0% |
| marriage | 8 | 6 | 1 | 32 | 1 | 81.2% |
| property | 13 | 12 | 0 | 29 | 1 | 92.3% |
| purchase_contract | 9 | 8 | 0 | 39 | 1 | 88.9% |

## 二、分类器错误详情

| 图片 | 预期类型 | 云端推断 | 系统分类 |
|------|---------|---------|---------|
| 6ef5f1c4453b4010897e... | id_card_front | DIVORCE_CERTIFICATE | DIVORCE_AGREEMENT |
| e25491d291254874bf85... | id_card_front | UNKNOWN | UNKNOWN |
| 4d9fd39863044a649884... | id_card_front | UNKNOWN | ID_CARD |
| aa43339a989f596ebc70... | id_card_front | UNKNOWN | ID_CARD |
| d128307774a04c9fa147... | id_card_front | UNKNOWN | ID_CARD |
| 84f68919b9da48cdb2ca... | id_card_front | UNKNOWN | ID_CARD |
| 027aa4151f75424c8529... | id_card_front | HOUSEHOLD_REGISTER | UNKNOWN |
| 7c61d257538e41cab0e1... | id_card_front | UNKNOWN | ID_CARD |
| 5cfff66a056c4baa95e1... | id_card_front | UNKNOWN | ID_CARD |
| 4032f69b8c0d4c3e9d4b... | marriage | MARRIAGE_CERTIFICATE | UNKNOWN |
| 17938b5ed94a4789a753... | marriage | DIVORCE_CERTIFICATE | UNKNOWN |
| 76f20eea31d045f39672... | marriage | MARRIAGE_CERTIFICATE | UNKNOWN |
| 147d9a19313a4594afb3... | marriage | DIVORCE_CERTIFICATE | UNKNOWN |
| 115b0f26466a4b76b1cb... | marriage | MARRIAGE_CERTIFICATE | UNKNOWN |
| 3f101385b95f452882e6... | marriage | MARRIAGE_CERTIFICATE | UNKNOWN |
| c34f94843f4d4f29ba21... | hukou | UNKNOWN | UNKNOWN |
| cc1b63ce8572495f880c... | hukou | HOUSEHOLD_REGISTER | UNKNOWN |
| 2b7aee7102a44d579ea9... | purchase_contract | PURCHASE_CONTRACT | UNKNOWN |
| ac7d32cfbee24cae8ef2... | purchase_contract | PURCHASE_CONTRACT | UNKNOWN |
| d871f7f0785045e5a150... | purchase_contract | PURCHASE_CONTRACT | UNKNOWN |
| 2bf5dbfd12c64176a3fd... | purchase_contract | UNKNOWN | PURCHASE_CONTRACT |
| 3418882883ff47809543... | purchase_contract | UNKNOWN | PURCHASE_CONTRACT |
| 25fc387ef8df4a068b6b... | purchase_contract | PURCHASE_CONTRACT | UNKNOWN |
| 21721add1dee4fc6a9c2... | purchase_contract | UNKNOWN | UNKNOWN |
| 942b7e1a18664ee2ab54... | purchase_contract | UNKNOWN | PURCHASE_CONTRACT |
| e9505e57b2d646b9a06c... | property | UNKNOWN | UNKNOWN |
| 061e171a8b6e41bbbf2b... | property | FUND_SUPERVISION | UNKNOWN |
| a81d1cfaf102418f848c... | property | UNKNOWN | UNKNOWN |
| 2f04ef2a8b5244c9b2ff... | property | INVOICE | INVOICE |
| 0d7b511c1e7144f4bad4... | property | PROPERTY_CERTIFICATE | UNKNOWN |
| 34314ee9baa24b398305... | property | FUND_SUPERVISION | UNKNOWN |

## 三、提取错误详情 (wrong字段)

| 图片 | 层级 | 类型 | 字段 | 提取值 |
|------|------|------|------|--------|
| 169c2ae3c7d1132eb6c1... | RULE | id_card_back | 姓名 | 工琼 |
| bc254b4fef8c41caaaf7... | RULE | marriage | 结婚证字号 | 340321-2020-006301备注姓名张梅梅性别女国籍 |
| c34f94843f4d4f29ba21... | VLM | hukou | 姓名 | 史海龙 |
| c34f94843f4d4f29ba21... | VLM | hukou | 户主 | 史海龙 |
| c34f94843f4d4f29ba21... | VLM | hukou | 民族 | 汉 |
| 942b7e1a18664ee2ab54... | LLM | purchase_contract | 总价款 | 1540000000 |
| 2f04ef2a8b5244c9b2ff... | LLM | property | 不动产单元号 | -； 土地增值税项目编号：-； 核定计税价格：-； 附赠车位 |