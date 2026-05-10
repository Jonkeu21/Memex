# Memex deployment guide

A walkthrough from a freshly flashed Raspberry Pi 5 to a working capture +
retrieval bot. Read top-to-bottom on the first install; the operations runbook
near the end is what you'll come back to.

## 1. Hardware checklist

- **Raspberry Pi 5, 4 GB RAM.** The 8 GB model is fine; 2 GB is too tight once
  whisper.cpp loads `ggml-base.en.bin`.
- **64 GB+ SD card or NVMe.** The vault grows; the SQLite WAL grows; whisper
  models live in the worker image.
- **Ethernet recommended.** Long-poll Telegram + Syncthing both prefer a
  stable link. Wi-Fi works but expect occasional reconnect noise in the logs.
- **Pi-hole compatibility.** Memex publishes Syncthing's sync ports
  (`22000/tcp`, `22000/udp`, `21027/udp`) and binds Syncthing's web UI to
  `127.0.0.1:8384` only. None of these collide with Pi-hole's `53/80/443/8080`.

## 2. OS prep

1. Flash **Raspberry Pi OS 64-bit Bookworm** (Lite is fine; we don't need a
   desktop).
2. SSH in. Update everything:

   ```sh
   sudo apt-get update && sudo apt-get -y full-upgrade
   sudo apt-get install -y openssl ca-certificates curl gnupg
   ```

3. Install Docker Engine + Compose plugin from the **official Docker repo**
   (the `docker.io` apt package is too old; the snap is unsupported):

   ```sh
   sudo install -m 0755 -d /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/debian/gpg | \
       sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
   echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.gpg] \
       https://download.docker.com/linux/debian bookworm stable" | \
       sudo tee /etc/apt/sources.list.d/docker.list
   sudo apt-get update
   sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
                           docker-buildx-plugin docker-compose-plugin
   ```

4. Add your user to the `docker` group and start a fresh shell:

   ```sh
   sudo usermod -aG docker "$USER"
   exit  # log back in via SSH so the group takes effect
   ```

5. Enable memory cgroups. On Bookworm the kernel cmdline lives at
   `/boot/firmware/cmdline.txt` (it moved from `/boot/cmdline.txt` in the
   Bookworm release). The file is one logical line — append on the same line:

   ```sh
   sudo sed -i 's/$/ cgroup_enable=cpuset cgroup_memory=1 cgroup_enable=memory/' \
       /boot/firmware/cmdline.txt
   sudo reboot
   ```

   After the reboot, confirm with `cat /proc/cmdline | tr ' ' '\n' | grep cgroup`.

## 3. Tailscale

```sh
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

MagicDNS gives you `<hostname>.<tailnet>.ts.net`. The capture API and the
Syncthing UI are reachable over Tailscale; nothing in this stack listens on a
public IP.

## 4. Clone the repo and run bootstrap

```sh
git clone https://github.com/<your-fork>/memex.git
cd memex
./scripts/bootstrap.sh
```

The script:

1. Refuses to run as root.
2. Verifies arch is `aarch64`/`arm64` and Docker is reachable.
3. Detects an existing `infra/.env` and offers `reconfigure` / `re-login` /
   `nothing` (idempotent).
4. Prompts for the Telegram bot token, allowed chat IDs, and host paths.
5. Generates the capture API token via `openssl rand -hex 32`.
6. `sudo mkdir`s `/srv/memex/{vault,data,syncthing}` (the only `sudo` step).
7. Writes `infra/.env`.
8. `docker compose build`.
9. **Runs `claude /login` headlessly** (see §5).
10. `docker compose up -d`, waits for `capture_api` health, sends a
    `bootstrap-ok` self-test capture, prints a summary.

Useful flags:

- `--force` — overwrite an existing `infra/.env` (the old one is backed up
  with a timestamp suffix).
- `--skip-login` — don't run `claude /login` (use if you've already done it).
- `--dry-run` — validate inputs only, write nothing, run no docker commands.

## 5. The headless `claude /login` walkthrough

This is the only step that requires a browser, and the Pi doesn't have one.
Memex handles it by spawning a one-shot worker container that runs
`claude /login` interactively in your SSH session.

What you see:

```
──── Claude Code CLI login ────
…
Ready to start the login flow? [Y/n]: y

[claude /login]  open this URL in a browser on a device that has one:

    https://claude.ai/oauth/authorize?...&device_code=ABC123

Paste the code Anthropic shows you back here:
```

What to do:

1. Copy the URL into a browser on your laptop.
2. Sign in to Anthropic if prompted; pick the right Claude Max account.
3. Anthropic shows a code; copy it.
4. Paste it back into the SSH terminal. Press Enter.
5. The CLI writes `/home/memex/.claude/credentials.json` into the named
   volume `memex_claude_auth`. Bootstrap then runs a no-op
   `claude -p --output-format json "ping"` to confirm the auth state works.

Failure modes:

- **The URL doesn't render cleanly.** Resize your terminal so the line isn't
  wrapped, or copy from `docker compose -f infra/docker-compose.yml logs`.
- **The code expired.** Codes are short-lived. Just rerun `scripts/bootstrap.sh`
  and pick `re-login`.
- **The CLI says "rate-limited" or "session unavailable".** Your Claude Max
  session is being used elsewhere (e.g. the Mac dev session). Wait a minute
  and rerun. The Pi is intentionally rate-limited — see CLAUDE.md
  "Rate-limit accounting".
- **The volume already has credentials.** Bootstrap detects this and skips
  the login step. To force a fresh login, run
  `scripts/teardown.sh --reset-claude-login` first.

## 6. First capture test (Telegram → vault)

1. From a whitelisted chat, send a URL to your bot, e.g.
   `https://www.example.com/my-favourite-page`.
