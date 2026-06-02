#!/bin/bash
# ==========================================
# 树莓派5 环境安装脚本
# ==========================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "========================================"
echo " 语言暴力干预系统 - 树莓派5 安装"
echo "========================================"
echo "项目目录: $PROJECT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "错误: 未找到 python3"
    exit 1
fi

PYTHON_VERSION="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')"
echo "Python版本: $PYTHON_VERSION"

echo ""
echo "[1/6] 安装系统依赖..."
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y \
        alsa-utils \
        build-essential \
        curl \
        ffmpeg \
        git \
        libasound2-dev \
        libopenblas-dev \
        mpg123 \
        mpv \
        portaudio19-dev \
        python3-dev \
        python3-pip \
        python3-venv
    echo "系统依赖安装完成"
elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y \
        alsa-lib-devel \
        ffmpeg \
        gcc \
        gcc-c++ \
        git \
        mpg123 \
        mpv \
        openblas-devel \
        portaudio-devel \
        python3-devel \
        python3-pip \
        python3-venv
    echo "系统依赖安装完成"
else
    echo "警告: 未知的包管理器，请手动安装系统依赖"
fi

mkdir -p audio data logs models

echo ""
echo "[2/6] 创建Python虚拟环境..."
if [ -d "venv" ]; then
    echo "虚拟环境已存在，跳过创建"
else
    python3 -m venv venv
    echo "虚拟环境创建完成"
fi

source venv/bin/activate

echo ""
echo "[3/6] 升级pip..."
pip install --upgrade pip "setuptools<82" wheel

echo ""
echo "[4/6] 安装Python依赖..."
pip install -r requirements.txt

echo ""
echo "[5/6] Whisper模型准备..."
if [ "${DOWNLOAD_WHISPER:-0}" = "1" ]; then
    python3 -c "import whisper; whisper.download_model('base')"
else
    echo "跳过 Whisper 模型下载。如需本地 ASR，执行: DOWNLOAD_WHISPER=1 bash scripts/setup.sh"
fi

echo ""
echo "[6/6] 检查环境变量文件..."
if [ ! -f ".env" ] && [ -f "deploy/env.rpi5.example" ]; then
    cp deploy/env.rpi5.example .env
    echo "已生成 .env，请按需填写 DASHSCOPE_API_KEY / SMB_PASS"
else
    echo ".env 已存在或无模板，跳过"
fi
if [ -f ".env" ]; then
    chmod 600 .env
fi

echo ""
echo "========================================"
echo "安装完成!"
echo "========================================"
echo ""
echo "运行方法:"
echo "  source venv/bin/activate"
echo "  python3 src/main.py"
echo "  python3 web_app.py"
echo ""
