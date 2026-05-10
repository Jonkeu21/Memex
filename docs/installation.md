# Memex installation guide

## What you are about to do

You will turn a new Raspberry Pi 5 into a personal capture and retrieval system called Memex. By the end you will be able to send a link, a note, a file, or a voice clip to a Telegram bot. The bot queues the item. A worker then files it into an Obsidian-friendly folder of markdown notes. You can search the result later from your phone, a browser, or a Mac. Plan for two to three hours from a fresh Pi to your first capture.

## What you will need

Hardware:

- A Raspberry Pi 5 with at least 4 GB of RAM.
- A 64 GB or larger SD card. An NVMe drive in a Pi 5 hat works too.
- An Ethernet cable. Wi-Fi works but the long-poll link to Telegram is more stable on a wired connection.
- A power supply rated for the Pi 5. The official 27 W USB-C supply is the safe pick.

Accounts and services:

- A Telegram account on your phone. Signup is free.
- An Anthropic account on the Claude Max plan. Memex uses the Claude Code command-line tool for the AI work.
- A Tailscale account on the free tier. Tailscale is a service that builds a private network between your devices.

Other devices:

- A laptop or desktop with a web browser and an SSH client. macOS, Linux, and Windows with WSL all work.
- A second device for Syncthing if you want to read the vault from another machine. A Mac is the common pick.

Time:

- Plan for two to three hours from first boot to your first capture.

Skill level:

- You should be comfortable pasting commands into a terminal and editing a text file. You do not need prior Docker, Linux, or networking experience. The guide teaches the few terms you need along the way.

## How the parts fit together

Memex has five small parts that run as Docker containers on the Pi. A container is a sandboxed program with its own files and process tree. An image is the prebuilt template a container is started from.

The first part is the `capture_api`. It receives a note, a link, a file, or a voice clip and adds a row to a queue. The queue is a single SQLite database file on the Pi.

The second part is the `worker`. It polls the queue every few seconds. For each item it fetches the page or reads the file. It then asks the Claude Code tool to pick a folder and a title. The worker writes a markdown note into the vault.

The third part is the `telegram_bot`. It is how you talk to Memex from your phone. It forwards captures to the capture API. It answers questions by asking Claude Code to search the vault.

The fourth part is the `dashboard`. It is a small web app on the Pi. You use it to triage notes, edit the taxonomy file, and chat with the vault from a browser.

The fifth part is `syncthing`. It mirrors the vault between the Pi and any device you pair with it, such as your Mac.

## Phase 1: Prepare the Raspberry Pi

This phase gets the Pi to a point where you can log in over the network.

### 1.1 Flash the SD card

You will install Raspberry Pi OS onto the SD card with a free tool called Raspberry Pi Imager. The Imager runs on your laptop.

Open `https://www.raspberrypi.com/software/` in a browser. Download Raspberry Pi Imager for your operating system. Install it the same way you install any other program.

Insert the SD card into your laptop's card reader. Open Raspberry Pi Imager.

Click "Choose Device" and pick "Raspberry Pi 5". Click "Choose OS" and pick "Raspberry Pi OS (64-bit)". Pick the "Lite" variant. The Lite variant has no desktop. Memex does not need one. Click "Choose Storage" and pick the SD card.

Before clicking "Write", click the gear icon to open the advanced options. Set a hostname (`memex-pi` is a good default). Enable SSH and pick password authentication for now. Set a username (`memex` is fine) and a password you will remember. Set your Wi-Fi credentials if you plan to use Wi-Fi.

Click "Save", then "Write". Confirm when prompted. Writing takes several minutes.

**Note** Take the SD card out only when the Imager tells you it is safe to eject.

### 1.2 First boot and SSH

Put the SD card into the Pi. Plug in the Ethernet cable. Plug in the power supply last. The Pi boots automatically.

Wait two minutes for the first boot to finish. The Pi writes config files and reboots itself once during this time.

From your laptop, open a shell on the Pi over SSH. SSH is a way to run commands on another computer over the network. Use the username and hostname you set in the Imager.

