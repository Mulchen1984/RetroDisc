# RetroDisc — All-in-One Media Suite

## App herunterladen (fertige Builds)

Nach dem Push zu GitHub automatisch verfügbar:
- **Actions** → letzter Build → **Artifacts** → RetroDisc-Windows / RetroDisc-macOS

Oder nach `git tag v1.0.0 && git push origin v1.0.0` unter **Releases**.

## Zu GitHub pushen → Build startet automatisch

```bash
git init
git add .
git commit -m "RetroDisc initial"
git remote add origin https://github.com/DEIN-NAME/retrodisc.git
git push -u origin main
```

→ GitHub baut in ~15 Min: RetroDisc.exe + RetroDisc.dmg
