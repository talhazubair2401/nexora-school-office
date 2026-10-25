from django.urls import path

from .views import attendance, auth, certificates, charges, classes, dashboard, fees, promotion, reports, students, teachers, tests, tools, users

app_name = "office"

urlpatterns = [
    path("", dashboard.dashboard, name="dashboard"),
    path("login/", auth.login_view, name="login"),
    path("first-time/", auth.first_time, name="first_time"),
    path("logout/", auth.logout_view, name="logout"),
    path("closing/", auth.closing, name="closing"),
    path("settings/", dashboard.school_settings, name="settings"),
    path("settings/password/", auth.change_password, name="change_password"),
    path("settings/backup/", tools.backup, name="backup"),
    path("settings/choose-folder/", tools.choose_folder, name="choose_folder"),
    path("activity/", tools.activity, name="activity"),
    path("logins/", users.users, name="users"),
    path("logins/new/", users.user_create, name="user_create"),
    path("logins/<int:pk>/", users.user_edit, name="user_edit"),
    path("logins/<int:pk>/on-off/", users.user_toggle, name="user_toggle"),

    # Attendance
    path("attendance/", attendance.attendance_home, name="attendance_home"),
    path("attendance/class/<int:pk>/", attendance.attendance_mark, name="attendance_mark"),
    path("attendance/class/<int:pk>/register/", attendance.attendance_register, name="attendance_register"),
    path("attendance/teachers/", attendance.teacher_attendance, name="teacher_attendance"),
    path("attendance/teachers/register/", attendance.teacher_attendance_month, name="teacher_attendance_month"),

    # Classes & subjects
    path("classes/", classes.class_list, name="class_list"),
    path("classes/new/", classes.class_create, name="class_create"),
    path("classes/promote/", promotion.promote, name="promote"),
    path("classes/promote/<int:pk>/undo/", promotion.promote_undo, name="promote_undo"),
    path("classes/<int:pk>/print-list/", classes.class_print_list, name="class_print_list"),
    path("classes/<int:pk>/", classes.class_detail, name="class_detail"),
    path("classes/<int:pk>/edit/", classes.class_update, name="class_update"),
    path("classes/<int:pk>/delete/", classes.class_delete, name="class_delete"),
    path("classes/<int:pk>/apply-fee/", classes.class_apply_fee, name="class_apply_fee"),
    path("classes/<int:pk>/subjects/add/", classes.subject_add, name="subject_add"),
    path("subjects/<int:pk>/edit/", classes.subject_update, name="subject_update"),
    path("subjects/<int:pk>/delete/", classes.subject_delete, name="subject_delete"),
    path("subjects/<int:pk>/move/<str:direction>/", classes.subject_move, name="subject_move"),

    # Students
    path("students/", students.student_list, name="student_list"),
    path("students/new/", students.student_create, name="student_create"),
    path("students/export/", students.student_export, name="student_export"),
    path("students/suggest/", students.student_suggest, name="student_suggest"),
    path("students/<int:pk>/", students.student_detail, name="student_detail"),
    path("students/<int:pk>/edit/", students.student_update, name="student_update"),
    path("students/<int:pk>/leave/", students.student_leave, name="student_leave"),
    path("students/<int:pk>/restore/", students.student_restore, name="student_restore"),
    path("students/<int:pk>/delete/", students.student_delete, name="student_delete"),
    path("students/<int:pk>/print/", students.student_print, name="student_print"),
    path("students/<int:pk>/challan/", fees.challan, name="challan"),
    path("students/<int:pk>/add-fee/", fees.fee_add_for_student, name="fee_add_for_student"),

    # Fees
    path("fees/", fees.fee_month, name="fee_month"),
    path("fees/create-month/", fees.fee_generate, name="fee_generate"),
    path("fees/<int:pk>/edit/", fees.fee_edit, name="fee_edit"),
    path("fees/<int:pk>/remove/", fees.fee_delete, name="fee_delete"),
    path("fees/<int:pk>/receive/", fees.payment_add, name="payment_add"),
    path("fees/<int:pk>/mark-paid/", fees.fee_mark_paid, name="fee_mark_paid"),
    path("payments/<int:pk>/delete/", fees.payment_delete, name="payment_delete"),
    path("payments/<int:pk>/receipt/", fees.receipt, name="receipt"),
    path("fees/challans/", fees.class_challans, name="class_challans"),
    path("fees/unpaid-list/", fees.unpaid_list, name="unpaid_list"),
    path("collection/", fees.daily_collection, name="daily_collection"),

    # Paper fund and fines
    path("paper-fund-fines/", charges.charge_list, name="charge_list"),
    path("paper-fund-fines/add/", charges.charge_add, name="charge_add"),
    path("paper-fund-fines/slips/", charges.charge_slips, name="charge_slips"),
    path("paper-fund-fines/<int:pk>/receive/", charges.charge_receive, name="charge_receive"),
    path("paper-fund-fines/<int:pk>/receipt/", charges.charge_receipt, name="charge_receipt"),
    path("paper-fund-fines/<int:pk>/remove/", charges.charge_delete, name="charge_delete"),
    path("paper-fund-fines/group/<str:batch>/remove/", charges.charge_batch_delete, name="charge_batch_delete"),

    # Other expenses
    path("expenses/", tools.expense_list, name="expense_list"),
    path("expenses/<int:pk>/edit/", tools.expense_edit, name="expense_edit"),
    path("profit/expenses-toggle/", tools.toggle_expenses, name="toggle_expenses"),

    # Certificates
    path("certificates/", certificates.certificate_list, name="certificate_list"),
    path("certificates/new/<str:kind>/", certificates.certificate_new, name="certificate_new"),
    path("certificates/preview/<str:kind>/", certificates.certificate_preview, name="certificate_preview"),
    path("certificates/<int:pk>/", certificates.certificate_print, name="certificate_print"),
    path("certificates/<int:pk>/edit/", certificates.certificate_edit, name="certificate_edit"),
    path("certificates/<int:pk>/delete/", certificates.certificate_delete, name="certificate_delete"),

    # Teachers & salaries
    path("teachers/", teachers.teacher_list, name="teacher_list"),
    path("teachers/new/", teachers.teacher_create, name="teacher_create"),
    path("teachers/<int:pk>/", teachers.teacher_detail, name="teacher_detail"),
    path("teachers/<int:pk>/edit/", teachers.teacher_update, name="teacher_update"),
    path("teachers/<int:pk>/delete/", teachers.teacher_delete, name="teacher_delete"),
    path("salaries/", teachers.salary_month, name="salary_month"),
    path("salaries/create-month/", teachers.salary_generate, name="salary_generate"),
    path("salaries/<int:pk>/", teachers.salary_edit, name="salary_edit"),
    path("salaries/<int:pk>/mark-paid/", teachers.salary_mark_paid, name="salary_mark_paid"),
    path("salaries/<int:pk>/slip/", teachers.salary_slip, name="salary_slip"),

    # Tests
    path("tests/", tests.test_list, name="test_list"),
    path("tests/new/", tests.test_create, name="test_create"),
    path("tests/<int:pk>/", tests.test_detail, name="test_detail"),
    path("tests/<int:pk>/edit/", tests.test_edit, name="test_edit"),
    path("tests/<int:pk>/delete/", tests.test_delete, name="test_delete"),
    path("tests/<int:pk>/marks/", tests.marks_entry, name="marks_entry"),
    path("tests/<int:pk>/result-sheet/", tests.result_sheet, name="result_sheet"),
    path("tests/<int:pk>/result-cards/", tests.result_cards, name="result_cards"),

    # Profit
    path("profit/", reports.profit, name="profit"),
]
