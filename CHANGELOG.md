# Changelog

## 3.5.0

### Added
- **Connectivity** diagnostic binary sensor per device. It is `on` while the
  websocket is connected and the HTTP API answers a light probe (`GET /rooms`,
  5 s timeout, every 60 s; `/discovery` on firmware without `/rooms`), and
  turns `off` as soon as either fails. The entity itself stays available, its
  state carries the information. Attributes: `last_probe_ok`,
  `websocket_connected`, `ws_reconnects`. Transitions are logged once
  (WARNING when the device goes offline, INFO when it comes back), not every
  failed probe. No external Ping entry is needed any more to condition an
  automation on the device being reachable.
- **Last backup** diagnostic timestamp sensor, read from the newest `.backup`
  file on disk at startup and after each successful backup, with a
  `backup_count` attribute. Nothing extra is written, neither on the device
  nor on the host.
- **Number of backups to keep** option (1 to 50). Entries without the option
  keep 5 backups as before.

### Changed
- The `espsomfy_rts_enhanced.backup` service (and the Backup button) now fails
  with an error when the backup could not be written, or right away, without
  any request, when the Connectivity sensor is `off`. A failed backup is
  therefore visible in automation traces instead of reporting success.
- Old backups are only rotated after a new one has been written.
- The Backup button no longer turns unavailable when the websocket drops:
  Home Assistant skips unavailable entities in service calls, which made a
  backup of an offline device a silent no-op instead of an error.