```sh
ssh memex@memex-pi.local
```

Expected output:

```text
The authenticity of host 'memex-pi.local (...)' can't be established.
ED25519 key fingerprint is SHA256:...
Are you sure you want to continue connecting (yes/no/[fingerprint])? yes
memex@memex-pi.local's password:
Linux memex-pi 6.6.20-v8+ #...
...
memex@memex-pi:~ $
```

Type the password you set in the Imager. The shell prompt now sits on the Pi.

**Tip** If `memex-pi.local` does not resolve, look up the Pi's IP address in your router's admin page. Log in with `ssh memex@<ip-address>` instead.

### 1.3 Confirm the hostname and the filesystem size

The Imager already set the hostname. The filesystem is also expanded to fill the SD card on first boot. Verify both with a quick command. The `hostname` command prints the current hostname. The `df` command shows free disk space.

```sh
hostname && df -h /
```

Expected output:

```text
memex-pi
Filesystem      Size  Used Avail Use% Mounted on
/dev/mmcblk0p2   58G  2.1G   55G   4% /
```

The "Size" column should be close to your SD card's capacity. If it is much smaller, run `sudo raspi-config`. Pick "Advanced Options", then "Expand Filesystem", then reboot.

### 1.4 Enable memory cgroups for Docker

Docker needs the kernel to expose memory cgroups. Cgroups are a Linux feature that lets a container claim a slice of memory. Bookworm hides them by default. The fix is a one-line edit to the boot command file.

The `sed` command below appends the cgroup flags to the kernel command line. The file is one logical line. You must append, not insert a new line.

```sh
sudo sed -i 's/$/ cgroup_enable=cpuset cgroup_memory=1 cgroup_enable=memory/' \
    /boot/firmware/cmdline.txt
sudo reboot
```

Your SSH session ends when the Pi reboots. Wait one minute. Log back in with the same SSH command. Verify the cgroup flags are active. The `cat` command prints the kernel's live command line.

```sh
cat /proc/cmdline | tr ' ' '\n' | grep cgroup
```

Expected output:

```text
cgroup_enable=cpuset
cgroup_memory=1
cgroup_enable=memory
```

If you see three lines, the cgroup setup is correct.

## Phase 2: Install the base software on the Pi

This phase installs Docker, which is the program that runs the Memex containers.

### 2.1 Update the system

A fresh install of Raspberry Pi OS lags behind on security updates. Bring the package list and the installed packages up to date. The `apt-get update` command refreshes the package list. The `full-upgrade` command updates everything else.

```sh
sudo apt-get update && sudo apt-get -y full-upgrade
sudo apt-get install -y openssl ca-certificates curl gnupg
```

Expected output (last few lines):

```text
...
Setting up curl (...) ...
Setting up gnupg (...) ...
```

The full upgrade takes one to five minutes. The exact list depends on how stale the SD image is.

### 2.2 Install Docker Engine and the Compose plugin

Docker is the program that runs containers. Compose is a small add-on that starts and stops a group of containers together. Memex needs both. The version of Docker in Debian's default package list is too old. You must install Docker from the official Docker repository.

The next four commands add Docker's package signing key and its repository to the Pi's package list. They are safe to copy as a block.

```sh
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/debian bookworm stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update
```

Expected output (last few lines):

```text
...
Reading package lists... Done
```

Now install Docker Engine itself plus the buildx and compose plugins.

```sh
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
                        docker-buildx-plugin docker-compose-plugin
```

Expected output (last few lines):

```text
Setting up docker-ce (...) ...
Setting up docker-buildx-plugin (...) ...
Setting up docker-compose-plugin (...) ...
```

### 2.3 Let your user talk to Docker without sudo

By default only root can run `docker` commands. Memex's bootstrap script refuses to run as root, so this step is required. The fix is to add your user to the `docker` group. The group grants permission to talk to the Docker socket. Log out and back in for the change to take effect.

```sh
sudo usermod -aG docker "$USER"
exit
```