2. The bot replies within ~2 s: `✓ Queued #N (url) — I'll let you know where it lands.`
3. Within `MEMEX_WORKER_BATCH_PAUSE_SECONDS + ~30 s`, the worker:
   - extracts the page,
   - calls `claude -p` with the filing prompt,
   - writes the markdown file to `${MEMEX_VAULT_PATH}/<folder>/<date>--<slug>.md`,
   - updates the queue row (`status='filed'`, `vault_path=...`).
4. Tail the worker's logs:

   ```sh
   docker compose -f infra/docker-compose.yml logs -f worker
   ```

   You'll see one batch tick per `MEMEX_WORKER_POLL_SECONDS` and an
   `event="worker_item_filed"` line per item.

5. From the same chat, ask a question:
   `What did I save about the Pi 5 power supply?`
   The bot returns three messages: an answer, a sources list, a quotes block.

## 7. Operations runbook

```sh
# Check status
docker compose -f infra/docker-compose.yml ps

# Tail logs
docker compose -f infra/docker-compose.yml logs -f worker
docker compose -f infra/docker-compose.yml logs -f telegram_bot
docker compose -f infra/docker-compose.yml logs -f capture_api

# Restart one service (no other services restart)
docker compose -f infra/docker-compose.yml restart telegram_bot

# Roll a code change
git pull
docker compose -f infra/docker-compose.yml up -d --build

# Add a chat ID (no rebuild needed)
$EDITOR infra/.env   # MEMEX_TELEGRAM_ALLOWED_CHAT_IDS=12345,-9876
docker compose -f infra/docker-compose.yml up -d telegram_bot

# Back up the vault (rsync to NAS)
rsync -aHAX --delete /srv/memex/vault/ user@nas:/backups/memex/vault/

# Back up the SQLite queue (use sqlite3 .backup so WAL is consistent)
sqlite3 /srv/memex/data/memex.db ".backup '/tmp/memex-$(date -u +%Y%m%d).db'"

# Open the Syncthing UI from your laptop (the Pi binds it to localhost)
ssh -L 8384:127.0.0.1:8384 pi@<host>     # → http://127.0.0.1:8384
```

## 8. Recovery scenarios

**`claude /login` expired.**

```sh
./scripts/teardown.sh --reset-claude-login
./scripts/bootstrap.sh    # answer "re-login" if prompted, or run a full bootstrap
```

**Reset the queue but keep the vault.**

```sh
docker compose -f infra/docker-compose.yml down
rm /srv/memex/data/memex.db /srv/memex/data/memex.db-wal /srv/memex/data/memex.db-shm
docker compose -f infra/docker-compose.yml up -d
# Migrations rerun automatically on the next capture.
```

**Corrupt SQLite WAL.**

The capture API and worker both open the DB with WAL mode. If a hard
power-loss leaves an orphan `-wal`, do:

```sh
docker compose -f infra/docker-compose.yml stop capture_api worker telegram_bot
sqlite3 /srv/memex/data/memex.db "PRAGMA wal_checkpoint(TRUNCATE);"
sqlite3 /srv/memex/data/memex.db "PRAGMA integrity_check;"
docker compose -f infra/docker-compose.yml up -d
```

**Full reset, keep nothing.**

```sh
./scripts/teardown.sh --prune-images --reset-claude-login --wipe-data
# (--wipe-data prompts twice; deletes the vault and the queue)
```

## 9. Known gotchas

- **Pi-hole port collisions.** Pi-hole binds `53/80/443/8080`. Memex doesn't.
  If you previously bound `80/443` to something else, no change required.
- **Syncthing UDP discovery over Tailscale.** If you only allow TCP through
  your Tailscale ACLs, the Pi and the Mac may discover each other slowly.
  Add `udp:22000` and `udp:21027` to the ACL or rely on the introducer pattern.
- **Whisper model swap.** The worker image bakes in `ggml-base.en.bin`. To
  switch to `ggml-tiny.en.bin`, override the `WHISPER_MODEL_URL` build arg in
  the worker Dockerfile and rebuild. The runtime config (`MEMEX_WHISPER_MODEL_FILE`
  in `infra/.env`) selects which model file under `/models/` to use, but the
  file has to exist in the image.
- **Syncthing image tag.** We pin to `syncthing/syncthing:1.27.10` because it
  is multi-arch (incl. `linux/arm64`) and is on the v1 line. v2.x is also
  available for ARM64; bump the tag deliberately when you're ready.
- **Container time.** The compose file bind-mounts `/etc/localtime`, so
  `docker compose logs` timestamps match wall-clock. The structured `ts`
  field in JSON log lines is always UTC, regardless.
- **Rate limits.** The Pi shares your Claude Max session with your laptop.
  If you're heavy-handed on the Mac, the worker's `claude -p` calls will
  start failing with rate-limit errors and the queue will back up. Bump
  `MEMEX_WORKER_BATCH_PAUSE_SECONDS` in `infra/.env` to slow the worker
  down.
