# Bojiboji

**Hide. Hunt. Hit.** A local browser survival game based on Olamide Bello's rules.

## Play

Run `node server.cjs` with Node.js 20 or newer, then open http://localhost:8080. Set `PORT` to change the port. No npm dependencies or build step are required. For other devices on the same network, use the server computer’s LAN address and port. Public internet play requires hosting this server with HTTPS and a reverse proxy that supports unbuffered server-sent events (`/events`). A static-only host supports local play, but cannot run online rooms.

Choose 3, 5, or 8 total players and 30, 60, or 90 seconds per round. One human plays against local computer opponents; eliminated humans spectate.

1. Players gather in a circle and a random toss chooses the ball holder.
2. Runners have four seconds to scatter while the seeker waits.
3. The seeker throws at a runner. A successful hit transfers the ball and seeker role immediately.
4. The previous seeker escapes. A 1.5-second transfer pause prevents immediate return hits.
5. At the round deadline, the ball holder is eliminated. An in-flight throw still belongs to its thrower until it hits.
6. Survivors gather again. The last player remaining wins.

WASD / arrows move. Mouse aims, click or Space throws. Touch arrows move and aim; tap the field to aim and throw or use the Throw button. Cover blocks both movement and throws. A miss automatically returns the ball. Pause freezes gameplay. Losing window focus pauses automatically.

## Scope

This is a first playable prototype with online rooms for 2–8 human players and a separate local AI mode. Create a room, share the code, and have the host start. Online rooms have no AI players or shared pause. The server owns movement, throws, timers, and elimination. Players cannot join mid-match. Disconnected sessions expire after 45 seconds; expired players are removed and a replacement host is selected. Rooms and profiles exist in memory and disappear on server restart. AI has basic line-of-sight pursuit and escape behavior. Cover dims hidden runners on the shared board rather than removing them entirely. No accounts, persistent storage, native mobile package, or payment system is included. Room codes grant room access; use this prototype with trusted participants.

## Validation

JavaScript syntax checked with `node --check game.js`. A headless simulation verified start, toss selection, hiding phase, ball transfer, elimination, next round, final winner, and pause. Visual browser and real-device checks remain pending.


## Personal hiding spots

Each user can save a spot name, description, manual location label, field position, and optional JPEG/PNG/WebP picture. Pictures are resized in the browser and shared with room members; no GPS is collected. Field positions must be clear of obstacles. Spots are marked on the map and shown as profile cards; they do not create collision cover or teleport users. Save again after joining an online room to share a local profile. Only the owner’s session can edit their profile. Profiles are not permanent.

## Multiplayer validation

Integration checks covered two separate sessions, host-only start authorization, valid and blocked spot coordinates, SSE profile sharing, rejecting mid-match joins, movement input, static assets, and leaving a room. Core simulation checks covered toss, hide, hit transfer, round elimination, final winner, and pause. Browser visual and real-device tests remain pending.

## Expanded game experience

- Original generated Bojiboji logo and village courtyard key art, delivered as optimized WebP assets, with a lightweight SVG favicon.
- Four animal avatars (fox, cat, owl, bear), richer cover detail, ball-transfer particles, a throw aiming guide, and winner celebrations.
- Three visual arena themes: Village Grove, Golden Dusk, and Moonlit Courtyard. Theme selection is personal and does not change collision geometry.
- Optional synthesized sound cues, a final-five-second alert, reduced-effects setting, keyboard focus styles, mobile layout improvements, and full screen where supported.
- Server-tracked throws, hits, accuracy and final match scoreboard. Personal games, wins, hits and the latest five results are kept on the current browser, not a global leaderboard.
- Player names, avatars, theme and reduced-effects preference are remembered on the current browser. Shared-device users can clear browser site data to reset these values.
- Ready-up lobby, invite links containing only the room code, and host removal between matches. Every member must be ready before the host starts. Session tokens are never included in invite links.
- Controls reset after 500 ms without input to stop disconnected players drifting. Empty matches end cleanly; leaving hosts transfer ownership.

## Checks

From the repository root, run:

```
node tests/gameplay.cjs
node tests/multiplayer.cjs
node tests/ui.cjs
```

The UI check uses a mock DOM/canvas to exercise script loading, avatars, rendering calls, room controls, invitations and result statistics. It does not replace browser screenshot or mobile-device testing. Those remain pending.

## Olamidepanel deployment

