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
