import unittest

from steps.crealityscan.scan_until_frames_then_stop.v1_0_0.impl import _extract_frame_from_text


class ScanUntilFramesThenStopOcrTests(unittest.TestCase):
    def test_extract_frame_joined_digits_for_thousands_separator(self) -> None:
        self.assertEqual(_extract_frame_from_text("1,12"), 112)
        self.assertEqual(_extract_frame_from_text("1.01"), 101)
        self.assertEqual(_extract_frame_from_text("帧数 1,198"), 1198)

    def test_extract_frame_plain_digits(self) -> None:
        self.assertEqual(_extract_frame_from_text("63"), 63)
        self.assertEqual(_extract_frame_from_text("9"), 9)


if __name__ == "__main__":
    unittest.main()