See [deploy/README.md](deploy/README.md) for the Ansible playbook, local deployment helper, remote inventory, isolated Node.js runtime, systemd service, health checks, rollback behavior, and domain reverse-proxy setup. The service uses loopback port 3087 by default. `GET /healthz` returns a small JSON health response.

## Terms, privacy, and ownership

Legal pages are served at `/legal/terms.html`, `/legal/privacy.html`, and `/legal/copyright.html`, with links in the footer and near room controls. Copyright: **© 2026 Olamide Olatayo Bello. All rights reserved.** See `LICENSE` for the proprietary notice and its exceptions for user content, third-party rights, and applicable law.

Players can delete their own shared hiding profile, leave a room to remove it, and clear locally saved preferences and personal statistics. No unconfigured support email is assumed. Set `BOJIBOJI_CONTACT_EMAIL` for direct Node.js hosting, or `bojiboji_contact_email` in the deployment variables, to publish the operator's contact email on legal pages. `/site-config` exposes only that intentionally public value.

Privacy text was matched to the application's current data flow. Reference: [FTC privacy and security guidance](https://www.ftc.gov/business-guidance/privacy-security). This reference is informational, not an endorsement or certification.

Additional checks: `node tests/privacy.cjs` and `node tests/privacy-server.cjs`.

Public domain: **bojiboji.africandroid.world**. After creating the dedicated domain in Olamidepanel, use `deploy/configure-domain.yml` to connect it to the already deployed backend. See the domain section in `deploy/README.md`.

## Nigerian Pidgin default language

The game opens in Nigerian Pidgin (`pcm`) by default, including its initial HTML. The language selector offers **Naija Pidgin** and **English**, and remembers a deliberate choice in `boji-language-v1` browser storage. Browser language detection does not override the Pidgin default. Clearing saved game data removes the saved choice and restores Pidgin. Switching also works when browser storage is unavailable.

Menus, rules, touch-control labels, lobby controls, match announcements, hiding-spot tools, result messages, common server errors, and new match-history entries are localized. Names, uploaded descriptions, pictures, room codes, gameplay rules and shared match state are not translated or changed. Match events use stable templates and values so each participant renders messages in their own selected language. The formal legal documents remain explicitly marked as English and have a clearly labelled Pidgin summary.

`locales/pcm.js` is the editable translation catalog; `i18n.js` handles static text, accessibility labels, interpolation, live switching, storage and fallback behavior. Unknown messages retain their original text. This is written Nigerian Pidgin, not a claim to cover every Nigerian language or community dialect. No translated voice recordings are included. Embedded artwork retains its original branding.

Checks: `node tests/localization.cjs` and `node tests/ui.cjs --pidgin`. Deployment also runs the localization checks before activation.

Deploy this update:

```bash
git -C /root/bojiboji-deploy pull --ff-only
bash /root/bojiboji-deploy/deploy/deploy-local.sh
```

Reload the game page afterward. The application restart ends active room sessions. Established Nginx routing does not need to change for this language update.

## Installable mobile app

The game includes an installable **Progressive Web App (PWA)** for supported Android, iPhone/iPad, and desktop browsers. The homepage's **Install / download app** link opens `/install`. The app uses the existing game server and keeps Pidgin as the default language. This release does not include a native APK, IPA, or store listing.

Features include home-screen icons, standalone app display, a manifest, a browser-authorized installation prompt where supported, iPhone/Safari instructions, offline computer-opponent practice after the app shell has cached successfully, and user-triggered updates. The device/browser controls installation; the page never silently installs software. Supported installation and service-worker behavior requires HTTPS (or localhost during development).

Only the known static game pages/assets enter the offline cache. Room APIs, event streams, tokens, public configuration and uploaded profile pictures are excluded. Online rooms always need internet; a disconnected player should leave their online room before starting local practice. Browser quotas or settings can prevent offline storage, and real-device installation remains to be checked after deploying over HTTPS.

Public install page after deployment: https://bojiboji.africandroid.world/install

Deploy:

```bash
git -C /root/bojiboji-deploy pull --ff-only
bash /root/bojiboji-deploy/deploy/deploy-local.sh
```

Run `node tests/mobile.cjs` for installation-flow, route, service-worker and cache-isolation integration checks. `node tests/mobile-static.cjs` validates distributable files/icons and is also run before deployment activation. The service-worker cache has a versioned `bojiboji-shell-` prefix; bump it when changing its precache list. Updates wait until existing clients close or the user selects Update app (reload), rather than automatically interrupting a match.

Installation references: https://web.dev/learn/pwa/installation-prompt and https://support.apple.com/guide/iphone/iphea86e5236/ios
