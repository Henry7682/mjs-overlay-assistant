"""Round-scoped guide state, independent of transient OCR and window visibility."""
from dataclasses import dataclass, field
import json
from .modes import PEAK_CHUHAN, RANKED_CHUHAN
from .peak_layout import draft_count


@dataclass(frozen=True)
class GuideQuery:
    purpose: str
    mode_id: str
    game_id: str
    request_id: str
    submitted: tuple[str, ...]
    budget: float


def card_key(card):
    return json.dumps(card, ensure_ascii=False, sort_keys=True)


def unique_cards(cards):
    seen = set()
    result = []
    for card in cards:
        pair = card.get('heroes', [])
        if len(pair) != 2 or pair[0] == pair[1]:
            continue
        key = card_key(card)
        if key not in seen:
            seen.add(key)
            result.append(card)
    return tuple(result)


@dataclass
class RoundGuideCache:
    mode_id: str
    game_id: str
    request_id: str = ''
    submitted: tuple[str, ...] = ()
    raw_cards: tuple[dict, ...] = ()
    recommendations: tuple = ()
    complete: bool = False
    no_match: bool = False
    received: bool = False
    limits: tuple[str, ...] = ()
    excluded: frozenset[str] = frozenset()
    frozen: bool = False
    local_incomplete: bool = False
    conflict_allowed: frozenset[str] | None = None

    def begin(self, query):
        if (query.game_id, query.mode_id) != (self.game_id, self.mode_id):
            return False
        self.request_id = query.request_id
        self.submitted = query.submitted
        self.raw_cards = (); self.recommendations = ()
        self.complete = self.no_match = self.received = False
        self.limits = ()
        self.conflict_allowed = None
        # Manual requery in the same round must keep the frozen ban decision.
        return True

    def accept(self, result):
        if (result.game_id, result.request_id) != (self.game_id, self.request_id):
            return False
        # A growing picker pool may insert stronger cards ahead of an earlier
        # batch. Prefer the latest public page order; retain older read cards
        # only after it, so incremental input does not freeze the first ranking.
        self.raw_cards = unique_cards(result.source_cards + self.raw_cards)
        self.recommendations = result.recommendations
        self.complete = result.complete; self.no_match = result.no_match
        self.received = True; self.limits = result.limits
        if self.mode_id==RANKED_CHUHAN and result.selected_candidates:
            selected=set(result.selected_candidates);observed=set(result.local_observed)
            self.conflict_allowed=frozenset(selected & observed) if observed-selected else None
        return True

    def freeze(self, excluded):
        if not self.frozen:
            self.excluded = frozenset(excluded)
            self.frozen = True

    def visible_cards(self):
        return tuple(c for c in self.raw_cards if not self.excluded.intersection(c['heroes'])
                     and (self.conflict_allowed is None or set(c['heroes'])<=self.conflict_allowed))

    def pair_cards(self, names, seats=()):
        if len(names) != 2:
            return ()
        cards = [c for c in self.visible_cards() if set(c['heroes']) == set(names)]
        # Stable priority only: keep the provider's text and all alternative directions.
        if len(seats) == 2 and all(seats):
            wanted = dict(zip(names, seats))
            def matches(c):
                return any({a: int(sa), b: int(sb)} == wanted for a, sa, b, sb in c.get('seats', []))
            cards.sort(key=lambda c: not matches(c))
        return tuple(cards)

    def hero_cards(self, name):
        return tuple(c for c in self.visible_cards() if name in c['heroes'])

    def empty_message(self):
        if self.no_match:
            return '小程序明确返回：未找到匹配组合'
        if not self.received:
            return '本局尚未取得攻略'
        return '本局缓存未找到此组合' + ('；缓存读取不完整' if not self.complete else '')


