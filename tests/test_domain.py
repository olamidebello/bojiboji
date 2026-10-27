import importlib.util
from pathlib import Path
import unittest
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
if __name__=='__main__':unittest.main()
