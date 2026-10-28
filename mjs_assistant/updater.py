from __future__ import annotations

import datetime as dt
import hashlib
import re
import time
import json
import copy
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .boards import decode_image, parse_words, validate_board
from .storage import write_json, read_json
from .modes import MODES, MINGDAO, identify_chart, board_mode

OFFICIAL_LIST = "https://www.taptap.cn/app/737825/topic?type=official&page={}"


def post_links(html):
    """Only the official listing is a discovery source; never related-post links."""
    soup = BeautifulSoup(html, "html.parser")
    result = []
    for a in soup.select('a[href*="/moment/"]'):
        href = a.get("href", "")
        if "武将胜率" in a.get_text("", strip=True):
            m = re.search(r"/moment/(\d+)", href)
            if m:
                result.append("https://www.taptap.cn/moment/" + m[1])
    return list(dict.fromkeys(result))


def post_images(html):
    # Only title-labelled article attachments; never arbitrary recommendation URLs
    # found in Nuxt data or elsewhere on the page. Unknown markup fails closed.
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.find('h1')
    title = title.get_text('', strip=True) if title else ''
    if '武将胜率' not in title:
        return []
    clean=[]
    for img in soup.find_all('img'):
        alt=img.get('alt','').strip()
        if not re.fullmatch(re.escape(title)+r'\s+\d+',alt):continue
        url=img.get('src') or img.get('data-src','')
        if not re.fullmatch(r'https://img[^/]+\.tapimg\.com/moment/etag/.+',url):continue
        m=re.match(r'(.+?\.(?:jpg|png|jpeg))(?:/[^?]*)?',url,re.I)
        if m:clean.append(m[1]+'/_tap_ugc.jpg')
    return list(dict.fromkeys(clean))[:12]