Reconnect over SSH from your laptop:

```sh
ssh memex@memex-pi.local
```

Verify with the `docker info` command. It prints a summary of the Docker setup.

```sh
docker info
```

Expected output (first few lines):

```text
Client: Docker Engine - Community
 Version:    ...
Server:
 Containers: 0
 ...
```

If you see "permission denied while trying to connect", the group membership did not refresh. Log out a second time and back in.

## Phase 3: Install Tailscale

Memex listens only on the Pi itself and on a private overlay network called a tailnet. A tailnet is a virtual network that connects your devices over Tailscale. Nothing in this stack is reachable from the public internet. Tailscale is what makes the Pi reachable from your laptop and your phone without poking holes in your home router.

### 3.1 Install the Tailscale daemon

Run the official one-line installer. The `curl` command fetches the install script. The `| sh` pipes the script into the shell that runs it. The script detects Bookworm and uses apt under the hood.

```sh
curl -fsSL https://tailscale.com/install.sh | sh
```

Expected output (last few lines):

```text
Installation complete! Log in to start using Tailscale by running:

sudo tailscale up
```

### 3.2 Sign the Pi into your tailnet

The `tailscale up` command brings the Tailscale connection online. The first time, it prints a URL. You open that URL on your laptop and sign in to your Tailscale account.

```sh
sudo tailscale up
```

Expected output:

```text
To authenticate, visit:

    https://login.tailscale.com/a/abcdef123456
```

Open that URL on your laptop. Sign in to Tailscale. Click "Connect device". The Pi is now on your tailnet.

### 3.3 Confirm the Pi is reachable from your laptop

Each device on a tailnet gets a name like `memex-pi.<your-tailnet>.ts.net`. The middle part is your tailnet name. You can find it in the Tailscale admin page on your laptop.

From your laptop, ping the Pi by its tailnet name. The `ping` command sends small packets to test reachability.

```sh
ping memex-pi.<your-tailnet>.ts.net
```

Expected output:

```text
PING memex-pi.<your-tailnet>.ts.net (100.x.x.x): 56 data bytes
64 bytes from 100.x.x.x: icmp_seq=0 ttl=64 time=21.3 ms
...
```

Press Ctrl-C to stop the ping. If you see replies, Tailscale is set up correctly.

## Phase 4: Create a Telegram bot

Memex talks to you through a Telegram bot. You will create the bot, save its token, and find your own Telegram user ID.

### 4.1 Talk to BotFather

BotFather is the official Telegram account that creates bots. Open Telegram on your phone. Search for `@BotFather` and start a chat. Tap the `/start` link in BotFather's first message.

Send the command `/newbot`. BotFather asks for a display name. Pick anything you like, for example `My Memex`. BotFather then asks for a username. The username must end in `bot`, for example `my_memex_bot`. Memex itself does not see the username.

BotFather replies with a token. The token looks like `123456789:ABCdef...` with a colon in the middle. Copy this token to a safe place. You will paste it into the bootstrap script in the next phase.

**Warning** Treat the token like a password. Anyone with the token can read every message the bot receives.

### 4.2 Find your own Telegram user ID

Memex refuses to talk to anyone whose chat ID is not on a whitelist. Without your own ID on the list, your bot will silently ignore your messages. You can read your ID from a different Telegram bot called `@userinfobot`.

In Telegram, search for `@userinfobot`. Start the chat. The bot replies with a short profile that includes your numeric ID. The ID is a positive integer, typically nine or ten digits long.

Copy the ID. You will paste it into the bootstrap script in the next phase.

**Note** If you also want a group chat to work, add your bot to the group. Look up the group's chat ID using a tool such as `@RawDataBot`. Group IDs are negative numbers. You can paste both IDs into the whitelist, separated by commas.

## Phase 5: Get the Memex source code onto the Pi

Memex's code lives in a Git repository. You will clone the repository into your home directory on the Pi. Cloning means downloading the repository and its history. The home directory is where your user's files live by default.

