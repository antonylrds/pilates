from datetime import timedelta

from tests.conftest import API, future_weekday


def _drop_in(client, studio, group, day, student, expected=200, justification=None):
    r = client.post(
        f"{API}/lessons/{group['id']}/{day.isoformat()}/drop-in",
        json={"student_id": student["id"], "justification": justification},
        headers=studio.h,
    )
    assert r.status_code == expected, r.text
    return r.json()


def _row(lesson, student):
    return next((s for s in lesson["students"] if s["student"]["id"] == student["id"]), None)


def test_free_plan_without_recurrence_allows_drop_in_lessons(client, studio):
    room, teacher = studio.room(capacity=2), studio.teacher()
    mon = studio.group(room, teacher, 0, 8)
    wed = studio.group(room, teacher, 2, 8)
    plan = studio.plan(sessions_per_week=0, total_classes=2, price="0.00", name="Aula experimental")
    assert plan["sessions_per_week"] == 0 and plan["price"] == "0.00"
    ana = studio.student("Ana Avulsa", plan)
    assert ana["free_schedule_slots"] == 0

    # sem recorrência: não entra no horário padrão
    r = client.put(f"{API}/students/{ana['id']}/schedule", json={"class_group_ids": [mon["id"]]}, headers=studio.h)
    assert r.status_code == 400 and "avulso" in r.json()["detail"]

    m = future_weekday(0)
    lesson = _drop_in(client, studio, mon, m, ana, justification="Aula experimental")
    row = _row(lesson, ana)
    assert row["is_drop_in"] and row["is_makeup"] and row["status"] == "pending"
    assert row["original_lesson"] is None and row["makeup_from"] is None
    assert row["justification"] == "Aula experimental"
    assert lesson["status"] == "confirmed"
    # não vira horário padrão
    assert _row(studio.lesson(mon, m + timedelta(weeks=1)), ana) is None
    upcoming = client.get(f"{API}/students/{ana['id']}/upcoming-lessons", headers=studio.h).json()
    assert [(u["class_group_id"], u["date"]) for u in upcoming] == [(mon["id"], m.isoformat())]

    _drop_in(client, studio, mon, m, ana, expected=409)  # já está na aula
    _drop_in(client, studio, wed, m + timedelta(days=2), ana)
    # plano com 2 aulas: a terceira avulsa pendente excede o saldo
    r = _drop_in(client, studio, mon, m + timedelta(weeks=1), ana, expected=400)
    assert "não tem aulas disponíveis" in r["detail"]

    # remover libera o saldo de novo
    r = client.delete(f"{API}/lessons/{mon['id']}/{m.isoformat()}/drop-in/{ana['id']}", headers=studio.h)
    assert r.status_code == 200 and _row(r.json(), ana) is None
    _drop_in(client, studio, mon, m + timedelta(weeks=1), ana)


def test_drop_in_respects_capacity_and_can_be_rescheduled(client, studio):
    room, teacher = studio.room(capacity=1), studio.teacher()
    mon = studio.group(room, teacher, 0, 9)
    tue = studio.group(room, teacher, 1, 9)
    fixed_plan = studio.plan(sessions_per_week=1)
    free = studio.plan(sessions_per_week=0, total_classes=1, price="0.00", name="Cortesia")
    studio.student("Fixo", fixed_plan, [mon])
    bia = studio.student("Bia Avulsa", free)
    m = future_weekday(0)

    r = _drop_in(client, studio, mon, m, bia, expected=409)
    assert "lotada" in r["detail"]

    t = future_weekday(1)
    _drop_in(client, studio, tue, t, bia)
    # avulsa pode ser reagendada como qualquer aula; aí não é mais removível como avulsa
    r = client.post(
        f"{API}/lessons/{tue['id']}/{t.isoformat()}/reschedule",
        json={"student_id": bia["id"], "target_class_group_id": tue["id"], "target_date": (t + timedelta(weeks=1)).isoformat()},
        headers=studio.h,
    )
    assert r.status_code == 200, r.text
    moved = _row(studio.lesson(tue, t + timedelta(weeks=1)), bia)
    assert moved["is_makeup"] and not moved["is_drop_in"] and moved["original_lesson"]["date"] == t.isoformat()
    r = client.delete(f"{API}/lessons/{tue['id']}/{t.isoformat()}/drop-in/{bia['id']}", headers=studio.h)
    assert r.status_code == 400
    # a reposição da avulsa continua usando a única aula do plano
    r = _drop_in(client, studio, tue, t + timedelta(weeks=2), bia, expected=400)
    assert "não tem aulas disponíveis" in r["detail"]


def test_student_detail_shows_lessons_available_for_drop_in(client, studio):
    room, teacher = studio.room(capacity=3), studio.teacher()
    mon = studio.group(room, teacher, 0, 10)
    plan = studio.plan(sessions_per_week=0, total_classes=1, price="0.00", name="Gratuito")
    caio = studio.student("Caio", plan)
    detail = lambda: client.get(f"{API}/students/{caio['id']}", headers=studio.h).json()
    assert detail()["drop_in_available"] == 1
    _drop_in(client, studio, mon, future_weekday(0), caio)
    d = detail()
    assert d["credits_remaining"] == 1 and d["drop_in_available"] == 0
    r = _drop_in(client, studio, mon, future_weekday(0, 2), caio, expected=400)
    assert "não tem aulas disponíveis" in r["detail"]


def test_change_lesson_teacher_checks_conflicts(client, studio):
    room, room2 = studio.room(capacity=3), studio.room("Sala 2", capacity=3)
    ana, beto, cris = studio.teacher("Ana"), studio.teacher("Beto"), studio.teacher("Cris")
    mon = studio.group(room, ana, 0, 11)
    studio.group(room2, beto, 0, 11)  # Beto já dá aula no mesmo horário
    m = future_weekday(0)
    url = f"{API}/lessons/{mon['id']}/{m.isoformat()}"

    r = client.patch(url, json={"teacher_id": beto["id"]}, headers=studio.h)
    assert r.status_code == 409 and "Beto já dá a turma" in r.json()["detail"]

    r = client.patch(url, json={"teacher_id": cris["id"]}, headers=studio.h)
    assert r.status_code == 200
    lesson = r.json()
    assert lesson["teacher"]["name"] == "Cris" and lesson["default_teacher"]["name"] == "Ana"
    # só nesta data: a semana seguinte continua com a titular
    nxt = studio.lesson(mon, m + timedelta(weeks=1))
    assert nxt["teacher"]["name"] == "Ana"
