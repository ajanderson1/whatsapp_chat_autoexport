# Wireless ADB

Connect to your Android device over Wi-Fi instead of USB.

## Setup

1. On your Android device: **Settings > Developer Options > Wireless debugging**
2. Enable "Wireless debugging"
3. Tap **"Pair device with pairing code"**
4. Note the **pairing IP:PORT** (e.g., `192.168.1.100:37453`) and **6-digit code**

!!! tip
    Use the **pairing port** shown in the "Pair device" dialog, **not** port 5555.

## Usage

### Interactive (TUI prompts for details)

```bash
poetry run whatsapp --wireless-adb
```

### With address (prompts for pairing code)

```bash
poetry run whatsapp --wireless-adb 192.168.1.100:37453
```

### Fully non-interactive

```bash
poetry run whatsapp --headless --output ~/exports --auto-select \
  --wireless-adb 192.168.1.100:37453
```

## Common Issues

| Issue | Solution |
|-------|----------|
| Pairing code expired | Get a fresh code (they expire in minutes) |
| Connection refused | Ensure device and computer are on the same Wi-Fi |
| Wrong port | Use the **pairing port**, not 5555 |
| Pairing fails | Keep the wireless debugging screen open during pairing |
| IP changed | Device may get a new IP after Wi-Fi reconnect |