The `git clone` command downloads the repository. The `cd` command changes the working directory to the new folder.

```sh
git clone https://github.com/<your-fork>/memex.git
cd memex
```

Expected output (last line):

```text
...
Resolving deltas: 100% (...), done.
```

**Note** Replace `<your-fork>` with the GitHub account or organization that hosts your copy. If you do not have a fork, ask the person who wrote Memex for the canonical URL.

You should now have a `memex/` folder in your home directory. All later commands assume you are inside this folder.

## Phase 6: Run the bootstrap script

The bootstrap script is the one command that sets up everything else. It prompts for the values it needs, writes a config file, builds the container images, and starts the stack.

### 6.1 Start the script

Run the script from inside the `memex` folder. The path starts with `./` to make clear you are running the local script, not a program from the system path.

```sh
./scripts/bootstrap.sh
```

The script first prints a "Pre-flight checks" header. It confirms the Pi is on ARM64. It confirms Docker is reachable. Then it begins prompting for values.

### 6.2 Answer the prompts

The prompts come in this order. Defaults are shown in square brackets. Press Enter to accept a default.

1. **Vault host path** `[/srv/memex/vault]`. The folder where Memex stores your notes. The default is the right pick for almost everyone.
2. **Data host path** `[/srv/memex/data]`. The folder where the queue database and uploaded files live. Keep the default.
3. **Syncthing config path** `[/srv/memex/syncthing]`. The folder where Syncthing keeps its keys and state. Keep the default.
4. **Worker poll interval** `[5]`. How often the worker checks for new items, in seconds. Keep the default.
5. **Worker batch pause** `[300]`. How long the worker waits between non-empty batches, in seconds. The pause throttles Claude Max usage. Keep the default for now.
6. **Whisper model file** `[ggml-base.en.bin]`. The transcription model the worker uses for voice notes. Keep the default.
7. **Container timezone** `[<your timezone>]`. The script reads the host's timezone. Keep the default unless you want the containers to run in UTC.
8. **BotFather token** (no default). Paste the token you saved from BotFather in section 4.1.
9. **Allowed chat IDs** (no default). Paste the numeric ID from section 4.2. For more than one chat, separate the IDs with commas.

**Warning** If you leave the chat IDs blank, the bot will drop every message it receives. You can edit the value later in `infra/.env` if you forget. A service restart picks up the change.

### 6.3 What the script does after the prompts

The script generates a random capture API token and a random dashboard token. It then creates the host folders under `/srv/memex/`. It asks for your sudo password once for the folder creation.

The script writes a config file at `infra/.env`. This file holds every setting the containers read at startup.

The script then builds the Docker images. The build step is the longest part of the install. Expect five to fifteen minutes on a Pi 5 with a fast SD card.

Expected output during the build (last few lines):

```text
...
 => => writing image sha256:...                                          0.0s
 => => naming to docker.io/memex/dashboard:latest                        0.0s
[+] Building 4/4
images built
```

The script then runs the Claude Code CLI login flow. That step is covered in the next phase.

## Phase 7: The headless `claude /login` step

This is the trickiest part of the install. The Pi has no web browser. The Claude Code CLI needs a browser to sign in. The bootstrap script bridges the gap. It runs the CLI in your SSH session and asks you to do the browser part on your laptop.

Read this whole phase once before you start. You will need to act within a couple of minutes once the login flow begins.

### 7.1 What you will see in the terminal

After the build step, the script prints a short explanation. It then asks:

```text
Ready to start the login flow? [Y/n]:
```

Press Enter to accept the default of "yes". The script then runs the Claude Code CLI inside a one-shot container. The CLI prints a block that looks like this:

```text
──── Claude Code CLI login ────
...

[claude /login]  open this URL in a browser on a device that has one:

    https://claude.ai/oauth/authorize?...&device_code=ABC123

Paste the code Anthropic shows you back here:
```

The URL is long. It usually wraps across two or three terminal lines.

### 7.2 What to do on your laptop

