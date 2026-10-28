"""Explicit mode identity. Display strings are never cross-season aliases."""
from dataclasses import dataclass
import re

MINGDAO='ranked_identity_mingdao'
RANKED_CHUHAN='ranked_chuhan_2v2'
PEAK_CHUHAN='peak_chuhan_2v2'
PEAK_SHUANGLONG='peak_identity_shuanglong'
MODES={MINGDAO:'明刀暗箭·8人身份',RANKED_CHUHAN:'排位·楚汉争霸（二二对战）',
       PEAK_CHUHAN:'巅峰竞技场·楚汉争霸',PEAK_SHUANGLONG:'巅峰竞技场·双龙争鼎'}


def entry_may_override(current_mode, evidence):
    """A user's explicit choice is authoritative until they clear/change it."""
    return current_mode is None or evidence != 'manual'

def board_mode(board):
    if board.get('schema_version',1)==1:
        return MINGDAO if board.get('mode')==MODES[MINGDAO] else None
    mode=board.get('mode_id')
    return mode if mode in MODES and board.get('mode')==MODES[mode] else None

def identify_chart(text):
    text=re.sub(r'\s+','',text)
    if '明刀暗箭' in text and '8人身份' in text: return MINGDAO
    if '巅峰楚汉' in text or ('巅峰' in text and '楚汉争霸' in text): return PEAK_CHUHAN
    if '楚汉争霸' in text and '巅峰' not in text: return RANKED_CHUHAN
    if '双龙争鼎' in text and '巅峰' in text: return PEAK_SHUANGLONG
    # 巅峰身份 is intentionally left for period-specific source verification.
    return None

def calibration_key(mode,scene,width,height,layout='default'):
    if mode not in MODES: return f'unknown:{scene}:{layout}:{width/height:.2f}'
    return f'{mode}:{scene}:{layout}:{width/height:.2f}'
