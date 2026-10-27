#!/usr/bin/env python3
"""Bind an existing panel-managed Nginx domain to Bojiboji, with rollback."""
import argparse
import datetime
import hashlib
import fnmatch
import ipaddress
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
        listeners=[d for d in server['directives'] if d and d[0]=='listen']
        only_http=bool(listeners) and all(len(d)>1 and listen_key(d[1]) and listen_key(d[1])[1]==80 for d in listeners)
        roots=[n for n in server['children'] if n['head'] in [['location','/'],['location','^~','/']]]
        if only_http and len(roots)==1 and not roots[0]['children']:
            directives=roots[0]['directives']
            if len(directives)==1 and len(directives[0])>2 and directives[0][0]=='return' and directives[0][1] in ['301','302','307','308'] and directives[0][2].startswith('https://'):
                continue  # Preserve an ACME-compatible HTTPS redirect location.
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



class DeploymentError(RuntimeError):
    def __init__(self,message,**details):
        super().__init__(message)
        self.details=details


def safe_location(value):
    # The health-check request has no credentials; do not print any redirect query.
    return value.split('?',1)[0].split('#',1)[0][:300]


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
                raise RuntimeError('Domain route at 127.0.0.1:80 returned HTTP '+str(response.status)+' redirect to '+safe_location(response.getheader('Location',''))+' instead of HTTPS for '+domain)
        else:
            raise RuntimeError('Domain health request returned HTTP '+str(response.status))
    finally:
        connection.close()


def config_sections(dump):
    headings=list(re.finditer(r'^# configuration file (/.+):\s*$',dump,re.M))
    return [(h.group(1),dump[h.end():headings[i+1].start() if i+1<len(headings) else len(dump)]) for i,h in enumerate(headings)]


def reusable_certificate(dump,domain):
    candidates=[(Path('/etc/letsencrypt/live')/domain/'fullchain.pem',Path('/etc/letsencrypt/live')/domain/'privkey.pem')]
    for _,text in config_sections(dump):
        for node in blocks(text):
            certs=[d[1] for d in node['directives'] if len(d)==2 and d[0]=='ssl_certificate']
            keys=[d[1] for d in node['directives'] if len(d)==2 and d[0]=='ssl_certificate_key']
            if len(certs)==len(keys)==1:
                candidates.append((Path(certs[0]),Path(keys[0])))
    for cert,key in candidates:
        if not cert.is_absolute() or not key.is_absolute() or not cert.is_file() or not key.is_file():
            continue
        try:
            match=command(['openssl','x509','-in',str(cert),'-noout','-checkhost',domain])
            if 'does match certificate' not in match.stdout:
                continue
            command(['openssl','x509','-in',str(cert),'-noout','-checkend','86400'])
        except (RuntimeError,OSError):
            continue
        return cert,key
    return None



def listen_key(value):
    if value.isdigit():return ('0.0.0.0',int(value))
    bracket=re.fullmatch(r'\[([^]]+)\]:(\d+)',value)
    if bracket:
        return (str(ipaddress.ip_address(bracket.group(1))),int(bracket.group(2)))
    if ':' in value:
        address,port=value.rsplit(':',1)
        if port.isdigit():
            if address=='*':address='0.0.0.0'
            try:return (str(ipaddress.ip_address(address)),int(port))
            except ValueError:return None
    return None


def listener_groups(dump,port):
    groups={}
    for _,text in config_sections(dump):
        for node in blocks(text):
            if node['head']!=['server'] or not any(d and d[0]=='server_name' for d in node['directives']):continue
            if port==80 and not any(d and d[0]=='listen' for d in node['directives']):
                groups.setdefault(('0.0.0.0',80),set())
            for directive in node['directives']:
                if len(directive)<2 or directive[0]!='listen' or any(option in directive for option in ['udp','quic']):continue
                key=listen_key(directive[1])
                if key is None or key[1]!=port:continue
                # Join existing socket groups without copying default-server or bind options.
                options={o for o in directive[2:] if o in ['ssl','http2','proxy_protocol']}
                groups.setdefault(key,set()).update(options)
    if not groups:groups[('0.0.0.0',port)]=set()
    return groups


def listen_line(key,options,tls=False):
    address,port=key
    endpoint=str(port) if address=='0.0.0.0' else ('['+address+']:'+str(port) if ':' in address else address+':'+str(port))
    flags=set(options)
    if tls:flags.add('ssl')
    return '    listen '+endpoint+''.join(' '+o for o in ['ssl','http2','proxy_protocol'] if o in flags)+';\n'


def listen_lines(dump,port,tls=False):
    return ''.join(listen_line(key,opts,tls) for key,opts in sorted(listener_groups(dump,port).items()))


