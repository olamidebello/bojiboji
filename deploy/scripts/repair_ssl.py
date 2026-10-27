#!/usr/bin/env python3
"""Repair only Bojiboji's HTTP/HTTPS hosts; validate certificates and retain backups."""
import argparse
import datetime
import fcntl
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import ssl
import sys
import time
import fnmatch
import configure_domain as routing


def quote(value):
    value=str(value)
    if any(c in value for c in ['\n','\r','$']):raise ValueError('Unsupported path')
    return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'


def managed_target(dump,domain):
    filename='bojiboji-'+domain+'.conf'
    choices=[]
    for _,text in routing.config_sections(dump):
        for node in routing.blocks(text):
            if node['head']!=['http']:continue
            for d in node['directives']:
                if len(d)!=2 or d[0]!='include':continue
                p=Path(d[1])
                if p.is_absolute() and '$' not in str(p) and '*' in p.name and p.parent.is_dir() and fnmatch.fnmatchcase(filename,p.name):choices.append(p.parent.resolve()/filename)
    if not choices:raise ValueError('No active http include directory found; inspect nginx -T before SSL repair')
    return sorted(set(choices),key=lambda p:(p.parent.name!='conf.d',str(p)))[0]


def remove_domain_servers(text,domain):
    edits=[]
    for node in routing.blocks(text):
        if node['head']!=['server']:continue
        names=[n for d in node['directives'] if d and d[0]=='server_name' for n in d[1:]]
        if domain not in names:continue
        if set(names)!={domain}:raise ValueError('Domain shares a server block with other names; isolate it before SSL repair')
        edits.append((node['start'],node['end']))
    for start,end in sorted(edits,reverse=True):text=text[:start]+text[end:]
    return text,len(edits)


def render(dump,domain,snippet,webroot,certificate=None):
    challenge='location ^~ /.well-known/acme-challenge/ {\n    root '+quote(webroot)+';\n    default_type text/plain;\n    try_files $uri =404;\n}\n'
    game=snippet.replace('location / {','location ^~ / {',1)
    prefix='# Managed Bojiboji SSL. Source: deploy/repair-ssl.yml\n'
    http='server {\n'+routing.listen_lines(dump,80)+'    server_name '+domain+';\n'+challenge
    if not certificate:return prefix+http+game+'\n}\n'
    cert,key=certificate
    return (prefix+http+'location / { return 301 https://'+domain+'$request_uri; }\n}\n'
            +'server {\n'+routing.listen_lines(dump,443,tls=True)+'    server_name '+domain+';\n'
            +'    ssl_certificate '+quote(cert)+';\n    ssl_certificate_key '+quote(key)+';\n'
            +'    ssl_protocols TLSv1.2 TLSv1.3;\n'+game+'\n}\n')


def desired_updates(dump,domain,target,content):
    originals={}
    candidates={}
    for name,loaded in routing.config_sections(dump):
        if domain not in loaded:continue
        _,loaded_count=remove_domain_servers(loaded,domain)
        if not loaded_count:continue
        path=Path(name).resolve()
        if path in originals:continue
        original=path.read_text();updated,count=remove_domain_servers(original,domain)
        if count:originals[path]=original;candidates[path]=updated
    target=target.resolve()
    if target.exists():
        for node in routing.blocks(target.read_text()):
            if node['head']==['server']:
                names=[n for d in node['directives'] if d and d[0]=='server_name' for n in d[1:]]
                if set(names)!={domain}:raise ValueError('The dedicated Bojiboji config also contains another site; refusing to replace it')
    if target.exists() and target not in originals:
        original=target.read_text()
        if original.strip() and not original.startswith(('# Managed Bojiboji domain.','# Managed Bojiboji SSL.')):raise ValueError('Refusing to overwrite unrelated configuration '+str(target))
        originals[target]=original;candidates[target]=original
    if target not in originals:originals[target]=None;candidates[target]=''
    # Own generated files are regenerated completely, avoiding repeated comments/blank lines.
    if originals[target] is None or (originals[target] or '').startswith(('# Managed Bojiboji domain.','# Managed Bojiboji SSL.')):candidates[target]=content
    else:candidates[target]=candidates[target].rstrip()+'\n'+content
    return {p:(originals[p],text) for p,text in candidates.items() if originals[p]!=text}


def apply_updates(updates):
    for path,(old,new) in updates.items():
        with path.open('x' if old is None else 'w') as f:f.write(new)
        if old is None:path.chmod(0o644)


def restore(originals):
    for path,old in originals.items():
        if old is None:path.unlink(missing_ok=True)
        else:
            with path.open('w') as f:f.write(old)


def trusted_certificate(certificate,domain):
    if not certificate:return False
    cert,key=certificate
    if not cert.is_file() or not key.is_file():return False
    try:
        result=routing.command(['openssl','x509','-in',str(cert),'-noout','-checkhost',domain])
        if 'does match certificate' not in result.stdout:return False
        routing.command(['openssl','x509','-in',str(cert),'-noout','-checkend','86400'])
        routing.command(['openssl','verify','-purpose','sslserver','-verify_hostname',domain,'-untrusted',str(cert),str(cert)])
        return True
    except (RuntimeError,OSError):return False


def check_http(domain,uri,expected,address):
    c=http.client.HTTPConnection(address,80,timeout=12)
    try:
        c.request('GET',uri,headers={'Host':domain});r=c.getresponse();body=r.read(4096).decode('utf-8','replace')
        if r.status!=200 or body!=expected:raise RuntimeError('ACME challenge check failed at '+address+': HTTP '+str(r.status)+'. Check DNS A/AAAA records and port 80; the domain must reach this server.')
    finally:c.close()


