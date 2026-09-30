# vmux

A terminal picker for Claude Code sessions that live in tmux on a remote
machine: a cloud dev VM, a box under your desk, a big shared server. Start a
long Claude job, close the laptop, open it later, and `vmux` puts you back in
the same session with its scrollback intact.

```
┌──────────────────────────────────────────────┐
│  vmux sessions                   ● connected │
├──────────────────────────────────────────────┤
│ ▸ claude-fix-flaky-tests    1 win  idle 2m   │
│   claude-search-ranking     1 win  attached  │
│   claude-0929-141502        1 win  idle 3h   │
├──────────────────────────────────────────────┤
│ ↵ attach  n new  x kill  r rename  g refresh │
└──────────────────────────────────────────────┘
```

What it does for you:

- **Reconnects after sleep.** When the SSH transport drops, vmux waits for the
  host to answer and re-attaches. The tmux session on the host never stopped.
- **Starts a stopped VM**, if you tell it how. Give it a status command and a
  start command and it will bring an auto-terminated cloud VM back before
  attaching. Without them it just waits for the host.
- **Survives host shutdowns.** Every Claude session is started with a fixed
  `--session-id`, recorded on the host's disk. After a shutdown, vmux rebuilds
  the missing sessions in their original directories with `claude --resume`, so
  the conversation continues rather than restarting.
- **Names sessions after the work.** Create one with a blank name and a small
  watcher on the host renames it from Claude's own session title once there is
  a real conversation (`✳ Color naming` becomes `claude-color-naming`).
- **Warns before certificate-based SSH logins expire**, and stops cleanly
  instead of looping a browser login flow.

It is one stdlib-only Python file. The host needs nothing beyond tmux and
Claude Code.

## Requirements

On your laptop:

- Python 3.9 or newer. The one that ships with Xcode's command-line tools is
  enough.
- SSH to the host already working: `ssh YOUR-HOST` gets you a shell, whether
  through a plain key or your organisation's SSO flow.

On the host:

- tmux, and Claude Code on the PATH of a login shell.

## Install

```sh
git clone https://github.com/ashavolian/vmux.git ~/vmux
~/vmux/install.sh
```

The installer symlinks `~/vmux/vmux` into `~/.local/bin`, so a later `git pull`
updates the command in place. It then runs `vmux setup` if you have no config
yet, and tells you if `~/.local/bin` isn't on your PATH.

Optional but recommended, on the host: the three-line `tmux.conf` in this repo
turns on focus events (Claude Code wants them), a long scrollback, and a short
escape delay.

```sh
scp ~/vmux/tmux.conf YOUR-HOST:~/.tmux.conf
```

If you like a shorter command, `alias vmc=vmux` in your shell rc.

## Setup

`vmux setup` asks a handful of questions and writes
`~/.config/vmux/config.json` with owner-only permissions. Enter keeps the
value shown in brackets, `-` clears it. Rerun it any time; existing values
come back as defaults.

1. **Where do your sessions run?** The ssh host (an `ssh_config` alias is
   fine) and the directory new sessions should start in. The directory is
   expanded on the host, so `$HOME/src` works.
2. **How should Claude be started?** A model to pass as `--model`, or blank
   for Claude's own default, plus any extra flags such as
   `--permission-mode auto`.
3. **Can the machine be stopped and started?** Say yes for a cloud VM. You
   give a local command that prints the VM's state, a regex that means
   running, a regex that means stopped, and the command that starts it. If
   neither regex matches the output, vmux treats the state as unknown and
   waits rather than starting anything.
4. **When ssh authentication fails**, a command to suggest, such as an SSO
   login. vmux prints it; it never runs it.

Finally it offers to test the connection. `vmux config` prints the path and
the values in effect.

### Sharing a config with your team

Any string value may contain `{user}`, which becomes the local username when
the file is read. So one file can serve a whole team whose hosts follow a
pattern:

```json
{
  "host": "{user}-dev.example.internal",
  "vm_start_command": "cloudctl vm start {user}"
}
```

Hand it around and install it with:

```sh
vmux setup --from team-config.json
```

### Example: a Google Cloud VM

```json
{
  "host": "{user}-dev.example.internal",
  "workdir": "$HOME/src",
  "claude_model": "",
  "claude_flags": "--permission-mode auto",
  "vm_status_command": "gcloud compute instances describe {user}-dev --zone us-central1-a --format='value(status)'",
  "vm_running_pattern": "^RUNNING$",
  "vm_stopped_pattern": "^(TERMINATED|SUSPENDED|STOPPING|STAGING|PROVISIONING)$",
  "vm_start_command": "gcloud compute instances start {user}-dev --zone us-central1-a",
  "login_command": "ssh-add ~/.ssh/id_ed25519",
  "auth_fatal_markers": [],
  "auth_fatal_hint": ""
}
```

### Configuration reference

