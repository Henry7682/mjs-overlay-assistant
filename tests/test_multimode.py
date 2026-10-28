import copy
import pytest
from mjs_assistant.storage import BoardStore,ASSETS,read_json,write_json,migrate_settings
from mjs_assistant.modes import MODES,MINGDAO,RANKED_CHUHAN,PEAK_CHUHAN,PEAK_SHUANGLONG,identify_chart
from mjs_assistant.boards import validate_board


def test_four_official_seeds_and_isolated_rollback(tmp_path):
    stores={mode:BoardStore(tmp_path,mode) for mode in MODES}
    assert {len(s.board['heroes']) for s in stores.values()}=={191}
    assert all(not validate_board(s.board) for s in stores.values())
    assert stores[RANKED_CHUHAN].lookup('白起')['win_rate']==67.95
    assert stores[PEAK_CHUHAN].lookup('白起')['win_rate']==62.73
    for mode,store in stores.items():
        old=copy.deepcopy(store.board);changed=copy.deepcopy(old)
        changed['period_start']='2026-10-09'
        if mode==PEAK_SHUANGLONG:changed['mode_evidence']['period_start']='2026-10-09'
        store.install(changed);store.rollback()
        assert store.board==old
        assert all(BoardStore(tmp_path,other).board==stores[other].board for other in MODES if other!=mode)


def test_migration_preserves_originals_and_profiles(tmp_path):
    board=read_json(ASSETS/'board.json');settings={'profiles':{'battle:1.78':{'regions':[[0,0,.1,.1]]}}}
    write_json(tmp_path/'board.json',board);write_json(tmp_path/'settings.json',settings)
    BoardStore(tmp_path);config=migrate_settings(tmp_path)
    assert read_json(tmp_path/'backup-v1/settings.json')==settings
    assert read_json(tmp_path/'board.json')==board
    assert config['mode_profiles']=={MINGDAO:settings['profiles']}
    assert config['selected_mode'] is None


def test_missing_mode_data_never_falls_back(tmp_path,monkeypatch):
    empty=tmp_path/'assets';empty.mkdir()
    monkeypatch.setattr('mjs_assistant.storage.ASSETS',empty)
    store=BoardStore(tmp_path,PEAK_CHUHAN)
    assert not store.board['heroes'] and store.lookup('白起') is None


def test_corrupt_cross_mode_current_is_not_used(tmp_path):
    target=BoardStore(tmp_path,PEAK_CHUHAN)
    write_json(target.path,BoardStore(tmp_path,MINGDAO).board)
    reloaded=BoardStore(tmp_path,PEAK_CHUHAN)
    assert reloaded.lookup('白起')['win_rate']==62.73
    bad=copy.deepcopy(reloaded.board);bad['mode_id']=RANKED_CHUHAN
    with pytest.raises(ValueError): reloaded.install(bad)


def test_identity_title_is_not_a_permanent_alias():
    assert identify_chart('巅峰身份 胜率 10.08-10.21') is None
    assert identify_chart('巅峰楚汉 胜率')==PEAK_CHUHAN
    assert identify_chart('楚汉争霸 胜率')==RANKED_CHUHAN


def test_wrong_mode_previous_file_cannot_mutate_any_mode(tmp_path):
    store=BoardStore(tmp_path,PEAK_CHUHAN);other=BoardStore(tmp_path,RANKED_CHUHAN)
    write_json(store.previous,other.board)
    with pytest.raises(ValueError):store.rollback()
    assert not other.path.exists() and store.lookup('白起')['win_rate']==62.73
def test_manual_mode_is_not_overwritten_by_another_entry():
    from mjs_assistant.modes import MODES,entry_may_override
    for mode in MODES:
        assert not entry_may_override(mode,'manual')
        assert entry_may_override(mode,'visible_entry')
    assert entry_may_override(None,'manual')
    assert entry_may_override(None,'unknown')


