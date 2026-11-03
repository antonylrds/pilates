from datetime import date, timedelta

from tests.conftest import API, LONG_AGO, login, past_weekday


def _history(client, studio, student):
    return client.get(f"{API}/students/{student['id']}/history", headers=studio.h).json()


def test_create_student_with_paid_plan_and_schedule_is_logged(client, studio):
    room, teacher = studio.room(), studio.teacher("Ana")
    mon = studio.group(room, teacher, 0, 7)
    wed = studio.group(room, teacher, 2, 7)
    plan = studio.plan(sessions_per_week=2, total_classes=8, price="320.00", name="2x")

    student = studio.post(
        "/students",
        {
            "name": "Maria",
            "phones": ["11999990000"],
            "subscription": {"plan_id": plan["id"], "is_paid": True, "paid_at": "2026-11-01"},
            "class_group_ids": [mon["id"], wed["id"]],
        },
    )
    assert student["subscription"]["is_paid"] is True and student["subscription"]["paid_at"] == "2026-11-01"
    assert len(student["schedule"]) == 2

    [entry] = _history(client, studio, student)
    assert entry["action"] == "student_created" and entry["user_name"] == "Dona"
    assert "2x" in entry["description"] and "pago em 01/11/2026" in entry["description"]
    assert "Segunda 07h" in entry["description"] and "Quarta 07h" in entry["description"]
    assert entry["created_at"].startswith(date.today().isoformat())


def test_unpaid_plan_then_mark_as_paid(client, studio):
    plan = studio.plan()
    student = studio.post("/students", {"name": "João", "subscription": {"plan_id": plan["id"]}})
    sub = student["subscription"]
    assert sub["is_paid"] is False and sub["paid_at"] is None

    r = client.patch(
        f"{API}/students/{student['id']}/subscriptions/{sub['id']}/payment", json={"is_paid": True}, headers=studio.h
    )
    assert r.json()["is_paid"] is True and r.json()["paid_at"] == date.today().isoformat()
    # repetir sem mudança não gera registro
    client.patch(f"{API}/students/{student['id']}/subscriptions/{sub['id']}/payment", json={"is_paid": True}, headers=studio.h)

    entries = _history(client, studio, student)
    assert [e["action"] for e in entries] == ["payment_updated", "student_created"]
    assert "marcado como pago" in entries[0]["description"]
    assert entries[0]["changes"]["is_paid"] == {"from": False, "to": True}


def test_edit_info_logs_only_changed_fields(client, studio):
    student = studio.post("/students", {"name": "Bia", "phones": ["11911112222"], "notes": "nada"})
    r = client.patch(
        f"{API}/students/{student['id']}",
        json={"name": "Bia", "phones": ["11933334444", "1155556666"], "notes": "Hérnia"},
        headers=studio.h,
    )
    assert r.status_code == 200
    entry = _history(client, studio, student)[0]
    assert entry["action"] == "student_updated"
    assert entry["description"] == "Dados alterados: telefones, observações"  # nome não mudou
    assert entry["changes"]["phones"] == {"from": ["11911112222"], "to": ["11933334444", "1155556666"]}

    # PATCH sem mudança real não gera registro
    client.patch(f"{API}/students/{student['id']}", json={"notes": "Hérnia"}, headers=studio.h)
    assert len(_history(client, studio, student)) == 2


def test_schedule_change_keeps_history_and_logs_who_and_when(client, studio):
    room, teacher = studio.room(), studio.teacher("Ana")
    mon = studio.group(room, teacher, 0, 7)
    wed = studio.group(room, teacher, 2, 8)
    plan = studio.plan(sessions_per_week=1)
    maria = studio.student("Maria", plan, [mon])  # desde LONG_AGO
    day = past_weekday(0)
    studio.complete(mon, day, [(maria, "present")])

    # outro admin muda o horário
    studio.post("/users", {"name": "Recepção", "email": "rec@alpha.com", "password": "secret123", "role": "admin"})
    rec = login(client, "alpha", "rec@alpha.com")
    effective = date.today() + timedelta(days=1)
    r = client.put(
        f"{API}/students/{maria['id']}/schedule",
        json={"class_group_ids": [wed["id"]], "effective_from": effective.isoformat()},
        headers=rec,
    )
    assert r.status_code == 200
    assert [s["class_group_id"] for s in r.json()["schedule"]] == [mon["id"], wed["id"]]  # seg vale até hoje

    history = client.get(f"{API}/students/{maria['id']}/schedule/history", headers=studio.h).json()
    by_group = {h["class_group_id"]: h for h in history}
    assert by_group[mon["id"]]["start_date"] == LONG_AGO
    assert by_group[mon["id"]]["end_date"] == date.today().isoformat()
    assert by_group[wed["id"]]["start_date"] == effective.isoformat() and by_group[wed["id"]]["status"] == "future"

    entry = _history(client, studio, maria)[0]
    assert entry["action"] == "schedule_changed" and entry["user_name"] == "Recepção"
    assert entry["description"] == (
        f"Horário padrão alterado a partir de {effective:%d/%m/%Y}: removeu Segunda 07h - Sala 1; "
        "adicionou Quarta 08h - Sala 1"
    )
    assert entry["changes"]["removed"] == ["Segunda 07h - Sala 1"]

    # o histórico de aulas não muda com a troca de horário
    attendances = client.get(f"{API}/students/{maria['id']}/attendances", headers=studio.h).json()
    assert [(a["lesson"]["date"], a["status"]) for a in attendances] == [(day.isoformat(), "present")]


def test_plan_renewal_cancel_and_deactivation_are_logged(client, studio):
    room, teacher = studio.room(), studio.teacher()
    group = studio.group(room, teacher, 0, 7)
    plan = studio.plan(sessions_per_week=1, name="Mensal")
    maria = studio.student("Maria", plan, [group])

    renewal = client.post(
        f"{API}/students/{maria['id']}/subscriptions", json={"plan_id": plan["id"], "is_paid": True}, headers=studio.h
    ).json()
    client.post(f"{API}/students/{maria['id']}/subscriptions/{renewal['id']}/cancel", headers=studio.h)
    client.delete(f"{API}/students/{maria['id']}", headers=studio.h)
    client.post(f"{API}/students/{maria['id']}/reactivate", headers=studio.h)

    entries = _history(client, studio, maria)
    assert [e["action"] for e in entries[:4]] == [
        "student_reactivated",
        "student_deactivated",
        "plan_cancelled",
        "plan_added",
    ]
    assert "renovação antecipada" in entries[3]["description"]
    assert "turmas liberadas: Segunda 07h - Sala 1" in entries[1]["description"]
