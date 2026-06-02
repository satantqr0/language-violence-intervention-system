#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿里云 DashScope LLM 引擎
支持 Qwen 系列大模型
"""

from typing import Optional, Dict, Any
import json


class AliLLMEngine:
    """阿里云 Qwen LLM 引擎"""
    
    def __init__(self, api_key: str, model: str = "qwen-plus"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        
    def load(self):
        """初始化 LLM 客户端"""
        try:
            import dashscope
            dashscope.api_key = self.api_key
            print(f"   阿里云 LLM 引擎初始化完成 (模型: {self.model})")
        except ImportError:
            raise RuntimeError("请安装 dashscope: pip install dashscope")
    
    def chat(self, messages: list, timeout: int = 15, **kwargs) -> Optional[str]:
        """
        对话补全
        
        Args:
            messages: 对话消息列表
            timeout: 请求超时秒数 (默认15s)
            **kwargs: 其他参数（temperature, max_tokens 等）
        
        Returns:
            模型回复文本
        """
        try:
            from openai import OpenAI
            
            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=timeout
            )
            
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                **kwargs
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"阿里云 LLM 异常: {e}")
            return None
    
    def analyze_emotion(self, text: str) -> Dict[str, Any]:
        """
        分析文本情绪
        
        Args:
            text: 要分析的文本
        
        Returns:
            情绪分析结果
        """
        prompt = f"""分析以下文本的情绪状态，返回 JSON 格式：
{{
  "emotion": "情绪类型（愤怒/焦虑/悲伤/恐惧/惊讶/厌恶/平静）",
  "intensity": 情绪强度（0-100）,
  "confidence": 置信度（0-1）,
  "keywords": ["关键词列表"]
}}

文本：{text}

只返回 JSON，不要其他内容。"""

        result = self.chat([{"role": "user", "content": prompt}], temperature=0.3)
        
        if result:
            try:
                # 提取 JSON
                import re
                json_match = re.search(r'\{[^}]+\}', result, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
            except:
                pass
        
        return {"emotion": "平静", "intensity": 50, "confidence": 0.5, "keywords": []}
    
    def detect_violence(self, text: str, context: str = "") -> Dict[str, Any]:
        """
        检测语言暴力
        
        Args:
            text: 要检测的文本
            context: 上下文
        
        Returns:
            暴力检测结果
        """
        prompt = f"""分析以下文本是否包含语言暴力，返回 JSON 格式：
{{
  "is_violence": true/false,
  "type": "暴力类型（侮辱/威胁/贬低/恐吓/无）",
  "severity": "严重程度（high/medium/low/none）",
  "confidence": 置信度（0-1）,
  "reason": "判断理由",
  "suggestion": "干预建议"
}}

文本：{text}
上下文：{context}

只返回 JSON，不要其他内容。"""

        result = self.chat([{"role": "user", "content": prompt}], temperature=0.2)
        
        if result:
            try:
                import re
                json_match = re.search(r'\{[^}]+\}', result, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
            except:
                pass
        
        return {"is_violence": False, "type": "无", "severity": "none", "confidence": 0.5}
