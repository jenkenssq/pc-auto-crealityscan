from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


Point = Tuple[int, int]


@dataclass
class DesktopConfig:
    default_confidence: Optional[float] = 0.9
    pause_sec: float = 0.1
    fail_safe: bool = True


class PyAutoGuiDesktop:
    def __init__(self, config: Optional[DesktopConfig] = None) -> None:
        self.config = config or DesktopConfig()
        self._pyautogui = self._load_pyautogui()

    def _load_pyautogui(self):
        try:
            import pyautogui  # type: ignore
        except Exception as exc:  # pragma: no cover - import depends on target env
            raise RuntimeError(
                "PyAutoGUI is not installed. Install dependencies from requirements-mac.txt first."
            ) from exc
        pyautogui.FAILSAFE = self.config.fail_safe
        pyautogui.PAUSE = max(0.0, float(self.config.pause_sec))
        return pyautogui

    @property
    def mod(self):
        return self._pyautogui

    def size(self) -> Point:
        width, height = self.mod.size()
        return int(width), int(height)

    def screenshot(self, path: str) -> str:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.mod.screenshot(str(target))
        return str(target)

    def sleep(self, sec: float) -> None:
        time.sleep(max(0.0, float(sec)))

    def move_mouse(self, x: int, y: int, duration_sec: float = 0.35) -> None:
        self.mod.moveTo(int(x), int(y), duration=max(0.0, float(duration_sec)))

    def click_point(
        self,
        x: int,
        y: int,
        clicks: int = 1,
        interval_sec: float = 0.0,
        button: str = "left",
    ) -> Point:
        self.mod.click(int(x), int(y), clicks=int(clicks), interval=max(0.0, float(interval_sec)), button=button)
        return int(x), int(y)

    def write_text(self, text: str, interval_sec: float = 0.02) -> None:
        self.mod.write(str(text), interval=max(0.0, float(interval_sec)))

    def press_key(self, key: str) -> None:
        self.mod.press(key)

    def hotkey(self, *keys: str) -> None:
        self.mod.hotkey(*keys)

    def _locate_center_once(
        self,
        image_path: str,
        confidence: Optional[float] = None,
        grayscale: bool = False,
    ) -> Optional[Point]:
        kwargs = {"grayscale": bool(grayscale)}
        if confidence is not None:
            kwargs["confidence"] = float(confidence)
        try:
            hit = self.mod.locateCenterOnScreen(image_path, **kwargs)
        except getattr(self.mod, "ImageNotFoundException", Exception):
            return None
        except NotImplementedError as exc:
            raise RuntimeError(
                "Image matching with confidence requires opencv-python. Install requirements-mac.txt."
            ) from exc
        if hit is None:
            return None
        return int(hit.x), int(hit.y)

    def locate_center(
        self,
        image_path: str,
        confidence: Optional[float] = None,
        grayscale: bool = False,
        timeout_sec: float = 0.0,
        interval_sec: float = 0.5,
    ) -> Optional[Point]:
        deadline = time.time() + max(0.0, float(timeout_sec))
        effective_confidence = self.config.default_confidence if confidence is None else confidence
        while True:
            hit = self._locate_center_once(
                image_path=image_path,
                confidence=effective_confidence,
                grayscale=grayscale,
            )
            if hit is not None:
                return hit
            if timeout_sec <= 0 or time.time() >= deadline:
                return None
            time.sleep(max(0.05, float(interval_sec)))

    def image_exists(
        self,
        image_path: str,
        confidence: Optional[float] = None,
        grayscale: bool = False,
    ) -> bool:
        return self.locate_center(image_path, confidence=confidence, grayscale=grayscale, timeout_sec=0) is not None

    def wait_image(
        self,
        image_path: str,
        confidence: Optional[float] = None,
        grayscale: bool = False,
        timeout_sec: float = 10.0,
        interval_sec: float = 0.5,
    ) -> Point:
        hit = self.locate_center(
            image_path=image_path,
            confidence=confidence,
            grayscale=grayscale,
            timeout_sec=timeout_sec,
            interval_sec=interval_sec,
        )
        if hit is None:
            raise RuntimeError(f"Image not found before timeout: {image_path}")
        return hit

    def wait_image_gone(
        self,
        image_path: str,
        confidence: Optional[float] = None,
        grayscale: bool = False,
        timeout_sec: float = 10.0,
        interval_sec: float = 0.5,
    ) -> None:
        deadline = time.time() + max(0.0, float(timeout_sec))
        effective_confidence = self.config.default_confidence if confidence is None else confidence
        while time.time() < deadline:
            hit = self._locate_center_once(
                image_path=image_path,
                confidence=effective_confidence,
                grayscale=grayscale,
            )
            if hit is None:
                return
            time.sleep(max(0.05, float(interval_sec)))
        raise RuntimeError(f"Image still visible after timeout: {image_path}")

    def click_image(
        self,
        image_path: str,
        confidence: Optional[float] = None,
        grayscale: bool = False,
        timeout_sec: float = 8.0,
        interval_sec: float = 0.5,
        move_duration_sec: float = 0.2,
    ) -> Point:
        x, y = self.wait_image(
            image_path=image_path,
            confidence=confidence,
            grayscale=grayscale,
            timeout_sec=timeout_sec,
            interval_sec=interval_sec,
        )
        self.move_mouse(x, y, duration_sec=move_duration_sec)
        self.click_point(x, y)
        return x, y

    def check_environment(self, expected_resolution: Optional[Tuple[int, int]] = None) -> dict:
        size = self.size()
        if expected_resolution and tuple(expected_resolution) != tuple(size):
            raise RuntimeError(
                f"Unexpected primary display resolution: got {size}, expected {tuple(expected_resolution)}"
            )
        try:
            self.mod.screenshot()
        except Exception as exc:
            raise RuntimeError(
                "Screenshot failed. On macOS, verify Screen Recording permission for Terminal/Python."
            ) from exc
        return {
            "screen_width": str(size[0]),
            "screen_height": str(size[1]),
            "primary_monitor_only": "true",
        }

