#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SemanticAnalyzer 单元测试
"""

import sys, os, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from semantic_analyzer import SemanticAnalyzer


class MockLLM:
    def __init__(self, response=None):
        self.response = response or '{"is_violence": false, "type": null, "confidence": 0.0, "severity": "low", "reason": "正常"}'
        self.call_count = 0

    def chat(self, messages, temperature=0.0, max_tokens=200):
        self.call_count += 1
        return self.response


def fresh_analyzer():
    """创建已加载的 SemanticAnalyzer 实例"""
    a = SemanticAnalyzer()
    a.load()
    return a


class TestRuleBased:
    def test_insults(self):
        a = fresh_analyzer()
        for text, expected in [
            ("你真是个笨蛋", "侮辱贬低类"),
            ("你这个废物", "侮辱贬低类"),
            ("你算什么东西", "侮辱贬低类"),
        ]:
            r = a.analyze(text)
            assert r["is_violence"], f"'{text}' 未检为暴力"
            assert r["type"] == expected, f"类型错误: {r['type']}"

    def test_threats(self):
        a = fresh_analyzer()
        cases = [
            ("小心我打断你的腿", "威胁恐吓类"),
            ("让你好看", "威胁恐吓类"),
            ("滚出去", "侮辱贬低类"),  # 滚命中侮辱贬低类规则
        ]
        for text, expected in cases:
            r = a.analyze(text)
            assert r["is_violence"], f"'{text}' 未检为暴力"
            assert r["type"] == expected, f"类型错误: {r['type']}"

    def test_emotional_manipulation(self):
        a = fresh_analyzer()
        for text, expected in [
            ("要不是为了你", "情感操控类"),
            ("都是你的错", "情感操控类"),
            ("我为你付出这么多", "情感操控类"),
        ]:
            r = a.analyze(text)
            assert r["is_violence"]
            assert r["type"] == expected

    def test_cold_violence(self):
        a = fresh_analyzer()
        for text, expected in [
            ("随便你", "冷暴力类"),
            ("你自己看着办", "冷暴力类"),
            ("不理你了", "冷暴力类"),
        ]:
            r = a.analyze(text)
            assert r["is_violence"]
            assert r["type"] == expected

    def test_personal_attack(self):
        a = fresh_analyzer()
        for text, expected in [
            ("你神经病吧", "人身攻击类"),
            ("你有病吧", "人身攻击类"),
            ("脑子有问题", "人身攻击类"),
        ]:
            r = a.analyze(text)
            assert r["is_violence"]
            assert r["type"] == expected

    def test_sarcasm(self):
        a = fresh_analyzer()
        for text, expected in [
            ("哟，真厉害", "嘲讽讽刺类"),
            ("你可真是了不起", "嘲讽讽刺类"),
            ("就你聪明", "嘲讽讽刺类"),
        ]:
            r = a.analyze(text)
            assert r["is_violence"]
            assert r["type"] == expected

    def test_normal_not_violence(self):
        a = fresh_analyzer()
        for text in ["今天天气真好", "我想吃苹果", "谢谢你的帮助"]:
            r = a.analyze(text)
            assert not r["is_violence"], f"'{text}' 误判为暴力"

    def test_confidence_at_least_06(self):
        a = fresh_analyzer()
        r = a.analyze("你真是个废物")
        assert r["confidence"] >= 0.6

    def test_pattern_regex(self):
        a = fresh_analyzer()
        r = a.analyze("你真的很蠢")
        assert r["is_violence"]
        assert r["type"] == "侮辱贬低类"


class TestConfidenceAdjustment:
    def test_high_emotion_boosts(self):
        a = fresh_analyzer()
        base = a.analyze("你真是个笨蛋", emotion_intensity="low")
        high = a.analyze("你真是个笨蛋", emotion_intensity="high")
        assert high["confidence"] > base["confidence"], "高情绪置信度未提升"

    def test_medium_emotion_boosts(self):
        a = fresh_analyzer()
        base = a.analyze("你真是个笨蛋", emotion_intensity="low")
        med = a.analyze("你真是个笨蛋", emotion_intensity="medium")
        assert med["confidence"] > base["confidence"]

    def test_capped_at_one(self):
        a = fresh_analyzer()
        r = a.analyze("你这个白痴", emotion_intensity="high")
        assert r["confidence"] <= 1.0


class TestLLMFallback:
    def test_llm_called_on_unmatched(self):
        mock = MockLLM()
        a = SemanticAnalyzer(llm_engine=mock)
        a.load()
        a.analyze("今天我们讨论工作安排")
        assert mock.call_count == 1

    def test_llm_not_called_when_rule_matched(self):
        mock = MockLLM()
        a = SemanticAnalyzer(llm_engine=mock)
        a.load()
        a.analyze("你真是个笨蛋")
        assert mock.call_count == 0

    def test_llm_result_used(self):
        mock = MockLLM('{"is_violence": true, "type": "威胁恐吓类", "confidence": 0.75, "severity": "high", "reason": "test"}')
        a = SemanticAnalyzer(llm_engine=mock)
        a.load()
        r = a.analyze("xxx_no_rule_match_xxx")
        assert r["is_violence"]
        assert r["type"] == "威胁恐吓类"
        assert r["severity"] == "high"

    def test_no_llm_no_crash(self):
        a = fresh_analyzer()
        r = a.analyze("你真是个笨蛋")
        assert r["is_violence"]
        assert r["type"] == "侮辱贬低类"

    def test_empty_text(self):
        a = fresh_analyzer()
        r = a.analyze("")
        assert not r["is_violence"]

    def test_short_text(self):
        a = fresh_analyzer()
        r = a.analyze("笨")
        assert "is_violence" in r


class TestCustomRules:
    def test_add_rule(self):
        a = fresh_analyzer()
        a.add_rule("自定义类", ["骂我"], [r".*?骂我.*?"])
        r = a.analyze("你骂我")
        assert r["is_violence"]
        assert r["type"] == "自定义类"

    def test_save_and_load(self):
        a = fresh_analyzer()
        a.add_rule("新类型", ["敏感词"])
        tmp = tempfile.mkdtemp()
        rules_file = os.path.join(tmp, "rules.json")
        try:
            a.save_rules(rules_file)
            assert os.path.exists(rules_file)
            a2 = SemanticAnalyzer(rules_path=rules_file)
            a2.load()
            assert "新类型" in a2.rules
        finally:
            shutil.rmtree(tmp)


class TestSeverity:
    def test_severity_in_valid_set(self):
        a = fresh_analyzer()
        r = a.analyze("你真是个笨蛋")
        assert r["severity"] in ("high", "medium", "low")


def _run_tests(classes):
    import traceback
    total = passed = failed = 0
    for cls in classes:
        print(f"\n{'='*50}\n  {cls.__name__}\n{'='*50}")
        inst = cls()
        for name in dir(inst):
            if name.startswith("test_"):
                total += 1
                try:
                    getattr(inst, name)()
                    print(f"  PASS  {name}")
                    passed += 1
                except AssertionError as e:
                    print(f"  FAIL  {name}: {e}")
                    failed += 1
                except Exception as e:
                    print(f"  ERROR {name}: {e}")
                    traceback.print_exc()
                    failed += 1
    print(f"\n{'='*50}\n  结果: {passed}/{total} 通过  {failed}/{total} 失败\n{'='*50}")
    sys.exit(failed)


if __name__ == "__main__":
    _run_tests([TestRuleBased, TestConfidenceAdjustment, TestLLMFallback, TestCustomRules, TestSeverity])