@dataclass
class PeakDraft:
    phase: str = 'unknown'
    ban_seen: set[str] = field(default_factory=set)
    locked_seen: set[str] = field(default_factory=set)
    selection_started: float | None = None
    candidate_signature: tuple = ()
    candidate_since: float = 0
    candidate_hits: int = 0
    frozen: bool = False
    excluded: frozenset[str] = frozenset()
    submitted: tuple[str, ...] = ()
    stable_since: float = 0
    stable_names: tuple[str, ...] = ()
    selection_seen: set[str] = field(default_factory=set)
    selection_count: int = 0
    auto_closed: bool = False
    message: str = '等待禁将画面'

    def update(self, phase, layout, names, visible_slots, now, locked=()):
        names = set(names)
        if self.frozen:
            if phase == 'battle': self.phase = 'battle'
            return
        if phase == 'battle':
            self.phase = 'battle'; self.message = '禁将筛选未确认，缓存仍保留'
            return
        if self.auto_closed:
            return  # A late OCR recovery/dropout must never become a new ban.
        if self.selection_started is not None and now-self.selection_started>3:
            self.auto_closed=True;self.phase='selection'
            self.message='禁将筛选待确认；阶段已结束，保留全部缓存，可手动确认'
            return
        if self.selection_started is not None and phase!='selection':
            return  # Once the selection landmark is seen, never re-enter ban.
        if layout == 'ban14':
            self.ban_seen.update(names)
            if phase == 'ban': self.phase = 'ban'
            else: self.phase = 'transition'
            current = tuple(sorted(names))
            if current != self.stable_names:
                self.stable_names = current; self.stable_since = now
            self.message = f'禁将名单已确认 {len(names)}/14；可先查询已识别姓名'
            return
        # Disappearance is only a diagnostic, never enough to freeze.
        if phase=='selection' and self.selection_started is None:
            self.selection_started=now
        expected=draft_count(layout)
        if phase != 'selection' or not expected:
            if len(self.ban_seen - names) >= 3:
                self.phase = 'transition'
            self.candidate_signature = (); self.candidate_hits = 0
            self.message = '禁将筛选待确认'
            return
        if not self.selection_count:self.selection_count=expected
        if expected!=self.selection_count:
            self.message='禁将筛选待确认；早期牌阵数量变化，保留缓存'
            return
        self.phase = 'selection_pending'
        if self.selection_started is None:
            self.selection_started = now
        self.locked_seen.update(locked)
        # Require every slot in the visually confirmed 6–12-card layout. Locked hero
        # evidence may replace a missing portrait only when separately confirmed.
        self.selection_seen.update(names)
        remaining = self.selection_seen | self.locked_seen
        signature = tuple(sorted(remaining))
        self.candidate_hits += 1
        if signature != self.candidate_signature:
            self.candidate_signature = signature; self.candidate_since = now
        self.message = '禁将筛选待确认；名单不完整时保留缓存'
        if (len(remaining) == expected
            and self.candidate_hits >= 2 and now - self.selection_started >= 1.5):
            self.confirm(remaining)

    def confirm(self, remaining):
        if self.frozen or len(set(remaining)) < 2:
            return False
        self.excluded = frozenset(self.ban_seen - set(remaining))
        self.frozen = True; self.phase = 'frozen'
        self.message = '禁将筛选已冻结；后续选将变化不再修改'
        return True


@dataclass(frozen=True)
class BattleRoster:
    friendly: tuple[str, ...] = ()
    enemy: tuple[str, ...] = ()
    friendly_seats: tuple[int | None, ...] = ()
    enemy_seats: tuple[int | None, ...] = ()
    camp: str | None = None
    confirmed: bool = False
    friendly_confirmed: bool = False
    enemy_confirmed: bool = False


class BattleTracker:
    def __init__(self):
        self.signature = None; self.hits = 0; self.roster = BattleRoster()
        self.side_signatures={};self.side_hits={}

    def update(self, items, badges):
        # roi4 is the verified self portrait in both 2v2 layouts. Team is NOT
        # inferred from top/left positions; every hero needs a readable camp badge.
        heroes = {d.slot: d.name for d in items if d.confirmed and d.name and d.slot.startswith('roi')}
        own = badges.get('roi4', {}).get('camp')
        if own not in ('楚军', '汉军') or len(set(heroes.values())) != len(heroes):
            self.signature = None; self.hits = 0
            self.side_signatures.clear();self.side_hits.clear()
            return self.roster
        friend = []; enemy = []
        for slot, name in heroes.items():
            info = badges.get(slot, {}); camp = info.get('camp')
            if camp not in ('楚军', '汉军'):
                continue
            (friend if camp == own else enemy).append((name, info.get('seat')))
        if len(friend)>2 or len(enemy)>2:
            self.signature = None; self.hits = 0
            self.side_signatures.clear();self.side_hits.clear()
            return self.roster
        # Portrait positions change on exchange; confirmed seats belong to the
        # hero, not the screen slot. Never fill a new team's seats from old data.
        if self.roster.camp and self.roster.camp!=own:
            self.roster=BattleRoster();self.side_signatures.clear();self.side_hits.clear()
        # Keep self first; enemy order remains source slot order.
        friend.sort(key=lambda n: n[0] != heroes.get('roi4'))
        sides=[]
        for side,current,previous,seats in (
            ('friend',friend,self.roster.friendly,self.roster.friendly_seats),
            ('enemy',enemy,self.roster.enemy,self.roster.enemy_seats)):
            if self.roster.camp==own and set(n for n,s in current)==set(previous):
                known=dict(zip(previous,seats))
                current=[(n,s if s is not None else known.get(n)) for n,s in current]
            signature=(tuple(current),own)
            self.side_hits[side]=self.side_hits.get(side,0)+1 if signature==self.side_signatures.get(side) else 1
            self.side_signatures[side]=signature
            if current and self.side_hits[side]>=2:
                # Keep a previously confirmed teammate through a temporary lost
                # glyph. A genuinely new name must pass two frames on its own.
                if set(n for n,s in current)<set(previous) and self.roster.camp==own:
                    sides.append((previous,seats))
                else:sides.append((tuple(n for n,s in current),tuple(s for n,s in current)))
            else:sides.append((previous,seats))
        (friendly,fs),(enemy,es)=sides
        self.roster=BattleRoster(friendly,enemy,fs,es,own if friendly or enemy else None,
                                len(friendly)==len(enemy)==2,len(friendly)==2,len(enemy)==2)
        return self.roster


def enemy_auto_allowed(mode, roster, attempted):
    return mode == RANKED_CHUHAN and (roster.enemy_confirmed or roster.confirmed) and len(roster.enemy)==2 and not attempted
