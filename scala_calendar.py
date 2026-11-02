#!/usr/bin/env python3
"""Unofficial La Scala calendar generator from official public pages.
Fail closed when essential information is missing; no fabricated performances.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, date
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

BASE='https://www.teatroallascala.org'
SEASON='https://www.teatroallascala.org/en/season/2026-2027/index.html'
SALES='https://www.teatroallascala.org/it/stagione/biglietteria/biglietti/calendario-apertura-vendite.html'
ROME=ZoneInfo('Europe/Rome')
LOCATION='Teatro alla Scala, Via Filodrammatici 2, 20121 Milano, Italy'
# Explicit official page paths serve as a fallback if the season-page navigation changes.
PRODUCTIONS={
 'Otello - UNDER30 Preview':'otello-under30-preview',
 'Otello':'otello',
 'Les Pêcheurs de perles':'les-pecheurs-de-perles',
 'Don Giovanni':'don-giovanni',
 'La bohème':'la-boheme',
 'Anna Bolena':'anna-bolena',
 "The Rake's Progress":'the-rake-s-progress',
 'Macbeth':'macbeth',
 'Don Quichotte':'don-quichotte',
 'I puritani':'i-puritani',
 'Nixon in China':'nixon-in-china',
 'Leonora':'leonora',
 'Il barbiere di Siviglia':'il-barbiere-di-siviglia',
 'Dido and Æneas':'dido-and-aeneas',
}
MONTHS={'gennaio':1,'febbraio':2,'marzo':3,'aprile':4,'maggio':5,'giugno':6,'luglio':7,'agosto':8,'settembre':9,'ottobre':10,'novembre':11,'dicembre':12}

def fetch(url,session=requests):
 r=session.get(url,timeout=35,headers={'User-Agent':'OperaSchedulesCalendar/1.0 (personal calendar; contact via GitHub repository)'})
 r.raise_for_status()
 return r.text

def lines(soup):
 for tag in soup(['script','style','nav','footer']):tag.decompose()
 return [re.sub(r'\s+',' ',x).strip() for x in soup.stripped_strings if x.strip()]

def slug_url(key):
 return BASE+'/en/season/2026-2027/opera/'+PRODUCTIONS[key]+'.html'

def season_urls(markup):
 soup=BeautifulSoup(markup,'html.parser')
 out={}
 for a in soup.find_all('a',href=True):
  href=urljoin(BASE,a['href'])
  if '/2026-2027/opera/' in href and href.endswith('.html'):
   for k in PRODUCTIONS:
    if PRODUCTIONS[k]+'.html' in href:
     out[k]=href
 return {k:out.get(k,slug_url(k)) for k in PRODUCTIONS}

def dt_from_parts(day,month,year,time):
 return datetime(int(year),int(month),int(day),int(time[:2]),int(time[3:5]),tzinfo=ROME)

def parse_performances(txt):
 """Extract official weekday/date plus following 12h clock time from page text."""
 result=[]
 pattern=re.compile(r'(?i)^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:day)?\s+(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})$')
 for i,t in enumerate(txt):
  m=pattern.match(t)
  if not m:continue
  for nextline in txt[i+1:i+5]:
   v=re.fullmatch(r'(\d{1,2}):(\d\d)\s*([AP]M)',nextline,re.I)
   if v:
    hour=int(v[1])%12+(12 if v[3].upper()=='PM' else 0)
    try:
     day=datetime.strptime(f'{m[1]} {m[2]} {m[3]}','%d %B %Y').date()
     result.append(datetime(day.year,day.month,day.day,hour,int(v[2]),tzinfo=ROME))
    except ValueError:pass
    break
 return sorted(set(result))

def parse_production(markup,key,url):
 soup=BeautifulSoup(markup,'html.parser')
 txt=lines(soup)
 perf=parse_performances(txt)
 if not perf:raise ValueError(f'{key}: no performance dates/times found; layout may have changed')
 # Conductor and cast are located between visible headings and synopsis.
 flat='\n'.join(txt)
 cm=re.search(r'(?im)^Conductor\s*(?:\||:)?\s*(.+)$',flat)
 conductor=cm.group(1).strip() if cm else 'Not published'
 if conductor in ('Staging','Cast') or len(conductor)>100:conductor='Not published'
 cast=[]
 try:
  start=next(i for i,v in enumerate(txt) if v.lower()=='cast')
  end=next((i for i in range(start+1,len(txt)) if txt[i].lower() in ('in brief','synopsis','the story','the plot')),len(txt))
  for item in txt[start+1:end]:
   if ' | ' in item:
    role,performers=item.split(' | ',1)
    if role and performers:cast.append((role.strip(),performers.strip()))
 except StopIteration:pass
 # Composer follows production title on official page, if discoverable.
 composer='Not published'
 for i,t in enumerate(txt):
  if t.casefold()==key.replace(' - UNDER30 Preview','').casefold() and i+1<len(txt):
   c=txt[i+1]
   if 2<=len(c)<=75 and not c.startswith('From '):composer=c;break
 return {'title':key,'composer':composer,'url':url,'conductor':conductor,'cast':cast,'dates':perf}

def sale_key(label):
 s=re.sub(r'\s+',' ',label).strip().casefold()
 for k in sorted(PRODUCTIONS,key=len,reverse=True):
  if k.casefold() in s:return k
 if 'otello' in s and 'under30' in s:return 'Otello - UNDER30 Preview'
 return None

def parse_sales(markup):
 soup=BeautifulSoup(markup,'html.parser')
 rows=[]
 for tr in soup.find_all('tr'):
  cells=[x.get_text(' ',strip=True) for x in tr.find_all(['td','th'],recursive=False)]
  if len(cells)>=2:rows.append(cells)
 # Also handle text extract if table is presented in a different semantic format.
 if not rows:
  t=lines(soup)
  rows=[t[i:i+2] for i in range(len(t)-1) if re.search(r'\b\d{2}/\d{2}/20\d{2}\s+ore\s+\d{1,2}[.:]\d{2}',t[i+1],re.I)]
 entries=[]
 for r in rows:
  label=' '.join(r[:-1]);when=r[-1]
  match=re.search(r'(\d{2})/(\d{2})/(20\d{2})\s+ore\s+(\d{1,2})[.:](\d{2})',when,re.I)
  if not match:continue
  if not ('opera' in label.lower() or any(k.lower() in label.lower() for k in PRODUCTIONS)):continue
  key=sale_key(label)
  if key=='Otello' and ('inaugurale' in label.lower() or '7 dicembre' in label.lower()):key='Otello - Opening Night'
  if key=='Otello' and 'under30' in label.lower():key='Otello - UNDER30 Preview'
  if not key:continue
  dd,mm,yy,hh,mi=map(int,match.groups())
  entries.append({'title':key,'when':datetime(yy,mm,dd,hh,mi,tzinfo=ROME),'label':label})
 return sorted({(x['title'],x['when']):x for x in entries}.values(),key=lambda x:x['when'])

def escaped(value):
 return str(value).replace('\\','\\\\').replace(';','\\;').replace(',','\\,').replace('\n','\\n')

def fold(s):
 # RFC5545 75-octet physical lines; don't split unicode code points
 parts=[];part=''
 for ch in s:
  if len((part+ch).encode('utf8'))>75:
   parts.append(part);part=' '+ch
  else:part+=ch
 if part:parts.append(part)
 return '\r\n'.join(parts)

def vevent(uid,start,summary,description,url,alarms=()):
 # Approximate 3-hour duration: explicitly mark as placeholder; user should check official duration.
 end=start+timedelta(minutes=30 if alarms else 180)
 rows=['BEGIN:VEVENT',f'UID:{uid}@opera-schedules',f'DTSTAMP:{datetime.now(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")}',
       f'DTSTART:{start.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")}',f'DTEND:{end.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")}',
       'SUMMARY:'+escaped(summary),'LOCATION:'+escaped(LOCATION if not alarms else 'Online: Teatro alla Scala ticketing'),
       'DESCRIPTION:'+escaped(description),'URL:'+url]
 for days in alarms:rows+=['BEGIN:VALARM','ACTION:DISPLAY',f'TRIGGER:-P{days}D','DESCRIPTION:'+escaped(summary),'END:VALARM']
 return '\r\n'.join(fold(r) for r in rows)+'\r\nEND:VEVENT\r\n'

def ics(events, name):
 return 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Opera Schedules//La Scala Official Source//EN\r\nCALSCALE:GREGORIAN\r\nMETHOD:PUBLISH\r\nX-WR-CALNAME:'+escaped(name)+'\r\n'+''.join(events)+'END:VCALENDAR\r\n'

def generate(session=requests):
 index=fetch(SEASON,session)
 urls=season_urls(index)
 prods=[];fail=[]
 for k,url in urls.items():
  try:prods.append(parse_production(fetch(url,session),k,url))
  except Exception as exc:fail.append(str(exc))
 if fail:raise RuntimeError('Production pages not verified; refusing incomplete publication:\n'+'\n'.join(fail))
 sales=parse_sales(fetch(SALES,session))
 if len(sales)<10:raise RuntimeError(f'Only {len(sales)} opera ticket-sales entries parsed. Refusing publication.')
 perf=[]
 for p in prods:
  for d in p['dates']:
   desc=f"Composer: {p['composer']}\nConductor: {p['conductor']}\n"
   desc+='Cast (as published for production; date-specific casting must be checked):\n'
   desc+='\n'.join(f'{role}: {names}' for role,names in p['cast']) if p['cast'] else 'Cast not published'
   desc+='\nEstimated calendar end time: 3 hours after start, NOT an official duration.\nOfficial: '+p['url']
   ident=hashlib.sha256((p['url']+'|'+d.isoformat()).encode()).hexdigest()[:24]
   perf.append(vevent('performance-'+ident,d,p['title']+' — Teatro alla Scala',desc,p['url']))
 ticket=[]
 for s in sales:
  label=s['title'];uid=hashlib.sha256(('sale-'+label).encode()).hexdigest()[:24]
  desc='Official PUBLIC ticket sale opening (not subscriptions).\n'+s['label']+'\nOfficial reference: '+SALES
  ticket.append(vevent('sale-'+uid,s['when'],'TICKET SALES: '+label,desc,SALES,(7,1)))
 if len(perf)<40:raise RuntimeError(f'Only {len(perf)} performances found; refusing publication')
 return ics(perf,'La Scala — Opera performances'),ics(ticket,'La Scala — Ticket sales'),{'performances':len(perf),'ticket_sales':len(sales),'productions':len(prods)}

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',default='site');args=p.parse_args()
 performances,sales,stats=generate()
 dest=Path(args.output);dest.mkdir(exist_ok=True,parents=True)
 (dest/'performances.ics').write_bytes(performances.encode('utf8'))
 (dest/'ticket-sales.ics').write_bytes(sales.encode('utf8'))
 (dest/'status.json').write_text(json.dumps({'updated_at':datetime.now(ZoneInfo('UTC')).isoformat(),**stats},indent=2))
 (dest/'.nojekyll').touch()
 print('Generated:',stats)
if __name__=='__main__':main()