Open the URL in a browser on your laptop. If the URL wraps in your terminal and you cannot copy it cleanly, drag the SSH window wider so it sits on one line.

You can also read the URL from the container's log. Open a second SSH session to the Pi. Run this command in the second session:

```sh
docker compose -f infra/docker-compose.yml logs worker | tail -n 50
```

Expected output (the relevant lines):

```text
worker-1  | [claude /login]  open this URL in a browser ...
worker-1  |     https://claude.ai/oauth/authorize?...&device_code=ABC123
```

With the URL open in your laptop's browser, sign in to your Anthropic account. Pick the right Claude Max account if you have several. Anthropic shows a code on the page. Copy the code.

Go back to your first SSH session. Paste the code at the prompt. Press Enter.

The CLI writes a credentials file inside a Docker volume called `memex_claude_auth`. A volume is a managed folder that Docker tracks and shares between containers. A bind mount is the other shape of shared folder: a folder on the Pi that is also visible inside a container.

The bootstrap script then runs a one-word test call to confirm everything works.

Expected output:

```text
Login flow exited successfully. Verifying with a no-op call...
claude CLI is authenticated and reachable.
```

### 7.3 Common failure modes

The login flow can fail in a few well-known ways. Each one is fixable.

**The code expired.** Anthropic's codes are short-lived. If you take more than a couple of minutes, the CLI rejects the code. Rerun `./scripts/bootstrap.sh`. When it asks what to do, pick `re-login`.

**The URL is wrapped and unreadable.** Make the terminal wider. If that does not help, read the URL from the worker container's logs using the second SSH session method above.

**The CLI prints "rate-limited" or "session unavailable".** Your Claude Max session is being used somewhere else, often by your own Claude Code on the Mac. Wait one minute. Rerun the bootstrap script and pick `re-login`.

**The volume already has credentials.** The bootstrap script detects this and skips the login step. To force a fresh login, first run `./scripts/teardown.sh --reset-claude-login`. That removes the old credentials. Then run `./scripts/bootstrap.sh` again.

## Phase 8: Bring the stack up

The bootstrap script runs `docker compose up -d` for you. The command starts all five containers in the background. A service in Compose terminology is one of the named containers in the compose file. The `-d` flag means detached, so the containers keep running after the script exits.

### 8.1 Confirm every container is healthy

The `docker compose ps` command lists the containers in the project. Run it from the `memex` folder.

```sh
docker compose -f infra/docker-compose.yml ps
```

Expected output (your container IDs and timestamps will differ):

```text
NAME                IMAGE                          STATUS         PORTS
memex-capture_api   memex/capture_api:latest       Up (healthy)
memex-dashboard     memex/dashboard:latest         Up (healthy)   0.0.0.0:8002->8002/tcp
memex-syncthing     syncthing/syncthing:1.27.10    Up             0.0.0.0:22000->22000/tcp, ...
memex-telegram_bot  memex/telegram_bot:latest      Up (healthy)
memex-worker        memex/worker:latest            Up (healthy)
```

All five rows must say `Up`. Four of them should also say `(healthy)`. Syncthing has no health check and just says `Up`.

### 8.2 What to do if a service is unhealthy

If any service is stuck in `Restarting`, look at its logs. The `docker compose logs` command prints recent log lines for one service.

```sh
docker compose -f infra/docker-compose.yml logs capture_api
```

You will see structured JSON log lines, one per event. The most useful field is `event`. If you see `event="db_open_failed"`, you have a permissions problem on `/srv/memex/data`. If you see `event="config_missing"`, the `infra/.env` file is missing a key.

If you cannot diagnose the issue, the section "What to do if something goes wrong" below covers the most common cases.

## Phase 9: Send your first capture

This is the moment of truth. You will send a link to your bot. The worker will pick it up. A markdown note will land in the vault.

### 9.1 Send a URL to the bot

On your phone, open Telegram. Open the chat with the bot you created in section 4.1. Send any web link as a normal message. For example:

```text
https://en.wikipedia.org/wiki/Raspberry_Pi
```