| Key                   | Default  | What it is |
|-----------------------|----------|------------|
| `host`                | required | SSH destination. Anything `ssh` accepts. |
| `workdir`             | `$HOME`  | Directory for new sessions, expanded by the shell on the host. |
| `claude_model`        | blank    | Passed as `claude --model`. Blank lets Claude Code choose. |
| `claude_flags`        | blank    | Appended verbatim to the `claude` command. |
| `vm_status_command`   | blank    | Local shell command that prints the VM's state. Blank disables VM handling. |
| `vm_running_pattern`  | blank    | Regex; if it matches the status output, the VM is running. |
| `vm_stopped_pattern`  | blank    | Regex; if it matches, the VM is stopped and `vm_start_command` runs. If a group is present, its text is shown in messages. |
| `vm_start_command`    | blank    | Local shell command that starts the VM. Blank means vmux only waits. |
| `login_command`       | blank    | Suggested to you when ssh authentication fails. Never executed. |
| `auth_fatal_markers`  | `[]`     | Extra ssh stderr substrings that mean retrying won't help, on top of the built-in `address already in use`. |
| `auth_fatal_hint`     | blank    | Free text printed alongside such an error, e.g. how to find the process holding a port. |

The two `*_command` values run through your local shell as the user running
vmux, exactly like a shell alias would. In those two keys `{user}` is quoted
so it is always a single word. The file lives at `~/.config/vmux/config.json`
(or `$XDG_CONFIG_HOME/vmux/config.json`); point `--config PATH` or
`$VMUX_CONFIG` somewhere else to keep several.

## Usage

```
vmux                open the picker (always, whatever is running)
vmux -n NAME        create claude-NAME and attach
vmux -n             create a session and let Claude name it
vmux -n NAME -s     create a plain shell session, no Claude
vmux -l             list sessions and exit
vmux --no-restore   don't rebuild sessions lost to a host shutdown
vmux setup          write or edit the config
vmux config         show the config in effect
vmux --help         everything above, plus the config path
```

Picker keys: `↵` attach, `n` new, `x` kill, `r` rename, `g` refresh,
`q` quit. `j`/`k` also move the cursor. Detaching from tmux (`C-b d`) brings
you back to the picker.

Names are prefixed `claude-` automatically. If there are no sessions at all,
vmux creates one and attaches rather than showing an empty picker.

## How it works

- Sessions are created detached, then Claude is started with `tmux send-keys`.
  The login shell outlives Claude, so when a job finishes the window stays put
  with its output instead of evaporating.
- Each session carries its Claude conversation id as a tmux user option
  (`@vmux_claude`), and vmux records `{name, cwd, claude_id}` in
  `~/.local/state/vmux/sessions.json` on the host. Startup reconciles records
  against live sessions by id, not name, so renames don't confuse it.
- One SSH round trip fetches the host's clock, the live sessions, and the state
  file together. Idle times use the host's clock so they don't drift with
  yours.
- Reconnect is a retry loop keyed on ssh exit status 255 with 2s→30s backoff.
  `ServerAliveInterval=5` / `ServerAliveCountMax=3` is what turns a
  slept-through socket into a prompt 255 instead of a hang.
- Attaches with `tmux attach -d` on purpose. After a lid close the pre-sleep
  client lingers server-side and would otherwise shrink your window to the
  ghost's size.
- When the host is down and VM handling is configured, vmux runs the status
  command, starts the VM if it reads as stopped, and re-checks every 60s while
  waiting. Unknown is treated as unknown, never as stopped. It gives up after
  12 minutes. A local lock file single-flights this across several vmux tabs
  so they don't all run the cloud commands at once.
- The rename watcher is a small POSIX sh script written to
  `~/.cache/vmux-watch.sh` on the host and run there with `setsid`. Polling
  from the laptop would cost a fresh SSH every few seconds. It backs off if
  you rename the session yourself.

## Troubleshooting

**"SSH auth is failing."** Your key isn't loaded or your SSH certificate
expired. If you configured a `login_command`, vmux prints it here. Otherwise
make `ssh YOUR-HOST` work on its own, then rerun.

**"ssh login can't complete: address already in use."** Another ssh or vmux is
holding a local port your login flow needs. Find and stop it, then rerun. Put
the commands you use for that in `auth_fatal_hint` so vmux reminds you next
time.

**Claude never starts, or errors about the model.** Either Claude Code on the
host is too old for the model you configured, or you don't have access to it.
Change `claude_model` with `vmux setup`, or leave it blank.

**"can't read the VM state."** The status command failed, timed out, or
printed something neither regex matched. Run it by hand once; if it wanted a
login, finish that and vmux will pick up. This is deliberate: vmux won't run
the start command against a VM that might already be running.

**After updating vmux, old behaviour persists.** Python reads the script once
at launch, so tabs opened before a `git pull` keep running the old code.
Restart them.

## Development

```sh
python3 -m unittest discover -s tests
```

The tests cover config loading, `{user}` expansion and quoting, the Claude
command line, VM state classification, and auth error matching. Nothing in
them touches the network.

## Updating

```sh
git -C ~/vmux pull
```

Then restart any vmux tabs you have open.
