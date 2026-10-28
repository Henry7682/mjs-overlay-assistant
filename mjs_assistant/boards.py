from __future__ import annotations

import datetime as dt
import hashlib
import re
from pathlib import Path

import cv2
import numpy as np

from .ocr import Names
from .modes import MODES, MINGDAO, PEAK_SHUANGLONG, board_mode, identify_chart

MODE = "明刀暗箭·8人身份"


def validate_board(board):
    if not isinstance(board, dict):
        return ['榜单根节点必须是对象']
    problems = []
    if not board_mode(board):
        problems.append("榜单模式未确认或模式标识与名称不一致")
    if board.get('schema_version',1) not in (1,2): problems.append('不支持的榜单版本')
    if board_mode(board)==PEAK_SHUANGLONG:
        evidence=board.get('mode_evidence') or {}
        if (evidence.get('status') not in ('source-reviewed','user-reviewed') or not evidence.get('source_url')
            or any(evidence.get(k)!=board.get(k) for k in ('period_start','period_end'))):
            problems.append('双龙争鼎需要与本统计周期一致的玩法来源核对')
    try:
        start = dt.date.fromisoformat(board["period_start"])
        end = dt.date.fromisoformat(board["period_end"])
        if start > end or end > dt.date.today() or (end - start).days > 40:
            problems.append("统计周期异常")
    except (ValueError, KeyError, TypeError):
        problems.append("统计周期无效，请填写 YYYY-MM-DD")
    heroes = board.get("heroes", [])
    if not isinstance(heroes, list) or any(not isinstance(x, dict) for x in heroes):
        return problems + ['武将数据必须是对象列表']
    n = len(heroes)
    if n < 50:
        problems.append("榜单少于50条，可能未完整导入")
    if board.get("expected_count") != n:
        problems.append("条数与原图最大排名不一致")
    names = [x.get("name", "") for x in heroes]
    if any(not isinstance(s,str) for s in names):
        return problems + ['武将名称必须为文本']
    if len(set(names)) != n or any(not re.fullmatch(r"[\u3400-\u9fff]{2,6}", s) for s in names):
        problems.append("武将名称为空、重复或含非法字符")
    for key in ("win_rank", "pick_rank"):
        ranks = [x.get(key) for x in heroes]
        if any(type(x) is not int for x in ranks) or set(ranks) != set(range(1, n + 1)):
            problems.append(f"{key} 必须从1连续到{n}且不重复")
    rates = [x.get("win_rate") for x in heroes]
    if any(type(x) not in (float, int) or not 0 <= x <= 100 for x in rates):
        problems.append("胜率应为0—100之间的数值")
    elif all(type(x.get("win_rank")) is int for x in heroes):
        ordered = sorted(heroes, key=lambda x: x["win_rank"])
        if any(a["win_rate"] < b["win_rate"] for a, b in zip(ordered, ordered[1:])):
            problems.append("胜率未按排名递减")
    if board.get("issues"):
        problems.extend(board["issues"])
    if board.get('review_status')=='pending_full_review': problems.append('尚未完成全表复核')
    if not board.get("source_url"):
        problems.append("缺少来源地址或本地图片路径")
    return problems


def decode_image(data):
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("无法读取图片")
    if img.shape[0] * img.shape[1] > 60_000_000:
        raise ValueError("图片过大（上限6000万像素）")
    return img


def parse_words(words, width, names: Names, source_url, image_hash="", year=None):
    """Parse visual rows, never fixed text-line offsets. Return a reviewable draft."""
    all_text = " ".join(x.text for x in words)
    mode_id=identify_chart(all_text)
    year = year or dt.date.today().year
    period = re.search(r"(\d{1,2})[.月/](\d{1,2})\s*[-~～—至]+\s*(\d{1,2})[.月/](\d{1,2})", all_text)
    start = end = ""
    if period:
        m1, d1, m2, d2 = map(int, period.groups())
        try:
            start = dt.date(year - (m1 > m2), m1, d1).isoformat()
            end = dt.date(year, m2, d2).isoformat()
        except ValueError:
            pass
    left, right, issues = [], [], []
    for side in (0, 1):
        candidates = [w for w in words if ((w.box[0] + w.box[2]) / 2 < width * .49) == (side == 0)]
        rows = []
        for word in sorted(candidates, key=lambda w: (w.box[1] + w.box[3]) / 2):
            cy = (word.box[1] + word.box[3]) / 2
            if not rows or abs(cy - rows[-1][0]) > max(7, (word.box[3] - word.box[1]) * .55):
                rows.append((cy, [word]))
            else:
                rows[-1][1].append(word)
        for cy, row in rows:
            row.sort(key=lambda w: w.box[0])
            if len(row) < 2:
                continue
            rank_text = row[0].text.strip().replace("I", "1").replace("l", "1")
            if not re.fullmatch(r"\d{1,3}", rank_text):
                continue
            rank = int(rank_text)
            if not 1 <= rank <= 999:
                continue
            if side == 0:
                raw = "".join(w.text for w in row[1:])
                match = re.search(r"(\d{1,3}\.\d{2})\s*[%％]", raw)
                if not match:
                    continue
                raw_name = raw[:match.start()].strip()
                name = names.resolve(raw_name) or raw_name
                left.append({"name": name, "win_rank": rank, "win_rate": float(match.group(1)), "raw_name": raw_name, "y": cy})
            else:
                raw_name = "".join(w.text for w in row[1:]).strip()
                if not re.search(r"[\u3400-\u9fff]", raw_name):
                    continue
                name = names.resolve(raw_name) or raw_name
                right.append({"name": name, "pick_rank": rank, "raw_name": raw_name, "y": cy})
            if names.resolve(raw_name) is None:
                issues.append(f"第{rank}名姓名待核对：{raw_name}")
            if min(w.confidence for w in row) < .85:
                issues.append(f"{'胜率' if side == 0 else '出场'}第{rank}名识别置信度不足")
    picks = {x["name"]: x["pick_rank"] for x in right}
    heroes = [{"name": x["name"], "win_rate": x["win_rate"], "win_rank": x["win_rank"], "pick_rank": picks.get(x["name"])} for x in left]
    if len(set(x["pick_rank"] for x in right)) != len(right):
        issues.append("出场榜存在重复排名")
    if len(right) != len(left):
        issues.append("两份榜单条数不一致")
    return {"schema_version": 2, "mode_id":mode_id, "mode": MODES.get(mode_id,"未确认模式"), "period_start": start, "period_end": end,
            "source_url": source_url, "image_sha256": image_hash,
            "expected_count": max([x["win_rank"] for x in left] + [0]), "heroes": heroes,
            "issues": sorted(set(issues)), "review_status": "ocr", "raw_win_rows": left, "raw_pick_rows": right}


def import_image(path, ocr, names, source_url=None):
    data = Path(path).read_bytes()
    bgr = decode_image(data)
    draft = parse_words(ocr.document(bgr), bgr.shape[1], names, source_url or str(Path(path).resolve()), hashlib.sha256(data).hexdigest())
    draft["image_path"] = str(Path(path).resolve())
    return draft
