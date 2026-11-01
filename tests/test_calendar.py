import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scala_calendar import parse_production,parse_sales,vevent,ROME
from datetime import datetime
class ScalaParsingTests(unittest.TestCase):
 def test_production_dates(self):
  h='''<div>Tue 30 March 2027</div><div>08:00 PM</div><h1>Anna Bolena</h1><p>Gaetano Donizetti</p><p>Conductor | FRANCESCO IVAN CIAMPA</p><h2>Cast</h2><p>Anna Bolena | Vasilisa Berzhanskaya</p><h2>In brief</h2>'''
  p=parse_production(h,'Anna Bolena','https://example.com')
  self.assertEqual(p['dates'][0].hour,20)
  self.assertEqual(p['conductor'],'FRANCESCO IVAN CIAMPA')
 def test_sales(self):
  h='''<table><tr><th>Spettacolo</th><th>In vendita da</th></tr><tr><td>Opera Otello - 7 dicembre Serata Inaugurale</td><td>07/10/2026 ore 13.00</td></tr><tr><td>Opera Anna Bolena</td><td>26/11/2026 ore 13.00</td></tr></table>'''
  vals=parse_sales(h)
  self.assertEqual(len(vals),2)
  self.assertTrue(any(x['title']=='Otello - Opening Night' for x in vals))
 def test_alarms_and_escaping(self):
  x=vevent('x',datetime(2027,1,1,13,tzinfo=ROME),'A, B','one\ntwo','https://example.com',(7,1))
  self.assertIn('TRIGGER:-P7D',x)
  self.assertIn('TRIGGER:-P1D',x)
  self.assertIn('SUMMARY:A\\, B',x)
  self.assertTrue(all(len(line.encode())<=75 for line in x.split('\r\n')))
if __name__=='__main__':unittest.main()
