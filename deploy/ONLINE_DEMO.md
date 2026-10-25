# Nexora School Office — public online demo (PythonAnywhere, free)

This puts a **demo copy** online so clients can try it from a link, for example
`https://nexoraschool.pythonanywhere.com`.

**What the demo does** (switched on only by the settings in `pythonanywhere_wsgi.py`):

- builds a complete **fictional school, "Nexora Model School"**: 13 classes, 14 teachers, about 160 students,
  fees and receipts since April, salaries, tests with marks, four weeks of attendance, paper fund and fines,
  expenses and three certificates. Every name, phone number and CNIC is made up.
- sign-in page with **one click** as *Principal (owner)*, *Office clerk* or *Exams teacher*.
  Each staff login only sees what the principal allows.
- demo logins have **no password**. Password changes, logins, backups and saving settings are switched off.
- the data is **wiped and rebuilt every 24 hours**.

---

## Steps

### 1. Create the free account
<https://www.pythonanywhere.com> → **Pricing & signup** → **Create a Beginner account**.
Your username becomes your link: `nexoraschool` → `https://nexoraschool.pythonanywhere.com`.

### 2. Upload
**Files** tab → **Upload a file** → `Nexora-School.zip`.

### 3. Install (Bash console)
**Consoles** tab → **Bash**. Paste one line at a time:

```bash
unzip -o Nexora-School.zip
mkvirtualenv --python=python3.11 school
pip install "Django>=5.2,<6.0" "Pillow>=10.0"
cd ~/Nexora-School
SCHOOL_DEMO=1 SCHOOL_DATA_DIR=~/school-demo-data python manage.py reset_demo
```

The last line should end with **"Demo school rebuilt."**

### 4. Create the web app
**Web** tab → **Add a new web app** → Next → **Manual configuration** → **Python 3.11** → Next. Then:

| Section | Setting | Value |
|---|---|---|
| Virtualenv | path | `/home/<username>/.virtualenvs/school` |
| Static files | URL | `/static/` |
| Static files | Directory | `/home/<username>/Nexora-School/static/` |
| Security | Force HTTPS | **Enabled** |

### 5. WSGI file
Click the **WSGI configuration file** link, delete everything, paste `deploy/pythonanywhere_wsgi.py`,
change `USERNAME = "yourusername"` to your username, **Save**.

### 6. Go live
Green **Reload** button → open `https://<username>.pythonanywhere.com`. You should see **"Try the live demo"**.

### 7. Once a month
**Web → "Run until 1 month from today"**, or the free web app goes to sleep.

## If something goes wrong
- Error page: Web tab → **Error log**.
- No styling: check the Static files row (path ends in `Nexora-School/static/`).
- "Bad Request (400)": the username in the WSGI file doesn't match.