def repair_listener_membership(text,dump,domain):
    additions=[]
    for server in blocks(text):
        if server['head']!=['server']:continue
        names=[n for d in server['directives'] if d and d[0]=='server_name' for n in d[1:]]
        if set(names)!={domain}:continue
        listeners=[d for d in server['directives'] if len(d)>1 and d[0]=='listen']
        existing={listen_key(d[1]) for d in listeners}
        if not listeners:
            existing={('0.0.0.0',80)}
            additions.append((server['open'],'    listen 80;\n'))
        ports={key[1] for key in existing if key and key[1] in [80,443]}
        for port in ports:
            tls=any(listen_key(d[1]) and listen_key(d[1])[1]==port and 'ssl' in d[2:] for d in listeners)
            missing=''.join(listen_line(key,opts,tls) for key,opts in sorted(listener_groups(dump,port).items()) if key not in existing)
            if missing:additions.append((server['open'],missing))
    for offset,value in sorted(additions,reverse=True):text=text[:offset]+'\n'+value+text[offset:]
    return text

def provision_missing(dump,domain,snippet):
    directories=[]
    filename='bojiboji-'+domain+'.conf'
    for _,text in config_sections(dump):
        for node in blocks(text):
            if node['head']!=['http']:
                continue
            for directive in node['directives']:
                if len(directive)!=2 or directive[0]!='include':
                    continue
                pattern=Path(directive[1])
                if '$' in str(pattern) or not pattern.is_absolute() or not pattern.parent.is_dir():
                    continue
                if '*' not in pattern.name or not fnmatch.fnmatchcase(filename,pattern.name):
                    continue
                directories.append(pattern.parent.resolve())
    if not directories:
        raise ValueError('No active writable-style http-context include directory was found in nginx -T; create the domain in Olamidepanel or provide its existing virtual host first')
    # Use a standard conf.d directory when available; otherwise use the active panel include.
    directories.sort(key=lambda p:(p.name!='conf.d',str(p)))
    target=directories[0]/filename
    if target.exists() or target.is_symlink():
        raise ValueError('Refusing to overwrite an existing unrelated configuration: '+str(target))
    tls=reusable_certificate(dump,domain)
    game=snippet.replace('location / {','location ^~ / {',1)
    header='# Managed Bojiboji domain. Source: deploy/configure-domain.yml\n'
    if tls:
        def quote(path):
            value=str(path)
            if '\n' in value or '\r' in value:
                raise ValueError('Invalid certificate path')
            return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'
        text=(header+'server {\n'+listen_lines(dump,80)+'    server_name '+domain+';\n    return 301 https://'+domain+'$request_uri;\n}\n'
              +'server {\n'+listen_lines(dump,443,tls=True)+'    server_name '+domain+';\n    ssl_certificate '+quote(tls[0])+';\n    ssl_certificate_key '+quote(tls[1])+';\n    ssl_protocols TLSv1.2 TLSv1.3;\n'+game+'\n}\n')
    else:
        text=header+'# HTTP only: enable a certificate in the panel before using HTTPS.\nserver {\n'+listen_lines(dump,80)+'    server_name '+domain+';\n'+game+'\n}\n'
    return target,text,bool(tls)