The bot replies within two seconds. The reply looks like this:

```text
Queued #1 (url). I'll let you know where it lands.
```

The `#1` is the queue row ID. The very first capture is always `#1`. The `(url)` tag names the kind of capture the bot detected.

### 9.2 Watch the worker pick it up

The worker polls the queue every five seconds. On the next tick it claims your row. It fetches the page, runs Claude Code to pick a folder, and writes the note.

Watch the worker's logs in real time. The `-f` flag follows new lines as they arrive.

```sh
docker compose -f infra/docker-compose.yml logs -f worker
```

Expected output (representative lines, your timestamps will differ):

```text
worker-1  | {"ts":"...","service":"worker","event":"poll_tick","level":"info"}
worker-1  | {"ts":"...","service":"worker","event":"item_claimed","queue_item_id":1,"level":"info"}
worker-1  | {"ts":"...","service":"worker","event":"extraction_done","queue_item_id":1,"level":"info"}
worker-1  | {"ts":"...","service":"worker","event":"claude_call_completed","queue_item_id":1,"duration_ms":4831,"level":"info"}
worker-1  | {"ts":"...","service":"worker","event":"worker_item_filed","queue_item_id":1,"vault_path":"resources/...","level":"info"}
```

Press Ctrl-C to stop following the logs.

### 9.3 Find the note in the vault

The vault lives at `/srv/memex/vault` on the Pi. The note's path is in the `vault_path` field of the log line above. List the files to confirm. The `find` command walks the vault tree and prints markdown files.

```sh
find /srv/memex/vault -name '*.md' -type f
```

Expected output:

```text
/srv/memex/vault/resources/2026-05-10--raspberry-pi.md
```

The exact folder depends on the model's filing choice. The file name uses today's date and a kebab-cased slug from the page title.

View the note's contents with the `cat` command, which prints a file.

```sh
cat /srv/memex/vault/resources/2026-05-10--raspberry-pi.md
```

The note starts with a YAML front-matter block. The block includes the queue row ID, the source URL, the model's confidence score, and the chosen folder. The body of the note has the title, a summary, and the extracted page text.

**Tip** If the note landed in `_inbox/` instead of a regular folder, the model's confidence was below the auto-file threshold. The dashboard's Inbox page is where you triage these.

## Phase 10: Open the dashboard

The dashboard is a web app on the Pi. You open it from a browser on your laptop. Tailscale gives the Pi a stable name on your tailnet. The dashboard listens on port 8002.

### 10.1 Find the dashboard token

The bootstrap script printed a long random token at the very end of its run. The line looks like this:

```text
Paste this token into the dashboard's Settings drawer:
abc123...ef
```

If you missed it, read it from the config file. The `grep` command searches the file for a single line.

```sh
grep MEMEX_DASHBOARD_BEARER_TOKEN infra/.env
```

Expected output:

```text
MEMEX_DASHBOARD_BEARER_TOKEN=abc123...ef
```

Copy the value after the equals sign. The token is 64 hexadecimal characters long.

### 10.2 Open the dashboard in your browser

On your laptop, open this URL in any browser:

```text
http://memex-pi.<your-tailnet>.ts.net:8002/
```

You should see a green Memex shell with a sidebar of pages. The read-only pages such as the queue list and the captures browser work without a token.

### 10.3 Paste the token

Click the gear icon at the top right. A settings drawer opens. Paste the token into the "Bearer token" field. Click outside the drawer to close it. The token is saved in your browser's local storage.

You can now trigger queue retries, edit the taxonomy, route inbox notes, and use the retrieval chat. The chat asks Claude Code questions against the vault, like the Telegram bot does.

## Phase 11: Connect Syncthing to your Mac or other device

Syncthing mirrors the vault between the Pi and any device you pair with it. Pairing happens through Syncthing's web UI. The Pi's UI is bound to localhost for safety. You reach it through an SSH tunnel.

### 11.1 Install Syncthing on your other device

