# delonghi-comfort

Async Python client for **De'Longhi "My Comfort Hub"** (Daedalus platform) connected
heaters — e.g. the **Dragon 5 Connect** (`TRD51024WIFI.G`).

It authenticates with Gigya, discovers your appliances, reads live state from the AWS IoT
device shadow, and sends control commands over MQTT. It is transport-friendly for Home
Assistant: bring your own `aiohttp` session and the library stays framework-agnostic.

> ⚠️ Unofficial. Built by reverse-engineering the public app for interoperability with
> hardware you own. Not affiliated with or endorsed by De'Longhi. API keys shipped here are
> app-global public client identifiers (like OAuth client IDs), not user secrets.

## Installation

```bash
pip install delonghi-comfort
```

## Usage

```python
import asyncio
import aiohttp
from delonghi_comfort import DelonghiComfort


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        client = DelonghiComfort(session=session)
        await client.async_login("you@example.com", "password")

        devices = await client.async_get_devices()
        heater = devices[0]
        print(heater.thing_name, heater.model, heater.online)

        await client.async_connect(heater)

        status = await client.async_get_status()
        print("on:", status.is_on, "room:", status.current_temperature,
              "target:", status.target_temperature)

        # live push updates
        client.add_status_listener(lambda s: print("update:", s.raw))

        # control
        await client.async_set_power(True)
        await client.async_set_temperature(21)
        await client.async_set_eco(True)

        await client.async_close()


asyncio.run(main())
```

### Persisting credentials

`async_login` stores a long-lived Gigya session in `client.credentials`. Persist it and
reconstruct the client without a password later:

```python
client = DelonghiComfort(session=session, credentials=saved_credentials)
await client.async_refresh_jwt()      # mint a fresh JWT from the stored session
```

## Command reference

| Method | Message | Reported field |
|---|---|---|
| `async_set_power(bool)` | `SetDeviceStatusRequest` | `DeviceStatus` |
| `async_set_temperature(int)` | `SetRoomTempRequest_degC` | `TempSetPoint` |
| `async_set_eco(bool)` | `SetEcoModeRequest` | `PowerLimit` |
| `async_set_child_lock(bool)` | `SetLockModeRequest` | `KeyLock` |
| `async_set_night_mode(bool)` | `SetNightModeRequest` | `NightModeEnable` |
| `async_set_silent(bool)` | `SetSoundRequest` | `SilentEnable` |
| `async_set_brightness(0-3)` | `SetBrightnessLevelRequest` | `BrightnessLevel` |
| `async_set_schedule_enabled(bool)` | `SetScheduleEnRequest` | `ScheduleEnable` |
| `async_set_temp_unit(bool)` | `SetTempUnitRequest` | `TempUnit` |

Read-only status telemetry (no control command exists): `power_level`, `on_off_timer_minutes`,
`timer_remaining`, `timer_active`, `ota_progress`, `running_partition`.

## How it works

- **Auth**: Gigya `accounts.login` → `accounts.getJWT` (OAuth1-signed), auto-probing pools.
- **Devices**: `GET devices` on the AWS API Gateway, authorized by the JWT as a Bearer token.
- **Read**: subscribe + `get` the `MachineStatus` / `MachineCapabilities` named shadows over
  MQTT 5 (TLS:443, ALPN `mqtt`, JWT custom authorizer). A unique client-id is used so the
  physical heater is never evicted.
- **Control**: publish `{"Message": "...", "AppId": "Comfort", "Value": N, "RequestId": "..."}`
  to `<thing>/commands/request` and await the ack on `<thing>/commands/response`.

## Development

```bash
uv sync
uv run pytest
uv run ruff check
uv run mypy delonghi_comfort
```

## License

GPL-3.0-or-later.
