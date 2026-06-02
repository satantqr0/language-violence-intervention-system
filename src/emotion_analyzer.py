#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语调情绪分析模块
LLM + 规则双引擎：LLM 做深度语义情绪判断，规则做快速兜底
针对家庭场景口语优化，支持上下文感知
"""

import json
import re
from typing import Dict, Optional, List


class EmotionAnalyzer:
    """情绪分析模块 — LLM 优先，规则兜底"""
    
    EMOTION_TYPES = ["平静", "愤怒", "焦虑", "悲伤", "压抑", "恐惧", "烦躁", "厌恶", "委屈"]
    
    def __init__(self, llm_engine=None):
        """
        Args:
            llm_engine: AliLLMEngine 实例，None 则纯规则模式
        """
        self.llm_engine = llm_engine
        
    def load(self):
        if self.llm_engine:
            print("   初始化LLM情绪分析 (在线模式)")
        else:
            print("   使用规则情绪分析 (离线模式)")
    
    def analyze(self, text: str, context: List[Dict] = None) -> Dict:
        """
        分析文本情绪
        
        Returns:
            {
                "type": str,          # 情绪类型
                "intensity": str,     # low/medium/high
                "score": int,         # 0-100 情绪指数
                "is_high_risk": bool  # score >= 80
            }
        """
        if not text or len(text.strip()) < 2:
            return self._default_result()
        
        # 优先 LLM 分析
        if self.llm_engine:
            result = self._analyze_with_llm(text, context)
            if result:
                return result
        
        # 兜底：规则分析
        return self._analyze_with_rules(text)
    
    def _analyze_with_llm(self, text: str, context: List[Dict] = None) -> Optional[Dict]:
        """使用 LLM 深度分析情绪"""
        # 构建上下文
        ctx_lines = ""
        if context:
            recent = context[-3:]
            for c in recent:
                ctx_lines += f"  - {c.get('text', '')}\n"
        
        prompt = f"""你是一个专业的情绪分析专家，专注于家庭场景下的口语情绪识别。

## 任务
分析说话人的情绪状态。注意区分：
- 说话人自身的情绪（愤怒、烦躁、压抑等）
- 说话内容中提到的事件/人物（不要把描述他人的词误判为说话人情绪）

## 情绪类型（只选一个）
平静 | 愤怒 | 焦虑 | 悲伤 | 压抑 | 恐惧 | 烦躁 | 厌恶 | 委屈

## 上下文（最近对话）
{ctx_lines if ctx_lines else "无"}

## 待分析文本
{text}

## 输出格式（严格 JSON，不要任何其他内容）
{{"type": "情绪类型", "intensity": "low或medium或high", "score": 0到100的整数, "reason": "简短判断理由"}}

## 评分指南
- 平静: 0-25
- 轻微情绪波动（有点不耐烦、小烦）: 26-45
- 明显情绪（生气但不激烈、担忧、明显焦虑）: 46-65
- 强烈情绪（大声愤怒、极度焦虑、强烈委屈）: 66-85
- 极端情绪（暴怒、崩溃、极度恐惧）: 86-100

## 重要
- 口语中"干嘛""烦死了""你干嘛呀"这种语气偏烦躁/愤怒，不要判为平静
- 反问句、短促感叹通常有情绪，score 不应低于 30
- "算了""随便"在家庭场景通常是压抑/委屈，不是平静
- 只有真正平淡叙述才判平静"""

        result = self.llm_engine.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=200
        )
        
        if result:
            try:
                # 提取 JSON
                json_match = re.search(r'\{[^}]+\}', result, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    score = int(data.get("score", 30))
                    return {
                        "type": data.get("type", "平静"),
                        "intensity": data.get("intensity", "low"),
                        "score": max(0, min(100, score)),
                        "is_high_risk": score >= 80
                    }
            except Exception as e:
                print(f"LLM情绪解析失败: {e}, 原始: {result[:100]}")
        
        return None
    
    def _analyze_with_rules(self, text: str) -> Dict:
        """规则分析（离线兜底）"""
        # 扩展关键词库
        anger_keywords = ["生气", "愤怒", "讨厌", "滚", "该死", "混蛋", "妈的", "气死我了", 
                         "发火", "烦死了", "你干嘛", "干嘛呀", "你有病", "有毛病"]
        anxiety_keywords = ["担心", "焦虑", "害怕", "紧张", "不安", "怎么办", "万一",
                           "急死了", "受不了了"]
        sadness_keywords = ["难过", "伤心", "痛苦", "绝望", "失望", "委屈", "哭",
                          "算了", "随便吧", "无所谓了"]
        fear_keywords = ["恐惧", "害怕", "不敢", "哆嗦", "别打", "求你"]
        suppressed_keywords = ["算了", "随便", "不想说", "无所谓", "忍", "算了不说",
                              "不想管", "懒得说", "没什么好说的"]
        irritate_keywords = ["烦", "啰嗦", "废话", "闭嘴", "吵死了", "烦不烦",
                            "你有完没完", "别说了", "行了行了"]
        
        scores = {
            "愤怒": sum(2 for kw in anger_keywords if kw in text),
            "焦虑": sum(2 for kw in anxiety_keywords if kw in text),
            "悲伤": sum(2 for kw in sadness_keywords if kw in text),
            "恐惧": sum(2 for kw in fear_keywords if kw in text),
            "压抑": sum(2 for kw in suppressed_keywords if kw in text),
            "烦躁": sum(2 for kw in irritate_keywords if kw in text),
        }
        
        max_type = max(scores, key=scores.get)
        max_score = scores[max_type]
        
        if max_score == 0:
            # 语气词检测
            if any(w in text for w in ["啊？", "哈？", "什么？", "嗯？"]):
                return {"type": "烦躁", "intensity": "low", "score": 30, "is_high_risk": False}
            if text.endswith("！") or text.endswith("!"):
                return {"type": "愤怒", "intensity": "low", "score": 35, "is_high_risk": False}
            return {"type": "平静", "intensity": "low", "score": 15, "is_high_risk": False}
        
        base_score = min(100, 35 + max_score * 15)
        
        # 感叹号加成
        excl = text.count("！") + text.count("!")
        base_score = min(100, base_score + excl * 8)
        
        # 问号加成
        quest = text.count("？") + text.count("?")
        base_score = min(100, base_score + quest * 5)
        
        if base_score >= 80:
            intensity = "high"
        elif base_score >= 50:
            intensity = "medium"
        else:
            intensity = "low"
        
        return {
            "type": max_type,
            "intensity": intensity,
            "score": int(base_score),
            "is_high_risk": base_score >= 80
        }
    
    def _default_result(self) -> Dict:
        return {"type": "平静", "intensity": "low", "score": 0, "is_high_risk": False}