On a Mac, install Syncthing with Homebrew. Homebrew is a package manager for macOS. The `brew install` command fetches and installs the program.

```sh
brew install --cask syncthing
```

Start the Syncthing app. On first run it opens `http://127.0.0.1:8384/` in your default browser. That page is the Mac's Syncthing web UI.

For Windows or Linux, download Syncthing from `https://syncthing.net/downloads/` and run the matching installer.

### 11.2 Open the Pi's Syncthing UI

From your laptop, open an SSH tunnel to the Pi. A tunnel forwards a port on your laptop to a port on the Pi. The `-L` flag tells SSH to forward local port 8384 to the Pi's localhost port 8384.

```sh
ssh -L 8384:127.0.0.1:8384 memex@memex-pi.local
```

Leave that SSH session running. Open a new browser tab on your laptop. Visit:

```text
http://127.0.0.1:8384/
```

You should see the Pi's Syncthing UI.

**Tip** If port 8384 is already taken on your laptop because the Mac's Syncthing is using it, pick a different local port. Use `ssh -L 18384:127.0.0.1:8384 ...` and open `http://127.0.0.1:18384/` instead.

### 11.3 Pair the two devices

In the Mac's Syncthing UI, click "Actions", then "Show ID". Copy the long device ID. The ID is a string of letters and dashes.

In the Pi's Syncthing UI, click "Add Remote Device" at the bottom right. Paste the Mac's device ID into the form. Give the device a label (`mac` is fine). Click "Save".

The Mac's UI now shows a banner asking whether to accept the Pi as a new device. Click "Add Device" on the banner. Confirm.

### 11.4 Share the vault folder

The Pi's Syncthing has the vault registered as a folder. The folder ID is `vault`. In the Pi's UI, click the `vault` folder, then "Edit". Open the "Sharing" tab. Tick the Mac device. Click "Save".

The Mac's UI now shows a banner asking whether to accept the new folder. Click "Add Folder". Pick a path on your Mac for the synced copy (for example `~/Documents/memex-vault`). Click "Save".

Syncthing now copies the vault to your Mac. The first sync may take one or two minutes depending on vault size. You can open the synced folder in Obsidian on your Mac and read your notes.

**Note** Edits on the Mac sync back to the Pi. The Pi is still the canonical copy: the worker writes new notes there.

## Operating Memex day-to-day

This section covers the few commands you will run during normal use. Each block stands alone. The developer runbook at `docs/deployment.md` has the full reference if you need more detail.

### Update Memex when there is a new version

Fetch the latest code from your fork. Rebuild any images that changed. The `git pull` command downloads new commits. The `--build` flag tells Compose to rebuild before starting.

```sh
cd ~/memex
git pull
docker compose -f infra/docker-compose.yml up -d --build
```

### Add another Telegram chat ID to the whitelist

Edit the `infra/.env` file. Append the new ID to the existing list. The bot picks up the change after you restart its service. The `nano` command opens a simple terminal editor.

```sh
nano infra/.env
# change MEMEX_TELEGRAM_ALLOWED_CHAT_IDS=<id1> to <id1>,<id2>
docker compose -f infra/docker-compose.yml up -d telegram_bot
```

### Find logs for a specific service

Each container's logs are tagged by service name. Pass the service name to the `logs` command. The five service names are `capture_api`, `worker`, `telegram_bot`, `dashboard`, and `syncthing`.

```sh
docker compose -f infra/docker-compose.yml logs -f worker
```

### Back up the vault and the queue database

The `rsync` command copies a folder to another machine over SSH. The `sqlite3 .backup` command writes a consistent copy of the queue, even with the database in use.

```sh
rsync -aHAX --delete /srv/memex/vault/ user@your-nas:/backups/memex/vault/
sqlite3 /srv/memex/data/memex.db ".backup '/tmp/memex-$(date -u +%Y%m%d).db'"
```

### Restart a single service without taking the whole stack down

The `restart` command bounces one container. The other services keep running. This is the right tool after editing `infra/.env`.

```sh
docker compose -f infra/docker-compose.yml restart telegram_bot
```

