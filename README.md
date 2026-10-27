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
