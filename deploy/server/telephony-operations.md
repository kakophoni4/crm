# PBX synchronization after a server migration

The API creates operator extensions in the CRM database. Asterisk must receive
those extensions and their passwords before browser calls can authenticate.
An active Asterisk container and a registered Bitcall trunk do not prove that
operator extensions are synchronized.

When running the separate `crm-asterisk` container without `crm-telephony-sync`,
install the host scheduler from the production checkout:

```sh
bash scripts/deploy/vps/install-telephony-sync-timer.sh
systemctl status crm-telephony-sync.timer
systemctl show crm-telephony-sync.service -p Result -p ExecMainStatus
journalctl -u crm-telephony-sync.service -n 20
docker exec crm-asterisk asterisk -rx 'pjsip show endpoints'
docker exec crm-asterisk asterisk -rx 'pjsip show registrations'
```

The oneshot service runs five seconds after its previous run finishes. It uses
the existing private deployment environment, synchronizes generated files only
when they change, and reloads PJSIP and the dialplan. The timer persists across
reboots. Reinstall it after relocating the checkout or migrating hosts.

Run one scheduler. The installer refuses to add a timer if the sync container
is running and disables the dedicated legacy cron file. If switching back to
the compose sync container, first disable the host timer:

```sh
systemctl disable --now crm-telephony-sync.timer
```

Generated PBX configuration contains passwords. Keep generated production files,
environment files, backups and diagnostic credentials out of Git. A signaling
health probe should use authenticated SIP OPTIONS, not an external call. TURN
checks should allocate and release a temporary relay with the application's
actual credentials; a STUN Binding reply alone does not validate TURN access.