class Updater:
    def __init__(self, folder, ocr, names, cancelled=lambda: False, busy=lambda:False):
        self.folder, self.ocr, self.names = Path(folder), ocr, names
        self.cancelled = cancelled
        self.busy=busy;self.failures=[]

    def check(self,current,force=False,progress=lambda x:None):
        state_path=self.folder/'update_state.json';state=read_json(state_path,{})
        now=dt.datetime.now(dt.timezone.utc)
        try:
            last=dt.datetime.fromisoformat(state.get('last_attempt',state.get('checked_at','')))
            if not force and 0<=(now-last).total_seconds()<86400:return None,'最近24小时已检查；可点击手动检查'
        except (ValueError,TypeError):pass
        state.update(last_attempt=now.isoformat(),status='checking');write_json(state_path,state)
        try:
            result=self._check(current,progress)
            state.update(status='cancelled' if self.cancelled() else ('partial' if self.failures else 'success'),last_error=self.failures[:3])
            if state['status']=='success':state['last_success']=dt.datetime.now(dt.timezone.utc).isoformat()
            return result
        except Exception as error:
            state.update(status='error',last_error=[str(error)[:500]]);raise
        finally:write_json(state_path,state)

    def _html(self,client,url):
        key=hashlib.sha256(url.encode()).hexdigest();folder=self.folder/'update-cache';folder.mkdir(parents=True,exist_ok=True)
        path=folder/(key+'.json');cached=read_json(path,{})
        headers={}
        if cached.get('etag'):headers['If-None-Match']=cached['etag']
        if cached.get('modified'):headers['If-Modified-Since']=cached['modified']
        response=client.get(url,headers=headers) if headers else client.get(url)
        if getattr(response,'status_code',200)==304 and cached.get('text'):return cached['text']
        response.raise_for_status();text=response.text
        if len(text)>4_000_000:raise ValueError('官方网页超过大小限制')
        h=getattr(response,'headers',{})
        write_json(path,{'text':text,'etag':h.get('etag'),'modified':h.get('last-modified')})
        return text

    def _idle(self,progress):
        if self.busy():progress('选将／配阵中，榜单OCR等待空闲…')
        while self.busy():
            if self.cancelled():return False
            time.sleep(.25)
        return not self.cancelled()

    def _check(self, current, progress=lambda x: None):
        legacy = "heroes" in current
        current = {MINGDAO: current} if legacy else current
        discovered = []
        failures = self.failures
        newest = {}
        headers = {"User-Agent": "MjsOverlay/1.0.0 (local official ranking reader)"}
        with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client:
            links = []
            for page in range(1, 4):
                if self.cancelled():return None, "已取消检查"
                progress(f"正在检查官方榜单，第{page}页…")
                links.extend(post_links(self._html(client,OFFICIAL_LIST.format(page))))
            if not links:
                raise ValueError("官方列表未解析到榜单帖子，可手动导入；当前榜单已保留")
            for link in sorted(set(links), key=lambda s: int(s.rsplit("/", 1)[1]), reverse=True)[:4]:
                if legacy and link.split('?')[0]==current[MINGDAO].get('source_url','').split('?')[0]:
                    return None,'已是最新发现的官方榜单'
                if all(current.get(mode, {}).get("heroes") and link.split("?")[0] == current[mode].get("source_url", "").split("?")[0] for mode in MODES):
                    continue
                try:
                    urls = post_images(self._html(client,link))
                    if not urls:raise ValueError("官方帖子原图未能解析，请手动导入官方图片")
                except (httpx.HTTPError,ValueError) as error:
                    failures.append(str(error));continue
                for url in urls:
                    if self.cancelled():return None, "已取消检查"
                    if not (urlparse(url).hostname or "").endswith(".tapimg.com"):
                        continue
                    try:
                        progress("正在核对官方图片的模式与周期…")
                        image_cache=self.folder/'update-cache'/(hashlib.sha256(url.encode()).hexdigest()+'.image')
                        checksum=read_json(image_cache.with_suffix('.sha.json'),{})
                        data=image_cache.read_bytes() if image_cache.is_file() and image_cache.stat().st_size<=20_000_000 else b''
                        if not data or hashlib.sha256(data).hexdigest()!=checksum.get('sha256'):
                            with client.stream("GET", url) as stream:
                                stream.raise_for_status()
                                data = bytearray()
                                for chunk in stream.iter_bytes():
                                    data.extend(chunk)
                                    if len(data) > 20_000_000:raise ValueError("榜单图片超过20MB")
                            image_cache.write_bytes(data)
                            write_json(image_cache.with_suffix('.sha.json'),{'sha256':hashlib.sha256(data).hexdigest()})
                        if not self._idle(progress):return None,'已取消检查'
                        img = decode_image(data)
                        header = self.ocr.read(img[:min(img.shape[0], 2100)])
                        text = " ".join(w.text for w in header)
                        mode = identify_chart(text)
                        if not mode and "巅峰身份" not in text.replace(" ", ""):
                            continue
                        baseline = current.get(mode, {})
                        year_match = re.search(r"_(20\d{2})\d{4}", url)
                        from .storage import ASSETS
                        model_manifest=read_json(ASSETS/'models/manifest.json',{})
                        parse_key=hashlib.sha256(json.dumps([url,hashlib.sha256(data).hexdigest(),model_manifest,sorted(self.names.names),self.names.aliases,'parser-v1'],sort_keys=True).encode()).hexdigest()
                        parsed_path=self.folder/'update-cache'/(parse_key+'.parsed.json')
                        draft=read_json(parsed_path)
                        if not draft:
                            if not self._idle(progress):return None,'已取消检查'
                            draft = parse_words(self.ocr.document(img), img.shape[1], self.names, link, hashlib.sha256(data).hexdigest(), int(year_match[1]) if year_match else None)
                            write_json(parsed_path,draft)
                        draft=copy.deepcopy(draft)
                        if draft["period_end"] and draft["period_end"] <= baseline.get("period_end", ""):
                            continue
                        if draft["expected_count"] < len(baseline.get("heroes", [])):
                            draft["issues"].append("新榜单条数少于当前版本，必须对照原图确认是否截断")
                        cache = self.folder / "boards" / (mode or "unassigned")
                        cache.mkdir(parents=True, exist_ok=True)
                        path = cache / (draft["image_sha256"] + ".jpg")
                        path.write_bytes(data)
                        draft["image_path"] = str(path)
                        key = mode or "unassigned"
                        if key not in newest or draft.get("period_end", "") > newest[key]:
                            newest[key] = draft.get("period_end", "")
                            discovered = [b for b in discovered if (b.get("mode_id") or "unassigned") != key]
                            discovered.append(draft)
                            write_json(cache / "pending.json", draft)
                            if legacy:write_json(self.folder/'boards/pending.json',draft)
                
                    except (httpx.HTTPError,ValueError,KeyError) as error:
                        failures.append(str(error));continue
            if failures and not discovered:raise ValueError("部分官方来源读取失败，当前榜单保留："+failures[0])
            if legacy:
                draft=next((b for b in discovered if board_mode(b)==MINGDAO),None)
                return draft, ('新榜单需要复核' if draft and validate_board(draft) else '官方榜单检查完成')
            return discovered or None, f"已检查各模式，发现 {len(discovered)} 份新榜单；{len(failures)} 项读取失败，有疑点的榜单待复核"
