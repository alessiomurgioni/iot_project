# DHome — Multi-tenant Domotic Digital-Twin Platform

A Flask + MongoDB platform where users sign in, add DHome devices (each a
Digital Twin), and monitor/control house temperature — turning the AC on/off or
letting it run automatically against a threshold. Built on the
`InternetOfThings_Architecture_Database_lecture` Digital-Twin framework.

## How it maps onto the reference architecture

```
config/                         Mongo config (database.yaml) + ConfigLoader  [reference]
  settings.py                   app knobs: secret, port, schema path, weather  [added]
src/
  virtualization/
    digital_replica/
      schema_registry.py        YAML -> Mongo $jsonSchema                     [reference]
      dr_factory.py             Pydantic-based DR builder                     [reference]
    templates/house_schema.yaml the house Digital Replica schema              [added]
  services/
    base.py                     BaseService ABC                              [reference]
    database_service.py         Mongo gateway: DR/DT + users/devices/memberships  [reference + extended]
    climate_control.py          ClimateControlService (control + telemetry)  [added]
    monitoring.py               MonitoringService (read-only summary)         [added]
  digital_twin/
    core.py                     DigitalTwin                                  [reference]
    dt_factory.py               DTFactory: registry CRUD, persist_dr          [reference]
    DHome/
      DHome_dt_factory.py       DHomeDTFactory(DTFactory): service mapping,
                                 create_twin_for_device, is_online            [added]
  application/
    base.py                     BaseApplication ABC                         [reference]
    api.py                      twin/device JSON API + generic dt/dr + register_api_blueprints  [reference + extended]
    auth.py                     login/signup, decorators, secret verification [added]
    web.py                      home, claim, dashboard, owner management pages [added]
    climate.py                  per-house outdoor-temperature poller          [added]
app.py                          FlaskServer bootstrap                        [reference + extended]
templates/ static/             Jinja pages + CSS/JS
firmware/                       NodeMCU (sensors/WiFi) + Arduino (actuators)
scripts/                        provisioning + migration CLIs
```

The multi-tenant model lives in three collections, all behind `DatabaseService`:
`users` (accounts), `devices` (provisioned units: hashed token + owner key,
`claimed_by_dt`), and `memberships` (the `(user, twin)` join carrying `role` and
`can_control`). Permissions live on the membership, so both "my devices" and
"this device's users" are cheap indexed lookups.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# Start MongoDB locally (config/database.yaml -> localhost:27017, db "domotic_db")
```

## Provision a device (factory step, once per unit)

```bash
python -m scripts.provision_device dhome-001 tok-secret-001 owner-key-001
```

Stores only hashes. Put `dhome-001` / `tok-secret-001` into
`firmware/nodemcu_webapp/nodemcu_webapp.ino` (`DEVICE_ID` / `DEVICE_TOKEN`).

## Run

```bash
python app.py         # serves on 0.0.0.0:8000
```

## Flows

1. **Sign up / log in** — accounts are independent of devices.
2. **Add a device** (home page) — enter `device_id` + `device_token`. Add the
   `owner_key` too to become an **owner** (management tab); omit it to join as a
   plain **member** (dashboard only). The first claim provisions the twin +
   house Digital Replica; later claims join the same twin.
3. **Open a device** — the dashboard shows indoor/outdoor temperature, occupancy,
   and fire status, and lets you set AC mode (Auto/Cool/Heat/Off), the auto
   threshold, and windows. Login already happened — no per-device sign-in.
4. **Manage (owners)** — revoke a member's control (`can_control=false` →
   view-only for that device) or remove them (membership deleted → no access;
   their account and other devices are untouched).

## API

Twin-scoped (member-gated): `GET /api/twins/<dt_id>/state`,
`POST /api/twins/<dt_id>/control`, `GET /api/twins/<dt_id>/monitoring`.
Device-facing (`device_id` + `token`): `GET|POST /api/report`, `GET /api/command`,
`GET /api/outdoor-temp`. Reference generic: `GET /api/dt/<id>`,
`GET /api/dr/<type>/<id>`.

Telemetry auth resolves the device row by its public `device_id` (O(1)) and does
a single hash comparison against that device's stored token hash — it never
scans devices.

## Migrating an existing single-house deployment

```bash
python -m scripts.migrate_to_multitenant \
  --device-id dhome-001 --device-token node-secret-123 \
  --owner-key YOUR_OWNER_KEY --owner-username alice
```

## Security notes

- Enable `SESSION_COOKIE_SECURE` in `app.py` once served over HTTPS (the owner
  key travels over the add-device form).
- Every `/twins/<dt_id>/...` route is guarded by membership (`twin_member_required`)
  or owner role (`twin_owner_required`) — the `dt_id` is user-controlled, so this
  is the IDOR defense.
