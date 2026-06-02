#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SceneManager 单元测试
"""

import sys, os, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from scene_manager import SceneManager


def mktmp():
    return tempfile.mkdtemp()


class TestBasics:
    def test_default_scene(self):
        m = SceneManager()
        assert m.current_scene == "家庭"
        assert m.sensitivity == 0.6

    def test_custom_default(self):
        m = SceneManager(default_scene="夫妻")
        assert m.current_scene == "夫妻"
        assert m.sensitivity == 0.7

    def test_load_no_crash(self):
        m = SceneManager()
        m.load()


class TestDetection:
    def test_detect_family(self):
        # 从不同默认场景检测，避免当前场景相同返回 None
        m = SceneManager(default_scene="夫妻")
        assert m.detect_scene("爸妈在家里做家务") == "家庭"

    def test_detect_couple(self):
        m = SceneManager(default_scene="家庭")
        assert m.detect_scene("老公什么时候回家") == "夫妻"

    def test_detect_education(self):
        m = SceneManager(default_scene="家庭")
        assert m.detect_scene("老师布置了很多作业") == "教育"

    def test_detect_child_protection(self):
        m = SceneManager(default_scene="家庭")
        assert m.detect_scene("不要打小孩") == "儿童保护"

    def test_child_protection_wins_keyword_tie(self):
        m = SceneManager(default_scene="家庭")
        assert m.detect_scene("孩子作业没写") == "儿童保护"

    def test_no_switch_on_same_scene(self):
        m = SceneManager(default_scene="家庭")
        assert m.detect_scene("我和爸妈在家里") is None

    def test_no_match(self):
        m = SceneManager(default_scene="家庭")
        assert m.detect_scene("今天天气很好") is None


class TestSwitching:
    def test_switch_valid(self):
        m = SceneManager(default_scene="家庭")
        ok = m.switch_scene("夫妻")
        assert ok
        assert m.current_scene == "夫妻"
        assert m.sensitivity == 0.7

    def test_switch_updates_sensitivity(self):
        m = SceneManager(default_scene="家庭")
        m.switch_scene("儿童保护")
        assert m.sensitivity == 0.9

    def test_switch_invalid_fails(self):
        m = SceneManager()
        ok = m.switch_scene("不存在的场景")
        assert not ok
        assert m.current_scene == "家庭"


class TestSensitivity:
    def test_get_sensitivity(self):
        m = SceneManager(default_scene="教育")
        assert m.get_sensitivity() == 0.5

    def test_set_sensitivity_clamp_max(self):
        m = SceneManager()
        m.set_sensitivity(2.0)
        assert m.sensitivity == 1.0

    def test_set_sensitivity_clamp_min(self):
        m = SceneManager()
        m.set_sensitivity(-0.5)
        assert m.sensitivity == 0.0

    def test_set_sensitivity_valid(self):
        m = SceneManager()
        m.set_sensitivity(0.8)
        assert m.sensitivity == 0.8


class TestPresetScenes:
    def test_child_protection_highest(self):
        m = SceneManager(default_scene="儿童保护")
        assert m.sensitivity == 0.9

    def test_list_scenes(self):
        m = SceneManager()
        scenes = m.list_scenes()
        assert "家庭" in scenes
        assert "夫妻" in scenes
        assert "教育" in scenes
        assert "儿童保护" in scenes
        assert "自定义" in scenes

    def test_get_scene_config(self):
        m = SceneManager()
        cfg = m.get_scene_config("儿童保护")
        assert cfg["sensitivity"] == 0.9


class TestCustomKeywords:
    def test_add_custom_keywords(self):
        m = SceneManager(default_scene="家庭")
        m.add_custom_keywords("自定义", ["特有关键词"])
        assert m.detect_scene("这里有特有关键词") == "自定义"


class TestSaveLoad:
    def test_save_and_load(self):
        tmp = mktmp()
        cfg_file = os.path.join(tmp, "scene.json")
        try:
            m = SceneManager(default_scene="夫妻")
            m.set_sensitivity(0.75)
            m.save_config(cfg_file)
            assert os.path.exists(cfg_file)
            m2 = SceneManager()
            m2.load_config(cfg_file)
            assert m2.current_scene == "夫妻"
            assert m2.sensitivity == 0.75
        finally:
            shutil.rmtree(tmp)


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
    _run_tests([TestBasics, TestDetection, TestSwitching, TestSensitivity,
                 TestPresetScenes, TestCustomKeywords, TestSaveLoad])
