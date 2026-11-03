from datetime import timedelta

from tests.conftest import API, LONG_AGO, future_weekday, login, past_weekday


def test_completion_consumes_credits_and_notifies_renewal(client, studio):
    room, teacher = studio.room(), studio.teacher()
    group = studio.group(room, teacher, 0, 7)
    plan = studio.plan(sessions_per_week=1, total_classes=2)
    maria = studio.student("Maria", plan, [group])

    lesson = studio.complete(group, past_weekday(0, 3), [(maria, "present")])
    assert lesson["status"] == "completed" and lesson["completed_at"] and lesson["completed_by"] == "Dona"
    assert studio.credits(maria) == 1
    assert client.get(f"{API}/notifications", headers=studio.h).json() == []

    # falta também consome (configuração padrão do estúdio)
    studio.complete(group, past_weekday(0, 2), [(maria, "absent", {"justification": "Consulta médica"})])
    detail = client.get(f"{API}/students/{maria['id']}", headers=studio.h).json()
    assert detail["credits_remaining"] == 0 and detail["needs_renewal"] is True
    assert detail["subscription"]["status"] == "exhausted"

    notes = client.get(f"{API}/notifications", params={"unread_only": True}, headers=studio.h).json()
    assert len(notes) == 1 and notes[0]["kind"] == "plan_exhausted" and "renovar" in notes[0]["message"]

    # aula sem créditos: registra e avisa
    studio.complete(group, past_weekday(0, 1), [(maria, "present")])
    kinds = [n["kind"] for n in client.get(f"{API}/notifications", headers=studio.h).json()]
    assert kinds == ["no_credits", "plan_exhausted"]

    # justificativa fica no histórico
    history = client.get(f"{API}/students/{maria['id']}/attendances", headers=studio.h).json()
    assert [h["justification"] for h in history] == [None, "Consulta médica", None]
    assert all(h["lesson_completed"] for h in history)

    # renovação restaura o saldo; o horário padrão é mantido
    client.post(f"{API}/students/{maria['id']}/subscriptions", json={"plan_id": plan["id"]}, headers=studio.h)
    detail = client.get(f"{API}/students/{maria['id']}", headers=studio.h).json()
    assert detail["credits_remaining"] == 2 and len(detail["schedule"]) == 1


def test_all_students_must_be_informed(client, studio):
    room, teacher = studio.room(), studio.teacher()
    group = studio.group(room, teacher, 0, 7)
    plan = studio.plan(sessions_per_week=1)
    maria = studio.student("Maria", plan, [group])
    joao = studio.student("João", plan, [group])
    day = past_weekday(0)

    r = client.post(
        f"{API}/lessons/{group['id']}/{day.isoformat()}/complete",
        json={"items": [{"student_id": maria["id"], "status": "present"}]},
        headers=studio.h,
    )
    assert r.status_code == 400 and "João" in r.json()["detail"]
    # nada foi gravado: aula continua pendente e sem débito
    assert studio.lesson(group, day)["status"] == "confirmed"
    assert studio.credits(maria) == 8

    lesson = studio.complete(group, day, [(maria, "present"), (joao, "absent", {"justification": "Gripe"})])
    by_name = {s["student"]["name"]: s for s in lesson["students"]}
    assert by_name["João"]["status"] == "absent" and by_name["João"]["justification"] == "Gripe"
    assert by_name["Maria"]["justification"] is None
    # não pode concluir duas vezes
    studio.complete(group, day, [(maria, "present"), (joao, "present")], expected=400)


def test_cannot_complete_future_cancelled_or_wrong_day(client, studio):
    room, teacher = studio.room(), studio.teacher()
    group = studio.group(room, teacher, 0, 7)
    plan = studio.plan(sessions_per_week=1)
    maria = studio.student("Maria", plan, [group])
    outsider = studio.student("Fora", plan)

    studio.complete(group, future_weekday(0), [(maria, "present")], expected=400)  # ainda não começou
    studio.complete(group, past_weekday(0), [(maria, "present"), (outsider, "present")], expected=400)
    studio.complete(group, past_weekday(1), [(maria, "present")], expected=400)  # turma não acontece na terça

    day = past_weekday(0, 2)
    client.post(f"{API}/lessons/{group['id']}/{day.isoformat()}/cancel", json={"reason": "Feriado"}, headers=studio.h)
    studio.complete(group, day, [(maria, "present")], expected=400)