def verify_tls(domain,address):
    context=ssl.create_default_context()
    raw=socket.create_connection((address,443),timeout=12)
    try:
        with context.wrap_socket(raw,server_hostname=domain) as tls:
            tls.sendall(('GET /healthz HTTP/1.1\r\nHost: '+domain+'\r\nConnection: close\r\n\r\n').encode())
            response=http.client.HTTPResponse(tls);response.begin();body=response.read(4096)
            if response.status!=200 or json.loads(body).get('app')!='bojiboji':raise RuntimeError('TLS certificate passed, but /healthz did not reach Bojiboji at '+address)
    finally:raw.close()


def retry(callback):
    for attempt in range(8):
        try:return callback()
        except (OSError,ValueError,RuntimeError,http.client.HTTPException):
            if attempt==7:raise
            time.sleep(.5)


def certbot_args(domain,webroot,email=''):
    args=['certbot','certonly','--webroot','--webroot-path',str(webroot),'--cert-name',domain,'-d',domain,'--non-interactive','--agree-tos','--keep-until-expiring']
    return args+(['--email',email] if email else ['--register-unsafely-without-email'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--domain',default='bojiboji.africandroid.world');p.add_argument('--email',default='');p.add_argument('--nginx',default='/usr/sbin/nginx');p.add_argument('--service',default='nginx');p.add_argument('--snippet',default='/etc/bojiboji/nginx-location.conf');a=p.parse_args()
    if os.geteuid()!=0:raise ValueError('Run as root')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',a.domain) or '..' in a.domain:raise ValueError('Invalid domain')
    if a.email and not re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}',a.email):raise ValueError('Invalid email')
    lock=open('/run/bojiboji-ssl-repair.lock','w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    dump=routing.command([a.nginx,'-T']).stdout;snippet=Path(a.snippet).read_text()
    if 'proxy_pass http://127.0.0.1:' not in snippet:raise ValueError('Deploy Bojiboji before SSL repair')
    target=managed_target(dump,a.domain);webroot=Path('/var/lib/bojiboji/acme');(webroot/'.well-known/acme-challenge').mkdir(parents=True,exist_ok=True)
    existing=routing.reusable_certificate(dump,a.domain);certificate=existing if trusted_certificate(existing,a.domain) else None
    reused=certificate is not None
    http_content=render(dump,a.domain,snippet,webroot,certificate)
    updates=desired_updates(dump,a.domain,target,http_content)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');backup=Path('/var/backups/bojiboji-ssl')/stamp;backup.mkdir(parents=True,mode=0o700)
    originals={path:old for path,(old,_) in updates.items()}
    if target not in originals:originals[target]=target.read_text() if target.exists() else None
    for path,old in originals.items():
        if old is not None:shutil.copy2(path,backup/(hashlib.sha256(str(path).encode()).hexdigest()+'.conf'))
    (backup/'manifest.json').write_text(json.dumps({str(path):hashlib.sha256(str(path).encode()).hexdigest()+'.conf' if old is not None else None for path,old in originals.items()},indent=2))
    changed=bool(updates);challenge_file=None
    try:
        routing.command(['systemctl','is-active','--quiet',a.service]);apply_updates(updates);routing.command([a.nginx,'-t']);routing.command(['systemctl','reload',a.service])
        if certificate is None:
            token='bojiboji-'+secrets.token_hex(16);challenge_file=webroot/'.well-known/acme-challenge'/token;challenge_file.write_text(token);challenge_file.chmod(0o644)
            uri='/.well-known/acme-challenge/'+token
            retry(lambda:check_http(a.domain,uri,token,'127.0.0.1'))
            check_http(a.domain,uri,token,a.domain)
            routing.command(certbot_args(a.domain,webroot,a.email))
            certificate=(Path('/etc/letsencrypt/live')/a.domain/'fullchain.pem',Path('/etc/letsencrypt/live')/a.domain/'privkey.pem')
            if not trusted_certificate(certificate,a.domain):raise RuntimeError('The issued certificate failed hostname, validity or chain verification')
            final=render(dump,a.domain,snippet,webroot,certificate)
            if target not in originals:originals[target]=target.read_text()
            with target.open('w') as f:f.write(final)
            target.chmod(0o644);changed=True;routing.command([a.nginx,'-t']);routing.command(['systemctl','reload',a.service])
        addresses=set()
        for address,port in routing.listener_groups(dump,443):addresses.add('127.0.0.1' if address=='0.0.0.0' else '::1' if address=='::' else address)
        for address in sorted(addresses):retry(lambda address=address:verify_tls(a.domain,address))
        # Public hostname uses real DNS, certificate trust, hostname validation and SNI.
        verify_tls(a.domain,a.domain)
        print(json.dumps({'ok':True,'changed':changed,'domain':a.domain,'https_verified':True,'certificate_reused':reused,'backup':str(backup)}))
    except Exception as exc:
        try:restore(originals);routing.command([a.nginx,'-t']);routing.command(['systemctl','reload',a.service])
        except Exception as rollback:raise routing.DeploymentError(str(exc)+'; rollback failed: '+str(rollback),changed=changed,rolled_back=False,backup=str(backup)) from exc
        raise routing.DeploymentError(str(exc),changed=False,rolled_back=True,backup=str(backup)) from exc
    finally:
        if challenge_file:challenge_file.unlink(missing_ok=True)
        lock.close()


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,RuntimeError,http.client.HTTPException) as exc:
        print(json.dumps({'ok':False,'changed':False,'error':str(exc),**getattr(exc,'details',{})}));print(str(exc),file=sys.stderr);sys.exit(1)
