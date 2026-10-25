from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin

from .. import certificates as C
from .. import search
from ..models import ActivityLog, Certificate, Student, Teacher


def _kind_or_404(kind):
    if kind not in C.FIELDS:
        raise Http404
    return kind


def certificate_list(request):
    qs = Certificate.objects.select_related("student__classroom", "teacher")
    kind = request.GET.get("kind", "")
    if kind in C.FIELDS:
        qs = qs.filter(kind=kind)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(person_name__icontains=q) | qs.filter(serial_no__icontains=q)
    # picking a person for a new certificate
    pick = request.GET.get("pick", "")
    found_students, found_teachers = [], []
    pq = request.GET.get("pq", "").strip()
    if pick in C.FIELDS and pq:
        if pick in Certificate.TEACHER_KINDS:
            found_teachers = [t for t in Teacher.objects.all() if search.words_match(t.name, pq)][:30]
        else:
            for _, _, items in search.search(Student.objects.select_related("classroom"), pq):
                found_students += items
            found_students = search.sort_students(found_students, "name")[:30]
    return render(request, "office/certificate_list.html", {
        "certs": qs[:300], "kinds": Certificate.Kind.choices, "kind": kind, "q": q,
        "student_kinds": [(k, v) for k, v in Certificate.Kind.choices if k in Certificate.STUDENT_KINDS],
        "teacher_kinds": [(k, v) for k, v in Certificate.Kind.choices if k in Certificate.TEACHER_KINDS],
        "pick": pick, "pick_label": dict(Certificate.Kind.choices).get(pick, ""), "pq": pq,
        "found_students": found_students, "found_teachers": found_teachers,
    })


def _person(request, kind):
    if kind in Certificate.TEACHER_KINDS:
        tid = request.GET.get("teacher") or request.POST.get("teacher")
        if not str(tid).isdigit():
            return None, None
        return None, get_object_or_404(Teacher, pk=int(tid))
    sid = request.GET.get("student") or request.POST.get("student")
    if not str(sid).isdigit():
        return None, None
    return get_object_or_404(Student.objects.select_related("classroom"), pk=int(sid)), None


def _form_page(request, kind, student, teacher, values, cert=None, body=""):
    fields = [{"key": k, "label": C.F[k][0], "type": C.F[k][1], "help": C.F[k][2], "value": values.get(k, "")}
              for k in C.FIELDS[kind]]
    return render(request, "office/certificate_form.html", {
        "kind": kind, "title": dict(Certificate.Kind.choices)[kind], "fields": fields, "student": student,
        "teacher": teacher, "conduct": C.CONDUCT, "cert": cert, "body_html": body,
        "person_name": (student.name if student else teacher.name if teacher else values.get("name", "")),
        "earlier": [] if cert else Certificate.objects.filter(kind=kind, student=student, teacher=teacher)[:5],
    })


def certificate_new(request, kind):
    kind = _kind_or_404(kind)
    student, teacher = _person(request, kind)
    if not student and not teacher:
        return redirect(f"{reverse('office:certificate_list')}?pick={kind}")
    initial = C.initial_for_teacher(kind, teacher) if teacher else C.initial_for_student(kind, student)
    body = ""
    if request.method == "POST":
        data = C.clean_data(kind, request.POST)
        body = C.body_from(request.POST)
        if body:
            data["body_html"] = body
        if not data.get("name"):
            messages.error(request, "The name can't be empty.")
        else:
            cert = Certificate.objects.create(
                kind=kind, student=student, teacher=teacher, person_name=data["name"],
                issued_on=C.parse_date(data.get("issued_on")) or timezone.localdate(), data=data)
            ActivityLog.add("certificate", f"{cert.get_kind_display()} {cert.serial_no} issued to {cert.person_name}"
                                           + (" (wording edited)" if body else ""),
                            link=reverse("office:certificate_print", args=[cert.pk]))
            messages.success(request, f"{cert.get_kind_display()} issued, serial no. {cert.serial_no}. "
                                      "It is saved; you can print it again any time from Certificates.")
            return redirect("office:certificate_print", pk=cert.pk)
        values = C.to_form_values(data)
    else:
        values = C.to_form_values(C.clean_data(kind, initial))
    return _form_page(request, kind, student, teacher, values, body=body)


def certificate_edit(request, pk):
    """Change the details or the wording of a certificate already issued (same serial number)."""
    cert = get_object_or_404(Certificate.objects.select_related("student", "teacher"), pk=pk)
    if request.method == "POST":
        data = C.clean_data(cert.kind, request.POST)
        body = C.body_from(request.POST)
        if body:
            data["body_html"] = body
        cert.data = data
        cert.person_name = data.get("name") or cert.person_name
        cert.issued_on = C.parse_date(data.get("issued_on")) or cert.issued_on
        cert.save()
        ActivityLog.add("certificate", f"{cert.get_kind_display()} {cert.serial_no} of {cert.person_name} changed",
                        link=reverse("office:certificate_print", args=[cert.pk]))
        messages.success(request, f"{cert.serial_no} saved.")
        return redirect("office:certificate_print", pk=cert.pk)
    values = C.to_form_values(C.clean_data(cert.kind, cert.data))
    return _form_page(request, cert.kind, cert.student, cert.teacher, values, cert=cert,
                      body=cert.data.get("body_html", ""))


@xframe_options_sameorigin
def certificate_preview(request, kind):
    """The certificate exactly as it will print, from the values in the form (nothing is saved)."""
    kind = _kind_or_404(kind)
    src = request.POST if request.method == "POST" else request.GET
    data = C.clean_data(kind, src)
    body = C.body_from(src)
    if body:
        data["body_html"] = body
    ctx = C.render_context(kind, data, serial=src.get("serial", ""), preview=True)
    ctx["embed"] = src.get("embed") == "1"
    ctx["editable"] = src.get("edit") == "1"
    return render(request, "print/certificate.html", ctx)


def certificate_print(request, pk):
    cert = get_object_or_404(Certificate, pk=pk)
    ctx = C.render_context(cert.kind, cert.data, serial=cert.serial_no)
    ctx["cert"] = cert
    return render(request, "print/certificate.html", ctx)


def certificate_delete(request, pk):
    cert = get_object_or_404(Certificate, pk=pk)
    back = reverse("office:certificate_list")
    if request.method == "POST":
        cert.delete()
        ActivityLog.add("certificate", f"Cancelled {cert.get_kind_display()} {cert.serial_no} of {cert.person_name}")
        messages.success(request, f"{cert.serial_no} removed from the register.")
        return redirect(back)
    return render(request, "office/confirm.html", {
        "title": f"Remove {cert.serial_no} from the register?",
        "message": f"The {cert.get_kind_display()} of {cert.person_name} issued on {cert.issued_on:%d-%m-%Y} will no "
                   "longer be listed. Do this only for a certificate made by mistake.",
        "button": "Remove", "cancel_url": back,
    })
