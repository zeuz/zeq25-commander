# ZEQ25 Server & Client

Python 3 emulator/proxy server and command-line client for the **iOptron ZEQ25** telescope mount using the LX200 iOptron protocol over TCP.

```
┌──────────────────────┐        TCP :4000        ┌─────────────────────┐
│  client-zeq25win.py  │ ──────────────────────► │  server-zeq25.py    │
│  (any machine)       │ ◄────────────────────── │  (mount machine)    │
└──────────────────────┘                         └────────┬────────────┘
                                                          │ ASCOM (optional)
                                                          ▼
                                                   iOptron ZEQ25
```

---

## Requirements

```
Python 3.13+
arrow
```

(Windows only):
```
pywin32      # ASCOM support
msvcrt       # built-in on Windows
```

Install dependencies:

```bash
pip install pywin32   # Windows only
```

---

## Configuration — `config.cfg`

Both programs read `config.cfg` from the working directory:

```ini
[server]
port = 4000
host = 0.0.0.0
token_server = my_secret_token

[ascom]
; Enable ASCOM integration (Windows only, requires ASCOM Platform)
enabled = false
; ASCOM device name – leave empty to use the graphical chooser at startup
device =
token_server = secure_and_temporal_password
```

| Key | Description |
|-----|-------------|
| `port` | TCP port the server listens on |
| `host` | Bind address (`0.0.0.0` = all interfaces) |
| `token_server` | Shared secret for authentication. Leave empty to disable auth. |

---

## Server — `server-zeq25.py`

Listens on the configured TCP port, processes LX200 iOptron commands, and optionally forwards them to a real mount via ASCOM.

### Start

```bash
python server-zeq25.py
```

Disable ASCOM (run as emulator only):

```bash
python server-zeq25.py --no-ascom
```

### Startup output

```
=== ZEQ25 Server started – 2024-01-15 22:30:00 -03:00 ===
    Port   : 4000  |  ASCOM : disabled
```

### Interactive menu

While the server is running, single-key commands are available in the terminal:

| Key | Action |
|-----|--------|
| `h` | Show this menu |
| `f` | Set output file name |
| `s` | Save observation list to CSV |
| `l` | List current RA/Dec observation log |
| `a` | Add current RA/Dec to the list |
| `d` | Delete an entry from the list |
| `c` | Clear the observation list |
| `z` | Toggle ASCOM connection |
| `v` | Set N/S/E/W button speed (1–9) |
| `g` | GoTo — enter RA/Dec manually |
| `j` | Go to HOME position |
| `t` | Show current date/time |
| `q` | Quit |

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--no-ascom` | — | Disable ASCOM (enabled by default if `win32com` is available) |

---

## Client — `client-zeq25win.py`

Command-line tool that sends LX200 commands to the server and prints the response.

### Basic usage

```bash
python client-zeq25win.py [options]
```

Without arguments, prints help and the configured server address.

### Connection options

| Argument | Default | Description |
|----------|---------|-------------|
| `--host HOST` | from `config.cfg` | Server host |
| `--port PORT` | `4000` | Server port |
| `--verbose` / `-v` | off | Show raw commands and responses |

### Queries

| Argument | LX200 command | Description |
|----------|---------------|-------------|
| `--get-ra` | `:GR#` | Current Right Ascension |
| `--get-dec` | `:GD#` | Current Declination |
| `--get-alt` | `:GA#` | Current Altitude |
| `--get-azm` | `:GZ#` | Current Azimuth |
| `--get-version` | `:V#` | Firmware version |
| `--get-info` | `:MountInfo#` | Mount type |
| `--get-time` | `:GL#` | Server local time |
| `--get-date` | `:GC#` | Server local date |

### Set coordinates

| Argument | Format | Description |
|----------|--------|-------------|
| `--ra HH:MM:SS` | `HH:MM:SS` or `HHhMMmSS.sss` | Set Right Ascension |
| `--dec [+-]DD:MM:SS` | `[+-]DD:MM:SS` or `[+-]DD°MM'SS.ss"` | Set Declination |
| `--alt [+-]DD:MM:SS` | `[+-]DD:MM:SS` | Set Altitude |
| `--azm DDD:MM:SS` | `DDD:MM:SS` | Set Azimuth |

> Passing `--ra` and `--dec` together automatically triggers a **GOTO**.

### Control

| Argument | Description |
|----------|-------------|
| `--go-home` | Move to HOME position |
| `--vel 1-9` | Set N/S/E/W button slew speed |
| `--track-on` | Start tracking |
| `--track-off` | Stop tracking |
| `--cmd :CMD#` | Send any raw LX200 command |

---

## Examples

```bash
# Get current position
python client-zeq25win.py --get-ra
python client-zeq25win.py --get-dec

# GOTO: set RA + DEC and slew
python client-zeq25win.py --ra 23:22:20 --dec +45:30:00
python client-zeq25win.py --ra 09h04m22.27s --dec "+34°58'46.12\""

# Set RA only (no slew)
python client-zeq25win.py --ra 06:45:08

# Set DEC only (no slew)
python client-zeq25win.py --dec -16:42:58

# Go to HOME
python client-zeq25win.py --go-home

# Set slew speed
python client-zeq25win.py --vel 5

# Start / stop tracking
python client-zeq25win.py --track-on
python client-zeq25win.py --track-off

# Firmware info
python client-zeq25win.py --get-version
python client-zeq25win.py --get-info

# Send a raw LX200 command
python client-zeq25win.py --cmd ":MH#"

# Connect to a remote server
python client-zeq25win.py --host 192.168.1.10 --port 4000 --get-ra

# Verbose mode (shows raw commands and responses)
python client-zeq25win.py --get-ra --verbose
```

---

## Authentication

Set `token_server` in `config.cfg` on **both** the server machine and the client machine to the same string:

```ini
[server]
token_server = my_secret_token
```

- If the token is set, the client prepends it to every command: `my_secret_token|:GR#`
- The server validates the token before processing. Wrong or missing token → connection closed immediately.
- Leave `token_server` empty (or omit it) to run without authentication.

The startup banner shows the auth status:
```
=== ZEQ25 Server started – 2024-01-15 22:30:00 -03:00 ===
    Port   : 4000  |  ASCOM : disabled  |  Auth : enabled
```

---

## ASCOM Integration (Windows only)

Requires [ASCOM Platform](https://ascom-standards.org/) and a compatible telescope driver installed.

Set the device name in `config.cfg`:

```ini
[ascom]
enabled = true
device = ASCOM.Simulator.Telescope
```

Or leave `device` empty to open the graphical device chooser at startup. The ASCOM connection can also be toggled at runtime with the `z` key in the server menu.

---

## License

MIT
