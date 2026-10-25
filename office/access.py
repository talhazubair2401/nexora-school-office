"""
Who may do what.

    Owner (the principal, user "admin")  - everything.
    Office staff                         - only the parts the owner switches on for them.

Some things always stay with the owner, whatever is switched on: changing a fee or a discount,
deleting or cancelling anything, salaries, profit, expenses, settings, backups, logins and the
activity log. That way nobody can lower a fee or remove a receipt to hide money.
"""
import threading

OWNER_USERNAME = "admin"

# The switches the owner can turn on for each office staff login.
PERMISSIONS = [
    ("fees", "Receive fees and print receipts",
     "Take payments, print receipts, challans and the unpaid list. Cannot change any amount due."),
    ("attendance", "Mark student and teacher attendance", "Daily attendance and the monthly registers."),
    ("students", "Admit students and edit their details",
     "New admissions and contact details. The fee and discount stay with the owner."),
    ("tests", "Tests and results", "Make tests, type marks and print result cards."),
    ("certificates", "Certificates", "Issue and print certificates and letters."),
]
PERMISSION_KEYS = [p[0] for p in PERMISSIONS]

# Pages anyone who is logged in may open.
OPEN_TO_ALL = {
    "dashboard", "login", "first_time", "logout", "change_password",
    "student_list", "student_detail", "student_suggest", "class_list", "class_detail", "class_print_list",
}

# Pages that need one of the switches above. Every other page is for the owner only.
NEEDS = {
    "fees": {"fee_month", "fee_generate", "payment_add", "fee_mark_paid", "receipt", "class_challans",
             "unpaid_list", "daily_collection", "challan",
             "charge_list", "charge_receive", "charge_receipt", "charge_slips"},
    "attendance": {"attendance_home", "attendance_mark", "attendance_register", "teacher_attendance",
                   "teacher_attendance_month"},
    "students": {"student_create", "student_update", "student_leave", "student_restore", "student_print"},
    "tests": {"test_list", "test_create", "test_detail", "test_edit", "marks_entry", "result_sheet", "result_cards"},
    "certificates": {"certificate_list", "certificate_new", "certificate_preview", "certificate_print",
                     "certificate_edit"},
}
URL_PERMISSION = {name: perm for perm, names in NEEDS.items() for name in names}

# Plain-language names for the "only the owner can do this" page and the activity log.
OWNER_ONLY_LABELS = {
    "fee_edit": "change a fee or discount", "fee_delete": "remove a month's fee",
    "fee_add_for_student": "add a fee month with a new amount", "payment_delete": "delete a payment",
    "student_delete": "delete a student", "student_export": "download all student records",
    "class_update": "change a class (fee, teacher, colour)", "class_apply_fee": "change the fee for a whole class",
    "class_delete": "delete a class", "class_create": "add a class", "promote": "promote classes",
    "promote_undo": "undo a promotion", "salary_month": "see salaries", "salary_edit": "change a salary",
    "salary_generate": "create salaries", "salary_mark_paid": "pay a salary", "salary_slip": "see a salary slip",
    "teacher_list": "see the teachers' records", "teacher_detail": "see a teacher's record",
    "teacher_create": "add a teacher", "teacher_update": "edit a teacher", "teacher_delete": "delete a teacher",
    "profit": "see the profit", "expense_list": "see expenses", "expense_edit": "change an expense",
    "settings": "change settings", "backup": "make a backup", "activity": "see the activity log",
    "closing": "make a backup", "users": "manage logins", "user_create": "add a login", "user_edit": "change a login",
    "charge_add": "add a paper fund or fine", "charge_delete": "remove a paper fund or fine",
    "charge_batch_delete": "remove a paper fund or fine",
    "test_delete": "delete a test", "certificate_delete": "delete a certificate",
}


# ---------------------------------------------------------------------------
# The person using the system right now (so records can say who did what)
# ---------------------------------------------------------------------------
_local = threading.local()


def set_current_user(user):
    _local.user = user


def current_user():
    user = getattr(_local, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


def is_owner(user):
    return bool(user and user.is_authenticated and (user.is_superuser or user.username == OWNER_USERNAME))


def display_name(user):
    if not user or not getattr(user, "is_authenticated", False):
        return ""
    if is_owner(user):
        return "Principal"
    return user.first_name or user.username


def allowed(user, perm):
    """Can this user use this part of the system? perm is one of PERMISSION_KEYS."""
    if is_owner(user):
        return True
    if not (user and user.is_authenticated and user.is_active):
        return False
    access = getattr(user, "staff_access", None)
    return bool(access and getattr(access, perm, False))


def can_open(user, url_name):
    if url_name in OPEN_TO_ALL:
        return True
    if is_owner(user):
        return True
    perm = URL_PERMISSION.get(url_name)
    return bool(perm and allowed(user, perm))


class Access:
    """Used in templates: {% if access.owner %} … {% if access.fees %} …"""

    def __init__(self, user):
        self.user = user
        self.owner = is_owner(user)
        self.name = display_name(user)
        for key in PERMISSION_KEYS:
            setattr(self, key, allowed(user, key))
