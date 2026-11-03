"""Popula um estúdio com dados de demonstração (salas, professores, planos, alunos, turmas,
chamadas das últimas semanas, uma reposição e uma aula cancelada).

Uso: uv run python -m app.cli seed-demo --slug demo [--reset]
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.api.deps import TenantContext
from app.core.security import hash_password
from app.db.base import TenantBase
from app.db.engines import central_session, tenant_session
from app.models.central import Studio
from app.models.tenant import ClassGroup, Discount, Plan, Room, Student, Teacher, User
from app.models.tenant.enums import AttendanceStatus, DiscountKind, UserRole
from app.schemas.catalog import SubscriptionCreate
from app.schemas.schedule import AttendanceItem
from app.services import attendance, credits, schedule

STUDENTS = [
    ("Mariana Costa", "11 98811-2233", "mariana.costa@email.com", "Hérnia de disco L4-L5. Evitar flexão profunda."),
    ("João Pereira", "11 97722-3344", "joao.p@email.com", None),
    ("Luciana Alves", "11 96633-4455", "lu.alves@email.com", "Gestante (20 semanas)."),
    ("Pedro Santos", "11 95544-5566", None, "Recuperação de lesão no joelho direito."),
    ("Fernanda Lima", "11 94455-6677", "fe.lima@email.com", None),
    ("Ricardo Gomes", "11 93366-7788", "ricardo.g@email.com", None),
    ("Beatriz Rocha", "11 92277-8899", "bia.rocha@email.com", "Escoliose leve."),
    ("Carlos Mendes", "11 91188-9900", None, None),
    ("Juliana Martins", "11 99900-1122", "ju.martins@email.com", None),
    ("André Ribeiro", "11 98899-0011", "andre.r@email.com", "Hipertenso, controlado."),
    ("Camila Ferreira", "11 97788-9900", "camila.f@email.com", None),
    ("Rafael Barbosa", "11 96677-8899", None, None),
    ("Patrícia Souza", "11 95566-7788", "pat.souza@email.com", "Prefere aulas pela manhã."),
    ("Gustavo Carvalho", "11 94455-6600", "gus.carvalho@email.com", None),
    ("Renata Dias", "11 93344-5500", "renata.dias@email.com", "Plano experimental."),
    ("Tatiana Nunes", "11 92233-4400", None, None),
]

# sala -> (professor, horários de início)
ROOMS = {
    "Reformer": (3, "Ana Paula", [7, 8, 9, 17, 18]),
    "Cadillac": (2, "Bruno Tavares", [8, 12, 18]),
    "Solo": (6, "Carla Menezes", [9, 17]),
}


def _wipe(db) -> None:
    for table in reversed(TenantBase.metadata.sorted_tables):
        if table.name != "users":
            db.execute(table.delete())
    db.commit()


def seed(slug: str, reset: bool = False) -> None:
    with central_session() as central:
        studio = central.scalar(select(Studio).where(Studio.slug == slug))
    if studio is None:
        raise SystemExit(f"Estúdio '{slug}' não existe")

    rng = random.Random(42)
    today = date.today()
    start = today - timedelta(days=28)

    with tenant_session(slug) as db:
        if reset:
            _wipe(db)
        elif db.scalar(select(Room.id)):
            raise SystemExit("Estúdio já possui dados. Use --reset para recriar.")

        admin = db.scalar(select(User).where(User.role == UserRole.ADMIN))
        if admin is None:
            raise SystemExit("Estúdio sem usuário admin")
        ctx = TenantContext(studio=studio, db=db, user=admin)

        # Professores e salas
        teachers: dict[str, Teacher] = {}
        pay = {"Ana Paula": ("60", "8"), "Bruno Tavares": ("70", "0"), "Carla Menezes": ("40", "10")}
        for name, (per_class, per_student) in pay.items():
            first = name.split()[0].lower()
            teachers[name] = Teacher(
                name=name,
                phones=["11 90000-0000"],
                emails=[f"{first}@studio.com"],
                pay_per_class=Decimal(per_class),
                pay_per_student=Decimal(per_student),
            )
            db.add(teachers[name])
        rooms = {name: Room(name=name, capacity=cap) for name, (cap, _, _) in ROOMS.items()}
        db.add_all(rooms.values())
        db.flush()

        # Login de professora para testar o papel "teacher"
        if not db.scalar(select(User).where(User.email == "ana@demo.com")):
            db.add(
                User(
                    name="Ana Paula",
                    email="ana@demo.com",
                    hashed_password=hash_password("admin123"),
                    role=UserRole.TEACHER,
                    teacher_id=teachers["Ana Paula"].id,
                )
            )

        # Planos e descontos
        plans = [
            Plan(name="1x por semana", sessions_per_week=1, total_classes=8, price=Decimal("220.00")),
            Plan(name="2x por semana", sessions_per_week=2, total_classes=16, price=Decimal("390.00")),
            Plan(name="3x por semana", sessions_per_week=3, total_classes=24, price=Decimal("520.00")),
            Plan(name="Experimental", description="Pacote de 4 aulas", sessions_per_week=1, total_classes=4,
                 price=Decimal("100.00")),
        ]
        db.add_all(plans)
        db.flush()
        discounts = [
            Discount(name="Família (10%)", kind=DiscountKind.PERCENT, value=Decimal("10")),
            Discount(name="Indicação", kind=DiscountKind.FIXED, value=Decimal("30"), plan_id=plans[1].id),
        ]
        db.add_all(discounts)
        db.commit()

        # Turmas (cada sala tem um professor fixo => sem conflitos)
        groups: list[ClassGroup] = []
        for room_name, (_, teacher_name, hours) in ROOMS.items():
            for weekday in range(5):
                for hour in hours:
                    group = ClassGroup(
                        room_id=rooms[room_name].id,
                        teacher_id=teachers[teacher_name].id,
                        weekday=weekday,
                        start_hour=hour,
                        capacity=rooms[room_name].capacity,
                        start_date=start,
                    )
                    db.add(group)
                    groups.append(group)
        db.commit()

        # Alunos com plano e turmas padrão
        occupancy = {g.id: 0 for g in groups}
        plan_cycle = [plans[1], plans[0], plans[2], plans[1], plans[0]]
        for i, (name, phone, email, notes) in enumerate(STUDENTS):
            student = Student(name=name, phones=[phone], emails=[email] if email else [], notes=notes)
            db.add(student)
            db.flush()
            plan = plans[3] if name == "Renata Dias" else plan_cycle[i % len(plan_cycle)]
            discount_id = discounts[0].id if i % 6 == 0 else None
            credits.create_subscription(
                db, student, SubscriptionCreate(plan_id=plan.id, discount_id=discount_id, start_date=start)
            )
            chosen: list[ClassGroup] = []
            for group in rng.sample(groups, len(groups)):
                if len(chosen) == plan.sessions_per_week:
                    break
                if occupancy[group.id] >= group.capacity:
                    continue
                if any(c.weekday == group.weekday for c in chosen):
                    continue
                chosen.append(group)
                occupancy[group.id] += 1
            schedule.set_schedule(db, student, [g.id for g in chosen], start)
        db.commit()

        # Chamadas das aulas passadas (expire_all: recarrega as turmas com os alunos recém-matriculados)
        db.expire_all()
        day = start
        while day < today:
            for group in groups:
                if not group.runs_on(day):
                    continue
                group = schedule.load_group(db, group.id)
                roster = schedule.build_roster(group, day, schedule.find_lesson(db, group.id, day))
                items = [
                    AttendanceItem(
                        student_id=r.student.id,
                        status=AttendanceStatus.PRESENT if rng.random() < 0.85 else AttendanceStatus.ABSENT,
                    )
                    for r in roster
                ]
                if items:
                    attendance.take_attendance(ctx, group, day, items)
            day += timedelta(days=1)

        # Uma reposição e uma aula cancelada na próxima semana
        next_monday = today + timedelta(days=7 - today.weekday())
        db.expire_all()
        for group in groups:
            group = schedule.load_group(db, group.id)
            roster = schedule.build_roster(group, next_monday, None) if group.runs_on(next_monday) else []
            if not roster:
                continue
            student_id = roster[0].student.id
            for target in groups:
                target_day = next_monday + timedelta(days=target.weekday)
                if target.weekday <= 1 or target.id == group.id:
                    continue
                try:
                    attendance.reschedule(ctx, group, next_monday, student_id, target.id, target_day)
                    break
                except Exception:
                    db.rollback()
            break

        friday = next_monday + timedelta(days=4)
        for group in groups:
            if group.weekday == 4 and group.start_hour == 18 and group.room_id == rooms["Cadillac"].id:
                attendance.cancel_lesson(ctx, schedule.load_group(db, group.id), friday, "Professor em congresso")

    print(f"Dados de demonstração criados no estúdio '{slug}'.")