def test_reschedule_during_completion(client, studio):
    room, teacher = studio.room(), studio.teacher()
    monday = studio.group(room, teacher, 0, 7)
    wednesday = studio.group(room, teacher, 2, 7)
    plan = studio.plan(sessions_per_week=1, total_classes=4)
    maria = studio.student("Maria", plan, [monday])
    joao = studio.student("João", plan, [monday])
    origin_day = past_weekday(0)
    target_day = future_weekday(2)

    lesson = studio.complete(
        monday,
        origin_day,
        [
            (maria, "present"),
            (joao, "rescheduled", {"justification": "Passou mal", "target_class_group_id": wednesday["id"],
                                   "target_date": target_day.isoformat()}),
        ],
    )
    joao_row = next(s for s in lesson["students"] if s["student"]["name"] == "João")
    assert joao_row["status"] == "rescheduled" and joao_row["justification"] == "Passou mal"
    assert joao_row["rescheduled_to"]["date"] == target_day.isoformat()
    assert studio.credits(joao) == 4  # reagendar não consome
    assert studio.credits(maria) == 3

    target = studio.lesson(wednesday, target_day)
    assert target["students"][0]["is_makeup"] is True
    # reagendar exige a aula de destino
    r = client.post(
        f"{API}/lessons/{monday['id']}/{past_weekday(0, 2).isoformat()}/complete",
        json={"items": [{"student_id": maria["id"], "status": "present"},
                        {"student_id": joao["id"], "status": "rescheduled"}]},
        headers=studio.h,
    )
    assert r.status_code == 422


def test_reopen_returns_credits_and_removes_from_report(client, studio):
    room = studio.room()
    teacher = studio.teacher("Ana", pay_per_class="50.00", student_share_percent="0")
    group = studio.group(room, teacher, 1, 9)
    plan = studio.plan(sessions_per_week=1, total_classes=4)
    joao = studio.student("João", plan, [group])
    day = past_weekday(1)
    period = {"date_from": (day - timedelta(days=1)).isoformat(), "date_to": day.isoformat()}

    studio.complete(group, day, [(joao, "present")])
    assert studio.credits(joao) == 3
    report = client.get(f"{API}/reports/teacher-payments", params=period, headers=studio.h).json()
    assert report["total_amount"] == "50.00"

    r = client.post(f"{API}/lessons/{group['id']}/{day.isoformat()}/reopen", headers=studio.h)
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    assert r.json()["students"][0]["status"] == "pending"
    assert studio.credits(joao) == 4
    report = client.get(f"{API}/reports/teacher-payments", params=period, headers=studio.h).json()
    assert report["total_amount"] == "0.00"

    # com falta "gratuita", concluir com falta não debita
    client.patch(f"{API}/studio", json={"absence_consumes_credit": False}, headers=studio.h)
    studio.complete(group, day, [(joao, "absent")])
    assert studio.credits(joao) == 4


def test_pending_lessons(client, studio):
    room, room2 = studio.room(), studio.room("Sala 2")
    ana, beto = studio.teacher("Ana"), studio.teacher("Beto")
    g_ana = studio.group(room, ana, 0, 7)
    g_beto = studio.group(room2, beto, 0, 7)
    studio.group(room, ana, 0, 8)  # sem alunos: não aparece
    plan = studio.plan(sessions_per_week=1)
    maria = studio.student("Maria", plan, [g_ana])
    studio.student("João", plan, [g_beto])
    day = past_weekday(0)
    params = {"date_from": day.isoformat(), "date_to": day.isoformat()}

    pending = client.get(f"{API}/lessons/pending", params=params, headers=studio.h).json()
    assert {p["class_group_id"] for p in pending} == {g_ana["id"], g_beto["id"]}

    studio.post("/users", {"name": "Ana", "email": "ana@alpha.com", "password": "secret123", "role": "teacher", "teacher_id": ana["id"]})
    ana_headers = login(client, "alpha", "ana@alpha.com")
    mine = client.get(f"{API}/lessons/pending", params=params, headers=ana_headers).json()
    assert [p["class_group_id"] for p in mine] == [g_ana["id"]]

    studio.complete(g_ana, day, [(maria, "present")], headers=ana_headers)
    assert client.get(f"{API}/lessons/pending", params=params, headers=ana_headers).json() == []
    cal = client.get(f"{API}/calendar", params=params, headers=studio.h).json()
    assert next(e for e in cal if e["class_group_id"] == g_ana["id"])["status"] == "completed"


