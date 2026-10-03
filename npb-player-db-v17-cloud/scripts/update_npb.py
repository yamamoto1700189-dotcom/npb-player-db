import asyncio, json, re, time, hashlib
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

BASE='https://npb.jp'
INDEX='https://npb.jp/bis/players/all/index.html'
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'site'/'data'/'database.json'
HEADERS={'User-Agent':'NPB-Player-DB/17 (+personal project; contact owner if needed)'}

session=requests.Session(); session.headers.update(HEADERS)

def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def num(s):
    s=clean(s).replace(',','')
    if s in ('','-','—','--'): return None
    s=s.replace('▲','-')
    try:
        return float(s) if any(c in s for c in '.%') else int(s)
    except: return s

def parse_year(v):
    m=re.search(r'(19|20)\d{2}',str(v)); return int(m.group()) if m else None

def slug(url): return hashlib.sha1(url.encode()).hexdigest()[:16]

def find_kana_links():
    r=session.get(INDEX,timeout=30); r.raise_for_status()
    soup=BeautifulSoup(r.text,'html.parser')
    links=[]
    for a in soup.find_all('a',href=True):
        href=urljoin(BASE,a['href'])
        if '/bis/players/all/index_' in href and href.endswith('.html'):
            links.append(href)
    return sorted(set(links))

def extract_player_links(html):
    soup=BeautifulSoup(html,'html.parser'); out=[]
    for a in soup.find_all('a',href=True):
        href=urljoin(BASE,a['href'])
        if re.search(r'/bis/players/\d{8}\.html$',href):
            txt=clean(a.get_text(' ',strip=True))
            parent=clean(a.parent.get_text(' ',strip=True)) if a.parent else txt
            pos='pitcher' if '投手' in parent else ('hitter' if any(x in parent for x in ['捕手','内野手','外野手']) else None)
            out.append({'url':href,'name':txt,'context':parent,'pos':pos})
    return out

async def collect_links():
    kana=find_kana_links()
    print(f'kana pages: {len(kana)}')
    links={}
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        page=await browser.new_page()
        for i,u in enumerate(kana,1):
            await page.goto(u,wait_until='domcontentloaded',timeout=60000)
            for _ in range(30):
                btn=page.get_by_text('更に読み込む',exact=True)
                if await btn.count()==0 or not await btn.first.is_visible(): break
                before=await page.locator('a[href*="/bis/players/"][href$=".html"]').count()
                try: await btn.first.click(timeout=5000)
                except: break
                try: await page.wait_for_function('(n)=>document.querySelectorAll(\'a[href*="/bis/players/"][href$=".html"]\').length>n',before,timeout=8000)
                except: break
            html=await page.content()
            for x in extract_player_links(html): links[x['url']]=x
            print(f'{i}/{len(kana)} links={len(links)}')
        await browser.close()
    return list(links.values())

