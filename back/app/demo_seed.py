"""Popula um estúdio com dados de demonstração (salas, professores, planos, alunos, turmas,
aulas concluídas nas últimas semanas, aulas pendentes de finalização, uma reposição e uma aula cancelada).

Uso: uv run python -m app.cli seed-demo --slug demo [--reset]
"""

import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.api.deps import TenantContext
from app.core.security import hash_password
from app.db.base import TenantBase
from app.db.engines import central_session, tenant_session
from app.models.central import Studio
from app.models.tenant import AuditLog, ClassGroup, Discount, Plan, Room, Service, Student, Teacher, User
from app.models.tenant.enums import (
    AttendanceStatus,
    DiscountKind,
    ServiceRecurrence,
    ServiceSessionStatus,
    UserRole,
)
from app.schemas.offerings import ServiceContractCreate
from app.schemas.catalog import SubscriptionCreate
from app.schemas.payments import PaymentCreate
from app.schemas.schedule import CompletionItem
from app.services import attendance, audit, credits, offerings, payments, schedule

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
        # (valor fixo por aula, % do valor da aula do plano por aluno presente, mínimo por aula)
        pay = {"Ana Paula": ("50", "40", "60"), "Bruno Tavares": ("40", "40", "60"), "Carla Menezes": ("30", "40", "50")}
        for name, (per_class, percent, minimum) in pay.items():
            first = name.split()[0].lower()
            teachers[name] = Teacher(
                name=name,
                phones=["11 90000-0000"],
                emails=[f"{first}@studio.com"],
                pay_per_class=Decimal(per_class),
                student_share_percent=Decimal(percent),
                min_pay_per_lesson=Decimal(minimum),
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
            Plan(name="Avulso gratuito", description="Plano de R$ 0 sem recorrência: o aluno é incluído nas aulas como avulso",
                 sessions_per_week=0, total_classes=1, price=Decimal("0.00")),
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
            paid = i % 4 != 3  # alguns ficam com pagamento pendente
            sub = credits.create_subscription(
                db,
                student,
                SubscriptionCreate(
                    plan_id=plan.id, discount_id=discount_id, start_date=start, is_paid=paid, paid_at=start if paid else None
                ),
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
            change = schedule.set_schedule(db, student, [g.id for g in chosen], start)
            audit.log(
                ctx,
                student.id,
                audit.Action.STUDENT_CREATED,
                f"Aluno cadastrado; plano {sub.plan_name} ({'pago' if paid else 'pagamento pendente'}); "
                f"turmas padrão: {', '.join(change.added)}",
            )
        db.commit()
        # registros de cadastro com a data de início (dados de demonstração)
        for entry in db.scalars(select(AuditLog)):
            entry.created_at = datetime.combine(start, datetime.min.time()).replace(hour=9)
        db.commit()

        # Troca de horário há 2 semanas (aparece no histórico de horários e de alterações)
        db.expire_all()
        mover = db.scalar(select(Student).where(Student.name == STUDENTS[1][0]))
        current_ids = [e.class_group_id for e in mover.enrollments if e.end_date is None]
        if current_ids:
            old = db.get(ClassGroup, current_ids[0])
            new = next(
                (
                    g for g in groups
                    if g.weekday != old.weekday and g.id not in current_ids and occupancy[g.id] < g.capacity
                ),
                None,
            )
            if new is not None:
                switch_day = today - timedelta(days=14)
                change = schedule.set_schedule(db, mover, [new.id, *current_ids[1:]], switch_day)
                audit.log(ctx, mover.id, audit.Action.SCHEDULE_CHANGED, change.describe(), change.as_changes())
                db.flush()
                db.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first().created_at = datetime.combine(
                    switch_day - timedelta(days=1), datetime.min.time()
                ).replace(hour=18, minute=30)
                db.commit()

        # Chamadas das aulas passadas (expire_all: recarrega as turmas com os alunos recém-matriculados)
        db.expire_all()
        day = start
        # Aulas de ontem e de hoje ficam pendentes de finalização (aparecem na tela "Finalizar aulas").
        reasons = ["Consulta médica", "Viagem a trabalho", "Avisou que estava doente", None]
        while day < today - timedelta(days=1):
            for group in groups:
                if not group.runs_on(day):
                    continue
                group = schedule.load_group(db, group.id)
                roster = schedule.build_roster(group, day, schedule.find_lesson(db, group.id, day))
                items = []
                for r in roster:
                    present = rng.random() < 0.85
                    items.append(
                        CompletionItem(
                            student_id=r.student.id,
                            status=AttendanceStatus.PRESENT if present else AttendanceStatus.ABSENT,
                            justification=None if present else rng.choice(reasons),
                        )
                    )
                if items:
                    attendance.complete_lesson(ctx, group, day, items)
            day += timedelta(days=1)

        # Renovação antecipada: a primeira aluna renova antes de acabar o plano atual
        first_student = db.scalar(select(Student).where(Student.name == STUDENTS[0][0]))
        credits.create_subscription(
            db, first_student, SubscriptionCreate(plan_id=plans[1].id, notes="Renovou antes do fim do plano")
        )
        db.commit()

        # Serviços avulsos: catálogo e algumas contratações
        catalog = {
            "Fisioterapia": ("150.00", "Sessão individual de fisioterapia (50 min)"),
            "RPG": ("180.00", "Reeducação Postural Global"),
            "Avaliação postural": ("120.00", "Avaliação inicial com relatório"),
        }
        services = {}
        for name, (price, description) in catalog.items():
            services[name] = Service(name=name, price=Decimal(price), description=description)
            db.add(services[name])
        # Sala e profissional dos atendimentos
        physio_room = Room(name="Sala de Fisioterapia", capacity=1)
        physio = Teacher(
            name="Daniela Rocha",
            phones=["11 90000-1111"],
            emails=["daniela@studio.com"],
            notes="Fisioterapeuta, RPG",
            pay_per_class=Decimal("0"),
            service_share_percent=Decimal("50"),
        )
        db.add_all([physio_room, physio])
        db.flush()

        def weekday_from(d: date) -> date:
            while d.weekday() > 4:
                d += timedelta(days=1)
            return d

        examples = [
            # (aluno, serviço, preço combinado, recorrência, sessões, início, hora, pago, observação)
            (STUDENTS[2][0], "Fisioterapia", None, ServiceRecurrence.WEEKLY, 6, today - timedelta(days=21), 10, True,
             "Gestante: foco em lombar e assoalho pélvico"),
            (STUDENTS[3][0], "RPG", "160.00", ServiceRecurrence.BIWEEKLY, 4, today - timedelta(days=14), 11, False,
             "Desconto combinado na recepção; pós-lesão no joelho"),
            (STUDENTS[0][0], "Avaliação postural", None, ServiceRecurrence.NONE, 1, today + timedelta(days=3), 14,
             False, None),
        ]
        yesterday = today - timedelta(days=1)
        for student_name, service_name, price, recurrence, n, start_day, hour, paid, note in examples:
            who = db.scalar(select(Student).where(Student.name == student_name))
            start_day = weekday_from(start_day)
            contract = offerings.contract_service(
                db,
                studio,
                who,
                ServiceContractCreate(
                    service_id=services[service_name].id,
                    room_id=physio_room.id,
                    teacher_id=physio.id,
                    start_hour=hour,
                    price=Decimal(price) if price else None,
                    recurrence=recurrence,
                    occurrences=n,
                    start_date=start_day,
                    is_paid=paid,
                    paid_at=start_day if paid else None,
                    notes=note,
                ),
            )
            # sessões antigas finalizadas; as de ontem e hoje ficam para a tela "Finalizar aulas"
            for i, session in enumerate(contract.sessions):
                if session.date < yesterday:
                    offerings.complete_session(ctx, session, present=i != 1, justification=None if i != 1 else "Desmarcou em cima da hora")
            audit.log(ctx, who.id, audit.Action.SERVICE_CONTRACTED, f"Serviço avulso contratado: {service_name}")
        db.commit()

        # Pagamentos de professores (nos professores criados acima, inclusive a fisioterapeuta):
        # pagos em datas diferentes, pendentes e um cancelado, para a ficha do professor e o caixa terem o que mostrar.
        teachers_by_name = {**teachers, physio.name: physio}
        month_start = today.replace(day=1)
        prev_end = month_start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        # (professor, valor, período, pago há N dias | None = pendente, observação, cancelar)
        teacher_payments = [
            ("Ana Paula", "650.00", (prev_start, prev_end), 20, "Fechamento do mês anterior", False),
            ("Ana Paula", "420.00", (month_start, today), 3, "Pagamento parcial do mês", False),
            ("Bruno Tavares", "580.00", (prev_start, prev_end), 12, "Fechamento do mês anterior", False),
            ("Bruno Tavares", "300.00", (month_start, today), None, "Aguardando fechamento do mês", False),
            ("Carla Menezes", "410.00", (prev_start, prev_end), 9, None, False),
            ("Carla Menezes", "150.00", (month_start, today), 2, "Adiantamento", False),
            ("Carla Menezes", "200.00", (month_start, today), 6, "Lançado em duplicidade", True),
            ("Daniela Rocha", "350.00", (prev_start, prev_end), 6, "Atendimentos de fisioterapia/RPG", False),
            ("Daniela Rocha", "280.00", (month_start, today), None, None, False),
        ]
        for name, amount, (period_start, period_end), paid_days_ago, note, cancel in teacher_payments:
            paid = paid_days_ago is not None or cancel
            payment = payments.create_payment(
                db,
                PaymentCreate(
                    kind="teacher",
                    teacher_id=teachers_by_name[name].id,
                    amount=Decimal(amount),
                    period_start=period_start,
                    period_end=period_end,
                    is_paid=paid,
                    paid_at=today - timedelta(days=paid_days_ago if paid_days_ago is not None else 0) if paid else None,
                    notes=note,
                ),
            )
            if cancel:
                payments.cancel(payment, note)
        db.commit()

        # Uma reposição e uma aula cancelada na próxima semana
        next_monday = today + timedelta(days=7 - today.weekday())
        db.expire_all()
        for group in groups:
            group = schedule.load_group(db, group.id)
            roster = schedule.build_roster(group, next_monday, None) if group.runs_on(next_monday) else []
            if not roster:
                continue
            student_id = roster[0].student.id
            moved_to = None
            for target in groups:
                target_day = next_monday + timedelta(days=target.weekday)
                if target.weekday != 2 or target.id == group.id:  # quarta
                    continue
                try:
                    attendance.reschedule(
                        ctx, group, next_monday, student_id, target.id, target_day, "Compromisso no trabalho"
                    )
                    moved_to = (target, target_day)
                    break
                except Exception:
                    db.rollback()
            # A reposição é reagendada de novo (aula reagendada 2 vezes)
            if moved_to:
                origin, origin_day = moved_to
                for target in groups:
                    if target.weekday != 4:  # sexta
                        continue
                    try:
                        attendance.reschedule(
                            ctx, schedule.load_group(db, origin.id), origin_day, student_id, target.id,
                            next_monday + timedelta(days=4), "Consulta médica",
                        )
                        break
                    except Exception:
                        db.rollback()
            break

        friday = next_monday + timedelta(days=4)
        for group in groups:
            if group.weekday == 4 and group.start_hour == 18 and group.room_id == rooms["Cadillac"].id:
                attendance.cancel_lesson(ctx, schedule.load_group(db, group.id), friday, "Professor em congresso")

    print(f"Dados de demonstração criados no estúdio '{slug}'.")