def test_reschedule_keeps_default_schedule(client, studio):
    room, teacher = studio.room(capacity=2), studio.teacher()
    monday = studio.group(room, teacher, 0, 7)
    wednesday = studio.group(room, teacher, 2, 7)
    plan = studio.plan(sessions_per_week=1, total_classes=4)
    maria = studio.student("Maria", plan, [monday])
    origin_day = future_weekday(0)
    target_day = origin_day + timedelta(days=2)

    r = client.post(
        f"{API}/lessons/{monday['id']}/{origin_day.isoformat()}/reschedule",
        json={"student_id": maria["id"], "target_class_group_id": wednesday["id"],
              "target_date": target_day.isoformat(), "justification": "Viagem"},
        headers=studio.h,
    )
    assert r.status_code == 200, r.text
    origin = r.json()
    assert origin["students"][0]["status"] == "rescheduled"
    assert origin["students"][0]["justification"] == "Viagem"
    assert origin["students"][0]["rescheduled_to"]["date"] == target_day.isoformat()
    assert origin["status"] == "inactive" and origin["attendees_count"] == 0

    target = studio.lesson(wednesday, target_day)
    assert target["status"] == "confirmed"
    assert target["students"][0]["is_makeup"] is True
    assert target["students"][0]["makeup_from"]["date"] == origin_day.isoformat()

    detail = client.get(f"{API}/students/{maria['id']}", headers=studio.h).json()
    assert [s["class_group_id"] for s in detail["schedule"]] == [monday["id"]]  # horário padrão intacto
    assert detail["upcoming_makeups"][0]["date"] == target_day.isoformat()
    assert detail["credits_remaining"] == 4

    next_monday = studio.lesson(monday, origin_day + timedelta(weeks=1))
    assert next_monday["students"][0]["status"] == "pending"

    r = client.delete(f"{API}/lessons/{monday['id']}/{origin_day.isoformat()}/reschedule/{maria['id']}", headers=studio.h)
    assert r.status_code == 200 and r.json()["students"][0]["status"] == "pending"
    assert studio.lesson(wednesday, target_day)["students"] == []


def test_reschedule_validations(client, studio):
    room, teacher = studio.room(capacity=1), studio.teacher()
    monday = studio.group(room, teacher, 0, 7)
    wednesday = studio.group(room, teacher, 2, 7)
    plan = studio.plan(sessions_per_week=1)
    maria = studio.student("Maria", plan, [monday])
    studio.student("Lia", plan, [wednesday])  # quarta lotada (capacidade 1)
    origin_day = future_weekday(0)

    def move(target_group, target_day):
        return client.post(
            f"{API}/lessons/{monday['id']}/{origin_day.isoformat()}/reschedule",
            json={"student_id": maria["id"], "target_class_group_id": target_group["id"], "target_date": target_day.isoformat()},
            headers=studio.h,
        )

    r = move(wednesday, origin_day + timedelta(days=2))
    assert r.status_code == 409 and "lotada" in r.json()["detail"]
    assert move(wednesday, origin_day + timedelta(days=3)).status_code == 400  # quinta: turma não acontece
    assert move(monday, past_weekday(0)).status_code == 400  # reposição no passado


def test_teacher_can_only_manage_own_lessons(client, studio):
    room, room2 = studio.room(), studio.room("Sala 2")
    ana, beto = studio.teacher("Ana"), studio.teacher("Beto")
    g_ana = studio.group(room, ana, 0, 7)
    g_beto = studio.group(room2, beto, 0, 7)
    plan = studio.plan(sessions_per_week=1)
    maria = studio.student("Maria", plan, [g_ana])
    joao = studio.student("João", plan, [g_beto])
    studio.post("/users", {"name": "Ana", "email": "ana@alpha.com", "password": "secret123", "role": "teacher", "teacher_id": ana["id"]})
    ana_headers = login(client, "alpha", "ana@alpha.com")
    day = past_weekday(0)

    studio.complete(g_ana, day, [(maria, "present")], headers=ana_headers)
    studio.complete(g_beto, day, [(joao, "present")], expected=403, headers=ana_headers)
    # professor não reabre aula
    r = client.post(f"{API}/lessons/{g_ana['id']}/{day.isoformat()}/reopen", headers=ana_headers)
    assert r.status_code == 403


