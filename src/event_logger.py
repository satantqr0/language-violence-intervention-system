#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
事件日志模块
JSONL + CSV 双格式本地存储
记录完整事件闭环数据
"""

import json
import numpy as np
import csv
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class EventLogger:
    """事件日志记录器"""
    
    def __init__(self, log_dir: str = "./logs"):
        """
        Args:
            log_dir: 日志存储目录
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 文件路径
        self.jsonl_file = self.log_dir / "events.jsonl"
        self.csv_file = self.log_dir / "events.csv"
        
        # CSV表头
        self.csv_headers = [
            "timestamp",
            "text",
            "emotion_type",
            "emotion_intensity", 
            "emotion_score",
            "violence_type",
            "violence_confidence",
            "violence_severity",
            "is_violence",
            "speaker",
            "speaker_verified",
            "speaker_match_source",
            "speaker_match_score",
            "speaker_match_threshold",
            "scene",
            "intervention_triggered",
            "intervention_text",
            "intervention_threshold",
            "volume_level",
            "volume_rms",
            "volume_spike",
            "volume_spike_ratio",
            "pitch_f0",
            "pitch_trend",
            "pitch_jump",
            "acoustic_risk_score",
            "acoustic_risk_factors",
            "analysis_reason"
        ]
        
        # 锁
        self.lock = threading.Lock()
        
        self._restrict_permissions()
        # 初始化CSV文件
        self._init_csv()
        self._restrict_permissions()

    @staticmethod
    def _private_opener(path, flags):
        return os.open(path, flags, 0o600)

    def _restrict_permissions(self):
        """Event transcripts and derived exports are private local records."""
        paths = (
            list(self.log_dir.glob("events*.jsonl"))
            + list(self.log_dir.glob("events*.csv"))
            + list(self.log_dir.glob("*.log"))
        )
        for path in paths:
            if path.exists():
                os.chmod(path, 0o600)
    
    def _init_csv(self):
        """初始化CSV文件"""
        if self.csv_file.exists() and self.csv_file.stat().st_size > 0:
            try:
                with open(self.csv_file, "r", newline="", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    existing_headers = next(reader, [])
                if existing_headers != self.csv_headers:
                    backup = self.csv_file.with_name(
                        f"{self.csv_file.stem}.legacy_{datetime.now().strftime('%Y%m%d_%H%M%S')}{self.csv_file.suffix}"
                    )
                    self.csv_file.rename(backup)
                    os.chmod(backup, 0o600)
            except Exception:
                backup = self.csv_file.with_name(
                    f"{self.csv_file.stem}.legacy_{datetime.now().strftime('%Y%m%d_%H%M%S')}{self.csv_file.suffix}"
                )
                self.csv_file.rename(backup)
                os.chmod(backup, 0o600)

        if not self.csv_file.exists() or self.csv_file.stat().st_size == 0:
            with open(self.csv_file, "w", newline="", encoding="utf-8", opener=self._private_opener) as f:
                writer = csv.DictWriter(f, fieldnames=self.csv_headers)
                writer.writeheader()
    
    def log(self, event_data: Dict):
        """
        记录事件
        
        Args:
            event_data: 事件数据字典
        """
        with self.lock:
            # 写入JSONL
            self._write_jsonl(event_data)
            
            # 写入CSV
            self._write_csv(event_data)
    
    def _write_jsonl(self, event_data: Dict):
        """写入JSONL格式"""
        with open(self.jsonl_file, "a", encoding="utf-8", opener=self._private_opener) as f:
            json_line = json.dumps(event_data, ensure_ascii=False, default=lambda o: bool(o) if isinstance(o, (np.bool_,)) else int(o) if isinstance(o, np.integer) else float(o) if isinstance(o, np.floating) else str(o))
            f.write(json_line + "\n")
        os.chmod(self.jsonl_file, 0o600)
    
    def _write_csv(self, event_data: Dict):
        """写入CSV格式"""
        # 准备CSV行数据
        row = {header: event_data.get(header, "") for header in self.csv_headers}
        
        # 追加到CSV
        with open(self.csv_file, "a", newline="", encoding="utf-8", opener=self._private_opener) as f:
            writer = csv.DictWriter(f, fieldnames=self.csv_headers)
            writer.writerow(row)
        os.chmod(self.csv_file, 0o600)
    
    def get_recent_events(self, limit: int = 100) -> List[Dict]:
        """
        获取最近的事件
        
        Args:
            limit: 返回数量限制
            
        Returns:
            事件列表
        """
        events = []
        
        if not self.jsonl_file.exists():
            return events
        
        with self.lock:
            # 倒序读取最后limit行
            with open(self.jsonl_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            for line in lines[-limit:]:
                try:
                    event = json.loads(line.strip())
                    events.append(event)
                except:
                    continue
        
        return events
    
    def get_events_by_scene(self, scene: str, limit: int = 100) -> List[Dict]:
        """按场景筛选事件"""
        all_events = self.get_recent_events(limit * 2)
        return [e for e in all_events if e.get("scene") == scene][:limit]
    
    def get_violence_events(self, limit: int = 100) -> List[Dict]:
        """获取检测到暴力的所有事件"""
        all_events = self.get_recent_events(limit * 2)
        return [e for e in all_events if e.get("is_violence")][:limit]
    
    def export_to_csv(self, output_path: str, start_date: str = None, end_date: str = None):
        """
        导出事件到CSV文件
        
        Args:
            output_path: 输出文件路径
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        """
        events = self.get_recent_events(limit=100000)
        
        # 日期筛选
        if start_date or end_date:
            filtered = []
            for e in events:
                ts = e.get("timestamp", "")[:10]  # YYYY-MM-DD
                if start_date and ts < start_date:
                    continue
                if end_date and ts > end_date:
                    continue
                filtered.append(e)
            events = filtered
        
        with open(output_path, "w", newline="", encoding="utf-8", opener=self._private_opener) as f:
            writer = csv.DictWriter(f, fieldnames=self.csv_headers)
            writer.writeheader()
            for e in events:
                row = {header: e.get(header, "") for header in self.csv_headers}
                writer.writerow(row)
        os.chmod(output_path, 0o600)
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        events = self.get_recent_events(limit=10000)
        
        if not events:
            return {
                "total_events": 0,
                "violence_count": 0,
                "violence_rate": 0.0,
                "scenes": {}
            }
        
        violence_count = sum(1 for e in events if e.get("is_violence"))
        
        # 各场景统计
        scenes = {}
        for e in events:
            scene = e.get("scene", "unknown")
            scenes[scene] = scenes.get(scene, 0) + 1
        
        # 暴力类型分布
        violence_types = {}
        for e in events:
            if e.get("is_violence"):
                vt = e.get("violence_type", "unknown")
                violence_types[vt] = violence_types.get(vt, 0) + 1
        
        return {
            "total_events": len(events),
            "violence_count": violence_count,
            "violence_rate": round(violence_count / len(events) * 100, 2),
            "scenes": scenes,
            "violence_types": violence_types
        }
    
    def close(self):
        """关闭日志器"""
        # 无需关闭，日志文件保持打开状态
        pass
    
    def __del__(self):
        self.close()
