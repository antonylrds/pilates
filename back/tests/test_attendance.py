from datetime import timedelta

from tests.conftest import API, future_weekday, login, past_weekday


def test_attendance_consumes_credits_and_notifies_renewal(client, studio):
    room, teacher = studio.room(), studio.teacher()
    group = studio.group(room, teacher, 0, 7)
    plan = studio.plan(sessions_per_week=1, total_classes=2)
    maria = studio.student("Maria", plan, [group])

    studio.attendance(group, past_weekday(0, 3), [(maria, "present")])
    detail = client.get(f"{API}/students/{maria['id']}", headers=studio.h).json()
    assert detail["credits_remaining"] == 1
    assert client.get(f"{API}/notifications", headers=studio.h).json() == []

    # falta também consome (configuração padrão do estúdio)
    studio.attendance(group, past_weekday(0, 2), [(maria, "absent")])
    detail = client.get(f"{API}/students/{maria['id']}", headers=studio.h).json()
    assert detail["credits_remaining"] == 0 and detail["needs_renewal"] is True
    assert detail["subscription"]["status"] == "exhausted"

    notes = client.get(f"{API}/notifications", params={"unread_only": True}, headers=studio.h).json()
    assert len(notes) == 1 and notes[0]["kind"] == "plan_exhausted"
    assert "renovar" in notes[0]["message"] and notes[0]["student"]["name"] == "Maria"

    # aula sem créditos: registra e avisa
    studio.attendance(group, past_weekday(0, 1), [(maria, "present")])
    kinds = [n["kind"] for n in client.get(f"{API}/notifications", headers=studio.h).json()]
    assert kinds == ["no_credits", "plan_exhausted"]

    # renovação restaura o saldo; o horário padrão é mantido
    client.post(f"{API}/students/{maria['id']}/subscriptions", json={"plan_id": plan["id"]}, headers=studio.h)
    detail = client.get(f"{API}/students/{maria['id']}", headers=studio.h).json()
    assert detail["credits_remaining"] == 2 and len(detail["schedule"]) == 1


def test_correcting_attendance_returns_credit_when_absence_is_free(client, studio):
    client.patch(f"{API}/studio", json={"absence_consumes_credit": False}, headers=studio.h)
    room, teacher = studio.room(), studio.teacher()
    group = studio.group(room, teacher, 1, 9)
    plan = studio.plan(sessions_per_week=1, total_classes=4)
    joao = studio.student("João", plan, [group])
    day = past_weekday(1)

    studio.attendance(group, day, [(joao, "present")])
    assert client.get(f"{API}/students/{joao['id']}", headers=studio.h).json()["credits_remaining"] == 3
    lesson = studio.attendance(group, day, [(joao, "absent")])
    assert lesson["students"][0]["status"] == "absent"
    assert client.get(f"{API}/students/{joao['id']}", headers=studio.h).json()["credits_remaining"] == 4


def test_cannot_take_attendance_of_future_lesson_or_foreign_student(client, studio):
    room, teacher = studio.room(), studio.teacher()
    group = studio.group(room, teacher, 0, 7)
    plan = studio.plan(sessions_per_week=1)
    maria = studio.student("Maria", plan, [group])
    outsider = studio.student("Fora", plan)
    studio.attendance(group, future_weekday(0), [(maria, "present")], expected=400)
    studio.attendance(group, past_weekday(0), [(outsider, "present")], expected=400)
    # data em que a turma não acontece
    studio.attendance(group, past_weekday(1), [(maria, "present")], expected=400)


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
        json={"student_id": maria["id"], "target_class_group_id": wednesday["id"], "target_date": target_day.isoformat()},
        headers=studio.h,
    )
    assert r.status_code == 200, r.text
    origin = r.json()
    assert origin["students"][0]["status"] == "rescheduled"
    assert origin["students"][0]["rescheduled_to"]["date"] == target_day.isoformat()
    assert origin["status"] == "inactive" and origin["attendees_count"] == 0

    target = studio.lesson(wednesday, target_day)
    assert target["status"] == "confirmed"
    assert target["students"][0]["is_makeup"] is True
    assert target["students"][0]["makeup_from"]["date"] == origin_day.isoformat()

    detail = client.get(f"{API}/students/{maria['id']}", headers=studio.h).json()
    assert [s["class_group_id"] for s in detail["schedule"]] == [monday["id"]]  # horário padrão intacto
    assert detail["upcoming_makeups"][0]["date"] == target_day.isoformat()
    assert detail["credits_remaining"] == 4  # reagendar não consome aula

    # na semana seguinte Maria continua na segunda
    next_monday = studio.lesson(monday, origin_day + timedelta(weeks=1))
    assert next_monday["students"][0]["status"] == "pending"

    # desfazer
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
    day = past_weekday(0).isoformat()

    ok = client.post(f"{API}/lessons/{g_ana['id']}/{day}/attendance", json={"items": [{"student_id": maria["id"], "status": "present"}]}, headers=ana_headers)
    assert ok.status_code == 200
    denied = client.post(f"{API}/lessons/{g_beto['id']}/{day}/attendance", json={"items": [{"student_id": joao["id"], "status": "present"}]}, headers=ana_headers)
    assert denied.status_code == 403


def test_teacher_payment_report(client, studio):
    room, room2 = studio.room(capacity=5), studio.room("Sala 2", capacity=5)
    ana = studio.teacher("Ana", pay_per_class="50.00", pay_per_student="10.00")
    beto = studio.teacher("Beto", pay_per_class="40.00")
    g = studio.group(room, ana, 0, 7)
    g_empty = studio.group(room2, ana, 1, 7)
    plan = studio.plan(sessions_per_week=2, total_classes=10)
    s1 = studio.student("Maria", plan, [g])
    s2 = studio.student("João", plan, [g])
    s3 = studio.student("Lia", plan, [g])
    studio.student("Rui", plan, [g_empty])

    week1, week2 = past_weekday(0, 2), past_weekday(0, 1)
    studio.attendance(g, week1, [(s1, "present"), (s2, "present"), (s3, "absent")])
    # semana 2: Beto substitui a Ana
    client.patch(f"{API}/lessons/{g['id']}/{week2.isoformat()}", json={"teacher_id": beto["id"]}, headers=studio.h)
    studio.attendance(g, week2, [(s1, "present")])
    # aula em que todos faltaram não conta como aula dada
    studio.attendance(g_empty, past_weekday(1), [(studio.c.get(f"{API}/students", params={"q": "Rui"}, headers=studio.h).json()[0], "absent")])

    report = client.get(
        f"{API}/reports/teacher-payments",
        params={"date_from": (week1 - timedelta(days=7)).isoformat(), "date_to": week2.isoformat()},
        headers=studio.h,
    ).json()
    by_name = {t["teacher"]["name"]: t for t in report["teachers"]}
    assert by_name["Ana"]["lessons_given"] == 1
    assert by_name["Ana"]["total_presences"] == 2
    assert by_name["Ana"]["amount"] == "70.00"  # 50 + 2 x 10
    assert [s["name"] for s in by_name["Ana"]["lessons"][0]["present_students"]] == ["João", "Maria"]
    assert [s["name"] for s in by_name["Ana"]["lessons"][0]["absent_students"]] == ["Lia"]
    assert by_name["Beto"]["amount"] == "40.00"
    assert report["total_amount"] == "110.00"
