import contextlib
import io
import builtins
from types import SimpleNamespace
import importlib.util
import json
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
SCRIPTS=Path(__file__).resolve().parents[1]/'deploy/scripts'
sys.path.insert(0,str(SCRIPTS))
import repair_ssl as repair
D='bojiboji.africandroid.world'
SNIPPET='location / { proxy_pass http://127.0.0.1:3087; }\nlocation = /events { proxy_pass http://127.0.0.1:3087; access_log off; }'
class SSLPlanTests(unittest.TestCase):
 def dump(self,folder):
  return f'# configuration file /etc/nginx/nginx.conf:\nhttp {{ include {folder}/*.conf; }}\n# configuration file /etc/nginx/source:\nserver {{ server_name panel.example; listen 80 default_server; listen 127.0.0.1:80; listen 154.16.170.86:80; }}\nserver {{ server_name panel.example; listen 443 ssl default_server; listen 127.0.0.1:443 ssl; listen 154.16.170.86:443 ssl; }}'
 def test_renderer_joins_existing_groups_without_default_server(self):
  text=repair.render(self.dump('/etc/nginx/conf.d'),D,SNIPPET,Path('/var/lib/bojiboji/acme'),(Path('/cert/fullchain.pem'),Path('/cert/key.pem')))
  for listener in ['127.0.0.1:80','154.16.170.86:80','127.0.0.1:443 ssl','154.16.170.86:443 ssl']:self.assertIn('listen '+listener+';',text)
  self.assertNotIn('default_server',text);self.assertIn('ssl_certificate "/cert/fullchain.pem";',text);self.assertIn('location ^~ /.well-known/acme-challenge/',text)
  nodes=repair.routing.blocks(text)
  http=[n for n in nodes if n['head']==['server'] and any(d[:2]==['listen','80'] for d in n['directives'])][0]
  self.assertFalse(any(d and d[0]=='return' for d in http['directives']))
 def test_domain_reroute_preserves_acme_http_redirect(self):
  text=repair.render(self.dump('/etc/nginx/conf.d'),D,SNIPPET,Path('/acme'),(Path('/cert'),Path('/key')))
  updated,count,routes=repair.routing.rewrite(text,D,SNIPPET)
  self.assertEqual(count,2);self.assertEqual(routes,1);self.assertIn('return 301 https://'+D+'$request_uri;',updated);self.assertIn('location ^~ /.well-known/acme-challenge/',updated)
 def test_http_stage_has_no_invalid_placeholder_certificate(self):
  text=repair.render(self.dump('/etc/nginx/conf.d'),D,SNIPPET,Path('/var/lib/bojiboji/acme'))
  self.assertNotIn('ssl_certificate',text);self.assertNotIn('return 301',text);self.assertIn('try_files $uri =404;',text)
 def test_unchanged_generated_file_is_idempotent(self):
  with tempfile.TemporaryDirectory() as folder:
   target=Path(folder)/('bojiboji-'+D+'.conf');text=repair.render(self.dump(folder),D,SNIPPET,Path('/acme'),(Path('/cert'),Path('/key')));target.write_text(text)
   dump=self.dump(folder)+f'\n# configuration file {target}:\n'+text
   self.assertEqual(repair.desired_updates(dump,D,target,text),{})
 def test_other_sites_are_preserved_and_shared_blocks_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   other=Path(folder)/'other.conf';original=f'server {{ server_name other.example; listen 80; }}\nserver {{ server_name {D}; listen 80; }}';other.write_text(original)
   target=Path(folder)/('bojiboji-'+D+'.conf');dump=self.dump(folder)+f'\n# configuration file {other}:\n'+original
   updates=repair.desired_updates(dump,D,target,'server { server_name '+D+'; }')
   self.assertIn('server_name other.example',updates[other][1]);self.assertNotIn('server_name '+D,updates[other][1]);self.assertFalse(target.exists())
   with self.assertRaises(ValueError):repair.remove_domain_servers('server { server_name '+D+' other.example; }',D)
 def test_refuses_other_sites_in_file_even_with_managed_header(self):
  with tempfile.TemporaryDirectory() as folder:
   target=Path(folder)/('bojiboji-'+D+'.conf');target.write_text('# Managed Bojiboji domain.\nserver { server_name other.example; }')
   with self.assertRaises(ValueError):repair.desired_updates(self.dump(folder),D,target,'replacement')
 def test_rollback_restores_previous_files_and_removes_new_ones(self):
  with tempfile.TemporaryDirectory() as folder:
   old=Path(folder)/'old.conf';new=Path(folder)/'new.conf';old.write_text('old');repair.apply_updates({old:('old','updated'),new:(None,'created')});repair.restore({old:'old',new:None});self.assertEqual(old.read_text(),'old');self.assertFalse(new.exists())
 def test_certbot_is_domain_specific_and_does_not_stop_nginx(self):
  args=repair.certbot_args(D,Path('/acme'));self.assertIn('--webroot',args);self.assertIn('--keep-until-expiring',args);self.assertIn('--register-unsafely-without-email',args);self.assertNotIn('--nginx',args);self.assertNotIn('--force-renewal',args);self.assertEqual(args[args.index('-d')+1],D)
  email_args=repair.certbot_args(D,Path('/acme'),'privacy@example.com');self.assertIn('--email',email_args);self.assertNotIn('--register-unsafely-without-email',email_args)

class TLSHandshakeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.folder=Path(cls.temp.name)
  def run(args):subprocess.run(['openssl',*args],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  cls.ca=cls.folder/'ca.pem';key=cls.folder/'ca.key'
  run(['req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cls.ca),'-days','2','-subj','/CN=Test CA','-addext','basicConstraints=critical,CA:TRUE'])
  for name,label in [(D,'correct'),('elsewhere.example','wrong')]:
   csr=cls.folder/(label+'.csr');serverkey=cls.folder/(label+'.key');cert=cls.folder/(label+'.pem');ext=cls.folder/(label+'.ext');ext.write_text('subjectAltName=DNS:'+name+'\nextendedKeyUsage=serverAuth\n')
   run(['req','-new','-newkey','rsa:2048','-nodes','-keyout',str(serverkey),'-out',str(csr),'-subj','/CN='+name]);run(['x509','-req','-in',str(csr),'-CA',str(cls.ca),'-CAkey',str(key),'-CAcreateserial','-out',str(cert),'-days','2','-extfile',str(ext)])
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def handshake(self,label,trust=True):
  listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();listener.settimeout(5);port=listener.getsockname()[1]
  server_context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);server_context.load_cert_chain(str(self.folder/(label+'.pem')),str(self.folder/(label+'.key')))
  def serve():
   try:
    raw,_=listener.accept()
    with server_context.wrap_socket(raw,server_side=True) as tls:
     tls.recv(4096);body=b'{"ok":true,"app":"bojiboji"}';tls.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\nConnection: close\r\n\r\n'+body)
   except (ssl.SSLError,OSError):pass
   finally:listener.close()
  thread=threading.Thread(target=serve,daemon=True);thread.start();context=ssl.create_default_context(cafile=str(self.ca)) if trust else ssl.create_default_context();real_connect=socket.create_connection
  try:
   with patch.object(repair.ssl,'create_default_context',return_value=context),patch.object(repair.socket,'create_connection',side_effect=lambda address,timeout:real_connect(('127.0.0.1',port),timeout)):
    repair.verify_tls(D,'127.0.0.1')
  finally:thread.join(timeout=6)
 def test_matching_trusted_name_and_game_health_succeed(self):self.handshake('correct')
 def test_wrong_hostname_is_rejected(self):
  with self.assertRaises(ssl.SSLCertVerificationError):self.handshake('wrong')
 def test_untrusted_certificate_is_rejected(self):
  with self.assertRaises(ssl.SSLCertVerificationError):self.handshake('correct',trust=False)

class SSLTransactionTests(unittest.TestCase):
 def test_issuance_or_tls_failure_restores_original_domain(self):
  for failure in ['issuance','tls']:
   with self.subTest(failure=failure),tempfile.TemporaryDirectory() as folder:
    base=Path(folder);conf=base/'conf.d';conf.mkdir();target=conf/('bojiboji-'+D+'.conf');old='# Managed Bojiboji domain.\nserver { listen 80; server_name '+D+'; location / { proxy_pass http://127.0.0.1:3087; } }';target.write_text(old)
    root=base/'nginx.conf';root.write_text('http { include '+str(conf)+'/*.conf; }');snippet=base/'snippet';snippet.write_text(SNIPPET)
    dump=f'# configuration file {root}:\n'+root.read_text()+f'\n# configuration file {target}:\n'+old
    calls=[]
    def fake_command(args):
     calls.append(args)
     if '-T' in args:return SimpleNamespace(stdout=dump,returncode=0)
     if args[0]=='certbot':raise RuntimeError('issuance failed')
     return SimpleNamespace(stdout='',returncode=0)
    def mapped_path(value):
     if str(value)=='/var/lib/bojiboji/acme':return base/'acme'
     if str(value)=='/var/backups/bojiboji-ssl':return base/'backups'
     return Path(value)
    def mapped_open(value,*args,**kwargs):return builtins.open(base/'lock' if value=='/run/bojiboji-ssl-repair.lock' else value,*args,**kwargs)
    candidate=(base/'cert.pem',base/'key.pem') if failure=='tls' else None
    with patch.object(repair,'Path',side_effect=mapped_path),patch.object(repair,'open',side_effect=mapped_open,create=True),patch.object(repair.os,'geteuid',return_value=0),patch.object(repair.routing,'command',side_effect=fake_command),patch.object(repair.routing,'reusable_certificate',return_value=candidate),patch.object(repair,'trusted_certificate',return_value=bool(candidate)),patch.object(repair,'check_http'),patch.object(repair,'verify_tls',side_effect=RuntimeError('TLS failed')),patch.object(repair.time,'sleep'),patch.object(sys,'argv',['repair_ssl.py','--domain',D,'--snippet',str(snippet)]),contextlib.redirect_stdout(io.StringIO()):
     with self.assertRaises(repair.routing.DeploymentError) as caught:repair.main()
    self.assertTrue(caught.exception.details['rolled_back']);self.assertEqual(target.read_text(),old)
    self.assertTrue(list((base/'backups').glob('*/manifest.json')))
    self.assertEqual(any(args[0]=='certbot' for args in calls),failure=='issuance')
if __name__=='__main__':unittest.main()
