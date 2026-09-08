from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, List, Tuple

import mss
import numpy as np
from PIL import Image

try:
    from rapidocr_onnxruntime import RapidOCR  # pip install rapidocr-onnxruntime
except Exception:
    RapidOCR = None


NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
FPS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*fps", re.IGNORECASE)


def parse_box(text: str) -> Tuple[int, int, int, int]:
    # 输入格式: x1,y1,x2,y2
    vals = [int(x.strip()) for x in text.replace("，", ",").split(",")]
    if len(vals) != 4:
        raise ValueError("需要 4 个整数: x1,y1,x2,y2")
    x1, y1, x2, y2 = vals
    if x2 <= x1 or y2 <= y1:
        raise ValueError("右下坐标必须大于左上坐标")
    return x1, y1, x2, y2


def iter_ocr_candidates(node: Any) -> List[Tuple[str, float]]:
    out: List[Tuple[str, float]] = []

    def walk(cur: Any) -> None:
        if isinstance(cur, str):
            s = cur.strip()
            if s:
                out.append((s, 1.0))
            return

        if isinstance(cur, dict):
            for v in cur.values():
                walk(v)
            return

        if isinstance(cur, (list, tuple)):
            if len(cur) >= 2 and isinstance(cur[1], str):
                score = float(cur[2]) if len(cur) >= 3 and isinstance(cur[2], (int, float)) else 1.0
                s = cur[1].strip()
                if s:
                    out.append((s, score))
            if (
                len(cur) >= 2
                and isinstance(cur[1], (list, tuple))
                and len(cur[1]) >= 1
                and isinstance(cur[1][0], str)
            ):
                score = float(cur[1][1]) if len(cur[1]) >= 2 and isinstance(cur[1][1], (int, float)) else 1.0
                s = cur[1][0].strip()
                if s:
                    out.append((s, score))
            for x in cur:
                walk(x)

    walk(node)
    return out


def extract_fps(text: str) -> float | None:
    if not text:
        return None
    norm = text.lower().replace(" ", "").replace(",", ".")
    m = FPS_RE.search(norm)
    if m:
        return float(m.group(1))
    m2 = NUMBER_RE.search(norm)
    if not m2:
        return None
    v = float(m2.group(0))
    return v if 0 <= v <= 240 else None


def ocr_read(ocr, img_bgr: np.ndarray) -> Tuple[List[Tuple[str, float]], float | None]:
    variants = [img_bgr]
    up = np.repeat(np.repeat(img_bgr, 3, axis=0), 3, axis=1)
    variants.append(up)

    gray = (0.114 * img_bgr[:, :, 0] + 0.587 * img_bgr[:, :, 1] + 0.299 * img_bgr[:, :, 2]).astype(np.uint8)
    bw = np.where(gray > 140, 255, 0).astype(np.uint8)
    bw3 = np.stack([bw, bw, bw], axis=2)
    variants.append(bw3)

    all_cands: List[Tuple[str, float]] = []
    for v in variants:
        out = ocr(v)
        if isinstance(out, tuple) and len(out) >= 1:
            out = out[0]
        cands = iter_ocr_candidates(out)
        all_cands.extend(cands)
        for t, _ in cands:
            fps = extract_fps(t)
            if fps is not None:
                return all_cands, fps
    return all_cands, None


def main() -> int:
    save_dir = Path("artifacts/_ocr_debug")
    save_dir.mkdir(parents=True, exist_ok=True)

    ocr = RapidOCR() if RapidOCR else None
    if ocr is None:
        print("[WARN] 未安装 rapidocr-onnxruntime，仅截图不识别。")

    print("输入坐标: x1,y1,x2,y2  (例如: 425,233,523,264)")
    print("输入 q 退出。直接回车可重复上一次坐标。")

    last_box: Tuple[int, int, int, int] | None = None

    with mss.mss() as sct:
        while True:
            raw = input("\n坐标> ").strip()
            if raw.lower() in {"q", "quit", "exit"}:
                break

            try:
                if not raw:
                    if last_box is None:
                        print("请先输入一次坐标")
                        continue
                    x1, y1, x2, y2 = last_box
                else:
                    x1, y1, x2, y2 = parse_box(raw)
                    last_box = (x1, y1, x2, y2)

                monitor = {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}
                shot = sct.grab(monitor)
                arr = np.frombuffer(shot.bgra, dtype=np.uint8).reshape((shot.height, shot.width, 4))
                bgr = arr[:, :, :3]  # BGR

                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                png = save_dir / f"ocr_roi_{ts}.png"
                txt = save_dir / f"ocr_roi_{ts}.txt"

                # 保存为 RGB PNG 方便查看
                Image.fromarray(bgr[:, :, ::-1]).save(str(png))

                lines = [f"box=({x1},{y1})-({x2},{y2})", f"size={x2-x1}x{y2-y1}"]
                if ocr is not None:
                    cands, fps = ocr_read(ocr, bgr)
                    lines.append("ocr_candidates:")
                    for t, s in cands[:20]:
                        lines.append(f"score={s:.3f} text={t}")
                    lines.append(f"parsed_fps={fps}")
                    print(f"[OK] {png}  parsed_fps={fps}")
                else:
                    print(f"[OK] {png}")

                txt.write_text("\n".join(lines), encoding="utf-8")
                print(f"[TXT] {txt}")

            except Exception as e:
                print(f"[ERR] {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