def parse_player(meta):
    r=session.get(meta['url'],timeout=30); r.raise_for_status(); soup=BeautifulSoup(r.text,'html.parser')
    text=clean(soup.get_text(' ',strip=True))
    title=clean(soup.title.get_text()) if soup.title else meta['name']
    name=meta['name']
    # profile fields
    kana=''
    for el in soup.find_all(string=re.compile('おおたに|ふりがな|・')):
        pass
    # use title/heading when available
    h=soup.find(['h1','h2'])
    if h:
        htxt=clean(h.get_text(' ',strip=True))
        if htxt: name=htxt.split('（')[0].strip()
    pos=meta.get('pos') or ('pitcher' if '投手成績' in text and '打撃成績' not in text else 'hitter')
    years={}
    teams=set()
    # locate tables with 年度 headers
    for table in soup.find_all('table'):
        rows=table.find_all('tr')
        if not rows: continue
        headers=[clean(c.get_text(' ',strip=True)) for c in rows[0].find_all(['th','td'])]
        if not any('年度' in h for h in headers): continue
        for tr in rows[1:]:
            cells=[clean(c.get_text(' ',strip=True)) for c in tr.find_all(['th','td'])]
            if len(cells)<3: continue
            yr=parse_year(cells[0])
            if not yr: continue
            data={}
            for h,v in zip(headers,cells):
                key=h.replace(' ','')
                if key in ('年度','年度合計'): continue
                data[key]=num(v)
            team=next((v for k,v in data.items() if '所属球団' in k),None)
            if isinstance(team,str): teams.add(team)
            # translate official headers to app fields
            y=years.setdefault(str(yr),{})
            if '打率' in data: y['ba']=data['打率']
            if '出塁率' in data: y['obp']=data['出塁率']
            if '長打率' in data: y['slg']=data['長打率']
            for src,dst in [('安打','h'),('本塁打','hr'),('打点','rbi'),('得点','runs'),('盗塁','sb'),('試合','g'),('打席','pa'),('打数','ab'),('登板','g'),('勝利','wins'),('セーブ','sv'),('H','hld'),('HP','hld'),('三振','k'),('投球回','ip'),('防御率','era'),('四球','bb'),('死球','hbp'),('自責点','er'),('敗北','losses')]:
                if src in data and dst not in y: y[dst]=data[src]
            if team and isinstance(team,str): y['team']=team
    # compute metrics
    if pos=='hitter':
        for y in years.values():
            if y.get('ops') is None and y.get('obp') is not None and y.get('slg') is not None: y['ops']=round(y['obp']+y['slg'],3)
            if y.get('iso') is None and y.get('slg') is not None and y.get('ba') is not None: y['iso']=round(y['slg']-y['ba'],3)
            if y.get('woba') is None and y.get('obp') is not None and y.get('slg') is not None: y['woba']=round(.72*y['obp']+.28*y['slg'],3)
    else:
        for y in years.values():
            if y.get('fip') is None and y.get('era') is not None: y['fip']=round(y['era'],2) # fallback until BB/HBP/HR/IP are available
            if y.get('kbb') is None and y.get('k') is not None and y.get('bb') is not None and y.get('bb') not in (0,None): y['kbb']=round(y['k']/y['bb'],2)
            if y.get('whip') is None and y.get('ip') and y.get('h') is not None and y.get('bb') is not None: y['whip']=round((y['h']+y['bb'])/y['ip'],2)
    # career sums/weighted rates
    career={}
    def sm(k): return sum(v.get(k,0) or 0 for v in years.values())
    for k in ['g','pa','h','hr','rbi','runs','sb','ab','wins','losses','sv','hld','k','ip','bb','hbp','er']: career[k]=sm(k)
    if pos=='hitter':
        hits=career.get('h',0); ab=career.get('ab',0)
        career['ba']=round(hits/ab,3) if ab else None
        # weighted approximation from yearly rates using AB/PA
        for rate,numkey in [('obp','pa'),('slg','ab')]:
            vals=[(v.get(rate),v.get(numkey,0) or 0) for v in years.values() if v.get(rate) is not None and (v.get(numkey,0) or 0)>0]
            career[rate]=round(sum(a*b for a,b in vals)/sum(b for _,b in vals),3) if vals else None
        if career.get('obp') is not None and career.get('slg') is not None: career['ops']=round(career['obp']+career['slg'],3); career['iso']=round(career['slg']-career['ba'],3)
        if career.get('obp') is not None and career.get('slg') is not None: career['woba']=round(.72*career['obp']+.28*career['slg'],3)
    else:
        ip=career.get('ip') or 0
        career['era']=round(career.get('er',0)*9/ip,2) if ip else None
        career['whip']=round((career.get('h',0)+career.get('bb',0))/ip,2) if ip else None
        career['kbb']=round(career.get('k',0)/career.get('bb'),2) if career.get('bb') else None
        career['fip']=career['era']
    status='current' if any('年 公式戦初出場' not in meta.get('context','') and x in meta.get('context','') for x in ['阪神','巨人','DeNA','ヤクルト','中日','広島','ソフトバンク','日本ハム','オリックス','楽天','西武','ロッテ']) else 'ob'
    return {'id':slug(meta['url']),'n':name,'y':'','a':[],'d':[],'pos':pos,'status':status,'teams':sorted(teams),'career':career,'years':years,'npbUrl':meta['url']}

def main():
    links=asyncio.run(collect_links())
    print('unique player pages:',len(links))
    players=[]
    for i,m in enumerate(links,1):
        try:
            players.append(parse_player(m))
        except Exception as e:
            print('ERROR',i,m['url'],e)
        if i%50==0: print('parsed',i)
        time.sleep(.15)
    players=[p for p in players if p.get('n')]
    payload={'version':17,'updatedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'source':'NPB公式 個人年度別成績','players':players}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print('saved',OUT,'players=',len(players))

if __name__=='__main__': main()