def diagnose(dump,domain,nginx,service):
    servers=[]
    includes=[]
    addresses={'127.0.0.1'}
    for source,text in config_sections(dump):
        for node in blocks(text):
            if node['head']==['http']:
                includes.extend(d[1] for d in node['directives'] if len(d)==2 and d[0]=='include')
            if node['head']!=['server']:
                continue
            names=[name for d in node['directives'] if d and d[0]=='server_name' for name in d[1:]]
            listeners=[d[1:] for d in node['directives'] if d and d[0]=='listen']
            relevant=[]
            for listener in listeners:
                if not listener:continue
                address=listener[0]
                if address=='80' or address.endswith(':80'):
                    relevant.append(listener)
                    candidate=address.rsplit(':',1)[0].strip('[]')
                    try:
                        ip=ipaddress.ip_address(candidate)
                        if ip.version==4 and not ip.is_unspecified:addresses.add(str(ip))
                    except ValueError:pass
            if relevant or domain in names:
                servers.append({'source':source,'names':names,'listen':listeners,'returns':[safe_location(' '.join(d[1:])) for d in node['directives'] if d and d[0]=='return']})
    # Use only configured/local server addresses, never resolve the domain to an external host.
    try:
        info=json.loads(command(['ip','-j','-4','address','show']).stdout)
        for interface in info:
            for addr in interface.get('addr_info',[]):
                if addr.get('scope')=='global' and addr.get('local'):addresses.add(addr['local'])
    except (OSError,RuntimeError,ValueError):pass
    probes=[]
    for address in sorted(addresses)[:10]:
        connection=http.client.HTTPConnection(address,80,timeout=2)
        try:
            connection.request('GET','/healthz',headers={'Host':domain})
            response=connection.getresponse();payload=response.read(2048)
            try:app=json.loads(payload).get('app')
            except (ValueError,AttributeError):app=None
            probes.append({'address':address,'status':response.status,'location':safe_location(response.getheader('Location','')),'app':app})
        except (OSError,http.client.HTTPException) as e:probes.append({'address':address,'error':str(e)[:200]})
        finally:connection.close()
    try:unit=command(['systemctl','show',service,'--property=ExecStart','--value']).stdout.strip()
    except (OSError,RuntimeError) as e:unit=str(e)
    return {'domain':domain,'mode':'read-only diagnosis','nginx':nginx,'service_exec_start':unit,'http_includes':includes,'servers':servers[:40],'server_count':len(servers),'probes':probes}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain',default='bojiboji.africandroid.world')
    parser.add_argument('--snippet',default='/etc/bojiboji/nginx-location.conf')
    parser.add_argument('--nginx',default=shutil.which('nginx') or '/usr/sbin/nginx')
    parser.add_argument('--service',default='nginx')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--diagnose',action='store_true',help='Read listener configuration and probe local routes without modifying files')
    parser.add_argument('--provision-missing',action='store_true',help='Create an isolated domain file in an already active http include directory')
    args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',args.domain):
        raise ValueError('Use a lowercase domain name, without a scheme or path')
    dump=command([args.nginx,'-T']).stdout
    if args.diagnose:
        print(json.dumps(diagnose(dump,args.domain,args.nginx,args.service),indent=2));return
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
        aligned=repair_listener_membership(original,dump,args.domain)
        updated,count,routes=rewrite(aligned,args.domain,snippet)
        matched+=count
        routed+=routes
        if routes and updated!=original:
            updates[target]=(original,updated)
    provisioned=False
    tls_reused=False
    if not matched:
        if not args.provision_missing:
            raise ValueError('Create '+args.domain+' in Olamidepanel first, or rerun with --provision-missing')
        target,text,tls_reused=provision_missing(dump,args.domain,snippet)
        updates[target]=(None,text)
        provisioned=True
        routed=1
    if not routed:
        raise ValueError('Only redirect blocks were found. Finish the domain/TLS setup in the panel first')
    plan={'domain':args.domain,'files':[str(p) for p in updates],'changed':bool(updates),'applied':False,'provisioned':provisioned,'tls_reused':tls_reused}
    if not args.apply or not updates:
        print(json.dumps(plan));return
    if os.geteuid()!=0:
        raise ValueError('Apply must run as root')
    command(['systemctl','is-active','--quiet',args.service])
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=Path('/var/backups/bojiboji-domain')/stamp
    backup.mkdir(parents=True,mode=0o700)
    for p,(original,updated) in updates.items():
        if original is not None:
            shutil.copy2(p,backup/(hashlib.sha256(str(p).encode()).hexdigest()+'.conf'))
    (backup/'manifest.json').write_text(json.dumps({str(p):hashlib.sha256(str(p).encode()).hexdigest()+'.conf' if original is not None else None for p,(original,_) in updates.items()},indent=2))
    written=[]
    try:
        for p,(original,updated) in updates.items():
            # Preserve ownership/mode of the panel-managed file.
            with p.open('x' if original is None else 'w') as f:
                written.append(p)
                f.write(updated)
            if original is None:
                p.chmod(0o644)
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
    except Exception as exc:
        try:
            for p in written:
                original=updates[p][0]
                if original is None:
                    p.unlink(missing_ok=True)
                else:
                    shutil.copyfile(backup/(hashlib.sha256(str(p).encode()).hexdigest()+'.conf'),p)
            command([args.nginx,'-t'])
            command(['systemctl','reload',args.service])
        except Exception as restore_error:
            raise DeploymentError(str(exc)+'; rollback also failed: '+str(restore_error),changed=bool(written),applied=False,rolled_back=False,backup=str(backup)) from exc
        raise DeploymentError(str(exc),changed=False,applied=False,rolled_back=True,backup=str(backup)) from exc
    plan.update(applied=True,backup=str(backup))
    print(json.dumps(plan))


if __name__=='__main__':
    try:
        main()
    except (ValueError,RuntimeError,OSError) as exc:
        print(json.dumps({'ok':False,'changed':False,'applied':False,'error':str(exc),**getattr(exc,'details',{})}))
        print(str(exc),file=sys.stderr)
        sys.exit(1)