## What to do if something goes wrong

These are the most common problems and their fixes. The developer runbook at `docs/deployment.md` covers rarer cases.

### The Telegram bot is not responding

**Symptom.** You send a message but the bot does not reply.

**Likely cause.** Your chat ID is not on the whitelist, or the bot container has crashed.

**Fix.**

1. Run `docker compose -f infra/docker-compose.yml ps`. Check that `telegram_bot` says `Up`.
2. Run `grep MEMEX_TELEGRAM_ALLOWED_CHAT_IDS infra/.env`. Check that your ID is on the list.
3. Run `docker compose -f infra/docker-compose.yml logs telegram_bot | tail -n 50`. Look for rejection events.

### A note is stuck in `_inbox/` and is not auto-filing

**Symptom.** Notes land in `_inbox/` and never move to a regular folder.

**Likely cause.** The model's confidence was below the auto-file threshold. This is by design.

**Fix.**

1. Open the dashboard.
2. Go to the Inbox page.
3. Pick the right folder for the note in the dropdown.
4. Click "Route". The dashboard moves the note and clears the `needs_review` flag.

### The dashboard is unreachable from the laptop

**Symptom.** The dashboard URL times out in your browser.

**Likely cause.** Tailscale is not connected, or the dashboard container is down.

**Fix.**

1. On the Pi, run `tailscale status`. Confirm the Pi is connected.
2. On your laptop, confirm Tailscale is running too.
3. Run `docker compose -f infra/docker-compose.yml ps dashboard`. Check the status.
4. If the dashboard is not healthy, read `docker compose -f infra/docker-compose.yml logs dashboard`.

### The worker says "Claude CLI not authenticated"

**Symptom.** Worker logs show repeated `event="claude_response_invalid_json"` lines or explicit authentication errors.

**Likely cause.** The Claude Code credentials file is missing or has expired.

**Fix.**

1. Stop the stack with `docker compose -f infra/docker-compose.yml down`.
2. Run `./scripts/teardown.sh --reset-claude-login` to clear the old credentials.
3. Run `./scripts/bootstrap.sh` again. Follow the headless login walkthrough in phase 7.

### A `git pull` and rebuild broke a service

**Symptom.** A service that used to run is now in a restart loop after an update.

**Likely cause.** A new release added an environment variable your live `infra/.env` does not have.

**Fix.**

1. Read the new `infra/.env.example` for any added keys.
2. Compare it with your live `infra/.env` using `diff infra/.env infra/.env.example`.
3. Add the missing keys to your live `infra/.env` with sensible values.
4. Run `docker compose -f infra/docker-compose.yml up -d --build` to apply.

### Syncthing is showing a conflict

**Symptom.** Files with names like `note.sync-conflict-20260510-143022.md` appear in your vault.

**Likely cause.** The same note was edited on the Pi and on the Mac at the same time.

**Fix.**

1. Open both files in your text editor.
2. Decide which version is correct.
3. Copy the right content into the original file (the one without `sync-conflict` in its name).
4. Delete the conflict file.

## Where to go next

You have a working Memex. The commands in "Operating Memex day-to-day" cover most of what you will do from here.

Three other files are worth reading next.

The first is `docs/deployment.md`. That is the developer's operations runbook. It covers recovery scenarios, port budgets, and the rarer gotchas. Read it when you need to debug a setting or tune a default.

The second is `Progress-Tracker.md`. That is the project's lab notebook. Each build phase is documented with the decisions it made and the questions it left open. Read it when you want to know why something is the way it is.

The third is `CLAUDE.md`. That is the binding contract for the stack. Schemas, names, paths, thresholds, and log event names all live there. Read it when you want to write your own captures by hand or change a default.

When you want to send captures by `curl` from another machine, look at the capture API endpoints documented in `CLAUDE.md`. When you want a second submitter (such as a dashboard token or a scripting token), look at the `MEMEX_CAPTURE_TOKEN_<LABEL>` pattern in `infra/.env.example`.
