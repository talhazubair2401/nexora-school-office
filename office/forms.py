from django import forms
from django.contrib.auth import password_validation
from django.utils import timezone

from .models import (CLASS_COLOURS, Charge, ClassRoom, Expense, Fee, FeePayment, Salary, School, Student, Subject, Teacher,
                     Test)

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
MONTH = forms.DateInput(attrs={"type": "month"}, format="%Y-%m")
MONTH_FORMATS = ["%Y-%m", "%Y-%m-%d"]


class Styled:
    """Adds Bootstrap classes to every widget."""

    def style(self):
        for field in self.fields.values():
            w = field.widget
            if isinstance(w, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                css = "form-select"
            else:
                css = "form-control"
            w.attrs["class"] = (w.attrs.get("class", "") + " " + css).strip()
            if isinstance(w, forms.Textarea):
                w.attrs.setdefault("rows", 2)


class StyledForm(Styled, forms.Form):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.style()


class StyledModelForm(Styled, forms.ModelForm):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.style()


# ---------------------------------------------------------------------------
# Password
# ---------------------------------------------------------------------------
class PasswordLoginForm(StyledForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


class StaffLoginForm(StyledForm):
    """Office staff: choose your name, then type your own password."""
    user = forms.ModelChoiceField(label="Your name", queryset=None, empty_label="Choose your name")
    staff_password = forms.CharField(label="Password", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        from django.contrib.auth import get_user_model
        self.fields["user"].queryset = (get_user_model().objects.filter(is_active=True, is_superuser=False,
                                                                        staff_access__isnull=False)
                                        .order_by("first_name"))
        self.fields["user"].label_from_instance = lambda u: u.first_name or u.username


class StaffUserForm(StyledForm):
    """Owner: add an office staff login or change what it may do."""
    name = forms.CharField(label="Name", max_length=60, help_text="Shown on the login screen and in the activity log.")
    password1 = forms.CharField(label="Password", required=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                help_text="At least 6 characters. Tell it only to this person.")
    password2 = forms.CharField(label="Type the password again", required=False,
                                widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def __init__(self, *a, instance=None, **kw):
        from .access import PERMISSIONS
        self.instance = instance
        super().__init__(*a, **kw)
        for key, label, help_text in PERMISSIONS:
            self.fields[key] = forms.BooleanField(label=label, help_text=help_text, required=False,
                                                  widget=forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}))
        if instance is None:
            self.fields["password1"].required = True
            self.fields["password2"].required = True
        else:
            self.fields["password1"].label = "New password"
            self.fields["password1"].help_text = "Leave empty to keep the current password."

    def clean_name(self):
        from django.contrib.auth import get_user_model
        name = " ".join(self.cleaned_data["name"].split())
        qs = get_user_model().objects.filter(first_name__iexact=name)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists() or name.lower() in ("admin", "principal", "owner"):
            raise forms.ValidationError("Please choose a different name; this one is already used.")
        return name

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 or p2:
            if p1 != p2:
                self.add_error("password2", "The two passwords don't match.")
            else:
                try:
                    password_validation.validate_password(p1)
                except forms.ValidationError as e:
                    self.add_error("password1", e)
        return data


class NewPasswordForm(StyledForm):
    password1 = forms.CharField(label="New password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                help_text="At least 6 characters. Write it down somewhere safe.")
    password2 = forms.CharField(label="Type it again", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords don't match.")
        if p1:
            try:
                password_validation.validate_password(p1)
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return data


class ChangePasswordForm(NewPasswordForm):
    current = forms.CharField(label="Current password", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    field_order = ["current", "password1", "password2"]

    def __init__(self, user, *a, **kw):
        self.user = user
        super().__init__(*a, **kw)

    def clean_current(self):
        if not self.user.check_password(self.cleaned_data["current"]):
            raise forms.ValidationError("That's not the current password.")
        return self.cleaned_data["current"]


# ---------------------------------------------------------------------------
# School settings
# ---------------------------------------------------------------------------
class SchoolForm(StyledModelForm):
    class Meta:
        model = School
        fields = ["name", "name_urdu", "address", "phone", "motto", "logo", "letterhead", "fee_due_day", "pass_percent",
                  "grade_scale", "ui_size"]
        labels = {"name_urdu": "Name in Urdu", "pass_percent": "Pass percentage", "fee_due_day": "Fee last date (day of month)"}
        widgets = {"grade_scale": forms.Textarea(attrs={"rows": 8, "class": "font-monospace"})}

    def clean_grade_scale(self):
        text = self.cleaned_data["grade_scale"]
        for line in text.splitlines():
            if not line.strip():
                continue
            parts = line.split(None, 1)
            try:
                float(parts[0])
                assert len(parts) == 2
            except (ValueError, AssertionError):
                raise forms.ValidationError(f'"{line}" should look like "80 A".')
        return text


# ---------------------------------------------------------------------------
# Classes & subjects
# ---------------------------------------------------------------------------
class ClassRoomForm(StyledModelForm):
    class Meta:
        model = ClassRoom
        fields = ["name", "colour", "default_fee", "class_teacher", "order"]
        widgets = {"colour": forms.TextInput(attrs={"type": "color", "class": "form-control-color"})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["class_teacher"].queryset = Teacher.objects.filter(status=Teacher.Status.ACTIVE)
        self.fields["colour"].widget.attrs["class"] = "form-control form-control-color"
        self.colour_choices = CLASS_COLOURS


class SubjectForm(StyledModelForm):
    class Meta:
        model = Subject
        fields = ["name"]
        labels = {"name": "Subject name"}


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------
class StudentForm(StyledModelForm):
    class Meta:
        model = Student
        fields = [
            "name", "father_name", "mother_name", "gender", "date_of_birth", "b_form_no", "father_cnic",
            "phone", "address", "photo", "previous_school", "blood_group", "medical_notes",
            "classroom", "roll_no", "admission_date", "monthly_fee", "discount", "remarks",
        ]
        widgets = {"date_of_birth": DATE, "admission_date": DATE, "remarks": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *a, fee_locked=False, **kw):
        super().__init__(*a, **kw)
        self.fee_locked = fee_locked
        if fee_locked:
            # Only the owner sets fees and discounts. Office staff see them but can't change them.
            for name in ("monthly_fee", "discount"):
                self.fields[name].disabled = True
                self.fields[name].required = False
                self.fields[name].help_text = "Only the owner can change this."
        self.fields["classroom"].required = True
        self.fields["classroom"].empty_label = "Choose class"
        self.fields["discount"].required = False
        self.fields["gender"].choices = [("", "—")] + list(self.fields["gender"].choices)[1:]
        self.fields["blood_group"].choices = [("", "—")] + list(self.fields["blood_group"].choices)[1:]
        self.fields["phone"].widget.attrs["placeholder"] = "03xx-xxxxxxx"
        self.fields["father_cnic"].widget.attrs["placeholder"] = "xxxxx-xxxxxxx-x"

    def clean_discount(self):
        return self.cleaned_data.get("discount") or 0

    def clean(self):
        data = super().clean()
        fee, disc = data.get("monthly_fee"), data.get("discount")
        if fee is not None and disc is not None and disc > fee:
            self.add_error("discount", "The discount can't be more than the fee.")
        return data


class StudentLeaveForm(StyledForm):
    left_on = forms.DateField(label="Left on", initial=timezone.localdate, widget=DATE)
    reason = forms.CharField(required=False, max_length=200, label="Reason (optional)")


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------
class TeacherForm(StyledModelForm):
    class Meta:
        model = Teacher
        fields = ["name", "father_name", "gender", "cnic", "phone", "address", "qualification", "subjects",
                  "joining_date", "salary", "status", "left_on", "remarks"]
        widgets = {"joining_date": DATE, "left_on": DATE, "remarks": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["gender"].choices = [("", "—")] + list(self.fields["gender"].choices)[1:]


# ---------------------------------------------------------------------------
# Fees
# ---------------------------------------------------------------------------
class MonthField(forms.DateField):
    widget = MONTH

    def __init__(self, **kw):
        kw.setdefault("input_formats", MONTH_FORMATS)
        super().__init__(**kw)

    def clean(self, value):
        d = super().clean(value)
        return d.replace(day=1) if d else d


class FeeEditForm(StyledModelForm):
    class Meta:
        model = Fee
        fields = ["amount", "discount", "note"]
        labels = {"amount": "Fee for this month", "discount": "Discount for this month"}

    def clean(self):
        data = super().clean()
        if data.get("discount") is not None and data.get("amount") is not None and data["discount"] > data["amount"]:
            self.add_error("discount", "The discount can't be more than the fee.")
        return data


class AddFeeMonthForm(StyledForm):
    month = MonthField(label="Month")


class PaymentForm(StyledModelForm):
    class Meta:
        model = FeePayment
        fields = ["amount", "paid_on", "note"]
        labels = {"amount": "Amount received", "paid_on": "Date received"}
        widgets = {"paid_on": DATE}

    def __init__(self, *a, balance=None, lock_date=False, **kw):
        super().__init__(*a, **kw)
        self.balance = balance
        if lock_date:
            # Office staff always record money on the day it is received.
            self.fields["paid_on"].disabled = True
            self.fields["paid_on"].initial = timezone.localdate()
            self.fields["paid_on"].help_text = "Today. Only the owner can enter a payment for another date."
        self.fields["note"].widget.attrs["placeholder"] = "Optional, e.g. paid by uncle"

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if self.balance is not None and amount > self.balance:
            raise forms.ValidationError(f"Only Rs. {self.balance:,.0f} is due for this month.")
        return amount


# ---------------------------------------------------------------------------
# Salaries
# ---------------------------------------------------------------------------
class SalaryForm(StyledModelForm):
    class Meta:
        model = Salary
        fields = ["amount", "paid_amount", "paid_on", "note"]
        labels = {"amount": "Salary for this month", "paid_amount": "Amount paid", "paid_on": "Paid on"}
        widgets = {"paid_on": DATE}

    def clean(self):
        data = super().clean()
        if data.get("paid_amount") and not data.get("paid_on"):
            data["paid_on"] = timezone.localdate()
        if data.get("paid_amount") is not None and data.get("amount") is not None and data["paid_amount"] > data["amount"]:
            self.add_error("paid_amount", "Paid can't be more than the salary.")
        if not data.get("paid_amount"):
            data["paid_on"] = None
        return data


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestForm(StyledModelForm):
    class Meta:
        model = Test
        fields = ["classroom", "kind", "name", "date"]
        widgets = {"date": DATE}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["classroom"].empty_label = "Choose class"
        self.fields["name"].widget.attrs["placeholder"] = "e.g. October monthly test"


# ---------------------------------------------------------------------------
# Other expenses
# ---------------------------------------------------------------------------
class ExpenseForm(StyledModelForm):
    class Meta:
        model = Expense
        fields = ["date", "category", "description", "amount"]
        widgets = {"date": DATE}
        labels = {"amount": "Amount (Rs.)", "description": "Details (optional)"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["description"].widget.attrs["placeholder"] = "e.g. October rent, LESCO bill"


# ---------------------------------------------------------------------------
# Paper fund and fines
# ---------------------------------------------------------------------------
class ChargeForm(StyledForm):
    WHO = [("student", "One student"), ("class", "A whole class")]
    HOW = [("fee", "Add it to a month's fee (paid with the fee, on the same challan and receipt)"),
           ("separate", "Keep it separate (its own slip and receipt)")]
    who = forms.ChoiceField(choices=WHO, widget=forms.RadioSelect, initial="student")
    student = forms.ModelChoiceField(queryset=Student.objects.none(), required=False)
    classroom = forms.ModelChoiceField(label="Class", queryset=ClassRoom.objects.none(), required=False,
                                       empty_label="Choose class")
    kind = forms.ChoiceField(label="Type", choices=Charge.Kind.choices)
    amount = forms.IntegerField(label="Amount (Rs.)", min_value=1)
    reason = forms.CharField(max_length=150, required=False,
                             help_text='Optional, e.g. "1st term exam papers" or "late for September".')
    date = forms.DateField(initial=timezone.localdate, widget=DATE)
    how = forms.ChoiceField(label="How to collect it", choices=HOW, widget=forms.RadioSelect, initial="fee")
    month = forms.DateField(label="Fee month", required=False, input_formats=MONTH_FORMATS, widget=MONTH,
                            help_text="If this month's fee isn't made yet, it is made now with the student's usual fee.")

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for name in ("who", "how"):
            self.fields[name].widget.attrs["class"] = "form-check-input"
        self.fields["student"].queryset = Student.objects.filter(status=Student.Status.ACTIVE).select_related("classroom").order_by("name")
        self.fields["student"].label_from_instance = lambda st: f"{st.name} — {st.classroom or 'no class'} ({st.admission_no})"
        self.fields["classroom"].queryset = ClassRoom.objects.order_by("order", "name")
        if not self.is_bound and not self.initial.get("month"):
            self.initial["month"] = timezone.localdate().replace(day=1)

    def clean(self):
        data = super().clean()
        if data.get("who") == "student" and not data.get("student"):
            self.add_error("student", "Choose the student.")
        if data.get("who") == "class" and not data.get("classroom"):
            self.add_error("classroom", "Choose the class.")
        if data.get("how") == "fee" and not data.get("month"):
            self.add_error("month", "Choose the fee month.")
        return data
