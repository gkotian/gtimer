# gTimer

gTimer is a Python GTK4 desktop app for tracking focused-window time on i3.
The default configuration emphasizes Minecraft play time and also shows system uptime.

## Run from this checkout

```bash
PYTHONPATH=src python -m gtimer
```

## Dependencies on Arch Linux

```bash
sudo pacman -S python-gobject gtk4 python-i3ipc
```

## Tests

```bash
python -m unittest discover -s tests
```
