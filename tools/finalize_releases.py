"""Read the signed Edison APK and write the metadata for its update channel."""
from pathlib import Path
import hashlib,json,os,re,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[1]
def finalize():
 expected=(ROOT/'VERSION').read_text(encoding='utf8').strip()
 name=f'Rogue-Duelist-Edison-v{expected}.apk'
 p=Path(os.environ.get('ANDROID_APK_OUTPUT',ROOT/'releases'/name)).resolve()
 with zipfile.ZipFile(p) as z:version=json.loads(z.read('assets/web/build.json'))['version']
 if version!=expected or p.name!=name:
  raise ValueError('Use the canonical Edison APK file name and the current VERSION.')
 sdk=Path(os.environ.get('ANDROID_HOME') or os.environ['ANDROID_SDK_ROOT'])
 bt=sdk/'build-tools/35.0.0'
 java=Path(os.environ['JAVA_HOME'])/'bin/java.exe'
 attributes=subprocess.check_output([bt/'aapt.exe','dump','badging',p],encoding='utf8')
 package=re.search(r"^package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'",attributes,re.M)
 if not package or package[1]!='io.github.guylfe.rogueduelist.edison' or package[3]!=version:
  raise ValueError('APK has the wrong Edison package or version.')
 result=subprocess.check_output([java,'-jar',bt/'lib/apksigner.jar','verify','--min-sdk-version','29','--verbose','--print-certs',p],encoding='utf8')
 signer=re.search(r'^Signer #1 certificate SHA-256 digest: ([0-9a-f]{64})$',result,re.M)
 expected_signer=(ROOT/'android/edison-signing-cert.sha256').read_text(encoding='utf8').strip()
 if not signer or signer[1]!=expected_signer or 'Number of signers: 1' not in result.splitlines():
  raise ValueError('APK needs exactly one verified Edison signer.')
 checksum=hashlib.sha256()
 with p.open('rb') as apk:
  for block in iter(lambda: apk.read(1024*1024),b''):checksum.update(block)
 digest=checksum.hexdigest()
 p.with_suffix('.apk.sha256').write_text(digest+'  '+p.name+'\n')
 data={'version':version,'files':{p.name:{'version':version,'bytes':p.stat().st_size,'sha256':digest}}}
 (p.parent/'release-manifest.json').write_text(json.dumps(data,indent=2)+'\n')
 update={'version':version,'versionCode':int(package[2]),'package':package[1],
         'signerSha256':signer[1],'bytes':p.stat().st_size,'sha256':digest}
 previous=int(os.environ.get('EDISON_ANDROID_PREVIOUS_CODE','0'))
 if not previous<update['versionCode']<=2100000000:
  raise ValueError('The Edison version code must exceed the last published Android code.')
 (p.parent/'edison-android-update.json').write_text(json.dumps(update,indent=2)+'\n',encoding='utf8')
 return data
if __name__=='__main__':print(finalize())
