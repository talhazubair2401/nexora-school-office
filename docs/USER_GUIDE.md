# Nexora School Office

**Offline school office system for Windows — by Nexora Software & Web Solutions.**

Fees and receipts, challans, paper fund and fines, attendance, tests and result cards,
certificates on the school letterhead (with Urdu), salaries, expenses and profit — for a
school's own office computer. It needs no internet after setup and keeps every record in one
SQLite file.

> **Live demo:** a public copy runs with a fictional school, *Nexora Model School*, and one-click
> sign-in as the principal or office staff. See [`deploy/ONLINE_DEMO.md`](../deploy/ONLINE_DEMO.md).
> All names, numbers and records in the demo are made up.

## Install (once)
1. Python 3.10 or newer must be installed (python.org, tick **"Add python.exe to PATH"**).
2. Double-click **`setup.bat`**. It installs what's needed, creates the database, adds the 13 classes
   (Play Group … Class 10) and puts a **Nexora School Office** icon on the desktop.
3. Double-click the desktop icon. The first time it asks you to **choose the admin password**.
4. Open **Settings** to put in your school's name (English and Urdu), address, phone and logo,
   and upload your own letterhead for certificates.

## Daily use
- **Open:** double-click **Nexora School Office** on the desktop. It opens in its own window.
- **Lock:** press **Lock (log out)** at the bottom of the menu. Closing the window also logs you out.
- **Stop completely:** `stop_school.bat` (not needed normally; it stops when the PC shuts down).

## What it does
| Area | What you can do |
|---|---|
| Students | Admit (automatic number like NMS-2026-0001), edit any detail, set each student's own fee and discount, mark as left (history kept), print the student record, download the list for Excel |
| Classes | Play Group … Class 10, each with its own colour, usual fee, class teacher and subjects you write yourself |
| Fees | Create a month's fees for everyone in one click, mark paid in full or receive part payments, change or discount any month, print receipts (PAID stamp), fee challans with all unpaid months, and the unpaid list |
| Teachers | Staff records, fixed monthly salary, monthly salary sheet, mark paid, salary slips with a PAID stamp |
| Tests | Monthly tests and 1st/2nd/3rd term exams per class, your own subjects and full marks, marks sheet, percentage, grade, position, remarks, printed result cards and class result sheet |
| Profit | Month by month for the school year (April–March): fees received − salaries paid, with a chart and printout |
| Settings | School name, address, phone, logo, pass percentage, grade scale, fee last date, password |

**Sending on WhatsApp:** open any printout, press **Print / Save as PDF**, choose **Save as PDF**, then attach the PDF in WhatsApp.

## Added in October 2026
- **Search**: results appear while typing, A to Z, click a column heading to re-sort. Student-name matches first (from the start of a word), father's-name matches listed separately. Typing only numbers searches admission no. and phone. "Search in" chooses one field. The search bar at the top shows suggestions while you type.
- **Back** button and a path line (Classes › Play Group › student) on every page; ‹ › arrows (or the ← → keys) move between students of the same class.
- **Classes → Promote to next class**: moves every class up for the new school year, Class 10 becomes "Passed out", untick anyone who stays back. Each student's Class history keeps the old class; the last promotion can be undone.
- **Settings → Backup**: saves a dated copy of the records (and photos) to a folder or USB stick you choose. Settings also has **Button and text size**.
- **Class page → Print class list** (names, father's names, phones, fees, dues).
- **Daily collection**: money received each day with totals; printable.
- **Other expenses** (rent, bills…), counted on the Profit page only when you switch it on.
- **"Are you sure?"** before *Paid in full*.
- **Recent activity**: everything done in the system, newest first.
- **Certificates**: School Leaving, Character, Date of Birth, Matric Passing (students); Experience, Relieving, Appreciation (teachers). They print on the school letterhead. Live preview before issuing: change the details in the boxes, or click on the certificate and type to change the wording (bold/italic/underline, undo, "Back to standard wording"). Issued certificates keep their serial number and can be changed later with "Change the text". Signed "Principal" only. A different letterhead picture can be uploaded in Settings.
- Urdu text everywhere uses **Jameel Noori Nastaleeq** (included in static/fonts).
- The school logo is printed faintly behind every printout.

## Safety of your records
Everything is saved in `db.sqlite3` in this folder (photos in `media`). Use **Settings → Backup** to save a
dated copy to a USB stick; the system reminds the owner when a week has passed without one.

## For a technical helper
Python + Django 5.2, SQLite, Bootstrap 5, Chart.js (all included offline). Runs at `http://127.0.0.1:8765`.
Tests: `venv\Scripts\python manage.py test office`.

Settings can be changed with environment variables: `SCHOOL_DATA_DIR` (where the database and photos are kept),
`SCHOOL_ADMISSION_PREFIX` (default `NMS`, giving admission numbers like NMS-2026-0001). The online demo mode
(`SCHOOL_DEMO=1`) is only for the public portfolio copy and is never used on an office computer.

## October 2026 update: two logins and attendance
- **Two logins.** The principal (owner) logs in with the admin password as before. Office staff get their own login: the owner adds them under **Logins** and switches on what each one may do (fees, attendance, admissions, tests, certificates).
- **Always owner only:** changing a fee or discount, deleting or cancelling anything, salaries, profit, expenses, settings, backups, logins and the activity log. If staff try, it is blocked and written in Recent activity.
- **Who did what:** Recent activity and Daily collection show who received each payment and who made each change. Daily collection has a **cash check** to compare the cash in the drawer with the receipts.
- **Attendance:** students (Present / Absent / Leave) and teachers (also Late), with monthly registers you can print. The student page shows their attendance.
- **New login screen** with the Owner / Office staff swap. **Backspace** goes back one screen when you are not typing in a box.
- **Paper fund & fines** (under Money): paper fund, late fee fine, absence fine or other fine, for one student or a whole class. Each one is either added to a month's fee (on the same challan and receipt) or kept separate with its own slip and receipt. Only the owner adds or removes them; staff with fee access can receive them.
- **Forgot the owner password?** A technical helper can set a new one: open the folder, then run `venv\Scripts\python manage.py changepassword admin`.
