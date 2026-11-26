import copy
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from mjs_assistant.custom_guides import CustomGuides
from mjs_assistant.jiangce import preferred
from mjs_assistant.guide_panel import card_html
from mjs_assistant.modes import identify_chart,board_mode,MINGDAO,PEAK_SHUANGLONG


def card():
 return {'heroes':['嬴政','白起'],'reason':'个人参考 <script>','variants':[{'group':'1/4','seats':[['嬴政',1],['白起',4]],'rating':'4/5'},{'group':'2/3','seats':[['白起',2],['嬴政',3]],'rating':'5/5'}]}


def test_custom_crud_and_update_isolation(tmp_path):
 base=preferred(tmp_path,custom=False).cards
 original=copy.deepcopy(base[0]);store=CustomGuides(tmp_path)
 changed=copy.deepcopy(original);changed['reason']='个人修改'
 store.put(changed,original['id']);new=store.put(card());store.hide(base[1]['id'])
 loaded=CustomGuides(tmp_path);merged=loaded.merge(base)
 assert next(c for c in merged if c['id']==original['id'])['reason']=='个人修改'
 assert all(c['id']!=base[1]['id'] for c in merged)
 assert next(c for c in loaded.merge([]) if c['id']==original['id'])['reason']=='个人修改'
 assert any(c['id']==new for c in preferred(tmp_path).cards)
 loaded.restore(original['id']);loaded.restore(base[1]['id']);loaded.restore(new)
 assert len(loaded.merge(base))==len(base)
 assert (tmp_path/'custom-guides.previous.json').exists()
 assert base[0]==original


@pytest.mark.parametrize('patch',[{'heroes':['白起','白起']},{'reason':''},{'variants':[{'rating':'6/5'}]}, {'variants':[{'seats':[['嬴政',1],['白起',1]]}]}])
def test_invalid_no_write(tmp_path,patch):
 c=card();c.update(patch)
 with pytest.raises(ValueError):CustomGuides(tmp_path).put(c)
 assert not (tmp_path/'custom-guides.json').exists()


def test_personal_rating_and_url(tmp_path):
 store=CustomGuides(tmp_path);c=card();c['url']='javascript:bad';store.put(c)
 html=card_html(store.merge([]))
 assert '个人评分' in html and 'javascript' not in html and '&lt;script&gt;' in html
 assert '4/5' in html and '5/5' in html


def test_corruption_is_not_silently_replaced(tmp_path):
 p=tmp_path/'custom-guides.json';p.write_text('{bad')
 with pytest.raises(ValueError):CustomGuides(tmp_path)
 assert p.read_text()=='{bad'


def test_identity_categories_and_history():
 assert identify_chart('8人身份胜率')==MINGDAO
 assert identify_chart('八人身份')==MINGDAO
 assert identify_chart('巅峰8人身份') is None
 assert identify_chart('巅峰双龙争鼎')==PEAK_SHUANGLONG
 assert identify_chart('兵临城下8人身份') is None
 assert board_mode({'schema_version':2,'mode_id':MINGDAO,'mode':'明刀暗箭·8人身份'})==MINGDAO


def test_editor_roundtrip(tmp_path):
 import subprocess,sys
 script = """
from pathlib import Path
from PySide6.QtWidgets import QApplication
from mjs_assistant.guide_editor import CardEditor,GuideEditor
app=QApplication([])
c={'heroes':['嬴政','白起'],'reason':'个人说明','variants':[{'group':'1/4','seats':[['嬴政',1],['白起',4]],'rating':'4/5'}]}
d=CardEditor(c);d.submit();assert d.result_card['variants']==c['variants']
m=GuideEditor(Path(__import__('sys').argv[1]));assert m.table.rowCount()>600
m.search.setText('嬴政');assert m.table.rowCount()>0
m.close();d.close()
"""
 subprocess.run([sys.executable,'-c',script,str(tmp_path)],check=True,timeout=30)


def test_season_entry_uses_category_not_old_title():
 import numpy as np
 from mjs_assistant.entry_detection import detect_entry
 from mjs_assistant.ocr import Word
 frame=np.zeros((1080,1920,3),dtype=np.uint8)
 frame[int(1080*.235):int(1080*.277),int(1920*.84):int(1920*.98)]=(0,80,240)
 def read(key,crop):return [Word('楚汉争霸' if key.endswith('_0') else '新季争锋',1,(0,0,1,1))]
 assert detect_entry(frame,[Word('竞技场',1,(0,0,1,1))],read)==(True,MINGDAO)
 assert detect_entry(frame,[Word('巅峰竞技场',1,(0,0,1,1))],read)!=(True,MINGDAO)


def test_same_round_snapshot_is_immutable_after_edit(tmp_path):
 before=preferred(tmp_path);n=len(before.cards)
 CustomGuides(tmp_path).put(card())
 assert len(before.cards)==n
 assert len(preferred(tmp_path).cards)==n+1
