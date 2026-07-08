#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试LLM层（PP-ChatOCRv4）

注意：需要PP-ChatOCRv4模型和Ollama服务的测试标记为slow/integration
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from ocr_three_layer_hybrid.llm_layer import PPChatOCRv4Layer
from ocr_three_layer_hybrid.interfaces import DocumentType, DocumentInfo, ProcessingLayer


class TestPPChatOCRv4LayerUnit:
    """LLM层单元测试（不依赖外部服务）"""

    @pytest.fixture
    def layer(self):
        return PPChatOCRv4Layer()

    def test_supported_doc_types(self, layer):
        assert DocumentType.PURCHASE_CONTRACT in layer.supported_doc_types
        assert DocumentType.STOCK_CONTRACT in layer.supported_doc_types
        assert DocumentType.PROPERTY_CERTIFICATE in layer.supported_doc_types
        assert DocumentType.ID_CARD not in layer.supported_doc_types

    def test_can_process_purchase_contract(self, layer):
        info = DocumentInfo(
            image_path="/tmp/contract.jpg",
            doc_type=DocumentType.PURCHASE_CONTRACT,
        )
        assert layer.can_process(info) is True

    def test_default_config(self, layer):
        assert layer.chat_bot_config["model_name"] == "qwen2.5:1.5b"
        assert layer.retriever_config["model_name"] == "nomic-embed-text"
        assert layer.ocr_config["use_doc_orientation_classify"] is True
        assert layer.ocr_config["use_table_recognition"] is True

    def test_custom_config(self):
        layer = PPChatOCRv4Layer(
            chat_bot_config={"model_name": "custom-model"},
            retriever_config={"model_name": "custom-embed"},
        )
        assert layer.chat_bot_config["model_name"] == "custom-model"
        assert layer.retriever_config["model_name"] == "custom-embed"

    def test_parse_chat_result_dict(self, layer):
        chat_result = {
            "chat_res": {
                "买受人": "张三",
                "出卖人": "李四",
            }
        }
        fields = layer._parse_chat_result(
            chat_result, ["买受人", "出卖人", "合同编号"]
        )
        assert fields["买受人"] == "张三"
        assert fields["出卖人"] == "李四"
        assert fields["合同编号"] == ""

    def test_parse_chat_result_list(self, layer):
        chat_result = [
            {"chat_res": {"买受人": "王五"}}
        ]
        fields = layer._parse_chat_result(chat_result, ["买受人"])
        assert fields["买受人"] == "王五"

    def test_parse_chat_result_json_string(self, layer):
        chat_result = {
            "chat_res": '{"买受人": "赵六"}'
        }
        fields = layer._parse_chat_result(chat_result, ["买受人"])
        assert fields["买受人"] == "赵六"

    def test_parse_chat_result_invalid_string(self, layer):
        chat_result = {
            "chat_res": "不是JSON"
        }
        fields = layer._parse_chat_result(chat_result, ["买受人"])
        assert fields["买受人"] == ""

    @patch("ocr_three_layer_hybrid.llm_layer.PPChatOCRv4Layer._get_pp_chatocr")
    def test_extract_success(self, mock_get_pp_chatocr, layer):
        """模拟PP-ChatOCRv4成功提取"""
        mock_pp_chatocr = MagicMock()
        mock_pp_chatocr.visual_predict.return_value = [
            {"visual_info": {"text": "mock text"}}
        ]
        mock_pp_chatocr.chat.return_value = {
            "chat_res": {"买受人": "张三", "出卖人": "李四"}
        }
        mock_get_pp_chatocr.return_value = mock_pp_chatocr

        info = DocumentInfo(
            image_path="/tmp/contract.jpg",
            doc_type=DocumentType.PURCHASE_CONTRACT,
        )
        result = layer.extract(
            info, ["买受人", "出卖人", "合同编号"]
        )

        assert result.success is True
        assert result.doc_type == DocumentType.PURCHASE_CONTRACT
        assert result.layer == ProcessingLayer.LLM
        assert result.fields["买受人"] == "张三"
        assert result.fields["出卖人"] == "李四"
        assert result.fields["合同编号"] == ""

    @patch("ocr_three_layer_hybrid.llm_layer.PPChatOCRv4Layer._get_pp_chatocr")
    def test_extract_failure(self, mock_get_pp_chatocr, layer):
        """模拟PP-ChatOCRv4失败"""
        mock_get_pp_chatocr.side_effect = Exception("模型未加载")

        info = DocumentInfo(
            image_path="/tmp/contract.jpg",
            doc_type=DocumentType.PURCHASE_CONTRACT,
        )
        result = layer.extract(info, ["买受人"])

        assert result.success is False
        assert "模型未加载" in result.error_message
        assert result.fields["买受人"] == ""


@pytest.mark.slow
@pytest.mark.pp_chatocr
@pytest.mark.integration
class TestPPChatOCRv4LayerIntegration:
    """LLM层集成测试（需要模型和Ollama服务）"""

    def test_real_extraction(self):
        """真实调用PP-ChatOCRv4"""
        layer = PPChatOCRv4Layer()
        info = DocumentInfo(
            image_path="/Users/dongsun/Github/sample-OCR/增量房图片资料/202403080014/5a99c19b869a4de7a42f2d798d5afde7.jpeg",
            doc_type=DocumentType.PURCHASE_CONTRACT,
        )
        result = layer.extract(
            info, ["买受人", "出卖人", "合同编号"]
        )

        assert result.success is True
        assert result.time_cost < 120
