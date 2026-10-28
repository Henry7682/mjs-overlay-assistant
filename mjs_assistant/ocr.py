from __future__ import annotations

import re
import threading
from dataclasses import dataclass

import cv2
import numpy as np

from .storage import ASSETS, read_json


@dataclass
class Word:
    text: str
    confidence: float
    box: tuple[float, float, float, float]


def clean_name(text):
    return re.sub(r"[^\u3400-\u9fff]", "", text)


class Ocr:
    def __init__(self):
        from rapidocr import RapidOCR
        models = ASSETS / "models"
        params = {"EngineConfig.onnxruntime.intra_op_num_threads": 2,
                  "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                  "Det.limit_side_len": 960, "Det.limit_type": "max", "Global.use_cls": False}
        for key, filename in (("Det", "det.onnx"), ("Cls", "cls.onnx"), ("Rec", "rec.onnx")):
            if not (models / filename).exists():
                raise FileNotFoundError(f"OCR 模型缺失：{filename}，请使用完整便携包")
            params[f"{key}.model_path"] = str(models / filename)
        self.engine = RapidOCR(params=params)
        self.lock = threading.Lock()

    def read(self, bgr: np.ndarray) -> list[Word]:
        if bgr is None or not bgr.size:
            return []
        with self.lock:
            result = self.engine(bgr)
        if result.boxes is None:
            return []
        words = []
        for box, text, score in zip(result.boxes, result.txts, result.scores):
            p = np.asarray(box)
            words.append(Word(text.strip(), float(score), (float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max()))))
        return words

    def document(self, bgr, before_read=lambda:None):
        """Tile tall official charts without shrinking characters to unreadable sizes."""
        h, w = bgr.shape[:2]
        output = []
        for y in range(0, h, 1100):
            before_read()
            start, end = max(0, y - 70), min(h, y + 1170)
            for word in self.read(bgr[start:end]):
                x1, y1, x2, y2 = word.box
                cy = (y1 + y2) / 2 + start
                if y <= cy < min(h, y + 1100):
                    output.append(Word(word.text, word.confidence, (x1, y1 + start, x2, y2 + start)))
        return output


class Names:
    def __init__(self, extra=()):
        data = read_json(ASSETS / "names.json", {})
        self.names = set(data.get("names", [])) | set(extra)
        self.aliases = data.get("aliases", {})

    def resolve(self, text):
        name = clean_name(text)
        if name in self.names:
            return name
        target = self.aliases.get(name)
        return target if target in self.names else None

    def candidates(self, text):
        import difflib
        return difflib.get_close_matches(clean_name(text), sorted(self.names), n=5, cutoff=0.45)
