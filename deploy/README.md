# Deploy Bojiboji on Olamidepanel

This playbook pulls the GitHub repository, prepares a release by commit SHA, checks JavaScript and gameplay/UI tests, installs a systemd service, and verifies HTTP health and the landing page. It supports Debian/Ubuntu with systemd, including Debian 12. The server needs outbound HTTPS access to GitHub and nodejs.org.

Bojiboji listens only at `127.0.0.1:3087` under the dedicated `bojiboji` account. The panel handles the public domain and TLS certificate. A separate maintained Node.js 22 runtime is downloaded from nodejs.org and checked against its official HTTPS SHA-256 manifest. Existing Node.js installations are not replaced. Existing panel virtual hosts and firewall rules are not modified.

## Deploy directly on your server

Run as root on the Olamidepanel server:

```bash
apt-get update
apt-get install -y git ansible-core
if [ -d /root/bojiboji-deploy/.git ]; then
  git -C /root/bojiboji-deploy pull --ff-only
else
  git clone https://github.com/olamidebello/bojiboji.git /root/bojiboji-deploy
fi
bash /root/bojiboji-deploy/deploy/deploy-local.sh
```

The helper uses `deploy/inventory.local.yml`, so localhost belongs to the playbook's `olamidepanel` group. It forwards extra Ansible arguments. To use another free backend port, add `-e bojiboji_port=3090` and use the newly generated proxy snippet.

## Attach a domain in Olamidepanel

1. Create or select a dedicated domain for Bojiboji and point its DNS to this server.
2. Use the panel to enable its HTTPS certificate.
3. If the panel offers reverse-proxy settings, set the backend to `http://127.0.0.1:3087`, preserve the original Host header, disable response buffering and caching, and allow long-lived responses for `/events`. Exclude `/events` query strings from access logs because its temporary session credential is sent in the event-stream URL. The generated Nginx snippet disables access logging for that endpoint.
4. For a panel with an editable Nginx virtual host, display `cat /etc/bojiboji/nginx-location.conf` and place both locations in the chosen domain's existing server block. Replace the existing application `location /`; do not create a duplicate. Retain the panel's certificate and TLS directives.
5. Validate with the panel's Nginx configuration checker, or its configured Nginx binary's `-t` option, before reloading through the panel. Do not reload a failed configuration.
6. Visit `https://YOUR-DOMAIN/healthz` and verify `{"ok":true,"app":"bojiboji"}`. Open the site in two separate browser sessions/devices, create/join a room, ready up and start a match.

The snippet is not automatically enabled because the repository does not specify the game domain or Olamidepanel's virtual-host layout. The app is deployed and checked locally before this domain-routing step. Do not expose port 3087 publicly; HTTPS traffic should enter through the panel.

## Deploy remotely from an Ansible control computer

Copy `inventory.example.ini` to `inventory.ini`, verify the server address (`154.16.170.86` is provided as the example Olamidepanel server), and use your existing SSH key or Ansible's password prompt. Verify SSH host keys normally.

```bash
ansible-playbook -i deploy/inventory.ini deploy/playbook.yml
```

For a non-root SSH account, use `--ask-become-pass` if its sudo configuration requires it. Do not put SSH passwords in the playbook, repository, or command history.

Optional settings: copy `vars.example.yml` to a file outside the checkout and supply it with `-e @/path/to/your-vars.yml`. Set `bojiboji_ref` to a branch, tag or full commit SHA to deploy an exact revision. When `bojiboji_install_node=false`, set `bojiboji_existing_node` to an executable for Node.js 20 or newer.

## Pull and redeploy later

```bash
git -C /root/bojiboji-deploy pull --ff-only
bash /root/bojiboji-deploy/deploy/deploy-local.sh
```

Identical releases with unchanged runtime and service configuration are left running. New releases or runtime changes restart the game. Rooms and shared hiding profiles currently live in memory: restarts end active rooms. Deploy between matches. Browser preferences and personal statistics remain on each player's device.

## Health, logs, and rollback

```bash
systemctl status bojiboji --no-pager
journalctl -u bojiboji -n 80 --no-pager
curl --fail http://127.0.0.1:3087/healthz
```

Pre-activation checks leave the running application untouched. If service activation or HTTP checks fail, the playbook attempts to restore the previous symlink and service unit, and fails visibly. On a failed first install, it stops the service. A previous working release remains available at `/opt/bojiboji/previous` after a successful upgrade. Older release directories are retained for inspection; no cleanup deletes them.

For an intentional rollback, rerun the playbook with `-e bojiboji_ref=PREVIOUS_COMMIT_SHA`. This retains the selected current port/runtime settings; use your earlier variables file too if those settings need reverting. The panel's routing configuration is managed separately.

## Validation

Run `ansible-playbook -i deploy/inventory.local.yml deploy/playbook.yml --syntax-check` and `bash -n deploy/deploy-local.sh`. Application checks are in `tests/`. A syntax check is not a live server deployment.

## Public contact and legal pages

