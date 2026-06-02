#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
场景识别与切换模块
内置5种预设场景：家庭、夫妻、教育、儿童保护、自定义
根据文本关键词自动识别切换场景
儿童保护模式灵敏度≥0.9
"""

import json
from typing import Dict, List, Optional
from pathlib import Path


class SceneManager:
    """场景管理器"""

    # When keyword scores tie, prefer the mode with stronger protection.
    SCENE_TIE_PRIORITY = {
        "儿童保护": 4,
        "教育": 3,
        "夫妻": 2,
        "家庭": 1,
        "自定义": 0,
    }
    
    # 预设场景定义
    PRESET_SCENES = {
        "家庭": {
            "sensitivity": 0.6,
            "keywords": ["家人", "家里", "爸", "妈", "哥", "姐", "弟", "妹", "亲戚", "家务", "生活费", "房子"],
            "description": "普通家庭场景"
        },
        "夫妻": {
            "sensitivity": 0.7,
            "keywords": ["老公", "老婆", "丈夫", "妻子", "结婚", "离婚", "孩子", "教育", "工作"],
            "description": "夫妻关系场景"
        },
        "教育": {
            "sensitivity": 0.5,
            "keywords": ["老师", "学生", "作业", "考试", "学习", "成绩", "学校", "补课", "课堂"],
            "description": "师生教育场景"
        },
        "儿童保护": {
            "sensitivity": 0.9,
            "keywords": ["小孩", "儿童", "孩子", "宝宝", "小朋友", "虐待", "打", "骂", "欺负"],
            "description": "儿童保护高敏场景"
        },
        "自定义": {
            "sensitivity": 0.6,
            "keywords": [],
            "description": "用户自定义场景"
        }
    }
    
    def __init__(self, default_scene: str = "家庭"):
        self.current_scene = default_scene
        self.sensitivity = self.PRESET_SCENES.get(default_scene, {}).get("sensitivity", 0.6)
        self.custom_keywords: Dict[str, List[str]] = {}
        
    def load(self):
        """加载场景配置"""
        print("   初始化场景管理器...")
        print(f"   默认场景: {self.current_scene}, 灵敏度: {self.sensitivity}")
    
    def detect_scene(self, text: str) -> Optional[str]:
        """
        根据文本检测场景
        
        Returns:
            检测到的场景名称，若无变化返回None
        """
        scores: Dict[str, int] = {}
        
        for scene_name, scene_config in self.PRESET_SCENES.items():
            keywords = scene_config.get("keywords", [])
            if scene_name == "自定义":
                keywords = self.custom_keywords.get(scene_name, [])
            
            # 计算关键词命中数
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[scene_name] = score
        
        if not scores:
            return None
        
        # 相同命中数时优先启用更高保护级别，避免儿童相关语句落入低敏模式。
        detected = max(
            scores,
            key=lambda name: (scores[name], self.SCENE_TIE_PRIORITY.get(name, 0))
        )
        
        # 只有当得分超过阈值时才切换
        if detected != self.current_scene and scores[detected] >= 1:
            return detected
        
        return None
    
    def switch_scene(self, scene_name: str) -> bool:
        """切换场景"""
        if scene_name in self.PRESET_SCENES:
            self.current_scene = scene_name
            self.sensitivity = self.PRESET_SCENES[scene_name]["sensitivity"]
            print(f"   场景已切换: {scene_name}, 灵敏度: {self.sensitivity}")
            return True
        return False
    
    def get_sensitivity(self) -> float:
        """获取当前灵敏度"""
        return self.sensitivity
    
    def set_sensitivity(self, sensitivity: float):
        """设置自定义灵敏度"""
        self.sensitivity = max(0.0, min(1.0, sensitivity))
    
    def add_custom_keywords(self, scene_name: str, keywords: List[str]):
        """添加自定义关键词到指定场景"""
        if scene_name not in self.custom_keywords:
            self.custom_keywords[scene_name] = []
        self.custom_keywords[scene_name].extend(keywords)
    
    def get_scene_config(self, scene_name: str = None) -> Dict:
        """获取场景配置"""
        name = scene_name or self.current_scene
        return self.PRESET_SCENES.get(name, {})
    
    def list_scenes(self) -> List[str]:
        """列出所有可用场景"""
        return list(self.PRESET_SCENES.keys())
    
    def save_config(self, path: str):
        """保存配置到文件"""
        config = {
            "default_scene": self.current_scene,
            "sensitivity": self.sensitivity,
            "custom_keywords": self.custom_keywords
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    
    def load_config(self, path: str):
        """从文件加载配置"""
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        self.current_scene = config.get("default_scene", "家庭")
        self.sensitivity = config.get("sensitivity", 0.6)
        self.custom_keywords = config.get("custom_keywords", {})
