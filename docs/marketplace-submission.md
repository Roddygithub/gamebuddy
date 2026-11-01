### Repository URL

https://github.com/Roddygithub/gamebuddy

### Category

Productivity

### Tags

ai, games, bar

### Suggest a missing tag

_No response_

### Maintainer notes

GameBuddy is a native Quattro bar-widget controlling a separate Python voice/AI gaming companion. The bar uses its own monochrome Buddy SVG, follows shell colors and supports engine startup, overlay visibility, AI settings and game-window selection. The preview contains only project-owned UI and demo text.

Manual setup is required: adding the plugin does not install the engine or run scripts automatically. The README documents Python/Qt/PortAudio dependencies, optional AI/voice engines, and the user-run installer. Only missing OS packages use the distro package manager with sudo. The installer creates a user venv, desktop entry, symbolic icon, compositor bindings and systemd user units; it enables a daily notification-only update check but not widget autostart. Modified compositor files are backed up. Full uninstall removes owned includes and retains user configuration and conversations; removing only the bar plugin leaves the standalone engine intact.

The engine uses the configured user's AI account or local provider. Game screenshots are attached when the user asks with vision enabled, or during explicitly enabled coach mode; microphone capture is user-controlled. There is no project telemetry service. No credentials are stored in shell.json. The bar polls local status every five seconds and starts no additional Quickshell process.

### Submission checklist

- [ ] The repository is public and contains installation and removal instructions.
- [ ] I have documented the plugin license and any external dependencies.
- [ ] I confirm that I own or have permission to submit this plugin and its preview assets.
- [ ] The plugin does not overwrite user configuration without explicit consent.
- [ ] I understand that approval is for listing and is not a security review.
