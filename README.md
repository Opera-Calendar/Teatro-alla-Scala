# La Scala Opera Calendar (unofficial)

Automatically publishes two `.ics` feeds from the official Teatro alla Scala season pages:

- `performances.ics`: opera performances, time, conductor and production-level cast information.
- `ticket-sales.ics`: public ticket sale openings with two `VALARM` reminders at 7 and 1 days prior.

## First-time installation

1. Create a **public** GitHub repository with a README (the name can be anything).
2. Unzip the supplied installation package on your Mac.
3. On GitHub open your repository → **Add file** → **Upload files**. Drag the **contents** of the extracted folder into GitHub (NOT the ZIP itself). Preserve `.github/workflows/update.yml` in its subdirectory. On macOS use `Cmd+Shift+.` in Finder to display the hidden `.github` directory. If the browser does not preserve folder structure, use GitHub's **Add file → Create new file** and type `.github/workflows/update.yml` as the filename, then paste the supplied workflow file.
4. Click **Commit changes**.
5. Open **Settings → Pages** and choose **Source: GitHub Actions**.
6. Open **Actions → Update La Scala subscriptions → Run workflow**. Wait for a green tick; a red cross means live source extraction needs repair. The first test is essential and cannot be guaranteed in advance.
7. After a successful run, get your Pages URL under **Settings → Pages**. Subscribe to `<Pages URL>/performances.ics` and `<Pages URL>/ticket-sales.ics` in Apple Calendar using **File → New Calendar Subscription**. Choose iCloud Location if desired, configure auto-refresh and do **not** ignore alerts.

## Important limitations

- **This is an initial implementation, NOT a verified live production feed.** The sample parsing tests pass locally; GitHub must confirm that La Scala's live HTML is compatible. Website structure may change. If extraction fails, this workflow does not overwrite the previously published calendar. Check failed GitHub Actions runs.
- Cast descriptions are currently **production-level**, including published alternate casts; the script does **not** reliably determine a single definitive singer per date. Check individual production pages before making travel decisions.
- Opera calendar end times are a clearly marked **3-hour placeholder**, not the official end time.
- Public ticket opening times are Europe/Rome; they are encoded in UTC in ICS for correct timezone conversion. Sales only come from the official ticket-sale table, never guessed.
- An alarm in a subscribed calendar may or may not fire depending on Apple Calendar and device settings: **test alerts before relying on them**. Keep other existing ticket reminders until confirmed.
- The workflow runs daily, subject to GitHub's scheduler delays and its **60-day inactivity suspension** policy for public repositories. Check workflow runs periodically.
- This repository and Pages files are public. No personal information is needed.

## Sources

- Season: https://www.teatroallascala.org/en/season/2026-2027/index.html
- Public ticket sales: https://www.teatroallascala.org/it/stagione/biglietteria/biglietti/calendario-apertura-vendite.html

This is an independent personal calendar generator and is not endorsed by Teatro alla Scala.
