# Commands that open a Mac system dialog

On the Mac, a command that can open a system dialog for a password, keychain item, certificate, or Touch ID takes the keyboard focus until someone answers it. With nobody at the Mac, the dialog stays open, and after the Mac sleeps the keyboard and Finder stop working until a forced shutdown. Such commands include `docker pull`, `push` or `login` against a private registry, `security`, `codesign`, credential helpers that read the keychain, `ssh-add` with the keychain, and `sudo` without `-n`. Before running one, get the credential without a dialog first (for Azure Container Registry, `scripts/az.sh acr login --name <registry>` in moldplan-center), or leave the step for the user; when a command hangs on such a dialog, say so in your report at once.

On 2026-11-13 an unattended `docker pull` from a private registry asked the keychain for its credentials at 05:53, and the Mac needed a forced shutdown in the morning.
