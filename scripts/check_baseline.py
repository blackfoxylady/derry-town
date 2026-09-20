#!/usr/bin/env python3
"""Check a pristine seed against hashes recorded from the original map."""
import hashlib,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.conf import settings
from atlas.rendering import compile_payload

def normalize(value):
 if isinstance(value,dict):return {k:normalize(v) for k,v in value.items()}
 if isinstance(value,list):return [normalize(x) for x in value]
 if isinstance(value,float) and value.is_integer():return int(value)
 return value

def sha(value):
 return hashlib.sha256(json.dumps(normalize(value),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def verify():
 doc=json.loads((settings.BASE_DIR/'data/initial.json').read_text())
 payload=compile_payload(doc,1)
 expected=json.loads((settings.BASE_DIR/'data/baseline.json').read_text())
 sites=payload['data']['sites']
 for site in sites:
  site['sources']=[{k:v for k,v in r.items() if k in ['reference']} for r in site['sources']]
 unplaced=[{k:v for k,v in r.items() if k!='sources'} for r in payload['data']['unplaced']]
 scene=[{k:v for k,v in s.items() if k not in ['feature_id','component_id']} for s in payload['base']]
 labels=[{k:v for k,v in s.items() if k not in ['web_offset','follow_name']} for s in payload['labels']]
 actual={'site_count':len(sites),'unplaced_count':len(unplaced),'scene_elements':len(scene),
  'sites_sha256':sha(sites),'unplaced_sha256':sha(unplaced),'scene_sha256':sha(scene),
  'labels_sha256':sha(labels),'relief_sha256':hashlib.sha256(payload['relief'].encode()).hexdigest()}
 report={k:{'passed':v==expected[k],'actual':v,'expected':expected[k]} for k,v in actual.items()}
 print(json.dumps(report,indent=2))
 if not all(r['passed'] for r in report.values()):raise SystemExit(1)

if __name__=='__main__':verify()
