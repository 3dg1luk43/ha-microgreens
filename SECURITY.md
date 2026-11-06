# Security Policy

## Report a vulnerability

**Do not open a public issue.** Report it privately through
[GitHub Security Advisories](https://github.com/3dg1luk43/ha-microgreens/security/advisories/new)
("Report a vulnerability"). There is no security e-mail address.

Include:

- what the problem is and what an attacker could do with it
- steps to reproduce
- affected versions (release tags, e.g. `v0.2.0`)
- a suggested fix, if you have one, and whether you want to be credited

What to expect: an acknowledgement within a few days, and a fix in a new release (critical issues
first). The advisory is published once the fix is out, and reporters are credited unless they ask not
to be. Please do not disclose the issue publicly before the fix is released.

## Supported versions

| Version | Security fixes |
| :--- | :--- |
| `0.2.x` (latest release) | Yes |
| `0.1.x` and older | No |

## What Microgreens sends and stores

- **Local only.** No telemetry, no online services, no third-party Python dependencies.
- **Stored data** (plots, crops, trays, history) lives in your Home Assistant config folder
  (`.storage/ha_microgreens`), unencrypted, protected by the file system. It is part of Home Assistant
  backups. A backup export from the panel is downloaded by your browser.
- **Notifications** go wherever your chosen notify service sends them (for example a phone push through a
  cloud service). They contain plot and crop names. Without notify targets nothing leaves Home Assistant.

## Access control

Every panel command is checked on the server, not only hidden in the UI.

- Administrator only: crops, plots, settings, test and digest sends, backup export and import,
  deleting a history entry.
- Any signed-in user: reading the garden, the everyday tray actions (sow, water, uncover, harvest,
  discard, shift), editing a tray and editing or reopening a history entry.
- Services follow Home Assistant's own rules: anyone who can call services can call these.
