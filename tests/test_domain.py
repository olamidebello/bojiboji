import importlib.util
from pathlib import Path
import unittest
import tempfile
import subprocess
from unittest.mock import patch, MagicMock
import io
import contextlib
import json
import sys
from types import SimpleNamespace
spec=importlib.util.spec_from_file_location('configure_domain',Path(__file__).resolve().parents[1]/'deploy/scripts/configure_domain.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
D='bojiboji.africandroid.world'
SNIPPET='location / { proxy_pass http://127.0.0.1:3087; }\nlocation = /events { proxy_pass http://127.0.0.1:3087; access_log off; }'
class DomainTests(unittest.TestCase):
 def test_preserves_ssl_and_other_domains(self):
  src=f'''server {{ listen 443 ssl; server_name {D}; ssl_certificate /cert/file; location / {{ try_files $uri /index.html; }} location = /events {{ return 404; }} location /.well-known/ {{ root /acme; }} }}\nserver {{ server_name other.example; location / {{ return 404; }} }}'''
  out,count,routes=m.rewrite(src,D,SNIPPET)
  self.assertEqual((count,routes),(1,1));self.assertIn('ssl_certificate /cert/file;',out);self.assertIn('location /.well-known/',out);self.assertNotIn('try_files',out);self.assertEqual(out.count('location = /events'),1);self.assertIn('server_name other.example; location / { return 404; }',out)
 def test_preserves_http_redirect(self):
  src=f'server {{ listen 80; server_name {D}; return 301 https://$host$request_uri; }}'
  self.assertEqual(m.rewrite(src,D,SNIPPET),(src,1,0))
 def test_ignores_comments_and_quoted_braces(self):
  src=f'server {{ server_name {D}; # }} comment\n add_header X-Test "{{a}}"; location / {{ return 200 "yes; {{ }}"; }} }}'
  out,_,_=m.rewrite(src,D,SNIPPET);self.assertIn('add_header X-Test "{a}";',out)
 def test_idempotent(self):
  out,_,_=m.rewrite(f'server {{ server_name {D}; }}',D,SNIPPET)
  again,_,_=m.rewrite(out,D,SNIPPET)
  self.assertEqual(out,again)
 def test_refuses_shared_server(self):
  with self.assertRaises(ValueError):m.rewrite(f'server {{ server_name {D} unrelated.example; }}',D,SNIPPET)
 def test_refuses_server_level_rewrite(self):
  with self.assertRaises(ValueError):m.rewrite(f'server {{ listen 443 ssl; server_name {D}; return 404; }}',D,SNIPPET)
 def test_no_match(self):
  src='server { server_name elsewhere.example; }';self.assertEqual(m.rewrite(src,D,SNIPPET),(src,0,0))
 def test_rejects_broken_config(self):
  with self.assertRaises(ValueError):m.rewrite('server {',D,SNIPPET)
class MissingDomainTests(unittest.TestCase):
 def test_plans_new_http_vhost_without_writing(self):
  with tempfile.TemporaryDirectory() as folder:
   dump=f'# configuration file /etc/nginx/nginx.conf:\nhttp {{ include {folder}/*.conf; }}'
   with patch.object(m,'reusable_certificate',return_value=None):
    target,text,tls=m.provision_missing(dump,D,SNIPPET)
   self.assertEqual(target.parent,Path(folder));self.assertFalse(target.exists());self.assertFalse(tls)
   self.assertIn('server_name '+D+';',text);self.assertIn('listen 80;',text);self.assertNotIn('listen 443',text)
   self.assertIn('location ^~ /',text)
 def test_rejects_include_in_server_context(self):
  with tempfile.TemporaryDirectory() as folder:
   with self.assertRaises(ValueError):m.provision_missing(f'# configuration file /etc/nginx/nginx.conf:\nhttp {{ server {{ include {folder}/*.conf; }} }}',D,SNIPPET)
 def test_does_not_overwrite_existing_filename(self):
  with tempfile.TemporaryDirectory() as folder:
   target=Path(folder)/('bojiboji-'+D+'.conf');target.write_text('unrelated content')
   with self.assertRaises(ValueError):m.provision_missing(f'# configuration file /etc/nginx/nginx.conf:\nhttp {{ include {folder}/*.conf; }}',D,SNIPPET)
   self.assertEqual(target.read_text(),'unrelated content')
 def test_reuses_matching_certificate_only(self):
  with tempfile.TemporaryDirectory() as folder:
   cert=Path(folder)/'cert.pem';key=Path(folder)/'key.pem'
   dump=f'# configuration file /etc/nginx/sites-enabled/source:\nserver {{ ssl_certificate {cert}; ssl_certificate_key {key}; }}'
   for name,expected in [('elsewhere.example',False),(D,True)]:
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','2','-subj','/CN='+name,'-addext','subjectAltName=DNS:'+name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    self.assertEqual(m.reusable_certificate(dump,D) is not None,expected)
 def test_https_plan_keeps_private_key_in_its_existing_file(self):
  with tempfile.TemporaryDirectory() as folder:
   dump=f'# configuration file /etc/nginx/nginx.conf:\nhttp {{ include {folder}/*.conf; }}'
   with patch.object(m,'reusable_certificate',return_value=(Path('/cert/chain.pem'),Path('/cert/private.pem'))):
    target,text,tls=m.provision_missing(dump,D,SNIPPET)
   self.assertTrue(tls);self.assertIn('listen 443 ssl;',text);self.assertIn('return 301 https://'+D,text);self.assertIn('ssl_certificate_key "/cert/private.pem";',text)
class ProvisionRollbackTests(unittest.TestCase):
 def test_new_file_is_removed_after_failed_validation_or_health(self):
  for failure in ['validation','health']:
   with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
    root=Path(folder);confdir=root/'conf.d';confdir.mkdir();main=root/'nginx.conf';main.write_text(f'http {{ include {confdir}/*.conf; }}')
    snippet=root/'snippet';snippet.write_text(SNIPPET);checks=[]
    def fake_command(args):
     if '-T' in args:return SimpleNamespace(stdout=f'# configuration file {main}:\n'+main.read_text(),returncode=0)
     if '-t' in args:
      checks.append('validate')
      if failure=='validation' and len(checks)==1:raise RuntimeError('Invalid new configuration')
     return SimpleNamespace(stdout='',returncode=0)
    real_path=Path
    def mapped_path(value):
     if str(value)=='/var/backups/bojiboji-domain':return root/'backups'
     return real_path(value)
    with patch.object(m,'Path',side_effect=mapped_path), patch.object(m,'command',side_effect=fake_command), patch.object(m,'reusable_certificate',return_value=None), patch.object(m,'verify_route',side_effect=RuntimeError('Health failed')), patch.object(m.time,'sleep'), patch.object(m.os,'geteuid',return_value=0), patch.object(m.sys,'argv',['configure_domain.py','--domain',D,'--snippet',str(snippet),'--provision-missing','--apply']), contextlib.redirect_stdout(io.StringIO()):
     with self.assertRaises(RuntimeError):m.main()
    self.assertFalse((confdir/('bojiboji-'+D+'.conf')).exists())
    self.assertIn('include',main.read_text());self.assertGreaterEqual(len(checks),2)
class RoutingDiagnosticsTests(unittest.TestCase):
 def test_redirect_failure_names_destination_without_its_query(self):
  response=MagicMock();response.status=302;response.getheader.return_value='https://panel.example/login?temporary=secret'
  connection=MagicMock();connection.getresponse.return_value=response
  with patch.object(m.http.client,'HTTPConnection',return_value=connection):
   with self.assertRaises(RuntimeError) as caught:m.verify_route(D)
  self.assertIn('https://panel.example/login',str(caught.exception));self.assertNotIn('secret',str(caught.exception));connection.close.assert_called_once()
 def test_error_output_is_valid_json(self):
  script=Path(__file__).resolve().parents[1]/'deploy/scripts/configure_domain.py'
  p=subprocess.run([sys.executable,str(script),'--domain','bad/name'],capture_output=True,text=True)
  self.assertEqual(p.returncode,1);self.assertFalse(json.loads(p.stdout)['changed']);self.assertIn('domain',p.stderr)
 def test_diagnosis_separates_listener_addresses_without_mutation(self):
  dump=f'# configuration file /etc/nginx/nginx.conf:\nhttp {{ include /etc/nginx/conf.d/*.conf; }}\n# configuration file /etc/nginx/sites-enabled/panel:\nserver {{ listen 127.0.0.1:80; server_name panel.example; return 302 https://panel.example/login; }}\nserver {{ listen 154.16.170.86:80; server_name {D}; }}'
  def mock_command(args):
   if args[0]=='ip':return SimpleNamespace(stdout='[]')
   if args[0]=='systemctl':return SimpleNamespace(stdout='/usr/sbin/nginx -c /etc/nginx/nginx.conf')
   raise AssertionError('Unexpected command '+str(args))
  response=MagicMock();response.status=200;response.read.return_value=b'{"app":"bojiboji"}';response.getheader.return_value=''
  connection=MagicMock();connection.getresponse.return_value=response
  with patch.object(m,'command',side_effect=mock_command),patch.object(m.http.client,'HTTPConnection',return_value=connection):
   result=m.diagnose(dump,D,'/usr/sbin/nginx','nginx')
  self.assertEqual({p['address'] for p in result['probes']},{'127.0.0.1','154.16.170.86'});self.assertEqual(result['server_count'],2);self.assertEqual(result['mode'],'read-only diagnosis')
class ExplicitAddressRegressionTests(unittest.TestCase):
 def live_layout(self,folder):
  return f'''# configuration file /etc/nginx/nginx.conf:
http {{ include {folder}/*.conf; }}
# configuration file /etc/nginx/sprintforge-managed.conf:
server {{
 server_name sprintforge.netwizzard.tech;
 listen 80;
 listen 127.0.0.1:80;
 listen 154.16.170.86:80;
 listen 172.17.0.1:80;
 listen 172.18.0.1:80;
 listen [::]:80;
 listen [::1]:80;
}}
# configuration file /etc/nginx/sites-enabled/default:
server {{ server_name _; listen 80 default_server; listen [::]:80 default_server; }}
'''
 def test_new_domain_joins_every_observed_http_address_group(self):
  with tempfile.TemporaryDirectory() as folder:
   dump=self.live_layout(folder)
   with patch.object(m,'reusable_certificate',return_value=None):_,text,tls=m.provision_missing(dump,D,SNIPPET)
   for address in ['80','127.0.0.1:80','154.16.170.86:80','172.17.0.1:80','172.18.0.1:80','[::]:80','[::1]:80']:
    self.assertIn('listen '+address+';',text)
   self.assertNotIn('default_server',text);self.assertNotIn('sprintforge',text);self.assertFalse(tls)
 def test_existing_domain_repair_is_scoped_and_idempotent(self):
  src=f'server {{ server_name {D}; listen 80; location / {{ proxy_pass http://127.0.0.1:3087; }} }}\nserver {{ server_name unrelated.example; listen 80; return 404; }}'
  dump=self.live_layout('/etc/nginx/conf.d')
  updated=m.repair_listener_membership(src,dump,D)
  self.assertIn('listen 154.16.170.86:80;',updated);self.assertIn('listen 127.0.0.1:80;',updated)
  self.assertIn('server_name unrelated.example; listen 80; return 404;',updated)
  self.assertEqual(m.repair_listener_membership(updated,dump,D),updated)
 def test_tls_joins_only_tls_port_groups_not_new_specific_addresses(self):
  dump=self.live_layout('/etc/nginx/conf.d')+'\n# configuration file /etc/nginx/sites-enabled/ssl:\nserver { server_name tls.example; listen 443 ssl default_server; listen 154.16.170.86:443 ssl; }'
  lines=m.listen_lines(dump,443,tls=True)
  self.assertIn('listen 443 ssl;',lines);self.assertIn('listen 154.16.170.86:443 ssl;',lines)
  self.assertNotIn('172.17.0.1:443',lines);self.assertNotIn('default_server',lines)
 def test_implicit_wildcard_is_retained_during_existing_domain_repair(self):
  dump=self.live_layout('/etc/nginx/conf.d');src=f'server {{ server_name {D}; }}'
  updated=m.repair_listener_membership(src,dump,D)
  self.assertIn('listen 80;',updated);self.assertIn('listen 127.0.0.1:80;',updated)
if __name__=='__main__':unittest.main()
