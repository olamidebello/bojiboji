# Bojiboji

**Hide. Hunt. Hit.** A local browser survival game based on Olamide Bello's rules.

## Play

Serve this directory with any static web server, for example `python3 -m http.server 8080`, and open http://localhost:8080. No build tools or dependencies are required.

Choose 3, 5, or 8 total players and 30, 60, or 90 seconds per round. One human plays against local computer opponents; eliminated humans spectate.

1. Players gather in a circle and a random toss chooses the ball holder.
2. Runners have four seconds to scatter while the seeker waits.
3. The seeker throws at a runner. A successful hit transfers the ball and seeker role immediately.
4. The previous seeker escapes. A 1.5-second transfer pause prevents immediate return hits.
5. At the round deadline, the ball holder is eliminated. An in-flight throw still belongs to its thrower until it hits.
6. Survivors gather again. The last player remaining wins.

WASD / arrows move. Mouse aims, click or Space throws. Touch arrows move and aim; tap the field to aim and throw or use the Throw button. Cover blocks both movement and throws. A miss automatically returns the ball. Pause freezes gameplay. Losing window focus pauses automatically.

## Scope

This is a first playable prototype, not an online multiplayer release. AI has basic line-of-sight pursuit and escape behavior. Cover dims hidden runners on the shared board rather than removing them entirely. No accounts, server, live player synchronization, mobile application package, or payment system is included.

## Validation

JavaScript syntax checked with `node --check game.js`. A headless simulation verified start, toss selection, hiding phase, ball transfer, elimination, next round, final winner, and pause. Visual browser and real-device checks remain pending.
