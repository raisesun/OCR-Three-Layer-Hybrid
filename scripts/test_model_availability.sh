#!/bin/bash

# OCR模型可用性验证脚本
# 测试目标：验证GLM-OCR、Qwen3.5-4B、PaddleOCR-VL的可用性

set -e

echo "========================================="
echo "OCR模型可用性验证"
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="
echo ""

# 模型路径
GLM_OCR_MODEL="/Users/dongsun/Github/models-OCR/GLM-OCR-GGUF/GLM-OCR-Q8_0.gguf"
GLM_OCR_MMPROJ="/Users/dongsun/Github/models-OCR/GLM-OCR-GGUF/mmproj-GLM-OCR-Q8_0.gguf"
QWEN_MODEL="/Users/dongsun/Github/models-OCR/Qwen3.5-4B/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"

# 测试图片（从样本数据中选择）
TEST_IMAGE="/Users/dongsun/Github/sample-OCR/存量房/BBJZ202401001/$(ls /Users/dongsun/Github/sample-OCR/存量房/BBJZ202401001/ | grep -E '\.(jpg|jpeg)$' | head -1)"

echo "测试图片: $TEST_IMAGE"
echo ""

# ========================================
# 测试1: GLM-OCR (llama-cli)
# ========================================
echo "========================================="
echo "测试1: GLM-OCR (llama-cli)"
echo "========================================="
echo ""

if [ ! -f "$GLM_OCR_MODEL" ]; then
    echo "❌ GLM-OCR模型文件不存在: $GLM_OCR_MODEL"
else
    echo "✅ GLM-OCR模型文件存在"
    echo "模型大小: $(ls -lh "$GLM_OCR_MODEL" | awk '{print $5}')"
    echo ""

    echo "开始推理测试..."
    START_TIME=$(date +%s.%N)

    # 使用llama-cli进行OCR推理
    llama-cli \
        --model "$GLM_OCR_MODEL" \
        --mmproj "$GLM_OCR_MMPROJ" \
        --image "$TEST_IMAGE" \
        --prompt "请识别这张图片中的所有文字内容，包括表格结构。" \
        --temp 0.1 \
        --n-predict 2048 \
        2>&1 | tee /tmp/glm_ocr_test.log

    END_TIME=$(date +%s.%N)
    DURATION=$(echo "$END_TIME - $START_TIME" | bc)

    echo ""
    echo "推理耗时: ${DURATION}秒"
    echo ""
fi

echo ""

# ========================================
# 测试2: Qwen3.5-4B (Ollama)
# ========================================
echo "========================================="
echo "测试2: Qwen3.5-4B (Ollama)"
echo "========================================="
echo ""

# 检查Ollama是否运行
if ! pgrep -x "ollama" > /dev/null; then
    echo "启动Ollama服务..."
    ollama serve > /tmp/ollama_serve.log 2>&1 &
    sleep 3
fi

echo "✅ Ollama服务运行中"
echo ""

# 创建Modelfile用于Qwen3.5-4B
QWEN_MODELFILE="/tmp/Qwen3.5-4B-Modelfile"
cat > "$QWEN_MODELFILE" <<EOF
FROM $QWEN_MODEL
PARAMETER temperature 0.1
PARAMETER num_predict 2048
SYSTEM "你是一个专业的文档识别助手，擅长从图片中提取结构化信息。"
EOF

echo "创建Ollama模型: qwen35-4b-test"
ollama create qwen35-4b-test -f "$QWEN_MODELFILE" 2>&1 | tee /tmp/ollama_create.log

echo ""
echo "开始推理测试..."
START_TIME=$(date +%s.%N)

# 测试文本推理（不含图片）
ollama run qwen35-4b-test "请提取以下信息：姓名=张三，身份证号=340104199001011234，地址=安徽省合肥市。请以JSON格式返回。" 2>&1 | tee /tmp/qwen_test.log

END_TIME=$(date +%s.%N)
DURATION=$(echo "$END_TIME - $START_TIME" | bc)

echo ""
echo "推理耗时: ${DURATION}秒"
echo ""

# ========================================
# 测试3: PaddleOCR-VL
# ========================================
echo "========================================="
echo "测试3: PaddleOCR-VL"
echo "========================================="
echo ""

PADDLE_VL_DIR="/Users/dongsun/Github/models-OCR/PaddleOCR-VL-0.9B"

if [ ! -d "$PADDLE_VL_DIR" ]; then
    echo "❌ PaddleOCR-VL目录不存在: $PADDLE_VL_DIR"
else
    echo "✅ PaddleOCR-VL目录存在"
    echo ""
    echo "检查SSL问题..."

    # 尝试导入PaddleOCR
    python3 -c "
import sys
sys.path.insert(0, '$PADDLE_VL_DIR')
try:
    from paddleocr import PaddleOCR
    print('✅ PaddleOCR导入成功')
    ocr = PaddleOCR(use_angle_cls=True, lang='ch')
    print('✅ PaddleOCR初始化成功')
except Exception as e:
    print(f'❌ PaddleOCR错误: {e}')
    sys.exit(1)
" 2>&1 | tee /tmp/paddle_test.log
fi

echo ""

# ========================================
# 测试总结
# ========================================
echo "========================================="
echo "测试总结"
echo "========================================="
echo ""
echo "测试完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "请检查以下日志文件："
echo "- GLM-OCR: /tmp/glm_ocr_test.log"
echo "- Qwen3.5: /tmp/qwen_test.log"
echo "- PaddleOCR: /tmp/paddle_test.log"
echo ""
echo "========================================="
