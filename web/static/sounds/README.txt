POMODORO TIMER - AUDIO FILES
=============================

Pro fungování zvukových notifikací přidej tyto soubory:

1. work_end.mp3   - Zvuk po skončení pracovní session (např. gong, bell)
2. break_end.mp3  - Zvuk po skončení pauzy (může být jiný tón)

DOPORUČENÍ:
-----------
- Délka: 1-3 sekundy
- Formát: MP3 (nebo OGG jako fallback)
- Hlasitost: Střední (ne příliš hlasité)

KDE STÁHNOUT ZDARMA:
--------------------
- https://freesound.org/ (hledej "notification", "bell", "chime")
- https://mixkit.co/free-sound-effects/
- https://www.zapsplat.com/

AKTIVACE ZVUKŮ:
---------------
V souboru web/config.json změň:
  "sound_enabled": false  ->  "sound_enabled": true
