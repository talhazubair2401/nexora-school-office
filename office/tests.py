"""Automated checks:  python manage.py test"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .models import ClassRoom, Fee, FeePayment, Mark, Salary, School, Student, Subject, Teacher, Test, TestSubject
from .results import test_results

User = get_user_model()
PW = "secret123"


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        User.objects.create_user("admin", password=PW)
        cls.c1 = ClassRoom.objects.create(name="Class 1", order=1, default_fee=1500)
        cls.c2 = ClassRoom.objects.create(name="Class 2", order=2, default_fee=1500)
        cls.a = Student.objects.create(name="Ali", father_name="Tariq", classroom=cls.c1, roll_no=1, monthly_fee=1500, discount=500)
        cls.b = Student.objects.create(name="Sara", father_name="Imran", classroom=cls.c1, roll_no=2, monthly_fee=1500)
        cls.z = Student.objects.create(name="Zain", classroom=cls.c2, roll_no=1, monthly_fee=0)  # fee not set
        cls.t = Teacher.objects.create(name="Asma", salary=20000)

    def setUp(self):
        self.client.login(username="admin", password=PW)


class LoginTests(TestCase):
    def test_first_run_asks_for_password_then_login_works(self):
        r = self.client.get("/")
        self.assertRedirects(r, reverse("office:first_time"))
        r = self.client.post(reverse("office:first_time"), {"password1": "school786", "password2": "school786"})
        self.assertRedirects(r, reverse("office:dashboard"))
        self.client.logout()
        r = self.client.get("/students/")
        self.assertRedirects(r, f"{reverse('office:login')}?next=/students/")
        r = self.client.post(reverse("office:login"), {"password": "wrong"})
        self.assertContains(r, "not right")
        r = self.client.post(reverse("office:login"), {"password": "school786"})
        self.assertRedirects(r, reverse("office:dashboard"))

    def test_first_time_page_closed_once_password_exists(self):
        User.objects.create_user("admin", password=PW)
        self.assertRedirects(self.client.get(reverse("office:first_time")), reverse("office:login"))


class StudentTests(Base):
    def test_admission_numbers(self):
        y = timezone.localdate().year
        self.assertEqual(self.a.admission_no, f"NMS-{y}-0001")
        self.assertEqual(self.z.admission_no, f"NMS-{y}-0003")
        s = Student.objects.create(name="Old", classroom=self.c1, admission_date=date(2025, 4, 1))
        self.assertEqual(s.admission_no, "NMS-2025-0001")

    def test_admit_through_form(self):
        r = self.client.post(reverse("office:student_create"), {
            "name": "Hira", "father_name": "Kamran", "classroom": self.c2.pk, "monthly_fee": 1800, "discount": 300,
            "admission_date": "2026-10-01"})
        s = Student.objects.get(name="Hira")
        self.assertRedirects(r, s.get_absolute_url())
        self.assertEqual(s.net_fee, 1500)

    def test_discount_cannot_exceed_fee(self):
        r = self.client.post(reverse("office:student_create"), {"name": "X", "classroom": self.c1.pk,
                                                                 "monthly_fee": 1000, "discount": 1200})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Student.objects.filter(name="X").exists())

    def test_mark_left_keeps_history(self):
        Fee.objects.create(student=self.a, month=date(2026, 9, 1), amount=1500)
        self.client.post(reverse("office:student_leave", args=[self.a.pk]), {"left_on": "2026-10-05", "reason": "Moved"})
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Student.Status.LEFT)
        self.assertEqual(self.a.fees.count(), 1)
        self.assertIn("Moved", self.a.remarks)


class FeeTests(Base):
    def test_create_month_uses_each_students_fee_and_skips_unset(self):
        self.client.post(reverse("office:fee_generate"), {"month": "2026-10"})
        self.assertEqual(Fee.objects.get(student=self.a).net, 1000)
        self.assertEqual(Fee.objects.get(student=self.b).net, 1500)
        self.assertFalse(Fee.objects.filter(student=self.z).exists())
        self.client.post(reverse("office:fee_generate"), {"month": "2026-10"})  # no duplicates
        self.assertEqual(Fee.objects.count(), 2)

    def test_part_payment_balance_and_arrears(self):
        sep = Fee.objects.create(student=self.b, month=date(2026, 9, 1), amount=1500)
        oct_ = Fee.objects.create(student=self.b, month=date(2026, 10, 1), amount=1500)
        self.client.post(reverse("office:payment_add", args=[sep.pk]), {"amount": 1000, "paid_on": "2026-09-10"})
        sep = Fee.objects.get(pk=sep.pk)
        self.assertEqual((sep.paid, sep.balance, sep.status), (1000, 500, "PART"))
        self.assertEqual(self.b.balance_due(), 2000)
        r = self.client.get(reverse("office:fee_month") + "?month=2026-10")
        row = r.context["rows"][0]
        self.assertEqual((row["fee"].pk, row["arrears"]), (oct_.pk, 500))
        # challan lists both months
        r = self.client.get(reverse("office:challan", args=[self.b.pk]))
        self.assertEqual(r.context["challans"][0]["total"], 2000)

    def test_overpayment_refused(self):
        f = Fee.objects.create(student=self.b, month=date(2026, 10, 1), amount=1500)
        r = self.client.post(reverse("office:payment_add", args=[f.pk]), {"amount": 2000, "paid_on": "2026-10-02"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(FeePayment.objects.exists())

    def test_mark_paid_and_receipt_numbers(self):
        f = Fee.objects.create(student=self.a, month=date(2026, 10, 1), amount=1500, discount=500)
        self.client.post(reverse("office:fee_mark_paid", args=[f.pk]))
        p = FeePayment.objects.get()
        self.assertEqual(p.amount, 1000)
        self.assertTrue(p.receipt_no.startswith(f"R-{p.paid_on:%Y}-"))
        self.assertEqual(self.client.get(reverse("office:receipt", args=[p.pk])).status_code, 200)

    def test_edit_month_discount(self):
        f = Fee.objects.create(student=self.b, month=date(2026, 10, 1), amount=1500)
        self.client.post(reverse("office:fee_edit", args=[f.pk]), {"amount": 1500, "discount": 700, "note": "Sibling"})
        f.refresh_from_db()
        self.assertEqual(f.net, 800)


class SalaryAndProfitTests(Base):
    def test_salary_sheet_pay_and_profit(self):
        self.client.post(reverse("office:salary_generate"), {"month": "2026-10"})
        s = Salary.objects.get()
        self.assertEqual(s.amount, 20000)
        f = Fee.objects.create(student=self.b, month=date(2026, 10, 1), amount=1500)
        FeePayment.objects.create(fee=f, amount=1500, paid_on=date(2026, 10, 3))
        s.paid_amount, s.paid_on = 20000, date(2026, 10, 30)
        s.save()
        r = self.client.get(reverse("office:profit") + "?session=2026")
        october = [x for x in r.context["rows"] if x["month"] == date(2026, 10, 1)][0]
        self.assertEqual((october["received"], october["salaries"], october["profit"]), (1500, 20000, -18500))
        self.assertEqual(self.client.get(reverse("office:salary_slip", args=[s.pk])).status_code, 200)


class TestResultTests(Base):
    def test_marks_entry_results_and_positions(self):
        Subject.objects.create(classroom=self.c1, name="English")
        r = self.client.post(reverse("office:test_create"), {
            "classroom": self.c1.pk, "kind": "MONTHLY", "name": "October test", "date": "2026-10-10",
            "subj_id": ["", ""], "subj_name": ["English", "Maths"], "subj_full": ["50", "25"]})
        test = Test.objects.get()
        self.assertRedirects(r, reverse("office:marks_entry", args=[test.pk]))
        eng, maths = test.subjects.all()
        data = {f"m_{self.a.pk}_{eng.pk}": "40", f"m_{self.a.pk}_{maths.pk}": "20",
                f"m_{self.b.pk}_{eng.pk}": "45", f"a_{self.b.pk}_{maths.pk}": "on", f"r_{self.b.pk}": "Good work"}
        self.client.post(reverse("office:marks_entry", args=[test.pk]), data)
        _, rows = test_results(test)
        res = {r["student"].name: r for r in rows}
        self.assertEqual((res["Ali"]["percent"], res["Ali"]["position"], res["Ali"]["grade"]), (80.0, 1, "A"))
        self.assertEqual((res["Sara"]["percent"], res["Sara"]["position"], res["Sara"]["remark"]), (60.0, 2, "Good work"))
        # marks above full are refused
        self.client.post(reverse("office:marks_entry", args=[test.pk]), {f"m_{self.a.pk}_{maths.pk}": "30"})
        self.assertEqual(Mark.objects.get(student=self.a, subject=maths).obtained, 20)
        for name in ("result_sheet", "result_cards", "test_detail"):
            self.assertEqual(self.client.get(reverse(f"office:{name}", args=[test.pk])).status_code, 200, name)

    def test_grade_scale_is_editable(self):
        school = School.get()
        school.grade_scale = "85 A+\n0 Try again"
        school.save()
        self.assertEqual(school.grade_for(86), "A+")
        self.assertEqual(school.grade_for(50), "Try again")


class PagesRender(Base):
    def test_every_page(self):
        f = Fee.objects.create(student=self.a, month=date(2026, 10, 1), amount=1500)
        Salary.objects.create(teacher=self.t, month=date(2026, 10, 1), amount=20000)
        test = Test.objects.create(classroom=self.c1, name="T")
        TestSubject.objects.create(test=test, name="Urdu", full_marks=50)
        urls = ["/", "/students/", "/students/new/", f"/students/{self.a.pk}/", f"/students/{self.a.pk}/edit/",
                f"/students/{self.a.pk}/print/", f"/students/{self.a.pk}/challan/", "/students/export/",
                "/classes/", "/classes/new/", f"/classes/{self.c1.pk}/", f"/classes/{self.c1.pk}/edit/",
                "/teachers/", "/teachers/new/", f"/teachers/{self.t.pk}/", f"/teachers/{self.t.pk}/edit/",
                "/fees/", "/fees/?month=2026-10", f"/fees/{f.pk}/edit/", f"/fees/{f.pk}/receive/",
                "/fees/unpaid-list/?month=2026-10", "/fees/challans/", "/salaries/?month=2026-10",
                "/tests/", "/tests/new/", f"/tests/{test.pk}/", f"/tests/{test.pk}/marks/", f"/tests/{test.pk}/edit/",
                "/profit/", "/profit/?print=1", "/settings/", "/settings/password/"]
        for u in urls:
            r = self.client.get(u)
            self.assertEqual(r.status_code, 200, u)


# ---------------------------------------------------------------------------
# October 2026 additions
# ---------------------------------------------------------------------------
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

from .models import ActivityLog, Certificate, ClassHistory, Expense, PromotionBatch  # noqa: E402
from . import certificates as C  # noqa: E402


class SearchTests(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.m = Student.objects.create(name="Muhammad Ali", father_name="Aslam", classroom=cls.c2, roll_no=2,
                                       monthly_fee=1500, phone="0301-1234567")
        cls.k = Student.objects.create(name="Khalid", father_name="Ali Raza", classroom=cls.c2, roll_no=3,
                                       monthly_fee=1500, phone="0345-9990001")

    def names(self, r):
        return {k: [s.name for s in items] for k, _, items in r.context["groups"]}

    def test_name_from_start_of_word_father_separate(self):
        r = self.client.get("/students/?q=ali")
        g = self.names(r)
        self.assertEqual(g["name"], ["Ali", "Muhammad Ali"])     # A to Z
        self.assertEqual(g["father"], ["Khalid"])                 # father Ali Raza, listed separately
        self.assertNotIn("other", g)  # "ali" inside "Khalid" doesn't count as a name match… it's the father group

    def test_numbers_only_admission_and_phone(self):
        r = self.client.get("/students/?q=1234")
        self.assertEqual(self.names(r), {"phone": ["Muhammad Ali"]})
        serial = self.k.admission_no.rsplit("-", 1)[1]
        r = self.client.get(f"/students/?q={int(serial)}")
        self.assertEqual(self.names(r)["exact"], ["Khalid"])

    def test_search_in_and_sort(self):
        r = self.client.get("/students/?q=ali&in=father")
        self.assertEqual(self.names(r), {"father": ["Khalid"]})
        r = self.client.get("/students/?sort=-name")
        self.assertEqual([s.name for s in r.context["groups"][0][2]][:2], ["Zain", "Sara"])
        r = self.client.get("/students/?q=ali&partial=1")
        self.assertTemplateUsed(r, "office/_student_results.html")

    def test_suggest_json(self):
        data = self.client.get("/students/suggest/?q=ali").json()
        self.assertEqual([g["title"] for g in data["groups"]], ["Student name matches", "Father's name matches"])

    def test_prev_next_in_class(self):
        r = self.client.get(f"/students/{self.m.pk}/")
        self.assertEqual((r.context["prev_s"][1], r.context["next_s"][1], r.context["pos"]), ("Zain", "Khalid", 2))


class PromotionTests(Base):
    def test_promote_keep_pass_out_and_undo(self):
        c10 = ClassRoom.objects.create(name="Class 10", order=10, default_fee=2500)
        top = Student.objects.create(name="Top", classroom=c10, monthly_fee=2500)
        self.c2.default_fee = 1800
        self.c2.save()
        seen = [self.a.pk, self.b.pk, self.z.pk, top.pk]
        r = self.client.post("/classes/promote/", {"year": 2027, "new_fee": "1", "seen": seen,
                                                    "move": [self.a.pk, self.z.pk, top.pk]})
        self.assertEqual(r.status_code, 302)
        for x in (self.a, self.b, self.z, top):
            x.refresh_from_db()
        self.assertEqual((self.a.classroom, self.a.monthly_fee, self.a.discount), (self.c2, 1800, 500))
        self.assertEqual(self.b.classroom, self.c1)                       # unticked: kept
        self.assertEqual(self.z.classroom, c10)                            # Class 2 -> next by order
        self.assertEqual(top.status, Student.Status.PASSED)
        self.assertEqual(ClassHistory.objects.count(), 4)
        # doing it twice for the same year is refused
        self.client.post("/classes/promote/", {"year": 2027, "seen": seen, "move": seen})
        self.assertEqual(PromotionBatch.objects.count(), 1)
        batch = PromotionBatch.objects.get()
        self.client.post(f"/classes/promote/{batch.pk}/undo/")
        for x in (self.a, top):
            x.refresh_from_db()
        self.assertEqual((self.a.classroom, self.a.monthly_fee), (self.c1, 1500))
        self.assertEqual(top.status, Student.Status.ACTIVE)
        self.assertTrue(ActivityLog.objects.filter(kind="promotion").count() == 2)


class MoneyAdditionsTests(Base):
    def test_daily_collection_and_activity(self):
        f = Fee.objects.create(student=self.b, month=date(2026, 10, 1), amount=1500)
        FeePayment.objects.create(fee=f, amount=500, paid_on=date(2026, 10, 3))
        FeePayment.objects.create(fee=f, amount=700, paid_on=date(2026, 10, 3))
        g = Fee.objects.create(student=self.a, month=date(2026, 10, 1), amount=1500, discount=500)
        self.client.post(reverse("office:fee_mark_paid", args=[g.pk]))
        r = self.client.get("/collection/?from=2026-10-01&to=2026-10-31")
        day3 = [d for d in r.context["days"] if d["day"] == date(2026, 10, 3)][0]
        self.assertEqual((day3["total"], day3["count"]), (1200, 2))
        self.assertEqual(self.client.get("/collection/?from=2026-10-01&to=2026-10-31&print=1").status_code, 200)
        log = ActivityLog.objects.get(kind="fee")
        self.assertIn("Ali", log.text)
        self.assertEqual(log.amount, 1000)

    def test_expenses_optional_on_profit(self):
        self.client.post("/expenses/?month=2026-10", {"date": "2026-10-05", "category": "Rent", "amount": 9000})
        self.assertEqual(Expense.objects.get().amount, 9000)
        r = self.client.get("/profit/?session=2026")
        october = [x for x in r.context["rows"] if x["month"] == date(2026, 10, 1)][0]
        self.assertEqual(october["profit"], 0)                       # off by default
        self.client.post("/profit/expenses-toggle/", {"on": "1"})
        r = self.client.get("/profit/?session=2026")
        october = [x for x in r.context["rows"] if x["month"] == date(2026, 10, 1)][0]
        self.assertEqual((october["expenses"], october["profit"]), (9000, -9000))

    def test_class_print_list_and_big_text_setting(self):
        r = self.client.get(f"/classes/{self.c1.pk}/print-list/")
        self.assertContains(r, "Tariq")
        school = School.get()
        school.ui_size = "large"
        school.save()
        self.assertContains(self.client.get("/"), 'class="ui-large"')


class CertificateTests(Base):
    def test_every_kind_previews_issues_and_prints(self):
        self.a.date_of_birth = date(2018, 3, 21)
        self.a.save()
        for kind in Certificate.STUDENT_KINDS + Certificate.TEACHER_KINDS:
            who = f"teacher={self.t.pk}" if kind in Certificate.TEACHER_KINDS else f"student={self.a.pk}"
            r = self.client.get(f"/certificates/new/{kind}/?{who}")
            self.assertEqual(r.status_code, 200, kind)
            values = {f["key"]: f["value"] for f in r.context["fields"]}
            self.assertEqual(self.client.get(f"/certificates/preview/{kind}/", values).status_code, 200)
            values[who.split("=")[0]] = who.split("=")[1]
            r = self.client.post(f"/certificates/new/{kind}/", values)
            cert = Certificate.objects.get(kind=kind)
            self.assertRedirects(r, reverse("office:certificate_print", args=[cert.pk]))
            r = self.client.get(reverse("office:certificate_print", args=[cert.pk]))
            self.assertContains(r, "Principal")
            self.assertNotContains(r, "Asma</b>, Principal")
        self.assertTrue(Certificate.objects.get(kind="SLC").serial_no.startswith("SLC-"))
        self.assertContains(self.client.get("/certificates/"), "Register")

    def test_wording_can_be_edited_and_is_cleaned(self):
        r = self.client.get(f"/certificates/new/CHAR/?student={self.a.pk}")
        values = {f["key"]: f["value"] for f in r.context["fields"]}
        values.update({"student": self.a.pk, "body_custom": "1",
                       "body_html": '<h1 class="cert-title"><span>CHARACTER CERTIFICATE</span></h1>'
                                    '<p class="cert-text">Ali is a <b>very</b> good boy.<script>alert(1)</script></p>'
                                    '<img src=x onerror=alert(1)>'})
        r = self.client.post("/certificates/preview/CHAR/", dict(values, embed="1", edit="1"))
        self.assertContains(r, 'contenteditable="true"')
        self.assertContains(r, "Ali is a <b>very</b> good boy.")
        self.client.post("/certificates/new/CHAR/", values)
        cert = Certificate.objects.get()
        self.assertNotIn("script", cert.data["body_html"])
        self.assertNotIn("img", cert.data["body_html"])
        r = self.client.get(reverse("office:certificate_print", args=[cert.pk]))
        self.assertContains(r, "Ali is a <b>very</b> good boy.")
        self.assertNotContains(r, "alert(1)")
        # change it later, keeping the serial number
        values["body_html"] = '<p class="cert-text">Changed text.</p>'
        self.client.post(reverse("office:certificate_edit", args=[cert.pk]), values)
        cert.refresh_from_db()
        self.assertEqual(cert.data["body_html"], '<p class="cert-text">Changed text.</p>')
        self.assertEqual(Certificate.objects.count(), 1)
        # back to the standard wording
        values["body_custom"] = "0"
        self.client.post(reverse("office:certificate_edit", args=[cert.pk]), values)
        cert.refresh_from_db()
        self.assertNotIn("body_html", cert.data)
        self.assertContains(self.client.get(reverse("office:certificate_print", args=[cert.pk])), "bona fide student")

    def test_date_in_words(self):
        self.assertEqual(C.date_in_words(date(2018, 3, 21)), "Twenty-first March, Two Thousand Eighteen")
        self.assertEqual(C.date_in_words(date(2009, 12, 30)), "Thirtieth December, Two Thousand Nine")


class NewPagesRender(Base):
    def test_new_pages(self):
        for u in ["/activity/", "/expenses/", "/collection/", "/classes/promote/", "/certificates/",
                  "/certificates/?pick=SLC&pq=ali", "/certificates/?pick=EXP&pq=asma", "/students/?q=sara&in=name",
                  f"/classes/{self.c1.pk}/print-list/?order=name&due=0"]:
            self.assertEqual(self.client.get(u).status_code, 200, u)


class BackupTests(TransactionTestCase):
    """Run outside a test transaction, like the real system (SQLite can't copy a database mid-transaction)."""

    def test_backup_makes_dated_copy(self):
        User.objects.create_user("admin", password=PW)
        self.client.login(username="admin", password=PW)
        Student.objects.create(name="Ali")
        with tempfile.TemporaryDirectory() as tmp:
            r = self.client.post("/settings/backup/", {"folder": tmp})
            self.assertEqual(r.status_code, 302)
            made = list(Path(tmp).glob("School_backup_*"))
            self.assertEqual(len(made), 1)
            self.assertTrue((made[0] / "db.sqlite3").stat().st_size > 0)
        self.assertIsNotNone(School.get().last_backup_at)


# ---------------------------------------------------------------------------
# October 2026 update: office staff logins and attendance
# ---------------------------------------------------------------------------
from .models import ActivityLog, StaffAccess, StudentAttendance, TeacherAttendance  # noqa: E402


class StaffTests(Base):
    def make_staff(self, **perms):
        u = User.objects.create_user("staff_x", password="bilal123", first_name="Bilal")
        StaffAccess.objects.create(user=u, **perms)
        return u

    def login_staff(self, u):
        self.client.logout()
        r = self.client.post(reverse("office:login"), {"role": "staff", "user": u.pk, "staff_password": "bilal123"})
        self.assertRedirects(r, reverse("office:dashboard"))

    def test_owner_makes_a_staff_login_from_the_logins_page(self):
        r = self.client.post(reverse("office:user_create"), {"name": "Bilal", "password1": "bilal123",
                                                              "password2": "bilal123", "fees": "on"})
        self.assertRedirects(r, reverse("office:users"))
        u = User.objects.get(first_name="Bilal")
        self.assertTrue(u.staff_access.fees)
        self.assertFalse(u.staff_access.tests)
        self.client.logout()
        self.assertContains(self.client.get(reverse("office:login")), "Office staff")

    def test_staff_login_wrong_password_and_owner_login_still_works(self):
        u = self.make_staff()
        self.client.logout()
        r = self.client.post(reverse("office:login"), {"role": "staff", "user": u.pk, "staff_password": "nope"})
        self.assertContains(r, "not right")
        r = self.client.post(reverse("office:login"), {"role": "owner", "password": PW})
        self.assertRedirects(r, reverse("office:dashboard"))

    def test_staff_cannot_change_fees_or_see_money_pages(self):
        u = self.make_staff(fees=True)
        fee = Fee.objects.create(student=self.a, month=date(2026, 10, 1), amount=5000)
        self.login_staff(u)
        for name, args in [("fee_edit", [fee.pk]), ("profit", []), ("salary_month", []), ("settings", []),
                           ("activity", []), ("users", []), ("student_delete", [self.a.pk]), ("expense_list", [])]:
            self.assertEqual(self.client.get(reverse(f"office:{name}", args=args)).status_code, 403, name)
        r = self.client.post(reverse("office:fee_edit", args=[fee.pk]), {"amount": 4000, "discount": 0})
        self.assertEqual(r.status_code, 403)
        fee.refresh_from_db()
        self.assertEqual(fee.amount, 5000)
        self.assertTrue(ActivityLog.objects.filter(kind="security", who="Bilal").exists())

    def test_staff_receives_fee_and_payment_says_who(self):
        u = self.make_staff(fees=True)
        fee = Fee.objects.create(student=self.a, month=date(2026, 10, 1), amount=5000)
        self.login_staff(u)
        r = self.client.post(reverse("office:payment_add", args=[fee.pk]), {"amount": 4000, "paid_on": "2020-01-01"})
        self.assertEqual(r.status_code, 302)
        p = FeePayment.objects.get(fee=fee)
        self.assertEqual(p.received_by, u)
        self.assertEqual(p.paid_on, timezone.localdate())        # staff can't back-date a payment
        self.assertEqual(fee.balance, 1000)                        # the rest still shows as due
        self.assertEqual(ActivityLog.objects.filter(kind="fee").first().who, "Bilal")
        r = self.client.get(reverse("office:daily_collection"))
        self.assertContains(r, "Received by <b>Bilal</b>")

    def test_switched_off_parts_are_closed(self):
        u = self.make_staff(fees=False, attendance=True, students=False)
        self.login_staff(u)
        self.assertEqual(self.client.get(reverse("office:fee_month")).status_code, 403)
        self.assertEqual(self.client.get(reverse("office:student_create")).status_code, 403)
        self.assertEqual(self.client.get(reverse("office:attendance_home")).status_code, 200)
        r = self.client.get(reverse("office:dashboard"))
        self.assertNotContains(r, "Profit this month")
        self.assertNotContains(r, reverse("office:fee_month"))

    def test_staff_edits_student_but_fee_stays(self):
        u = self.make_staff(students=True)
        self.login_staff(u)
        r = self.client.post(reverse("office:student_update", args=[self.a.pk]), {
            "name": "Ali Khan", "classroom": self.c1.pk, "monthly_fee": 100, "discount": 1400,
            "admission_date": "2026-04-01"})
        self.assertEqual(r.status_code, 302)
        self.a.refresh_from_db()
        self.assertEqual(self.a.name, "Ali Khan")
        self.assertEqual((self.a.monthly_fee, self.a.discount), (1500, 500))

    def test_turned_off_login_cannot_log_in(self):
        u = self.make_staff()
        self.client.post(reverse("office:user_toggle", args=[u.pk]))
        self.client.logout()
        r = self.client.post(reverse("office:login"), {"role": "staff", "user": u.pk, "staff_password": "bilal123"})
        self.assertEqual(r.status_code, 200)


class AttendanceTests(Base):
    def test_mark_class_attendance_and_register(self):
        today = timezone.localdate()
        url = reverse("office:attendance_mark", args=[self.c1.pk])
        self.assertContains(self.client.get(url), "Ali")
        r = self.client.post(url, {"date": today.isoformat(), f"s{self.a.pk}": "A", f"s{self.b.pk}": "P"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(StudentAttendance.objects.get(student=self.a, date=today).status, "A")
        # change it: no duplicates
        self.client.post(url, {"date": today.isoformat(), f"s{self.a.pk}": "L", f"s{self.b.pk}": "P"})
        self.assertEqual(StudentAttendance.objects.filter(date=today).count(), 2)
        r = self.client.get(reverse("office:attendance_home"))
        self.assertContains(r, "Ali")      # in the absent / leave list
        r = self.client.get(reverse("office:attendance_register", args=[self.c1.pk]))
        self.assertContains(r, "m-L")
        r = self.client.get(reverse("office:attendance_register", args=[self.c1.pk]) + "?print=1")
        self.assertContains(r, "ATTENDANCE REGISTER")
        r = self.client.get(self.a.get_absolute_url())
        self.assertContains(r, "Attendance this month")

    def test_future_date_is_not_allowed(self):
        future = timezone.localdate() + timezone.timedelta(days=3)
        self.client.post(reverse("office:attendance_mark", args=[self.c1.pk]), {"date": future.isoformat()})
        self.assertFalse(StudentAttendance.objects.filter(date=future).exists())

    def test_teacher_attendance(self):
        today = timezone.localdate()
        r = self.client.post(reverse("office:teacher_attendance"), {"date": today.isoformat(), f"t{self.t.pk}": "T"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(TeacherAttendance.objects.get(teacher=self.t).status, "T")
        self.assertContains(self.client.get(reverse("office:teacher_attendance_month")), "Asma")
        self.assertContains(self.client.get(reverse("office:dashboard")), "Attendance today")


class NewLoginPageTests(TestCase):
    def test_login_page_has_both_sides(self):
        User.objects.create_superuser("admin", password=PW)
        r = self.client.get(reverse("office:login"))
        self.assertContains(r, "Owner login")
        self.assertNotContains(r, "Sign in here")        # no staff logins yet
        u = User.objects.create_user("staff_y", password="sana1234", first_name="Sana")
        StaffAccess.objects.create(user=u)
        r = self.client.get(reverse("office:login"))
        self.assertContains(r, "Sign in here")
        self.assertContains(r, "Sana")


from .models import Charge  # noqa: E402


class PaperFundAndFinesTests(Base):
    def test_paper_fund_for_whole_class_added_to_fee(self):
        r = self.client.post(reverse("office:charge_add"), {"who": "class", "classroom": self.c1.pk, "kind": "PAPER",
                                                             "amount": 300, "reason": "1st term", "date": "2026-10-05",
                                                             "how": "fee", "month": "2026-10"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Charge.objects.count(), 2)          # Ali and Sara
        fee = Fee.objects.get(student=self.a, month=date(2026, 10, 1))   # made automatically
        self.assertEqual(fee.extra, 300)
        self.assertEqual(fee.net, 1000 + 300)               # 1500 - 500 discount + 300
        r = self.client.get(reverse("office:challan", args=[self.a.pk]))
        self.assertContains(r, "Paper fund")
        self.client.post(reverse("office:fee_mark_paid", args=[fee.pk]))
        p = FeePayment.objects.get(fee=fee)
        self.assertEqual(p.amount, 1300)
        self.assertContains(self.client.get(reverse("office:receipt", args=[p.pk])), "1st term")
        # removing the charge lowers the fee again
        c = Charge.objects.get(student=self.b)
        self.client.post(reverse("office:charge_delete", args=[c.pk]))
        self.assertEqual(Fee.objects.get(student=self.b, month=date(2026, 10, 1)).extra, 0)

    def test_separate_fine_slip_receipt_and_profit(self):
        self.client.post(reverse("office:charge_add"), {"who": "student", "student": self.a.pk, "kind": "LATE",
                                                        "amount": 100, "date": timezone.localdate().isoformat(),
                                                        "how": "separate"})
        c = Charge.objects.get()
        self.assertIsNone(c.fee)
        self.assertContains(self.client.get(reverse("office:charge_slips") + f"?student={self.a.pk}"), "Late fee fine")
        r = self.client.post(reverse("office:charge_receive", args=[c.pk]), {"print": "1"})
        c.refresh_from_db()
        self.assertRedirects(r, reverse("office:charge_receipt", args=[c.pk]), fetch_redirect_response=False)
        self.assertTrue(c.receipt_no.startswith("C-"))
        self.assertContains(self.client.get(reverse("office:charge_receipt", args=[c.pk])), "PAID")
        self.assertContains(self.client.get(reverse("office:daily_collection")), "paid separately")
        self.assertContains(self.client.get(reverse("office:charge_list")), "Late fee fine")

    def test_staff_can_receive_but_not_add(self):
        u = User.objects.create_user("staff_z", password="bilal123", first_name="Bilal")
        StaffAccess.objects.create(user=u, fees=True)
        c = Charge.objects.create(student=self.a, kind="OTHER", amount=50, reason="uniform")
        self.client.logout()
        self.client.login(username="staff_z", password="bilal123")
        self.assertEqual(self.client.get(reverse("office:charge_add")).status_code, 403)
        self.assertEqual(self.client.post(reverse("office:charge_delete", args=[c.pk])).status_code, 403)
        self.client.post(reverse("office:charge_receive", args=[c.pk]))
        c.refresh_from_db()
        self.assertEqual(c.received_by, u)


class ReviewFixTests(Base):
    def test_login_is_logged_with_name_and_link_noise_is_not(self):
        u = User.objects.create_user("staff_w", password="bilal123", first_name="Bilal")
        StaffAccess.objects.create(user=u, fees=True, tests=False)
        self.client.logout()
        self.client.post(reverse("office:login"), {"role": "staff", "user": u.pk, "staff_password": "bilal123"})
        self.assertEqual(ActivityLog.objects.filter(kind="login").first().who, "Bilal")
        t = Test.objects.create(classroom=self.c1, name="Oct test")
        self.assertEqual(self.client.get(t.get_absolute_url()).status_code, 403)
        self.assertFalse(ActivityLog.objects.filter(kind="security").exists())   # just a link, not logged
        self.client.get(reverse("office:profit"))
        self.assertTrue(ActivityLog.objects.filter(kind="security").exists())    # money page, logged

    def test_fine_link_from_fees_page_prefills_month(self):
        r = self.client.get(reverse("office:charge_add") + f"?student={self.a.pk}&kind=LATE&month=2026-09")
        self.assertContains(r, 'value="2026-09"')


class PaperFundGroupTests(Base):
    def test_remove_whole_class_paper_fund_keeps_paid_ones(self):
        self.client.post(reverse("office:charge_add"), {"who": "class", "classroom": self.c1.pk, "kind": "PAPER",
                                                        "amount": 300, "date": "2026-10-05", "how": "fee", "month": "2026-10"})
        batch = Charge.objects.first().batch
        self.assertTrue(batch)
        self.assertContains(self.client.get(reverse("office:charge_list")), "Remove all")
        fee_a = Fee.objects.get(student=self.a, month=date(2026, 10, 1))
        self.client.post(reverse("office:fee_mark_paid", args=[fee_a.pk]))          # Ali paid already
        r = self.client.get(reverse("office:charge_batch_delete", args=[batch]))
        self.assertContains(r, "already paid")
        self.client.post(reverse("office:charge_batch_delete", args=[batch]), {"mode": "unpaid"})
        self.assertEqual(list(Charge.objects.values_list("student__name", flat=True)), ["Ali"])
        self.assertEqual(Fee.objects.get(student=self.b, month=date(2026, 10, 1)).extra, 0)
        self.client.post(reverse("office:charge_batch_delete", args=[batch]), {"mode": "all"})
        self.assertFalse(Charge.objects.exists())

    def test_owner_sees_delete_on_edit_page(self):
        self.assertContains(self.client.get(reverse("office:student_update", args=[self.a.pk])), "Delete this student")


class ClosingBackupTests(Base):
    def test_lock_asks_for_backup_when_due_and_backs_up_then_locks(self):
        import tempfile
        r = self.client.post(reverse("office:logout"))
        self.assertRedirects(r, reverse("office:closing"))
        self.assertContains(self.client.get(reverse("office:closing")), "Back up before you close")
        from pathlib import Path
        from unittest import mock
        # The copy itself is tested on the real system; inside a test transaction SQLite can't copy, so pretend.
        with tempfile.TemporaryDirectory() as d, \
                mock.patch("office.views.tools.make_backup", return_value=(Path(d) / "School_backup_x", 3)):
            r = self.client.post(reverse("office:backup"), {"folder": d, "then_lock": "1"})
            self.assertRedirects(r, reverse("office:login"), fetch_redirect_response=False)
        self.assertIsNotNone(School.get().last_backup_at)
        self.assertContains(self.client.get(reverse("office:login")), "The office is locked")
        # logged out now
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_lock_without_backup_and_no_reminder_after_recent_backup(self):
        r = self.client.post(reverse("office:logout"), {"skip_backup": "1"})
        self.assertRedirects(r, reverse("office:login"), fetch_redirect_response=False)
        self.client.login(username="admin", password=PW)
        s = School.get(); s.last_backup_at = timezone.now(); s.save()
        r = self.client.post(reverse("office:logout"))
        self.assertRedirects(r, reverse("office:login"), fetch_redirect_response=False)

    def test_staff_lock_never_asks(self):
        u = User.objects.create_user("staff_v", password="bilal123", first_name="Bilal")
        StaffAccess.objects.create(user=u)
        self.client.logout(); self.client.login(username="staff_v", password="bilal123")
        r = self.client.post(reverse("office:logout"))
        self.assertRedirects(r, reverse("office:login"), fetch_redirect_response=False)


# ---------------------------------------------------------------------------
# Public online demo (SCHOOL_DEMO=1)
# ---------------------------------------------------------------------------
import shutil as _shutil  # noqa: E402

from django.test import Client, override_settings  # noqa: E402


class DemoModeTests(TransactionTestCase):
    def setUp(self):
        from . import demo
        self.demo = demo
        self.tmp = Path(tempfile.mkdtemp())
        self.ov = override_settings(DEMO_MODE=True, DATA_DIR=self.tmp, MEDIA_ROOT=self.tmp / "media")
        self.ov.enable()
        demo._last_check = 0.0

    def tearDown(self):
        self.ov.disable()
        self.demo._last_check = 0.0
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def sign_in(self, username):
        c = Client()
        c.get("/login/")
        self.assertEqual(c.post("/demo-login/", {"username": username}).status_code, 302)
        return c

    def test_builds_fictional_school_on_first_visit(self):
        r = Client().get("/login/")
        self.assertContains(r, "Try the live demo")
        self.assertEqual(School.get().name, "Nexora Model School")
        self.assertGreater(Student.objects.count(), 100)
        self.assertTrue(FeePayment.objects.exists())
        self.assertTrue(Student.objects.first().admission_no.startswith("NMS-"))
        for u in get_user_model().objects.all():
            self.assertFalse(u.has_usable_password())

    def test_staff_limits_still_apply(self):
        c = self.sign_in("demo_clerk")
        self.assertEqual(c.get(reverse("office:dashboard")).status_code, 200)
        self.assertEqual(c.get(reverse("office:profit")).status_code, 403)
        self.assertEqual(c.get(reverse("office:salary_month")).status_code, 403)

    def test_risky_pages_blocked_for_owner(self):
        c = self.sign_in("admin")
        for name in ("change_password", "backup", "user_create"):
            r = c.get(reverse(f"office:{name}"))
            self.assertEqual(r.status_code, 302, name)
        before = School.get().name
        c.post(reverse("office:settings"), {"name": "Hacked"})
        self.assertEqual(School.get().name, before)

    def test_unknown_user_cannot_one_click(self):
        Client().get("/login/")
        c = Client()
        c.post("/demo-login/", {"username": "staff_x"})
        self.assertEqual(c.get(reverse("office:dashboard")).status_code, 302)

    def test_stale_data_is_rebuilt(self):
        c = self.sign_in("admin")
        Student.objects.create(name="Visitor Test", classroom=ClassRoom.objects.first(), monthly_fee=1000)
        (self.tmp / "demo_built_at.txt").write_text("2020-01-01T00:00:00")
        self.demo._last_check = 0.0
        Client().get("/login/")
        self.assertFalse(Student.objects.filter(name="Visitor Test").exists())

    def test_off_by_default(self):
        with override_settings(DEMO_MODE=False):
            with self.assertRaises(RuntimeError):
                self.demo.build_demo()
            c = Client()
            c.post("/demo-login/", {"username": "admin"})
            self.assertNotContains(c.get("/login/", follow=True), "Try the live demo")
            self.assertFalse((self.tmp / "demo_built_at.txt").exists())
