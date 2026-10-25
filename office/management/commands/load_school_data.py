"""
Set up the school's classes and load the students from the old Excel register.

    python manage.py load_school_data

Runs only when the database has no students yet, so it is safe to run again.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from office.models import CLASS_COLOURS, ClassRoom, School, Student

CLASSES = ["Play Group", "Nursery", "Prep", "Class 1", "Class 2", "Class 3", "Class 4", "Class 5",
           "Class 6", "Class 7", "Class 8", "Class 9", "Class 10"]
DEFAULT_FEES = {"Play Group": 1500, "Nursery": 1500, "Prep": 1700, "Class 1": 1800, "Class 2": 1800, "Class 3": 2000,
                "Class 4": 2000, "Class 5": 2200, "Class 6": 2400, "Class 7": 2400, "Class 8": 2600, "Class 9": 3000,
                "Class 10": 3000}


class Command(BaseCommand):
    help = "Create the 13 classes and load students from the old register (only into an empty database)."

    def add_arguments(self, parser):
        parser.add_argument("--classes-only", action="store_true", help="Create the classes but no students")

    @transaction.atomic
    def handle(self, *args, **opts):
        School.get()
        src = Path(__file__).resolve().parents[2] / "data" / "students_2026.json"
        # The school's own register is private and is not shipped with this copy; without it,
        # only the classes are created (with typical fees) and students are added in the app.
        data = json.loads(src.read_text("utf-8")) if src.exists() else {"default_fees": DEFAULT_FEES, "students": []}
        fees = data["default_fees"]

        created_classes = 0
        classes = {}
        for i, name in enumerate(CLASSES, start=1):
            c, made = ClassRoom.objects.get_or_create(
                name=name, defaults={"order": i, "colour": CLASS_COLOURS[(i - 1) % len(CLASS_COLOURS)],
                                     "default_fee": fees.get(name) or 0})
            classes[name] = c
            created_classes += made
        self.stdout.write(f"Classes ready ({created_classes} new).")

        if opts["classes_only"]:
            return
        if not data["students"]:
            self.stdout.write("No student register file, so no students were loaded. Add students in the app.")
            return
        if Student.objects.exists():
            self.stdout.write("Students already exist, so none were loaded.")
            return

        for row in data["students"]:
            Student.objects.create(
                name=row["name"], father_name=row["father"], gender=row["gender"],
                classroom=classes[row["cls"]], roll_no=row["roll"], admission_date=None,
                monthly_fee=row["fee"], discount=row["discount"],
                status=Student.Status.ACTIVE if row["status"] == "ACTIVE" else Student.Status.INACTIVE,
                remarks=row.get("remarks", ""),
            )
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(data['students'])} students from the old register."))