def test_teacher_payment_report_counts_only_completed_lessons(client, studio):
    room, room2 = studio.room(capacity=5), studio.room("Sala 2", capacity=5)
    # 40% (padrão) do valor da aula do plano por aluno presente
    ana = studio.teacher("Ana", pay_per_class="50.00")
    beto = studio.teacher("Beto", pay_per_class="40.00", student_share_percent="0")
    g = studio.group(room, ana, 0, 7)
    g_empty = studio.group(room2, ana, 1, 7)
    plan = studio.plan(sessions_per_week=2, total_classes=10, price="500.00")  # R$ 50/aula -> 40% = R$ 20
    s1 = studio.student("Maria", plan, [g])
    s2 = studio.student("João", plan, [g])
    s3 = studio.student("Lia", plan, [g])
    rui = studio.student("Rui", plan, [g_empty])

    week1, week2, week3 = past_weekday(0, 3), past_weekday(0, 2), past_weekday(0, 1)
    studio.complete(g, week1, [(s1, "present"), (s2, "present"), (s3, "absent")])
    # semana 2: Beto substitui a Ana
    client.patch(f"{API}/lessons/{g['id']}/{week2.isoformat()}", json={"teacher_id": beto["id"]}, headers=studio.h)
    studio.complete(g, week2, [(s1, "present"), (s2, "absent"), (s3, "absent")])
    # semana 3: aula aconteceu mas não foi concluída => não conta
    client.patch(f"{API}/lessons/{g['id']}/{week3.isoformat()}", json={"notes": "sem chamada"}, headers=studio.h)
    # aula em que todos faltaram (sem mínimo) não conta como aula dada
    studio.complete(g_empty, past_weekday(1), [(rui, "absent")])

    report = client.get(
        f"{API}/reports/teacher-payments",
        params={"date_from": (week1 - timedelta(days=7)).isoformat(), "date_to": week3.isoformat()},
        headers=studio.h,
    ).json()
    by_name = {t["teacher"]["name"]: t for t in report["teachers"]}
    ana_lesson = by_name["Ana"]["lessons"][0]
    assert by_name["Ana"]["lessons_given"] == 1
    assert by_name["Ana"]["total_presences"] == 2
    assert by_name["Ana"]["amount"] == "90.00"  # 50 + 2 x 20
    assert [(s["name"], s["amount"], s["plan"]) for s in ana_lesson["present_students"]] == [
        ("João", "20.00", "2x semana"),
        ("Maria", "20.00", "2x semana"),
    ]
    assert [s["name"] for s in ana_lesson["absent_students"]] == ["Lia"]
    assert ana_lesson["student_share_percent"] == "40.00"
    assert by_name["Beto"]["amount"] == "40.00"  # 0% por aluno
    assert report["total_amount"] == "130.00"


def test_student_value_uses_price_paid_and_plan_classes(client, studio):
    # faltas não debitam, para que só o "Sem saldo" esgote o plano nas aulas anteriores
    client.patch(f"{API}/studio", json={"absence_consumes_credit": False}, headers=studio.h)
    room = studio.room(capacity=5)
    ana = studio.teacher("Ana", pay_per_class="0")
    group = studio.group(room, ana, 0, 7)
    plan = studio.plan(sessions_per_week=1, total_classes=10, price="500.00")
    small = studio.plan(sessions_per_week=1, total_classes=4, price="100.00", name="Experimental")
    family = studio.post("/discounts", {"name": "Família", "kind": "percent", "value": "10"})

    full = studio.student("Cheio", plan, [group])  # 500/10 = 50 -> 40% = 20.00
    discounted = studio.post(  # 450/10 = 45 -> 40% = 18.00
        "/students",
        {"name": "Desconto", "subscription": {"plan_id": plan["id"], "discount_id": family["id"], "start_date": LONG_AGO}},
    )
    client.put(
        f"{API}/students/{discounted['id']}/schedule",
        json={"class_group_ids": [group["id"]], "effective_from": LONG_AGO},
        headers=studio.h,
    )
    trial = studio.student("Experimental", small, [group])  # 100/4 = 25 -> 40% = 10.00
    no_credit = studio.student("Sem saldo", small, [group])
    # esgota as 4 aulas do plano do "Sem saldo" antes
    for weeks in (5, 4, 3, 2):
        studio.complete(
            group,
            past_weekday(0, weeks),
            [(full, "absent"), (discounted, "absent"), (trial, "absent"), (no_credit, "present")],
        )

    day = past_weekday(0, 1)
    studio.complete(group, day, [(full, "present"), (discounted, "present"), (trial, "present"), (no_credit, "present")])
    report = client.get(
        f"{API}/reports/teacher-payments",
        params={"date_from": day.isoformat(), "date_to": day.isoformat()},
        headers=studio.h,
    ).json()
    lesson = report["teachers"][0]["lessons"][0]
    assert {s["name"]: s["amount"] for s in lesson["present_students"]} == {
        "Cheio": "20.00",
        "Desconto": "18.00",
        "Experimental": "10.00",
        "Sem saldo": "0.00",  # presença sem aula disponível no plano
    }
    assert lesson["amount"] == "48.00"


