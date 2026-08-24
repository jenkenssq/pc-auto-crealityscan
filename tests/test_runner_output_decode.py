import unittest

from jens_platform.runner import _decode_process_output


class ProcessOutputDecodeTests(unittest.TestCase):
    def test_decodes_utf8_output(self) -> None:
        text = "[JENS] run_dir=D:\\自动化工具\\任务"
        self.assertEqual(_decode_process_output(text.encode("utf-8")), text)

    def test_falls_back_to_windows_ansi_output(self) -> None:
        text = "[JENS] run_dir=D:\\自动化工具\\任务"
        self.assertEqual(_decode_process_output(text.encode("gbk")), text)


if __name__ == "__main__":
    unittest.main()
