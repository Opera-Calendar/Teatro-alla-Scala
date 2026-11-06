#!/usr/bin/env python3
"""Unofficial La Scala opera calendars. Official pages only; fail closed.

Automatic season discovery does not imply guaranteed future compatibility: if the
website layout changes, this tool refuses to replace the published calendars.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE = 'https://www.teatroallascala.org'
SALES = BASE + '/it/stagione/biglietteria/biglietti/calendario-apertura-vendite.html'
ROME = ZoneInfo('Europe/Rome')
UTC = ZoneInfo('UTC')
LOCATION = 'Teatro alla Scala, Via Filodrammatici 2, 20121 Milano, Italy'
# The verified 26/27 titles are retained as a safe fallback only for that season.
KNOWN_2627 = {
 'Otello - UNDER30 Preview':'otello-under30-preview', 'Otello':'otello',
 'Les Pêcheurs de perles':'les-pecheurs-de-perles', 'Don Giovanni':'don-giovanni',
 'La bohème':'la-boheme', 'Anna Bolena':'anna-bolena',
 "The Rake's Progress":'the-rake-s-progress', 'Macbeth':'macbeth',
 'Don Quichotte':'don-quichotte', 'I puritani':'i-puritani',
 'Nixon in China':'nixon-in-china', 'Leonora':'leonora',
 'Il barbiere di Siviglia':'il-barbiere-di-siviglia',
 'Dido and Æneas':'dido-and-aeneas',
}
MONTHS = {m: n for n, m in enumerate(('january','february','march','april','may','june','july','august','september','october','november','december'), 1)}

def fetch(url, session=requests):
    r = session.get(url, timeout=35, headers={'User-Agent':'OperaSchedulesCalendar/2.0 (public calendar, GitHub)'})
    r.raise_for_status()
    return r.text

def text_lines(markup):
    soup = BeautifulSoup(markup, 'html.parser')
    for t in soup(['script','style','nav','footer']): t.decompose()
    return [re.sub(r'\s+', ' ',s).strip() for s in soup.stripped_strings if s.strip()]

def season_url(start):
    return f'{BASE}/en/season/{start}-{start+1}/index.html'

def season_links(markup, start):
    """Discover production hrefs from official Opera section, never guessing slugs."""
    soup = BeautifulSoup(markup, 'html.parser')
    season = f'/{start}-{start+1}/opera/'
    found = {}
    # Prefer links in the explicitly labelled Opera section. This avoids ballets.
    h = next((h for h in soup.find_all(re.compile('^h[1-6]$')) if h.get_text(' ',strip=True).casefold() == 'opera'), None)
    if h:
        for node in h.next_elements:
            if getattr(node, 'name', None) in ('h1','h2') and node is not h:
                break
            if getattr(node,'name', None) == 'a' and node.get('href'):
                u = urljoin(BASE,node['href'])
                if season in urlparse(u).path and u.endswith('.html'):
                    heading = node.find(re.compile('^h[1-6]$'))
                    title = (heading or node).get_text(' ',strip=True)
                    if title: found[title] = u
    # Fallback: all links explicitly in /opera/ (only from the season index).
    if not found:
        for a in soup.find_all('a',href=True):
            u=urljoin(BASE,a['href'])
            if season in urlparse(u).path and u.endswith('.html'):
                title=a.get_text(' ',strip=True)
                if title and len(title)<120: found[title]=u
    if start == 2026:
        for title,slug in KNOWN_2627.items():
            found.setdefault(title, f'{BASE}/en/season/2026-2027/opera/{slug}.html')
    # Avoid duplicate links to same production; keep meaningful titles.
    return {(title, url) for title,url in found.items()}

def find_seasons(session=requests, now=None):
    now = now or datetime.now(ROME)
    # Cover current and upcoming season, keep the known 2026/27 season as anchor.
    starts = list(range(2026, max(2027, now.year+2)))
    result=[]
    for year in starts:
        try: markup = fetch(season_url(year),session)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (404,410) and year>2026:
                continue  # A future season has simply not been announced yet.
            raise
        result.append((year,markup))
    return result

def parse_dates(lines):
    out=[]
    pat=re.compile(r'(?i)^(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)\s+(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})$')
    for i,t in enumerate(lines):
        m=pat.match(t)
        if not m: continue
        for s in lines[i+1:i+5]:
            v=re.fullmatch(r'(\d{1,2}):(\d\d)\s*([AP]M)',s,re.I)
            if v:
                mo=MONTHS.get(m[2].lower())
                if mo:
                    hour=int(v[1])%12+(12 if v[3].upper()=='PM' else 0)
                    try:out.append(datetime(int(m[3]),mo,int(m[1]),hour,int(v[2]),tzinfo=ROME))
                    except ValueError: pass
                break
    return sorted(set(out))

def parse_production(markup,title,url):
    lines=text_lines(markup)
    dates=parse_dates(lines)
    if not dates: raise ValueError(f'{title}: performance dates not found ({url})')
    flat='\n'.join(lines)
    m=re.search(r'(?im)^Conductor\s*(?:\||:)?\s*(.+)$',flat)
    conductor=m.group(1).strip() if m else 'Not published'
    if conductor in ('Staging','Cast') or len(conductor)>100: conductor='Not published'
    cast=[]
    try:
        first=next(i for i,x in enumerate(lines) if x.casefold()=='cast')
        last=next((i for i in range(first+1,len(lines)) if lines[i].casefold() in ('in brief','synopsis','the story','the plot')),len(lines))
        for item in lines[first+1:last]:
            if ' | ' in item:
                role,artists=item.split(' | ',1)
                if role and artists: cast.append((role.strip(),artists.strip()))
    except StopIteration:pass
    composer='Not published'
    for i,line in enumerate(lines):
        if line.casefold()==title.replace(' - UNDER30 Preview','').casefold() and i+1<len(lines):
            candidate=lines[i+1]
            if 2<=len(candidate)<=75 and not candidate.startswith('From '):
                composer=candidate
                break
    return dict(title=title,composer=composer,url=url,conductor=conductor,cast=cast,dates=dates)

def parse_sales(markup, production_titles=None):
    soup=BeautifulSoup(markup,'html.parser'); rows=[]
    for tr in soup.find_all('tr'):
        cells=[x.get_text(' ',strip=True) for x in tr.find_all(['td','th'],recursive=False)]
        if len(cells)>=2:rows.append(cells)
    if not rows:
        ls=text_lines(markup)
        rows=[ls[i:i+2] for i in range(len(ls)-1) if re.search(r'\b\d{2}/\d{2}/20\d{2}\s+ore\s+\d{1,2}[.:]\d{2}',ls[i+1],re.I)]
    entries=[]
    titles=sorted(production_titles if production_titles is not None else KNOWN_2627,key=len,reverse=True)
    for r in rows:
        label=' '.join(r[:-1]); raw=r[-1]
        m=re.search(r'(\d{2})/(\d{2})/(20\d{2})\s+ore\s+(\d{1,2})[.:](\d{2})',raw,re.I)
        if not m:continue
        lower=label.casefold()
        key=next((t for t in titles if t.casefold() in lower),None)
        if key=='Otello' and ('inaugurale' in lower or '7 dicembre' in lower):key='Otello - Opening Night'
        if key=='Otello' and 'under30' in lower:key='Otello - UNDER30 Preview'
        if not key:continue
        dd,mm,yy,hh,minute=map(int,m.groups())
        entries.append(dict(title=key,when=datetime(yy,mm,dd,hh,minute,tzinfo=ROME),label=label))
    return sorted({(x['title'],x['when']):x for x in entries}.values(),key=lambda x:x['when'])

def escape(s):
    return str(s).replace('\\','\\\\').replace(';','\\;').replace(',','\\,').replace('\n','\\n')

def fold(s):
    parts=[];part=''
    for c in s:
        if len((part+c).encode())>75:
            parts.append(part);part=' '+c
        else:part+=c
    if part:parts.append(part)
    return '\r\n'.join(parts)

def event(uid,when,summary,description,url,alarms=()):
    end=when+timedelta(minutes=60 if alarms else 180)
    lines=['BEGIN:VEVENT',f'UID:{uid}@opera-schedules',f'DTSTAMP:{datetime.now(UTC):%Y%m%dT%H%M%SZ}',
        f'DTSTART:{when.astimezone(UTC):%Y%m%dT%H%M%SZ}',f'DTEND:{end.astimezone(UTC):%Y%m%dT%H%M%SZ}',
        'SUMMARY:'+escape(summary),'LOCATION:'+escape('Online: Teatro alla Scala ticketing' if alarms else LOCATION),
        'DESCRIPTION:'+escape(description),'URL:'+url]
    for days in alarms:
        lines += ['BEGIN:VALARM','ACTION:DISPLAY',f'TRIGGER:-P{days}D','DESCRIPTION:'+escape(summary),'END:VALARM']
    return '\r\n'.join(fold(x) for x in lines)+'\r\nEND:VEVENT\r\n'

vevent = event  # Backward-compatible interface for the existing test suite.

def ics(events,name):
    return ('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Opera Schedules//La Scala//EN\r\n'
            'CALSCALE:GREGORIAN\r\nMETHOD:PUBLISH\r\nX-WR-CALNAME:'+escape(name)+'\r\n'+''.join(events)+'END:VCALENDAR\r\n')

def generate(session=requests,now=None):
    now=now or datetime.now(ROME)
    discovered={}; seasons=[]
    for year,markup in find_seasons(session,now):
        links=season_links(markup,year)
        if not links: raise RuntimeError(f'Season {year}/{year+1} exists but no opera links found; refusing incomplete publication')
        seasons.append(year)
        for title,url in links: discovered[url]=title
    if not discovered: raise RuntimeError('No productions found; refusing publication')
    productions=[];failed=[]
    for url,title in sorted(discovered.items()):
        try: productions.append(parse_production(fetch(url,session),title,url))
        except Exception as e: failed.append(f'{title}: {e}')
    if failed: raise RuntimeError('Some official production pages failed; refusing incomplete publication:\n'+'\n'.join(failed))
    sales=parse_sales(fetch(SALES,session),{p['title'] for p in productions})
    if not sales:raise RuntimeError('No matching official ticket sale events found; refusing publication')
    perfs=[]
    for p in productions:
        for d in p['dates']:
            if d.date()<now.date()-timedelta(days=2):continue
            desc=f"Composer: {p['composer']}\nConductor: {p['conductor']}\nCast (production-level; check date-specific casting):\n"
            desc+='\n'.join(f'{role}: {artists}' for role,artists in p['cast']) if p['cast'] else 'Not published'
            desc+='\nEstimated end time (3h, not official).\nOfficial: '+p['url']
            uid=hashlib.sha256((p['url']+'|'+d.isoformat()).encode()).hexdigest()[:24]
            perfs.append(event('performance-'+uid,d,p['title']+' — Teatro alla Scala',desc,p['url']))
    if len(perfs)<10:raise RuntimeError(f'Only {len(perfs)} upcoming performances found; refusing publication')
    tickets=[]
    for s in sales:
        uid=hashlib.sha256(('sale-'+s['title']).encode()).hexdigest()[:24]
        desc='Public individual-ticket sales (not subscriptions).\n'+s['label']+'\nOfficial: '+SALES
        tickets.append(event('sale-'+uid,s['when'],'TICKET SALES: '+s['title'],desc,SALES,(7,1)))
    return ics(perfs,'La Scala — Opera performances'),ics(tickets,'La Scala — Ticket sales'),dict(seasons=seasons,productions=len(productions),performances=len(perfs),ticket_sales=len(sales))

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',default='site');a=p.parse_args()
    performances,sales,stats=generate()
    dest=Path(a.output);dest.mkdir(parents=True,exist_ok=True)
    (dest/'performances.ics').write_bytes(performances.encode())
    (dest/'ticket-sales.ics').write_bytes(sales.encode())
    (dest/'status.json').write_text(json.dumps({'updated_at':datetime.now(UTC).isoformat(),**stats},indent=2))
    (dest/'.nojekyll').touch()
    print('Generated',stats)
if __name__=='__main__':main()
