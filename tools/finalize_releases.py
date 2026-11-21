"""Write Android release metadata; native desktop releases are retired."""
from pathlib import Path
import hashlib,json,os,zipfile
ROOT=Path(__file__).resolve().parents[1]
def finalize():
 p=Path(os.environ.get('ANDROID_APK_OUTPUT',ROOT/'releases/Rogue-Duelist-Edison-Three-Acts.apk')).resolve()
 with zipfile.ZipFile(p) as z:version=json.loads(z.read('assets/web/build.json'))['version']
 checksum=hashlib.sha256()
 with p.open('rb') as apk:
  for block in iter(lambda: apk.read(1024*1024),b''):checksum.update(block)
 digest=checksum.hexdigest()
 p.with_suffix('.apk.sha256').write_text(digest+'  '+p.name+'\n')
 data={'version':version,'files':{p.name:{'version':version,'bytes':p.stat().st_size,'sha256':digest}}}
 (p.parent/'release-manifest.json').write_text(json.dumps(data,indent=2)+'\n')
 return data
if __name__=='__main__':print(finalize())
