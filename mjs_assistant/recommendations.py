"""Pure recommendation contracts and legality checks; no UI or network calls."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import time

RECOMMENDATION_MODES=frozenset(('ranked_chuhan_2v2','peak_chuhan_2v2'))

# 用户在 2026-10-26 表示：普通排位八张牌可能由双方共享，但尚不确定。
# 此规则集中于此，不能仅凭左右位置将候选划归自己／队友。
# 后续若证实是分池或交换规则，改此默认值并提供各方候选，不改过滤器。
# 巅峰的禁将／轮流选择另有状态；不能把普通排位假设直接用于巅峰。
RANKED_SHARED_POOL_ASSUMPTION=True


@dataclass(frozen=True)
class ModeContext:
    mode_id: str | None
    game_id: str
    scene: str
    evidence: str='unknown'


@dataclass(frozen=True)
class SelectionSnapshot:
    context: ModeContext
    own_pool: tuple[str,...]=()
    ally_pool: tuple[str,...]=()
    ally_locked: str | None=None
    own_locked: str | None=None
    enemies: tuple[str,...]=()
    own_seat: int | None=None
    ally_seat: int | None=None
    phase: str='unknown'  # ban / selection / waiting / battle / unknown
    remaining_seconds: float | None=None
    captured_at: float=field(default_factory=time.monotonic)
    pools_confirmed: bool=False
    shared_pool_assumed: bool=False
    visual_revision: str=''  # Changes when card badges/availability change, even with identical names.
    reference_only: bool=False  # Visible names are known; ownership/availability is not.
    image_only: bool=False  # Ranked 2v2: mini program reads the full PNG, local names are optional.
    purpose: str='selection'  # selection / enemy_battle

    @property
    def fingerprint(self):
        # Time/countdown changes alone do not invalidate a still-identical request.
        data=asdict(self)
        for key in ('captured_at','remaining_seconds'): data.pop(key)
        for key in ('own_pool','ally_pool','enemies'): data[key]=sorted(set(data[key]))
        if self.image_only:
            # Local OCR filling in more names must not cancel a PNG request.
            data['own_pool']=[];data['ally_pool']=[]
            # A newly readable seat is not a different screenshot. Actual seat
            # swaps are invalidated explicitly by the scene controller.
            data['own_seat']=None;data['ally_seat']=None
        return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

    def can_request(self, automatic=False):
        if self.purpose=='enemy_battle':
            return (self.context.mode_id=='ranked_chuhan_2v2' and self.context.scene=='battle'
                    and self.pools_confirmed and len(set(self.own_pool))==2)
        if self.context.mode_id=='peak_chuhan_2v2':
            return (self.context.scene=='selection' and self.phase in ('ban','selection','transition')
                    and len(set(self.own_pool+self.ally_pool))>=2 and self.reference_only
                    and (not automatic or self.remaining_seconds is None or self.remaining_seconds>=33))
        if (self.context.mode_id not in RECOMMENDATION_MODES or self.context.scene!='selection'
            or self.phase!='selection' or self.own_locked):
            return False
        if self.image_only:
            return (self.context.mode_id=='ranked_chuhan_2v2' and self.reference_only
                    and (not automatic or self.remaining_seconds is None or self.remaining_seconds>=18))
        if not self.own_pool:return False
        if not self.pools_confirmed:
            expected=8 if self.context.mode_id=='ranked_chuhan_2v2' else 9
            if not self.reference_only or len(set(self.own_pool+self.ally_pool))!=expected:return False
        if not self.ally_pool and not self.ally_locked: return False
        # User explicitly requested automatic queries even when the observed
        # game UI exposes only a progress bar, with no reliable seconds value.
        return not automatic or self.remaining_seconds is None or self.remaining_seconds>=18


@dataclass(frozen=True)
class Recommendation:
    own_hero: str
    ally_hero: str
    own_seat: int | None
    ally_seat: int | None
    reason: str
    rating: str | None=None
    provider_order: int=0


@dataclass(frozen=True)
class RecommendationResult:
    request_id: str
    game_id: str
    fingerprint: str
    recommendations: tuple[Recommendation,...]=()
    source: str='名将小助手'
    complete: bool=False
    no_match: bool=False
    limits: tuple[str,...]=()
    reference_only: bool=False
    selected_candidates: tuple[str,...]=()
    source_cards: tuple[dict,...]=()
    local_observed: tuple[str,...]=()
    previous_selection_state: bool=False

    def is_current(self, snapshot: SelectionSnapshot, request_id: str):
        return (self.request_id==request_id and self.game_id==snapshot.context.game_id
                and self.fingerprint==snapshot.fingerprint and self.reference_only==snapshot.reference_only
                and snapshot.can_request())

    def can_display(self, snapshot: SelectionSnapshot, request_id: str):
        # Ranked references remain useful through previews, swaps and locks.
        # Request/round identity and the selection scene still form a hard boundary.
        return self.is_current(snapshot,request_id) or (
            snapshot.context.mode_id=='ranked_chuhan_2v2'
            and snapshot.context.scene=='selection'
            and self.request_id==request_id and self.game_id==snapshot.context.game_id)


def retain_previous_selection(result, retry_key):
    from dataclasses import replace
    if result.previous_selection_state:return result
    return replace(result,previous_selection_state=True,
                   limits=(f'基于上次查询：选将状态已变化；按 {retry_key} 重算',)+result.limits)


def filter_cards(cards, snapshot: SelectionSnapshot, limit=None):
    """Keep provider order and seat direction. Never invent a numeric score."""
    if not snapshot.can_request(): return ()
    own=set(snapshot.own_pool)
    ally={snapshot.ally_locked} if snapshot.ally_locked else set(snapshot.ally_pool)
    result=[];seen=set()
    for order,card in enumerate(cards):
        pair=card.get('heroes',[])
        if len(pair)!=2 or pair[0]==pair[1]: continue
        variants=card.get('seats',[])
        # A known seat requires an explicit provider seat variant.
        if not variants and snapshot.own_seat is None and snapshot.ally_seat is None:
            variants=[(pair[0],None,pair[1],None)]
        for first,seat1,second,seat2 in variants:
            if {first,second}!=set(pair): continue
            try:
                seat1=int(seat1) if seat1 is not None else None
                seat2=int(seat2) if seat2 is not None else None
            except (ValueError,TypeError): continue
            if seat1 is not None and (seat1 not in (1,2,3,4) or seat2 not in (1,2,3,4) or seat1==seat2): continue
            for a,sa,b,sb in ((first,seat1,second,seat2),(second,seat2,first,seat1)):
                if a not in own or b not in ally: continue
                if snapshot.own_seat is not None and snapshot.own_seat!=sa: continue
                if snapshot.ally_seat is not None and snapshot.ally_seat!=sb: continue
                key=(a,b,sa,sb)
                if key in seen: continue
                seen.add(key)
                result.append(Recommendation(a,b,sa,sb,card.get('reason',''),
                                             card.get('rating'),order))
                if limit is not None and len(result)>=limit: return tuple(result)
    return tuple(result)


def capability_limits(snapshot):
    limits=['未计入敌方阵容','评级未能区分亮星与灰星时不展示']
    if snapshot.image_only:
        limits.append('候选由小程序截图识别，本地未完整核对；组合参考不代表双方都可选')
    elif snapshot.reference_only:
        limits.append('仅按可见姓名查询；候选归属、锁将和当前可选性未确认，不代表双方都可选')
    if snapshot.context.mode_id=='peak_chuhan_2v2':
        limits.append('通用二二搭配，未针对巅峰规则单独评估')
    if snapshot.own_seat is None or snapshot.ally_seat is None: limits.append('座次未确认')
    if snapshot.shared_pool_assumed: limits.append('按双方共享候选池计算，此规则尚待确认')
    return tuple(limits)


def validate_image_candidates(selected,known,observed=()):
    """Validate provider OCR without requiring a complete local OCR result."""
    if len(selected)!=8 or len(set(selected))!=8:return '小程序尚未识别出八个不同候选'
    if not set(selected)<=set(known):return '小程序候选含未知姓名，需要复核'
    # A final, structurally valid mini roster may disagree with local OCR.
    # This is now handled per combination, not by rejecting the entire request.
    return None


def filter_image_cards(cards, selected, observed, snapshot):
    """Exclude ambiguous candidates only when there is positive disagreement.

    Mini selection chips do not establish a reliable original slot mapping.
    With partial local evidence and a conflict we therefore keep the common
    names; absent local OCR alone is not evidence of a conflicting hero.
    """
    from dataclasses import replace
    selected=set(selected);observed=set(observed)
    conflict=bool(observed-selected)
    allowed=selected & observed if conflict else selected
    limits=()
    if conflict:
        excluded='、'.join(sorted(selected-observed))
        limits=(f'姓名存在冲突，已剔除含以下未一致武将的组合：{excluded}',)
        if len(observed)<8:
            limits+=('本地姓名尚未完整确认，暂仅保留双方一致的武将组合',)
    filtered=filter_cards(cards,replace(snapshot,own_pool=tuple(allowed),ally_pool=tuple(allowed)))
    return filtered,limits


def refresh_image_result(result, snapshot):
    """Late local OCR can remove unsafe combinations after the mini has returned."""
    from dataclasses import replace
    if result.previous_selection_state or not snapshot.image_only or not result.selected_candidates:return result
    observed=tuple(sorted(set(result.local_observed+snapshot.own_pool+snapshot.ally_pool)))
    if observed==result.local_observed:return result
    cards,limits=filter_image_cards(result.source_cards,result.selected_candidates,observed,snapshot)
    return replace(result,recommendations=cards,local_observed=observed,
                   limits=limits+capability_limits(snapshot)+(() if result.complete else ('攻略读取不完整；展示已读全部适用组合',)))
