import plistlib, sys, hashlib
data = sys.stdin.buffer.read()
p = plistlib.loads(data)
for cert in p.get('DeveloperCertificates', []):
  print(hashlib.sha1(cert).hexdigest().upper())
