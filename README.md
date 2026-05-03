# gTimer

gTimer is a Python GTK4 desktop app for tracking focused-window time on i3.
The default configuration emphasizes Minecraft play time and also shows system uptime.

## Run from this checkout

```bash
PYTHONPATH=src python -m gtimer
```

## Admin password and adjustments

Create the admin password hash:

```bash
PYTHONPATH=src python -m gtimer.admin set-password
```

The password hash is stored at:

```text
~/.config/gtimer/admin_password.json
```

Add Minecraft allowance time:

```bash
PYTHONPATH=src python -m gtimer.admin adjust minecraft --minutes 30 --note "Bonus time"
```

Deduct Minecraft allowance time:

```bash
PYTHONPATH=src python -m gtimer.admin adjust minecraft --minutes -5 --note "Correction"
```

Show the exact current Minecraft allowance balance:

```bash
PYTHONPATH=src python -m gtimer.admin balance minecraft
```

The GTK app is read-only; manual allowance changes are only added through this password-protected command.

## Dependencies on Arch Linux

```bash
sudo pacman -S python-gobject gtk4 python-i3ipc
```

## Tests

```bash
python -m unittest discover -s tests
```
