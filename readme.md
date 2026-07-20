# MKOV Visa CRM

Internal staff CRM for Uniglobe MKOV Travel — visa applications, client records, document vault, invoicing, leads, and team communication. Staff-only, not client-facing.

**Live app:** `https://visa-and-crm-system.onrender.com/admin`
**API docs (Swagger):** `https://visa-and-crm-system.onrender.com/docs`

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Tech Stack](#tech-stack)
3. [How to Use the Software](#how-to-use-the-software)
4. [Troubleshooting / How to Fix Bugs](#troubleshooting--how-to-fix-bugs)
5. [Environment Variables](#environment-variables)
6. [Deploying Changes](#deploying-changes)
7. [Database Notes](#database-notes)

---

## Quick Start

1. Go to `https://visa-and-crm-system.onrender.com/admin`
2. Log in with your staff email + password (ask your Super Admin if you don't have one)
3. Install it as an app on your phone: Android gets an "Install App" button in the top bar; iPhone — open in Safari → Share → Add to Home Screen

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python + FastAPI |
| Database | Turso (cloud SQLite, via the `libsql` package) |
| Frontend | Single-file HTML/CSS/JS (`static/admin.html`) — no framework |
| Hosting | Render (free tier) |
| Auth | JWT tokens, bcrypt password hashing |
| OCR | pytesseract (passport scanning) |
| PDF generation | reportlab (checklists, letters) |
| Email | Gmail SMTP |
| WhatsApp/SMS | Meta WhatsApp API / Twilio |
| PWA | Installable on iOS/Android via manifest + service worker |

**Key files:**
```
main.py           → all API routes (~120 endpoints)
auth.py           → login, JWT, role permissions
database.py       → Turso connection + all table schemas
notifier.py       → WhatsApp/SMS/Email sending logic
static/admin.html → the entire frontend (one file, no build step)
static/manifest.json, static/sw.js → PWA install support
requirements.txt  → Python dependencies
```

---

## How to Use the Software

### Roles
| Role | Access |
|---|---|
| **Super Admin** | Everything, including staff management, staff monitoring, direct messages |
| **Sales Admin** | Everything Sales does + manage sales team |
| **Visa Admin** | Everything Visa Staff does + manage visa team |
| **Sales** | Leads, follow-ups, clients, messaging, packages |
| **Visa Staff** | Applications, documents, checklists, invoices, letters |

### Core workflows

**Adding a new client + application**
Dashboard → New Application → enter client email (if new, also fill name/phone) → destination + visa type → Create. This auto-creates the client if they don't exist and generates the correct document upload slots.

**Converting a lead**
Leads page → open a lead → mark **Won** → Convert to Client. This automatically creates the client, creates the application, attaches the matching VFS checklist for that country/visa type, and creates empty document slots — no retyping data three times.

**Uploading documents (Document Vault)**
Client Profile → Document Vault → Upload Document → pick type. Uploading a **passport** automatically runs OCR and tries to fill in Passport Number, DOB, and Expiry Date — review and confirm before saving.

**Invoices — government fee vs. service fee**
When creating an invoice, add line items under **Government/Embassy Fees** separately from **Agency Service Fees**. If a client cancels, use "Cancel Invoice" — you choose whether to keep the service fee while marking the government fee as lost.

**Letter Templates**
Letter Templates page → pick a client + template (cover letter, authority letter, invitation letter, performa) → Generate. Fields auto-fill from the client's profile and OCR-extracted passport data. Download as PDF or copy the text.

**Calendar & reminders**
Add an event (embassy appointment, deadline, etc.) with a reminder lead time. You'll get an email at that time, and a popup next time anyone loads the app (until each staff member individually dismisses it).

**Team Chat**
One shared channel for all staff. The system also **auto-posts here** if an application has been stuck in the same status for 4+ days — tagging the assigned staff member to flag it's stalling.

**Staff Monitor** (Super Admin only)
See who's online, their recent activity, and message/ping any staff member directly.

**Export CRM**
Download applications, clients, invoices, or hotel/package manifests as CSV/PDF for Excel or embassy/ground-handler paperwork.

---

## Troubleshooting / How to Fix Bugs

### The app won't load at all / blank page

1. Check Render → your service → **Logs**. Look for the last error before the crash.
2. Common cause: a missing environment variable. Check the [Environment Variables](#environment-variables) section below — `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` are required or the app won't start.
3. If logs show `AttributeError: ... no attribute 'row_factory'` — this was a known libsql compatibility issue and is already fixed in `database.py` (the `DictRow`/`_ConnWrapper` classes). If you see this again, someone likely reverted that fix — restore it from git history.

### "HTTP 404" or generic "Error" toast when clicking a button

Since a fix applied to `admin.html`'s `api()` helper, every error toast should show the *actual* backend reason (e.g. "Client not found") instead of a bare status code. If you see a generic error:
1. Open browser DevTools (F12) → Network tab → click the failed request → check the Response tab for the real error message
2. Open `https://visa-and-crm-system.onrender.com/docs`, find the matching endpoint, click "Try it out," and reproduce the exact call to see the full error

### A button does nothing when clicked

This has happened before due to **duplicate JavaScript function declarations** — if the same `function xyz()` is defined twice in `admin.html`, JavaScript silently uses the *last* one, and if that later copy references something from before it's loaded (hoisting order), it can crash silently or recurse infinitely.

**How to check:**
```bash
python3 -c "
import re
html = open('static/admin.html').read()
m = re.search(r'<script>(.*)</script>', html, re.DOTALL)
js = m.group(1)
open('/tmp/extracted.js', 'w').write(js)
"
node --check /tmp/extracted.js
grep -oP '^(async )?function \w+' /tmp/extracted.js | sort | uniq -c | sort -rn | head -10
```
If `node --check` reports a syntax error, it'll tell you the exact line. If the `uniq -c` list shows any count above 1, that function name is declared more than once — search for it and delete the older/dead copy.

### Nav tabs / sidebar links don't open anything

This exact bug happened once: a wrapper function was added around `nav()` using `const _orig = nav; function nav() { _orig(); ... }`. Because JavaScript hoists `function` declarations before running any code, `_orig` ended up pointing at itself, causing infinite recursion and a silent crash. **Never wrap `nav()` this way** — if you need to run extra code on every navigation, add it directly inside the single `nav()` function body instead.

### Service worker / PWA install warning in console

If you see `Failed to register a ServiceWorker ... 404` — this is expected and harmless if you're previewing `admin.html` outside of the real deployed app (e.g. in a design/preview tool). The service worker only exists at `/sw.js` on your actual Render domain. It will register correctly once visited at your real `https://visa-and-crm-system.onrender.com/admin` URL. If it still fails there, confirm `static/sw.js` exists in the repo and that `main.py` still has the `/sw.js` and `/manifest.json` routes.

### Passport OCR isn't extracting anything

- Confirm `pytesseract`, `Pillow`, and `PyMuPDF` are in `requirements.txt` and installed on Render
- Confirm the Render build installed the `tesseract-ocr` system package (check your `render.yaml` or build command — this is a system-level dependency, not just `pip install`)
- OCR accuracy depends heavily on scan quality — blurry or angled photos often fail to extract fields; a flat, well-lit scan works best

### WhatsApp / SMS / Email not sending

Check these environment variables are set on Render: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` (email), `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID` (WhatsApp), `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` (SMS). Missing credentials fail silently in the background — check `notifier.py`'s logs on Render for the actual send error.

### Database looks empty / data disappeared after a deploy

If you're still on local SQLite (not Turso), Render's free tier wipes the filesystem on every redeploy — this is expected behavior, not a bug. The fix is already in place: `database.py` uses Turso (cloud database), which persists across redeploys. Confirm `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` are set — if they're missing, the app would fail to start entirely (see the first section above), not silently fall back to a local file.

### Superadmin password isn't saving / keeps resetting

The superadmin account is created once via `INSERT OR IGNORE` in `database.py` — it will never be overwritten by a redeploy once it exists. If you truly need to reset it, you must do so directly in the Turso database (via `turso db shell` or the Turso web console), not by changing the `SUPERADMIN_PASS` environment variable — that variable is only read the very first time the table is created.

### General debugging checklist

1. **Check Render logs first** — most errors show a full Python traceback there
2. **Check the browser console (F12)** for JavaScript errors
3. **Use `/docs`** to isolate whether a bug is backend (API returns wrong data/error) or frontend (API works fine in Swagger but the button doesn't call it correctly)
4. **Validate syntax before pushing changes:**
   ```bash
   python3 -c "import ast; ast.parse(open('main.py').read())"
   node --check /tmp/extracted.js   # after extracting JS as shown above
   ```

---

## Environment Variables

Set these in Render → your service → **Environment**:

| Variable | Required | Purpose |
|---|---|---|
| `TURSO_DATABASE_URL` | Yes | Cloud database connection |
| `TURSO_AUTH_TOKEN` | Yes | Cloud database auth |
| `SECRET_KEY` | Yes | JWT signing — any long random string |
| `SUPERADMIN_EMAIL` | First deploy only | Initial admin login |
| `SUPERADMIN_PASS` | First deploy only | Initial admin password |
| `SUPERADMIN_NAME` | First deploy only | Initial admin display name |
| `GMAIL_ADDRESS` | For email | Sending address |
| `GMAIL_APP_PASSWORD` | For email | 16-character Gmail app password |
| `WHATSAPP_TOKEN` | For WhatsApp | Meta API token |
| `WHATSAPP_PHONE_ID` | For WhatsApp | Meta phone number ID |
| `TWILIO_ACCOUNT_SID` | For SMS | Twilio account |
| `TWILIO_AUTH_TOKEN` | For SMS | Twilio auth |
| `TWILIO_PHONE_NUMBER` | For SMS | Sending number |

---

## Deploying Changes

```bash
git add <changed files>
git commit -m "describe the change"
git push
```

Render auto-redeploys on every push to `main`. Watch the **Logs** tab during deploy — if it fails, the error will be at the bottom of the build/deploy log.

**Before pushing**, always validate:
```bash
python3 -c "import ast; ast.parse(open('main.py').read())"
python3 -c "import ast; ast.parse(open('database.py').read())"
```

---

## Database Notes

- All tables are created automatically by `init_db()` in `database.py` on every startup (`CREATE TABLE IF NOT EXISTS`) — safe to redeploy, nothing gets dropped
- To add a new table or column, edit the `CREATE TABLE` statements in `database.py` and redeploy — existing data is untouched, only new tables/columns are added
- To inspect or manually query the database: `turso db shell <your-db-name>` from the Turso CLI, or use the Turso web dashboard
- Full API reference for every table's fields is visible at `/docs` — expand any endpoint to see its request/response schema
