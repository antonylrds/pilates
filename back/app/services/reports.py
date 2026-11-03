"""Controle de aulas dadas por professor e cálculo da remuneração.

Regra (por aula concluída):
  valor do aluno presente = % do professor x (preço pago no plano / aulas do plano)
  valor da aula           = valor fixo por aula + soma dos valores dos presentes, nunca abaixo do mínimo
  todos ausentes          = apenas o mínimo (sem mínimo, a aula não gera pagamento)

Os valores são congelados na conclusão: mudar a remuneração do professor ou o preço do plano
não altera aulas já concluídas.
"""

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.tenant import (
    Attendance,
    ClassGroup,
    Lesson,
    ServiceContract,
    ServiceSession,
    Subscription,
    Teacher,
)
from app.models.tenant.enums import AttendanceStatus, ServiceSessionStatus
from app.schemas.people import StudentSummary, TeacherSummary
from app.schemas.schedule import (
    PresentStudent,
    TeacherLessonReport,
    TeacherPaymentReport,
    TeacherPaymentsResponse,
    TeacherServiceReport,
)

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def student_value(subscription: Subscription | None, percent: Decimal) -> Decimal:
    """Valor que um aluno presente gera ao professor: % x valor de uma aula do plano dele.

    Sem plano debitado (aluno sem aulas disponíveis), não há valor de referência: zero.
    """
    if subscription is None or subscription.total_classes <= 0:
        return ZERO
    per_lesson = subscription.final_price / subscription.total_classes
    return (per_lesson * percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_pay(per_class: Decimal, students_total: Decimal, minimum: Decimal, presences: int) -> tuple[Decimal, bool]:
    """Valor da aula e se o mínimo foi aplicado."""
    calculated = per_class + students_total if presences else ZERO
    if calculated < minimum:
        return minimum, True
    return calculated, False


def freeze_pay(db: Session, lesson: Lesson, teacher: Teacher) -> None:
    """Na conclusão: grava o valor de cada presente, os valores do professor e o valor da aula."""
    students_total = ZERO
    presences = 0
    for attendance in lesson.attendances:
        if attendance.status != AttendanceStatus.PRESENT:
            attendance.teacher_pay = None
            continue
        subscription = db.get(Subscription, attendance.subscription_id) if attendance.subscription_id else None
        attendance.teacher_pay = student_value(subscription, teacher.student_share_percent)
        students_total += attendance.teacher_pay
        presences += 1
    amount, minimum_applied = calculate_pay(
        teacher.pay_per_class, students_total, teacher.min_pay_per_lesson, presences
    )
    lesson.pay_per_class = teacher.pay_per_class
    lesson.student_share_percent = teacher.student_share_percent
    lesson.min_pay_per_lesson = teacher.min_pay_per_lesson
    lesson.pay_amount = amount
    lesson.pay_minimum_applied = minimum_applied


def clear_pay(lesson: Lesson) -> None:
    lesson.pay_per_class = lesson.student_share_percent = lesson.min_pay_per_lesson = lesson.pay_amount = None
    lesson.pay_minimum_applied = False
    for attendance in lesson.attendances:
        attendance.teacher_pay = None


def teacher_payments(
    db: Session, date_from: date, date_to: date, teacher_id: int | None = None
) -> TeacherPaymentsResponse:
    """Soma os valores congelados das aulas concluídas no período.

    Aula dada = aula concluída que gerou pagamento (com presentes, ou todos ausentes com mínimo).
    """
    query = (
        select(Lesson)
        .options(
            selectinload(Lesson.class_group).selectinload(ClassGroup.room),
            selectinload(Lesson.attendances).selectinload(Attendance.student),
            selectinload(Lesson.attendances).selectinload(Attendance.subscription).selectinload(Subscription.plan),
        )
        .where(
            Lesson.date >= date_from,
            Lesson.date <= date_to,
            Lesson.is_cancelled.is_(False),
            Lesson.completed_at.is_not(None),
        )
        .order_by(Lesson.date)
    )
    teachers_query = select(Teacher).order_by(Teacher.name)
    if teacher_id is not None:
        query = query.where(Lesson.teacher_id == teacher_id)
        teachers_query = teachers_query.where(Teacher.id == teacher_id)

    by_teacher: dict[int, list[Lesson]] = defaultdict(list)
    for lesson in db.scalars(query):
        by_teacher[lesson.teacher_id].append(lesson)

    # Sessões de serviços avulsos finalizadas (presente gera valor; falta aparece com R$ 0)
    sessions_query = (
        select(ServiceSession)
        .options(
            selectinload(ServiceSession.contract).selectinload(ServiceContract.student),
            selectinload(ServiceSession.room),
        )
        .where(
            ServiceSession.date >= date_from,
            ServiceSession.date <= date_to,
            ServiceSession.completed_at.is_not(None),
        )
        .order_by(ServiceSession.date, ServiceSession.start_hour)
    )
    if teacher_id is not None:
        sessions_query = sessions_query.where(ServiceSession.teacher_id == teacher_id)
    services_by_teacher: dict[int, list[TeacherServiceReport]] = defaultdict(list)
    for s in db.scalars(sessions_query):
        services_by_teacher[s.teacher_id].append(
            TeacherServiceReport(
                session_id=s.id,
                date=s.date,
                start_hour=s.start_hour or 0,
                service_name=s.contract.service_name,
                student=StudentSummary.model_validate(s.contract.student),
                room=s.room.name if s.room else "—",
                present=s.status == ServiceSessionStatus.DONE,
                price=s.contract.price,
                share_percent=s.share_percent or ZERO,
                amount=s.teacher_pay or ZERO,
            )
        )

    reports: list[TeacherPaymentReport] = []
    for teacher in db.scalars(teachers_query):
        busy = teacher.id in by_teacher or teacher.id in services_by_teacher
        if teacher_id is None and not busy and not teacher.is_active:
            continue
        lesson_reports = []
        for lesson in sorted(by_teacher.get(teacher.id, []), key=lambda l: (l.date, l.class_group.start_hour)):
            attendances = sorted(lesson.attendances, key=lambda a: a.student.name.lower())
            present = [a for a in attendances if a.status == AttendanceStatus.PRESENT]
            amount = lesson.pay_amount or ZERO
            if amount <= 0 and not present:
                continue  # todos faltaram e não há mínimo: não conta como aula dada
            lesson_reports.append(
                TeacherLessonReport(
                    date=lesson.date,
                    start_hour=lesson.class_group.start_hour,
                    class_group_id=lesson.class_group_id,
                    class_group_name=lesson.class_group.display_name,
                    room=lesson.class_group.room.name,
                    present_students=[
                        PresentStudent(
                            id=a.student.id,
                            name=a.student.name,
                            amount=a.teacher_pay,
                            plan=a.subscription.plan.name if a.subscription else None,
                        )
                        for a in present
                    ],
                    absent_students=[
                        StudentSummary.model_validate(a.student)
                        for a in attendances
                        if a.status == AttendanceStatus.ABSENT
                    ],
                    amount=amount,
                    minimum_applied=lesson.pay_minimum_applied,
                    pay_per_class=lesson.pay_per_class or ZERO,
                    student_share_percent=lesson.student_share_percent,
                    min_pay_per_lesson=lesson.min_pay_per_lesson or ZERO,
                )
            )
        service_reports = services_by_teacher.get(teacher.id, [])
        lessons_amount = sum((r.amount for r in lesson_reports), ZERO)
        services_amount = sum((r.amount for r in service_reports), ZERO)
        reports.append(
            TeacherPaymentReport(
                teacher=TeacherSummary.model_validate(teacher),
                pay_per_class=teacher.pay_per_class,
                student_share_percent=teacher.student_share_percent,
                min_pay_per_lesson=teacher.min_pay_per_lesson,
                service_share_percent=teacher.service_share_percent,
                lessons_given=len(lesson_reports),
                lessons_without_presence=sum(1 for r in lesson_reports if not r.present_students),
                total_presences=sum(len(r.present_students) for r in lesson_reports),
                lessons_amount=lessons_amount,
                services_given=sum(1 for r in service_reports if r.present),
                services_amount=services_amount,
                amount=lessons_amount + services_amount,
                lessons=lesson_reports,
                services=service_reports,
            )
        )

    return TeacherPaymentsResponse(
        date_from=date_from,
        date_to=date_to,
        total_amount=sum((r.amount for r in reports), ZERO),
        teachers=reports,
    )
