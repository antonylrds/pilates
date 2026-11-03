from datetime import timedelta

from tests.conftest import API, future_weekday


def _move(client, studio, group, day, student, target_group, target_day, justification=None):
    r = client.post(
        f"{API}/lessons/{group['id']}/{day.isoformat()}/reschedule",
        json={
            "student_id": student["id"],
            "target_class_group_id": target_group["id"],
            "target_date": target_day.isoformat(),
            "justification": justification,
        },
        headers=studio.h,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _row(lesson, student):
    return next(s for s in lesson["students"] if s["student"]["id"] == student["id"])


def test_tracks_how_many_times_a_lesson_was_rescheduled(client, studio):
    room, teacher = studio.room(capacity=3), studio.teacher()
    mon = studio.group(room, teacher, 0, 7)
    wed = studio.group(room, teacher, 2, 7)
    fri = studio.group(room, teacher, 4, 7)
    plan = studio.plan(sessions_per_week=1)
    maria = studio.student("Maria", plan, [mon])
    m = future_weekday(0)
    w, f = m + timedelta(days=2), m + timedelta(days=4)

    _move(client, studio, mon, m, maria, wed, w, "Viagem")
    _move(client, studio, wed, w, maria, fri, f, "Médico")  # reagenda a própria reposição

    friday = _row(studio.lesson(fri, f), maria)
    assert friday["is_makeup"] and friday["status"] == "pending"
    assert friday["reschedule_count"] == 2
    assert friday["original_lesson"]["date"] == m.isoformat()
    assert friday["makeup_from"]["date"] == w.isoformat()
    assert _row(studio.lesson(wed, w), maria)["reschedule_count"] == 2
    assert _row(studio.lesson(mon, m), maria)["reschedule_count"] == 1

    # segunda cadeia, independente (semana seguinte)
    m2 = m + timedelta(weeks=1)
    _move(client, studio, mon, m2, maria, wed, m2 + timedelta(days=2))

    chains = client.get(f"{API}/students/{maria['id']}/reschedules", headers=studio.h).json()
    assert [(c["original_lesson"]["date"], c["reschedule_count"]) for c in chains] == [
        (m2.isoformat(), 1),
        (m.isoformat(), 2),
    ]
    first = chains[1]
    assert [(s["from_lesson"]["date"], s["to_lesson"]["date"], s["justification"]) for s in first["steps"]] == [
        (m.isoformat(), w.isoformat(), "Viagem"),
        (w.isoformat(), f.isoformat(), "Médico"),
    ]
    assert first["current_lesson"]["date"] == f.isoformat()
    assert first["current_status"] == "pending" and first["current_completed"] is False

    detail = client.get(f"{API}/students/{maria['id']}", headers=studio.h).json()
    by_date = {u["date"]: u for u in detail["upcoming_makeups"]}
    assert by_date[f.isoformat()]["reschedule_count"] == 2
    assert by_date[f.isoformat()]["original_date"] == m.isoformat()

    # desfazer o segundo reagendamento volta a cadeia para 1
    r = client.delete(f"{API}/lessons/{wed['id']}/{w.isoformat()}/reschedule/{maria['id']}", headers=studio.h)
    assert r.status_code == 200
    chains = client.get(f"{API}/students/{maria['id']}/reschedules", headers=studio.h).json()
    first = next(c for c in chains if c["original_lesson"]["date"] == m.isoformat())
    assert first["reschedule_count"] == 1 and first["current_lesson"]["date"] == w.isoformat()
    assert _row(studio.lesson(wed, w), maria)["reschedule_count"] == 1