The site includes Terms and Conditions, a Privacy Policy, and a copyright notice naming Olamide Olatayo Bello. To publish your support/privacy inbox, set `bojiboji_contact_email` in your variables file or deploy with `-e bojiboji_contact_email=YOUR-EMAIL`. The value is intentionally public and must be a plain email address. If unset, legal pages instruct players to request operator contact details from the person who supplied their room invitation. No inbox is invented by the installer.

Review the policies against your actual hosting and logging practices before public operation. The game describes its current implementation; adding tracking, payments, user accounts or persistent uploads requires updating those descriptions. The templates do not assert jurisdiction-wide legal compliance.

## Connect bojiboji.africandroid.world

The chosen domain is **bojiboji.africandroid.world**, using the existing application backend at `127.0.0.1:3087`.

Point the DNS A record for this domain to `154.16.170.86`. The routing playbook now provisions a missing Nginx virtual host automatically in an already active HTTP include directory. If you already created the dedicated domain through Olamidepanel, its existing host is used instead. A suitable existing certificate is reused when one is available; otherwise the new host serves HTTP until you enable SSL through the panel. Remove any incorrect AAAA record unless this server is configured for that IPv6 address.

Then run on the server:

```bash
git -C /root/bojiboji-deploy pull --ff-only
ansible-playbook -i /root/bojiboji-deploy/deploy/inventory.local.yml \
  /root/bojiboji-deploy/deploy/configure-domain.yml
```

This separate routing playbook discovers active virtual-host files from `nginx -T`. It modifies only server blocks naming exactly this domain; shared server blocks and unfamiliar server-level rewrite configurations are rejected for manual review. Standard port-80 HTTP-to-HTTPS redirects are retained. Existing TLS certificate directives and other domains remain untouched. The game route uses `location ^~ /` to prevent an old PHP/static handler intercepting game requests, while longer ACME locations are retained. Event-stream buffering/caching are disabled, and `/events` access logs are disabled because its URL carries a temporary room token.

The helper saves original configurations under `/var/backups/bojiboji-domain/`, validates with `nginx -t`, reloads Nginx, and checks the local Host-based HTTP route. Configuration validation, reload, or route-check failure triggers an attempt to restore the saved files and reload the previous configuration. The helper does not issue certificates or create DNS records. For missing domains it adds an isolated Nginx configuration in an existing HTTP include directory discovered from the active configuration; it does not create a panel database record or replace the main nginx.conf. If no suitable active include exists, it stops rather than inventing a global layout. A server managed through the panel may regenerate its virtual hosts later; keep the resulting proxy settings in the panel's domain configuration too.

If the panel uses a custom Nginx binary or service, pass `-e bojiboji_nginx_binary=/actual/path/to/nginx` and `-e bojiboji_nginx_service=ACTUAL_SERVICE`. The defaults are `/usr/sbin/nginx` and `nginx`.

After routing and TLS setup, check:

```bash
curl --fail https://bojiboji.africandroid.world/healthz
```

Expect `{"ok":true,"app":"bojiboji"}`. This HTTPS check verifies public DNS, TLS, and routing; a local HTTP redirect check alone does not verify them.

Routing-helper checks: `python3 tests/test_domain.py` covers isolation of other domains, TLS/ACME preservation, redirects, quoted braces, repeated runs, and refusal of ambiguous configurations. These checks do not substitute for running against your actual panel installation.

### Missing-domain repair

The previous error `Create bojiboji.africandroid.world as a dedicated domain...` meant no exact domain entry was present in the active Nginx configuration. The routing playbook now passes `--provision-missing` during both discovery and apply. It creates only a uniquely named domain file, refuses to overwrite a conflicting file, and removes a newly created file if validation or the local route check fails.

A certificate is reused only if OpenSSL confirms that its hostname matches and it remains valid for at least 24 hours. The key remains in its existing file. If no certificate matches, the result is explicitly HTTP-only; the script does not claim HTTPS is working. After panel-managed certificate setup, verify HTTPS publicly with curl. Do not create a second duplicate panel virtual host without first reconciling the managed domain file.

For a local route check independent of DNS:

```bash
curl --fail -H 'Host: bojiboji.africandroid.world' http://127.0.0.1/healthz
```

A successful HTTP health response is not a check of the public DNS or SSL certificate.

### Unexpected redirect during route verification

If local route verification reports a redirect to a different hostname, the backend can still be healthy while an Nginx listener or another virtual host handles the domain request. The helper reports the redirect's actual destination without its query string, attempts rollback, and emits structured JSON describing whether rollback succeeded. Ansible no longer tries to decode empty stdout on command failure.

Before another routing change, run this read-only diagnostic:

```bash
git -C /root/bojiboji-deploy pull --ff-only
python3 /root/bojiboji-deploy/deploy/scripts/configure_domain.py --diagnose
```

