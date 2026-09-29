# matrix-mautrix-discord

openSUSE RPM packaging for the [mautrix-discord](https://github.com/mautrix/discord)
Matrix-Discord puppeting bridge, built from upstream source instead of the
`dock.mau.dev/mautrix/discord` Docker image.

## Why this exists

Part of migrating the mautrix bridge fleet off Docker — see
[matrix-mautrix-telegram](https://github.com/sleep-walker-matrix-bridges/matrix-mautrix-telegram)
for the full rationale.

## Packaged version

- Upstream tag: `v0.7.7` — this bridge predates the CalVer (`v26.xx`) switch
  used by telegram/whatsapp/signal, still on the older `v0.x` scheme, but is
  actively maintained.

## Security audit

See `audit/govulncheck-v0.7.7.txt` and `audit/osv-scanner-v0.7.7.txt`.

**Unlike telegram and whatsapp, this bridge had a real, exploitable
finding**, not just an unreachable transitive dependency:

- `github.com/gorilla/websocket@1.5.0`: **GO-2026-6278** (CVSS 6.9) — used
  `math/rand` instead of `crypto/rand` for WebSocket frame mask key
  generation, making mask keys predictable and enabling frame-content
  injection. govulncheck's call-graph analysis confirms this is REACHABLE
  through the bridge's `remoteauth`/QR-login websocket flow
  (`provisioning.go qrLogin` → `websocket.Upgrader.Upgrade`, plus the
  Discord gateway websocket connection itself). Fixed by upgrading to
  `1.5.3` (`0001-security-fixes-discord.patch`).
- `golang.org/x/crypto@0.55.0`: same GO-2026-6354/6355 SSH-client DoS
  findings as the other bridges — unreachable (no SSH client used here
  either), bumped to `0.56.0` anyway as defense-in-depth.

After the patch: **0 exploitable vulnerabilities** per govulncheck.

## Build dependencies

- `go1.27`
- `olm-devel` (build), `libolm3` (runtime)
- `zstd` (build, for unpacking the vendor tarball)

## Vendored dependencies (`vendor.tar.zst`)

Same reasoning as the other bridges: OBS build workers have no network
access. Regenerate after a `go.mod`/`go.sum` change:

```bash
cd mautrix-discord-src
go mod vendor
tar --zstd -cf vendor.tar.zst vendor/
```

## Package layout

- Binary: `/usr/bin/matrix-mautrix-discord`
- Config: `/etc/matrix-mautrix-discord/` (generated on first run — run
  `matrix-mautrix-discord -c /etc/matrix-mautrix-discord/config.yaml -e`
  once, then `-g -r registration.yaml`)
- Data (SQLite DB, media cache): `/var/lib/matrix-mautrix-discord/`
- Logs: `/var/log/matrix-mautrix-discord/`
- Runs as dedicated system user `matrix-mautrix-discord` (sysusers.d).

## Migrating existing bridge data from the Docker deployment

Copy the Docker `data/` directory's `mautrix-discord.db*` files into
`/var/lib/matrix-mautrix-discord/` (owned by the `matrix-mautrix-discord`
user) to preserve any existing Discord login/session state.

## OBS packaging

Source lives in this git repository; the OBS package definition points at
it via `<scmsync>`.

## Status

- [x] Upstream tag pinned, source vendored as reproducible tarball
- [x] Security audit (govulncheck + osv-scanner) — 1 exploitable finding
      patched (GO-2026-6278)
- [x] RPM spec, systemd unit, sysusers/tmpfiles config
- [x] Go module dependencies vendored (vendor.tar.zst) for offline OBS builds
- [x] Built and tested in OBS (base v0.7.7 + security patch, 2026-09-15)
- [x] Deployed, Docker container decommissioned (2026-09-15/23)

## Forum-channel thread bridging (2026-09-29)

`0002-forum-thread-bridging.patch` adds Discord forum-channel → Matrix
`m.thread` (MSC3440) bridging on top of v0.7.7 + the security patch above.
Developed and reviewed in an isolated local fork
(`~/git/mautrix-discord-forum-threads`, branch `forum-thread-support`,
18 commits on top of upstream `c62165a`), through a strict iterative
Sonnet-writes/Opus-reviews loop: 12 rounds each finding a real concurrency
bug in an initial "noticeComplete channel + sync.Once" completion-barrier
design, followed by a full redesign (`EnsureRoot()` single memoized
election point, merged Thread constructors, persisted `is_forum_post`
discriminator via migration v25) that two independent Opus design
reviews recommended and a third Opus review confirmed structurally closes
that entire bug class. One Medium finding (N1: `discordThreadID` wrongly
blanked on `EnsureRoot` failure, breaking Discord-side edit/reaction/
redact/permalink routing for that message) was found and fixed in a final
round; the fix was independently re-verified by a 4th Opus review
(VERDICT: PASS, mergeable/deployable).

**Deployed 2026-09-29** as a manual hotfix on doom (binary built locally
matching the spec's build flags — `CGO_ENABLED=1 GOFLAGS=-buildmode=pie
go build -ldflags=-linkmode=external`, checksummed, scp'd, installed over
the RPM-owned `/usr/bin/matrix-mautrix-discord`, service restarted) ahead
of a proper OBS rebuild, because the fix was fully reviewed/verified and
the user asked to ship it now. Old binary + DB backed up on doom under
`/root/matrix-mautrix-discord-backup-<timestamp>/` before the swap.
Verified live: `thread` DB table populated (forum posts electing real
roots), no panics/restarts, portal/puppet counts grew as expected.

**Follow-up still needed**: fold `0002-forum-thread-bridging.patch` AND
`0003-manual-backfill-command.patch` into the OBS package properly (bump
Release, add Patch1/Patch2, rebuild via OBS) so the RPM matches what's
actually running and a future `zypper update` doesn't silently overwrite
these hotfixes with the old unpatched binary.
Known LOW-severity follow-ups from review (not deploy blockers): N2 dead
code, N3 (same ThreadID-blanking bug in `convertMessageBatch`'s backfill
path, pre-existing, same fix shape as N1), N4 error-wrap loses type info,
N5 dead `Thread.Update()` method, N6 unsynchronized `initialBackfillAttempted`
bool, N7 doubled nil-check. Also: the two tests added for N1
(`TestDiscordThreadIDRecordedOnEnsureRootFailure`,
`TestDiscordThreadIDRoutingCorrect`) were proven by mutation testing to
NOT actually guard against N1 regressing — they pass even with the bug
reintroduced. Needs a real regression test driving
`handleDiscordMessageCreate` itself, or the tests should be removed so
they stop implying coverage they don't provide.

## Manual thread-history backfill command (2026-09-29)

`0003-manual-backfill-command.patch` adds a `!discord backfill [count]`
admin command (reply to any message inside a bridged Discord thread; a
room moderator can pull up to 500 older messages that predate when the
bridge first saw that thread — fixes missing context for reactions on
old messages in threads bridged after they already had history).

Developed on the same `forum-thread-support` branch, 5 commits
(248244f..71186bd), through the same Sonnet/Opus-writes + Opus-reviews
loop as the forum-thread work — but this round specifically surfaced a
routing mistake in HOW the writing side was dispatched: rounds 1-3 were
sent via `delegate_task`, which silently runs on Haiku (the Hermes
`delegation.model` default) rather than the `code-writer` profile's own
configured Opus model, despite looking like an "Opus writes, Opus
reviews" loop. This produced two real, independently-caught bugs beyond
what review alone found: a lock-scope bug (forwardBackfillLock released
before the actual async work ran, providing zero protection) and a
wrong-pagination-direction bug (reused an existing helper with
stop-at-already-bridged semantics instead of genuinely fetching older
history — would have silently reported "no messages found" in
production). Both were caught by the orchestrating Dispatcher's own
independent code reading BEFORE reaching formal review, and fixed in a
round-2 pass. Round 3's formal Opus review then found three further
Medium findings: M1 (cross-portal thread resolution — a moderator could
leak another Discord channel's message history into the wrong Matrix
room and silently defeat the concurrency lock), M2 (the batch-send path
never recorded Discord thread membership in the DB, making the backfill
cursor blind to that history on hungryserv-capable homeservers — same
"reports zero even though history exists" symptom via a different
route), and M3 (missing login requirement + no nil-Session guard, a
disconnected user's command silently hangs forever via a swallowed
panic). Round 3's own pagination-direction test was also found
inadequate (tested unrelated helper functions, not the real function) —
same "looks like coverage but isn't" mistake this branch has made once
before, caught again by review rather than by trusting the round's own
report.

After the routing mistake was identified and corrected (user caught the
pattern: "když používáš [Haiku] na psaní kódu, tak se dostáváš do
problémů se zamykáním" — see dispatcher-team-routing skill, now records
this as a standing pitfall), round 4 (fixing M1/M2/M3) and round 5
(building a genuine HTTP-level pagination test via an httptest.Server
intercepting discordgo's real HTTP client, with two self-administered
mutation tests proving the test actually catches a broken pagination
direction) were both dispatched via the `code-writer` CLI profile
(confirmed running claude-opus-5), not `delegate_task`. Final review
(round 5, full 5-commit feature reviewed end-to-end for the first time)
returned VERDICT: PASS — independently re-verified both round-2 bugs,
all three Medium findings, ran its own two additional mutation tests
(surfacing two Low-severity, non-blocking test-coverage gaps around
`foundAll` accuracy), and confirmed no single fix regressed another.

**Deployed 2026-09-29** as a manual hotfix on doom, same procedure as
0002 (local build matching spec flags, checksum verified, old binary +
DB backed up under `/root/matrix-mautrix-discord-backup-<timestamp>/`,
restart). Verified live: service stable 2.5+ minutes, `NRestarts=0`, no
panics, new command's string literals present in the compiled binary
(`Backfilling up to %d older messages…`), DB counts unchanged/sane.

Outstanding Low follow-ups from the round-5 review (not blockers):
inaccurate code comments (backfill.go's "none of these acquire
forwardBackfillLock" claim is imprecise though the no-deadlock
conclusion holds; a test-stub comment about after/around), two
uncovered edge cases in the truncation/limit-boundary logic (`foundAll`
correctness on an exact-limit-overshooting short final page; one
redundant API call on an exact-multiple limit), M3's user-facing error
message says "no messages found" rather than "not connected" (correct
code, misleading text), and `!backfill` won't work inside DM/group-DM
threads (fails closed, not a security issue — just a known limitation
inherited from base bridge behavior).
