# vmux

Get to your Claude Code agents on a remote machine, and back.

Your agents live in [herdr](https://herdr.dev) on the host: a cloud dev VM, a
box under your desk, a shared server. herdr owns their terminals, shows which
one is working, blocked, or idle, restores its layout after a restart, and
resumes the conversations. vmux does the part herdr has no opinion on, which
is making the host reachable from your laptop:

- **Starts a stopped VM**, if you tell it how. Give it a status command and a
  start command and it will bring an auto-terminated cloud VM back before
  attaching. Without them it just waits for the host.
- **Reconnects after sleep.** When the SSH transport drops, vmux waits for the
  host to answer and re-attaches to herdr. Nothing on the host stopped.
- **Warns before certificate-based SSH logins expire**, and stops cleanly
  instead of looping a browser login flow.
- **Opens work with one command.** `vmux -n NAME` creates a herdr workspace
  with Claude already running in it, using the model and flags you configured.

It is one stdlib-only Python file.

## Requirements

On your laptop:

- Python 3.9 or newer. The one that ships with Xcode's command-line tools is
  enough.
- SSH to the host already working: `ssh YOUR-HOST` gets you a shell, whether
  through a plain key or your organisation's SSO flow.

On the host:

- herdr, and Claude Code on the PATH of a login shell.

```sh
brew install herdr               # or: curl -fsSL https://herdr.dev/install.sh | sh
herdr integration install claude
```

The integration adds one hook script under `~/.claude/hooks/` and matching
`SessionStart` entries to Claude Code's settings, so herdr learns each
conversation's id and can `claude --resume` it after a restart. It is not
needed for status detection. `herdr integration uninstall claude` removes it.

## Install

```sh
git clone https://github.com/ashavolian/vmux.git ~/vmux
~/vmux/install.sh
```

The installer symlinks `~/vmux/vmux` into `~/.local/bin`, so a later `git pull`
updates the command in place. It then runs `vmux setup` if you have no config
yet, and tells you if `~/.local/bin` isn't on your PATH.

If you like a shorter command, `alias vmc=vmux` in your shell rc.

## Setup

`vmux setup` asks a handful of questions and writes
`~/.config/vmux/config.json` with owner-only permissions. Enter keeps the
value shown in brackets, `-` clears it. Rerun it any time; existing values
come back as defaults.

1. **Where do your agents run?** The ssh host (an `ssh_config` alias is
   fine), the directory new workspaces should start in, and the command that
   opens herdr there. The directory is expanded on the host, so `$HOME/src`
   works. The herdr command runs through your login shell, so wherever the
   installer put it is fine.
2. **How should `vmux -n` start Claude?** A model to pass as `--model`, or
   blank for Claude's own default, plus any extra flags such as
   `--permission-mode auto`.
3. **Can the machine be stopped and started?** Say yes for a cloud VM. You
   give a local command that prints the VM's state, a regex that means
   running, a regex that means stopped, and the command that starts it. If
   neither regex matches the output, vmux treats the state as unknown and
   waits rather than starting anything.
4. **When ssh authentication fails**, a command to suggest, such as an SSO
   login. vmux prints it; it never runs it.

Finally it offers to test the connection and check that herdr answers on the
host. `vmux config` prints the path and the values in effect.

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
  "herdr_command": "herdr",
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
| `workdir`             | `$HOME`  | Directory for new workspaces, expanded by the shell on the host. |
| `herdr_command`       | `herdr`  | Command that opens herdr on the host, run through your login shell. |
| `claude_model`        | blank    | Passed as `claude --model` by `vmux -n`. Blank lets Claude Code choose. |
| `claude_flags`        | blank    | Appended verbatim to the `claude` command by `vmux -n`. |
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
vmux              attach to herdr on the host
vmux -n NAME      open workspace claude-NAME with Claude running, then attach
vmux -n           the same, with a timestamp name
vmux -n NAME -s   open a workspace with just a shell
vmux -l           list herdr's agents and their states
vmux setup        write or edit the config
vmux config       show the config in effect
```

Inside herdr, `ctrl+b q` detaches and leaves everything running. Running
`vmux` again puts you back. Names are prefixed `claude-` automatically and
become the herdr agent name, lower-cased.

## How it works

- Attaching is `ssh -t HOST herdr`, through your login shell so PATH additions
  made in profile files apply. herdr's own server on the host holds the
  terminals; the ssh session is just a view of it.
- Reconnect is a retry loop keyed on ssh exit status 255 with 2s→30s backoff.
  `ServerAliveInterval=5` / `ServerAliveCountMax=3` is what turns a
  slept-through socket into a prompt 255 instead of a hang.
- Before anything else, vmux probes the host. When the host is down and VM
  handling is configured, it runs the status command, starts the VM if it
  reads as stopped, and re-checks every 60s while waiting. Unknown is treated
  as unknown, never as stopped. It gives up after 12 minutes. A local lock
  file single-flights this across several vmux tabs so they don't all run the
  cloud commands at once.
- `vmux -n` talks to herdr's JSON CLI: `herdr workspace create` for the
  workspace, then `herdr agent start … --kind claude -- <args>` in its root
  pane, which returns once Claude is ready for input. If no herdr server is
  running yet, vmux starts one headless first.
- A stopped cloud VM usually loses its DNS record, so "could not resolve
  hostname" is the cheap first hint that it's down. It isn't proof, so vmux
  checks the VM's state before starting anything.

## Troubleshooting

**"SSH auth is failing."** Your key isn't loaded or your SSH certificate
expired. If you configured a `login_command`, vmux prints it here. Otherwise
make `ssh YOUR-HOST` work on its own, then rerun.

**"ssh login can't complete: address already in use."** Another ssh or vmux is
holding a local port your login flow needs. Find and stop it, then rerun. Put
the commands you use for that in `auth_fatal_hint` so vmux reminds you next
time.

**"herdr isn't on the host's login PATH."** Install it on the host, or set
`herdr_command` to its full path. `vmux setup` offers a connection test that
checks this.

**"herdr server did not start on the host."** Run the herdr command by hand
over ssh once to see its error. First runs show a short onboarding screen.

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
argument line, VM state classification, auth error matching, and the herdr
reply shapes. Nothing in them touches the network.

## Updating

```sh
git -C ~/vmux pull
```

Then restart any vmux tabs you have open.