It lists the active HTTP listener groups, virtual-host names and configuration paths, checks `/healthz` with the chosen Host header on local/configured IPv4 addresses, and shows the Nginx service's ExecStart. It does not edit files, reload services, resolve the public domain to arbitrary remote hosts, or print TLS private-key contents. The diagnostic does not claim a repair has occurred; use its output to identify the actual listener or redirect mismatch.

### Explicit listener groups redirecting Bojiboji to Sprintforge

The supplied server diagnosis showed `sprintforge-managed.conf` participating in wildcard, loopback, public-IP, Docker-bridge and IPv6 HTTP listener groups, while a newly provisioned Bojiboji host used only `listen 80`. Nginx selects an address/port group before matching Host, so the exact game hostname must participate in the corresponding existing groups too. Reference: https://nginx.org/en/docs/http/request_processing.html

The helper now discovers existing HTTP listener address groups and joins them in the Bojiboji virtual host. It handles the observed `127.0.0.1:80`, `154.16.170.86:80`, `172.17.0.1:80`, `172.18.0.1:80`, `[::]:80`, and `[::1]:80` addresses dynamically, without hardcoding the server's IP into the helper. It preserves implicit wildcard membership and does not copy `default_server`, bind, or socket-tuning flags. It also repairs missing memberships on existing dedicated Bojiboji hosts without changing other domains. TLS, if enabled, joins groups already on port 443 rather than inventing new specific-address groups that could shadow other HTTPS sites.

After pulling the update, rerun `deploy/configure-domain.yml`. Check both loopback and the server's public IP with the Bojiboji Host header:

```bash
curl --fail -H 'Host: bojiboji.africandroid.world' http://127.0.0.1/healthz
curl --fail -H 'Host: bojiboji.africandroid.world' http://154.16.170.86/healthz
```

HTTP-only installations should return the Bojiboji JSON health response. If a matching existing certificate was reused, a redirect to the same Bojiboji HTTPS hostname is expected instead; verify `https://bojiboji.africandroid.world/healthz` to check the final HTTPS route and certificate.

## Repair NET::ERR_CERT_COMMON_NAME_INVALID

A browser showing this error for `bojiboji.africandroid.world` received a certificate that does not cover that hostname. A working backend or an HTTP redirect is not proof of valid HTTPS. Use the dedicated repair playbook on the Olamidepanel server:

```bash
git -C /root/bojiboji-deploy pull --ff-only
ansible-playbook -i /root/bojiboji-deploy/deploy/inventory.local.yml \
  /root/bojiboji-deploy/deploy/repair-ssl.yml
curl --fail https://bojiboji.africandroid.world/healthz
```

DNS A/AAAA records must lead to this server, and public ports 80 and 443 must be reachable. The playbook installs Certbot, OpenSSL and CA certificates. It checks the existing game backend first. It only rewrites server blocks that name this exact domain; shared server blocks and unrelated content in the dedicated destination file are rejected rather than overwritten. Other virtual hosts are preserved. The matching HTTP and HTTPS hosts join existing address-specific listener groups to prevent another site's default certificate from being served.

The helper first looks for an existing certificate with the correct hostname, a trusted chain, and at least 24 hours of validity. Otherwise it configures a dedicated ACME webroot exception, verifies a random test file through local and public HTTP routing, and requests a domain-specific Let's Encrypt certificate with Certbot's webroot authenticator. Certbot is not permitted to rewrite arbitrary Nginx configurations or stop the web server. This operation uses Certbot's `--agree-tos` for certificate issuance. It registers without an email unless you provide `-e bojiboji_acme_email=YOUR-EMAIL`; no email address is invented or taken from unrelated account data. An existing certificate and its private key are referenced in place; key contents are never printed or uploaded to GitHub.

The final checks use normal trusted TLS, certificate hostname validation, and SNI against local listener groups and the real public hostname, followed by a Bojiboji `/healthz` check. No certificate-validation bypass or self-signed placeholder is used. Failure triggers an attempt to restore the prior domain files from `/var/backups/bojiboji-ssl/` and reload the previous configuration. Newly issued certificate files remain on the server even if a later route check fails; the script does not revoke or delete credentials automatically. The game backend is not restarted by this playbook.

The playbook enables `certbot.timer` and adds a domain-specific Nginx validation/reload deploy hook for renewals. If an existing certificate belongs to another certificate manager, that manager remains responsible for its renewal. Keep the resulting domain settings in the panel if it regenerates virtual-host files later.

After success, reload the site normally and revisit `/install`; browser app installation requires trusted HTTPS. Do not bypass the browser certificate warning. Public DNS/CDN configuration can still need correction if traffic is routed away from this server.

Validation: `python3 tests/test_ssl.py` includes real local TLS handshakes for matching trusted certificates, rejected hostname mismatches and rejected untrusted chains, plus scoped rendering, ACME routing, rollback and repeat-run checks. `python3 tests/test_domain.py` covers the shared address-group layout seen in the server's diagnostic output. Syntax checks are not a live certificate issuance.

Primary reference for the webroot and renewal workflow: https://eff-certbot.readthedocs.io/en/stable/using.html
