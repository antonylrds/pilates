"""Controle de aulas dadas por professor e cálculo da remuneração."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.tenant import Attendance, ClassGroup, Lesson, Teacher
from app.models.tenant.enums import AttendanceStatus
from app.schemas.people import StudentSummary, TeacherSummary
from app.schemas.schedule import TeacherLessonReport, TeacherPaymentReport, TeacherPaymentsResponse


def teacher_payments(
    db: Session, date_from: date, date_to: date, teacher_id: int | None = None
) -> TeacherPaymentsResponse:
    """Aula dada = aula não cancelada com ao menos um aluno presente.

    Valor = aulas dadas x valor por aula + presenças x valor por aluno (valores atuais do professor).
    """
    query = (
        select(Lesson)
        .options(
            selectinload(Lesson.class_group).selectinload(ClassGroup.room),
            selectinload(Lesson.attendances).selectinload(Attendance.student),
        )
        .where(Lesson.date >= date_from, Lesson.date <= date_to, Lesson.is_cancelled.is_(False))
        .order_by(Lesson.date)
    )
    teachers_query = select(Teacher).order_by(Teacher.name)
    if teacher_id is not None:
        query = query.where(Lesson.teacher_id == teacher_id)
        teachers_query = teachers_query.where(Teacher.id == teacher_id)

    by_teacher: dict[int, list[Lesson]] = defaultdict(list)
    for lesson in db.scalars(query):
        by_teacher[lesson.teacher_id].append(lesson)

    reports: list[TeacherPaymentReport] = []
    for teacher in db.scalars(teachers_query):
        if teacher_id is None and teacher.id not in by_teacher and not teacher.is_active:
            continue
        lesson_reports = []
        for lesson in sorted(by_teacher.get(teacher.id, []), key=lambda l: (l.date, l.class_group.start_hour)):
            attendances = sorted(lesson.attendances, key=lambda a: a.student.name.lower())
            present = [a.student for a in attendances if a.status == AttendanceStatus.PRESENT]
            if not present:
                continue
            absent = [a.student for a in attendances if a.status == AttendanceStatus.ABSENT]
            lesson_reports.append(
                TeacherLessonReport(
                    date=lesson.date,
                    start_hour=lesson.class_group.start_hour,
                    class_group_id=lesson.class_group_id,
                    class_group_name=lesson.class_group.display_name,
                    room=lesson.class_group.room.name,
                    present_students=[StudentSummary.model_validate(s) for s in present],
                    absent_students=[StudentSummary.model_validate(s) for s in absent],
                    amount=teacher.pay_per_class + teacher.pay_per_student * len(present),
                )
            )
        presences = sum(len(r.present_students) for r in lesson_reports)
        reports.append(
            TeacherPaymentReport(
                teacher=TeacherSummary.model_validate(teacher),
                pay_per_class=teacher.pay_per_class,
                pay_per_student=teacher.pay_per_student,
                lessons_given=len(lesson_reports),
                total_presences=presences,
                amount=sum((r.amount for r in lesson_reports), Decimal("0.00")),
                lessons=lesson_reports,
            )
        )

    return TeacherPaymentsResponse(
        date_from=date_from,
        date_to=date_to,
        total_amount=sum((r.amount for r in reports), Decimal("0.00")),
        teachers=reports,
    )
