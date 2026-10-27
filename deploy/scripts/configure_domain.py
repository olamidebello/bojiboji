#!/usr/bin/env python3
"""Bind an existing panel-managed Nginx domain to Bojiboji, with rollback."""
import argparse
import datetime
import hashlib
import http.client
from urllib.parse import urlsplit
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


def tokens(text):
    # Retain offsets so untouched TLS, redirects and panel directives stay intact.
    pattern = r'''\s+|\#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\$\{[^}]*\}|[{};]|(?:\\.|[^\s{};\#"'])+'''
    result = []
    for match in re.finditer(pattern, text):
        value = match.group()
        if value.isspace() or value.startswith('#'):
            continue
        if value[:1] in ['"', "'"]:
            value = value[1:-1]
        result.append((value, match.start(), match.end()))
    return result


def blocks(text):
    stack, result, head = [], [], []
    for value, start, end in tokens(text):
        if value == '{':
            node = {'head': [t[0] for t in head], 'start': head[0][1] if head else start,
                    'open': end, 'children': [], 'directives': []}
            if stack:
                stack[-1]['children'].append(node)
            stack.append(node)
            head = []
        elif value == '}':
            if not stack:
                raise ValueError('Unbalanced Nginx braces')
            node = stack.pop()
            node['end'] = end
            result.append(node)
            head = []
        elif value == ';':
            if stack:
                stack[-1]['directives'].append([t[0] for t in head])
            head = []
        else:
            head.append((value, start, end))
    if stack:
        raise ValueError('Unbalanced Nginx braces')
    return result


def rewrite(text, domain, snippet):
    changes = []
    matched = 0
    routed = 0
    # A ^~ root prevents unrelated PHP/static regex handlers intercepting the game.
    snippet = snippet.replace('location / {', 'location ^~ / {', 1)
    desired={tuple(n['head']):[t[0] for t in tokens(snippet[n['start']:n['end']])] for n in blocks(snippet)}
    for server in blocks(text):
        if server['head'] != ['server']:
            continue
        names = [d[1:] for d in server['directives'] if d and d[0] == 'server_name']
        names = [name for group in names for name in group]
        if domain not in names:
            continue
        matched += 1
        if set(names) != {domain}:
            raise ValueError('Domain shares a server block with other names; isolate it in the panel first')
        returns = [d for d in server['directives'] if d and d[0] in ['return', 'rewrite']]
        if returns:
            listens = [d for d in server['directives'] if d and d[0] == 'listen']
            http_only = bool(listens) and all(len(d)>1 and (d[1] == '80' or d[1].endswith(':80')) for d in listens)
            if http_only and all(d[0] == 'return' and len(d)>2 and d[1] in ['301','302','307','308'] and d[2].startswith('https://') for d in returns):
                continue  # Keep the panel's HTTP-to-HTTPS redirect.
            raise ValueError('Domain has a server-level return/rewrite. Adjust routing in the panel first')
        routed += 1
        existing=[n for n in server['children'] if n['head'] in [['location','/'],['location','^~','/'],['location','=','/events']]]
        if len(existing)==len(desired) and all(desired.get(tuple(n['head']))==[t[0] for t in tokens(text[n['start']:n['end']])] for n in existing):
            continue
        for child in server['children']:
            h = child['head']
            if h in [['location','/'],['location','^~','/'],['location','=','/events']]:
                changes.append((child['start'],child['end'],''))
        changes.append((server['open'],server['open'],'\n'+snippet+'\n'))
    for start,end,value in sorted(changes,reverse=True):
        text=text[:start]+value+text[end:]
    return text, matched, routed


def command(args):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError('Command failed: '+args[0]+' '+str(args[1:])+': '+p.stderr[-2500:])
    return p



def verify_route(domain):
    connection=http.client.HTTPConnection('127.0.0.1',80,timeout=8)
    try:
        connection.request('GET','/healthz',headers={'Host':domain})
        response=connection.getresponse()
        if response.status==200:
            if json.loads(response.read()).get('app')!='bojiboji':
                raise RuntimeError('Domain route did not reach Bojiboji')
        elif response.status in [301,302,307,308]:
            destination=urlsplit(response.getheader('Location',''))
            if destination.scheme!='https' or destination.hostname!=domain:
                raise RuntimeError('Domain redirected somewhere unexpected')
        else:
            raise RuntimeError('Domain health request returned HTTP '+str(response.status))
    finally:
        connection.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain',default='bojiboji.africandroid.world')
    parser.add_argument('--snippet',default='/etc/bojiboji/nginx-location.conf')
    parser.add_argument('--nginx',default=shutil.which('nginx') or '/usr/sbin/nginx')
    parser.add_argument('--service',default='nginx')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',args.domain):
        raise ValueError('Use a lowercase domain name, without a scheme or path')
    dump=command([args.nginx,'-T']).stdout
    snippet=Path(args.snippet).read_text()
    if '127.0.0.1:' not in snippet or 'location = /events' not in snippet:
        raise ValueError('Run the application deployment first to generate its proxy snippet')
    paths=re.findall(r'^# configuration file (/.+):\s*$',dump,re.M)
    updates={}
    matched=routed=0
    for name in dict.fromkeys(paths):
        target=Path(name).resolve()
        if target in updates:
            continue
        original=target.read_text()
        updated,count,routes=rewrite(original,args.domain,snippet)
        matched+=count
        routed+=routes
        if routes and updated!=original:
            updates[target]=(original,updated)
    if not matched:
        raise ValueError('Create '+args.domain+' as a dedicated domain in Olamidepanel first, then rerun this command')
    if not routed:
        raise ValueError('Only redirect blocks were found. Finish the domain/TLS setup in the panel first')
    plan={'domain':args.domain,'files':[str(p) for p in updates],'changed':bool(updates),'applied':False}
    if not args.apply or not updates:
        print(json.dumps(plan));return
    if os.geteuid()!=0:
        raise ValueError('Apply must run as root')
    command(['systemctl','is-active','--quiet',args.service])
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=Path('/var/backups/bojiboji-domain')/stamp
    backup.mkdir(parents=True,mode=0o700)
    for p,(original,updated) in updates.items():
        shutil.copy2(p,backup/(hashlib.sha256(str(p).encode()).hexdigest()+'.conf'))
    (backup/'manifest.json').write_text(json.dumps({str(p):hashlib.sha256(str(p).encode()).hexdigest()+'.conf' for p in updates},indent=2))
    try:
        for p,(original,updated) in updates.items():
            # Preserve ownership/mode of the panel-managed file.
            with p.open('w') as f:
                f.write(updated)
        command([args.nginx,'-t'])
        command(['systemctl','reload',args.service])
        for attempt in range(10):
            try:
                verify_route(args.domain)
                break
            except (OSError, ValueError, RuntimeError, http.client.HTTPException):
                if attempt == 9:
                    raise
                time.sleep(0.5)
    except Exception:
        for p in updates:
            shutil.copyfile(backup/(hashlib.sha256(str(p).encode()).hexdigest()+'.conf'),p)
        command([args.nginx,'-t'])
        command(['systemctl','reload',args.service])
        raise
    plan.update(applied=True,backup=str(backup))
    print(json.dumps(plan))


if __name__=='__main__':
    try:
        main()
    except (ValueError,RuntimeError,OSError) as exc:
        print(str(exc),file=sys.stderr)
        sys.exit(1)
