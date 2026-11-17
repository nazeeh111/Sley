"""Verify this complete synthetic archive and independently reconstruct WIF lifts."""
from pathlib import Path
import hashlib,json,zipfile,csv,io,sys
P=Path(__file__).resolve().parent
manifest=json.loads((P/'MANIFEST.json').read_text())
for n,h in manifest.items():assert hashlib.sha256((P/n).read_bytes()).hexdigest()==h,n
with zipfile.ZipFile(P/'adapted.zip') as z:
 assert set(z.namelist())=={'adapted.wif','actions.csv','tie-up.html'}
 for n in z.namelist():assert z.read(n)==(P/n).read_bytes(),n
sections={};part=None
for line in (P/'adapted.wif').read_text().splitlines():
 if line.startswith('['):part=line.strip('[]').upper();sections[part]={}
 elif '=' in line and part:
  a,b=line.split('=',1);sections[part][a.upper()]=b
parse=lambda s:[int(x) for x in s.split(',') if int(x)]
tie={int(k):set(parse(v)) for k,v in sections['TIEUP'].items()};tread={int(k):parse(v) for k,v in sections['TREADLING'].items()};lifts=[sorted(set().union(*(tie[j] for j in tread[i]))) for i in range(1,5)];assert lifts==[[1],[2],[1,2],[]];assert set(tie)=={1,2,3} and tie[3]==set();actions=list(csv.DictReader((P/'actions.csv').open(newline='')));assert [r['physical_slots'] for r in actions]==['1','2','1 2',''];assert json.loads((P/'saved.sley.json').read_text())==json.loads((P/'source.sley.json').read_text())
if '--native' in sys.argv:
 from sley.wif import import_wif
 a=import_wif((P/'source.wif').read_text());b=import_wif((P/'adapted.wif').read_text());assert a.liftplan==b.liftplan and a.threading==b.threading
print(json.dumps({'manifestPayloads':len(manifest),'allNativeArchiveMembersExact':True,'independentWIFLiftUnion':lifts,'allPhysicalActionsExact':True,'unusedUntiedPedal':3,'nativeFreshImport':'--native' in sys.argv}))
