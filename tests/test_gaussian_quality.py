# -*- coding: utf-8 -*-
"""后处理对比：高斯渲染质量等级选择逻辑测试。

覆盖“点击高斯渲染后弹窗中的快速/标准/高质量”选择：
- 默认“高质量”已在弹窗中选中，不产生额外点击；
- 选择“标准”时点击 (180, 220)，选择“快速”时点击 (70, 220)；
- 未知质量等级抛错。
"""
import unittest
from unittest import mock

from steps.tool.postprocess_compare.gaussian_rendering.v1_0_0 import impl as gaussian_impl


class GaussianQualitySelectTest(unittest.TestCase):
    def test_default_high_quality_does_not_click(self) -> None:
        touch = mock.Mock()
        sleep = mock.Mock()
        gaussian_impl._select_quality(touch, sleep, "高质量")
        touch.assert_not_called()
        sleep.assert_not_called()

    def test_standard_clicks_180_220(self) -> None:
        touch = mock.Mock()
        sleep = mock.Mock()
        gaussian_impl._select_quality(touch, sleep, "标准")
        touch.assert_called_once_with((180, 220))
        sleep.assert_called_once_with(0.5)

    def test_quick_clicks_70_220(self) -> None:
        touch = mock.Mock()
        sleep = mock.Mock()
        gaussian_impl._select_quality(touch, sleep, "快速")
        touch.assert_called_once_with((70, 220))
        sleep.assert_called_once_with(0.5)

    def test_unknown_quality_raises(self) -> None:
        touch = mock.Mock()
        sleep = mock.Mock()
        with self.assertRaises(RuntimeError):
            gaussian_impl._select_quality(touch, sleep, "超高")


if __name__ == "__main__":
    unittest.main()