def test_teacher_minimum_pay_per_lesson(client, studio):
    room = studio.room(capacity=6)
    ana = studio.teacher("Ana", pay_per_class="30.00", min_pay_per_lesson="50.00")
    group = studio.group(room, ana, 0, 7)
    plan = studio.plan(sessions_per_week=1, total_classes=10, price="125.00")  # 12,50/aula -> 40% = 5,00
    students = [studio.student(f"Aluno {i}", plan, [group]) for i in range(5)]
    w1, w2, w3 = past_weekday(0, 3), past_weekday(0, 2), past_weekday(0, 1)

    # 2 presentes: 30 + 2x5 = 40 -> mínimo 50
    studio.complete(group, w1, [(s, "present" if i < 2 else "absent") for i, s in enumerate(students)])
    # todos faltaram: recebe o mínimo
    studio.complete(group, w2, [(s, "absent") for s in students])
    # 5 presentes: 30 + 5x5 = 55 (acima do mínimo)
    studio.complete(group, w3, [(s, "present") for s in students])

    period = {"date_from": w1.isoformat(), "date_to": w3.isoformat()}
    report = client.get(f"{API}/reports/teacher-payments", params=period, headers=studio.h).json()
    ana_report = report["teachers"][0]
    assert ana_report["min_pay_per_lesson"] == "50.00"
    assert [(l["amount"], l["minimum_applied"]) for l in ana_report["lessons"]] == [
        ("50.00", True),
        ("50.00", True),
        ("55.00", False),
    ]
    assert ana_report["lessons_given"] == 3 and ana_report["lessons_without_presence"] == 1
    assert ana_report["total_presences"] == 7
    assert ana_report["amount"] == "155.00"

    # mudar a remuneração do professor ou o preço do plano...
    r = client.patch(
        f"{API}/teachers/{ana['id']}",
        json={"min_pay_per_lesson": "0", "pay_per_class": "100", "student_share_percent": "80"},
        headers=studio.h,
    )
    assert r.json()["min_pay_per_lesson"] == "0.00" and r.json()["student_share_percent"] == "80.00"
    client.patch(f"{API}/plans/{plan['id']}", json={"price": "999.00"}, headers=studio.h)
    report = client.get(f"{API}/reports/teacher-payments", params=period, headers=studio.h).json()
    ana_report = report["teachers"][0]
    # ...não altera o histórico congelado
    assert ana_report["amount"] == "155.00"
    assert ana_report["min_pay_per_lesson"] == "0.00"  # valor atual
    assert ana_report["lessons"][0]["min_pay_per_lesson"] == "50.00"  # valor da época
    assert ana_report["lessons"][0]["student_share_percent"] == "40.00"
    assert ana_report["lessons"][0]["pay_per_class"] == "30.00"

    # reabrir e concluir de novo aplica os valores atuais (sem mínimo: todos ausentes não paga)
    client.post(f"{API}/lessons/{group['id']}/{w2.isoformat()}/reopen", headers=studio.h)
    studio.complete(group, w2, [(s, "absent") for s in students])
    report = client.get(f"{API}/reports/teacher-payments", params=period, headers=studio.h).json()
    assert report["teachers"][0]["amount"] == "105.00"  # 50 + 55
    assert report["teachers"][0]["lessons_given"] == 2


def test_cannot_change_teacher_of_completed_lesson(client, studio):
    room = studio.room()
    ana, beto = studio.teacher("Ana"), studio.teacher("Beto")
    group = studio.group(room, ana, 0, 7)
    plan = studio.plan(sessions_per_week=1)
    maria = studio.student("Maria", plan, [group])
    day = past_weekday(0)
    studio.complete(group, day, [(maria, "present")])
    r = client.patch(f"{API}/lessons/{group['id']}/{day.isoformat()}", json={"teacher_id": beto["id"]}, headers=studio.h)
    assert r.status_code == 400 and "reabra" in r.json()["detail"]
    # observações continuam editáveis
    r = client.patch(f"{API}/lessons/{group['id']}/{day.isoformat()}", json={"notes": "ok"}, headers=studio.h)
    assert r.status_code == 200
