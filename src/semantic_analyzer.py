#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
混合语义分析模块
规则引擎 + LLM 双引擎协同检测
- 规则引擎覆盖6大类暴力类型，命中置信度0.8
- LLM深度分析处理复杂语义，处理规则未命中的隐含暴力
- 情绪强度调整置信度：高+0.3，中+0.15
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional


class SemanticAnalyzer:
    """混合语义分析器 — 规则快速匹配 + LLM 深度判断"""
    
    VIOLENCE_CATEGORIES = [
        "侮辱贬低类", "威胁恐吓类", "情感操控类", 
        "冷暴力类", "人身攻击类", "嘲讽讽刺类"
    ]
    
    def __init__(self, rules_path: str = None, llm_engine=None):
        """
        Args:
            rules_path: 暴力规则JSON文件路径
            llm_engine: AliLLMEngine 实例
        """
        self.rules_path = rules_path
        self.llm_engine = llm_engine
        self.rules = {}
        
    def load(self):
        print("   加载语义分析规则引擎...")
        self._load_rules()
        if self.llm_engine:
            print("   初始化LLM语义分析 (在线模式)")
        else:
            print("   语义分析仅规则模式 (离线)")
    
    def _load_rules(self):
        if self.rules_path and Path(self.rules_path).exists():
            with open(self.rules_path, "r", encoding="utf-8") as f:
                self.rules = json.load(f)
        else:
            self.rules = self._get_default_rules()
    
    def _get_default_rules(self) -> Dict:
        return {
            "侮辱贬低类": {
                "keywords": ["笨蛋", "废物", "没用", "垃圾", "白痴", "智障", "蠢货", 
                            "下贱", "卑鄙", "无耻", "丢人", "丑陋", "窝囊废", "没出息",
                            "你怎么这么笨", "你算什么东西", "你有什么用"],
                "patterns": [r"你真.*?(笨|蠢|傻|废)", r"(滚|闭嘴)", r".*?算.*?东西", 
                            r"你.*?(配|资格)"]
            },
            "威胁恐吓类": {
                "keywords": ["打死", "杀了", "弄死", "滚蛋", "滚出去", "不要你", "赶出去",
                            "威胁", "小心点", "打断你的腿", "让你好看", "别想好过"],
                "patterns": [r".*?(小心|等着).*?(收拾|整)", r".*?(让你|看你).*?(好过|舒服)",
                            r"再.*?就.*?(打|滚|收拾)"]
            },
            "情感操控类": {
                "keywords": ["还不是", "要不是为了", "要不是因为", "我容易吗", "我为了谁",
                            "你对的起", "都是你的错", "你不配", "我为你付出"],
                "patterns": [r".*?要不是为了.*?", r".*?都是.*?(的错|害的)", 
                            r"没有我.*?你.*?"]
            },
            "冷暴力类": {
                "keywords": ["不理", "不管", "随便", "无所谓", "爱咋咋", "不说话",
                            "懒得理你", "不想跟你说话", "你自己看着办"],
                "patterns": [r".*?(半天|多久).*?不说话", r"(沉默|冷战)",
                            r"你.*?自己.*?(办|想)"]
            },
            "人身攻击类": {
                "keywords": ["神经病", "有病", "脑子有问题", "心理变态", "疯子", "病态",
                            "脑子进水", "脑残", "变态", "你疯了"],
                "patterns": [r".*?(脑子|神经|心理).*?(问题|有病|变态)", 
                            r".*?是不是.*?(有病|疯了)"]
            },
            "嘲讽讽刺类": {
                "keywords": ["哟", "啧啧", "真是", "厉害", "了不起", "能耐", "本事",
                            "你行你上", "就你聪明", "你可真行"],
                "patterns": [r".*?(哟|啧).*?(厉害|能|行)", r".*?真是.*?(厉害|了不起)",
                            r"就你.*?(聪明|能|行)"]
            }
        }
    
    def analyze(self, text: str, emotion_intensity: str = "low", 
                context: List[Dict] = None) -> Dict:
        """
        混合语义分析
        
        Returns:
            {
                "is_violence": bool,
                "type": str,
                "confidence": float,
                "severity": str,
                "reason": str
            }
        """
        # 步骤1: 规则引擎快速预检
        rule_result = self._rule_based_detection(text)
        
        if rule_result["matched"]:
            confidence = self._adjust_confidence(rule_result["confidence"], emotion_intensity)
            return {
                "is_violence": confidence >= 0.6,
                "type": rule_result["type"],
                "confidence": confidence,
                "severity": self._get_severity(confidence),
                "reason": f"规则匹配: {rule_result['matched_keyword']}"
            }
        
        # 步骤2: LLM 深度分析（处理隐含暴力/间接暴力）
        if self.llm_engine:
            llm_result = self._llm_analysis(text, context, emotion_intensity)
            if llm_result:
                return llm_result
        
        # 无匹配
        return {
            "is_violence": False,
            "type": None,
            "confidence": 0.0,
            "severity": "low",
            "reason": "无暴力特征"
        }
    
    def _rule_based_detection(self, text: str) -> Dict:
        for category, rules in self.rules.items():
            keywords = rules.get("keywords", [])
            for kw in keywords:
                if kw in text:
                    return {"matched": True, "type": category, "confidence": 0.8, "matched_keyword": kw}
            
            patterns = rules.get("patterns", [])
            for pattern in patterns:
                if re.search(pattern, text):
                    return {"matched": True, "type": category, "confidence": 0.8, "matched_keyword": pattern}
        
        return {"matched": False, "type": None, "confidence": 0.0}
    
    def _llm_analysis(self, text: str, context: List[Dict] = None, 
                      emotion_intensity: str = "low") -> Optional[Dict]:
        """LLM 深度分析 — 识别隐含暴力、间接暴力"""
        ctx_lines = ""
        if context:
            recent = context[-3:]
            for c in recent:
                ctx_lines += f"  - {c.get('text', '')} (情绪:{c.get('emotion', {}).get('type', '?')})\n"
        
        prompt = f"""你是一个专业的语言暴力检测专家，专注于家庭场景。

## 任务
判断以下文本是否包含语言暴力。注意识别：
- 直接暴力：辱骂、威胁、恐吓
- 间接暴力：冷嘲热讽、情感操控、道德绑架、隐性贬低
- 语境暴力：看似普通的话但在家庭场景中有施压/控制意味

## 暴力类型
侮辱贬低类 | 威胁恐吓类 | 情感操控类 | 冷暴力类 | 人身攻击类 | 嘲讽讽刺类

## 上下文（最近对话）
{ctx_lines if ctx_lines else "无"}

## 待分析文本
{text}

## 当前说话人情绪强度: {emotion_intensity}

## 输出格式（严格 JSON）
{{"is_violence": true或false, "type": "暴力类型或null", "confidence": 0到1的小数, "severity": "high或medium或low或none", "reason": "判断理由"}}

## 评分指南
- 明确辱骂/威胁 → confidence 0.8-1.0, severity high
- 讽刺/贬低/操控 → confidence 0.6-0.8, severity medium
- 语气重但无明确暴力 → confidence 0.3-0.5, severity low
- 正常交流 → is_violence: false, confidence 0-0.2

## 重要
- "你干嘛呀" 在愤怒语气下可能是责骂，不是简单疑问
- "算了随便你" 在家庭场景可能是冷暴力
- 不要过度敏感：普通讨论/争论不等于语言暴力
- 结合上下文判断，单一短句不要轻易判暴力"""

        result = self.llm_engine.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.15,
            max_tokens=200
        )
        
        if result:
            try:
                json_match = re.search(r'\{[^}]+\}', result, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    confidence = self._adjust_confidence(
                        float(data.get("confidence", 0)),
                        emotion_intensity
                    )
                    return {
                        "is_violence": data.get("is_violence", False) and confidence >= 0.6,
                        "type": data.get("type"),
                        "confidence": confidence,
                        "severity": data.get("severity", "low"),
                        "reason": f"LLM: {data.get('reason', '')}"
                    }
            except Exception as e:
                print(f"LLM语义解析失败: {e}, 原始: {result[:100]}")
        
        return None
    
    def _adjust_confidence(self, base_confidence: float, emotion_intensity: str) -> float:
        adjustments = {"high": 0.3, "medium": 0.15, "low": 0.0}
        return min(1.0, base_confidence + adjustments.get(emotion_intensity, 0))
    
    def _get_severity(self, confidence: float) -> str:
        if confidence >= 0.9: return "high"
        elif confidence >= 0.7: return "medium"
        else: return "low"
    
    def add_rule(self, category: str, keywords: List[str], patterns: List[str] = None):
        if category not in self.rules:
            self.rules[category] = {"keywords": [], "patterns": []}
        self.rules[category]["keywords"].extend(keywords)
        if patterns:
            self.rules[category]["patterns"].extend(patterns)
    
    def save_rules(self, path: str = None):
        save_path = path or self.rules_path
        if save_path:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(self.rules, f, ensure_ascii=False, indent=2)
