"""Display-only source mapping: raw board storage/update identities stay intact."""
from .modes import RANKED_CHUHAN, PEAK_CHUHAN, MODES


def statistics_mode(game_mode):
    return PEAK_CHUHAN if game_mode == RANKED_CHUHAN else game_mode


def source_label(game_mode):
    return ('排位·楚汉争霸｜统计来源：巅峰楚汉' if game_mode == RANKED_CHUHAN
            else MODES.get(game_mode, '模式待确认'))


def is_strong(record):
    if not record:
        return False
    win, pick = record.get('win_rank'), record.get('pick_rank')
    valid = lambda x: isinstance(x, int) and not isinstance(x, bool) and x > 0
    return bool(valid(win) and (win <= 20 or (win <= 50 and valid(pick) and pick <= 50)))
