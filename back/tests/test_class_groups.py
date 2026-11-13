from datetime import timedelta

from app.core import clock
from tests.conftest import API, future_weekday


def _create(client, studio, room, teacher, weekday, hour):
    return client.post(
        f"{API}/class-groups",
        json={"room_id": room["id"], "teacher_id": teacher["id"], "weekday": weekday, "start_hour": hour},
        headers=studio.h,
    )


def test_room_and_teacher_conflicts(client, studio):
    sala1, sala2 = studio.room("Sala 1"), studio.room("Sala 2")
    ana, beto = studio.teacher("Ana"), studio.teacher("Beto")

    assert _create(client, studio, sala1, ana, 0, 7).status_code == 201
    r = _create(client, studio, sala1, beto, 0, 7)
    assert r.status_code == 409 and "Sala 1" in r.json()["detail"]
    r = _create(client, studio, sala2, ana, 0, 7)
    assert r.status_code == 409 and "Ana" in r.json()["detail"]
    assert _create(client, studio, sala2, beto, 0, 7).status_code == 201  # outra sala e professor
    assert _create(client, studio, sala1, ana, 0, 8).status_code == 201  # horário seguinte


def test_business_hours_and_weekdays(client, studio):
    room, teacher = studio.room(), studio.teacher()
    assert _create(client, studio, room, teacher, 0, 6).status_code == 201
    assert _create(client, studio, room, teacher, 4, 18).status_code == 201  # última turma: 18h-19h
    assert _create(client, studio, room, teacher, 1, 5).status_code == 400
    assert _create(client, studio, room, teacher, 1, 19).status_code == 400
    assert _create(client, studio, room, teacher, 5, 9).status_code == 422  # sábado


def test_capacity_cannot_exceed_room(client, studio):
    room, teacher = studio.room(capacity=3), studio.teacher()
    r = client.post(
        f"{API}/class-groups",
        json={"room_id": room["id"], "teacher_id": teacher["id"], "weekday": 0, "start_hour": 7, "capacity": 5},
        headers=studio.h,
    )
    assert r.status_code == 400
    g = _create(client, studio, room, teacher, 0, 7).json()
    assert g["capacity"] == 3 and g["display_name"] == "Segunda 07h - Sala 1"


def test_end_group_frees_slot(client, studio):
    room, teacher = studio.room(), studio.teacher()
    g = _create(client, studio, room, teacher, 0, 7).json()
    end = clock.today() + timedelta(days=1)
    assert client.delete(f"{API}/class-groups/{g['id']}", params={"end_date": end.isoformat()}, headers=studio.h).status_code == 204
    # nova turma no mesmo slot começando após o encerramento
    r = client.post(
        f"{API}/class-groups",
        json={"room_id": room["id"], "teacher_id": teacher["id"], "weekday": 0, "start_hour": 7,
              "start_date": (end + timedelta(days=1)).isoformat()},
        headers=studio.h,
    )
    assert r.status_code == 201, r.text


def test_calendar_statuses(client, studio):
    room, teacher = studio.room(), studio.teacher("Ana")
    full = studio.group(room, teacher, 0, 7)
    empty = studio.group(room, teacher, 0, 8)
    plan = studio.plan(sessions_per_week=1)
    studio.student("Maria", plan, [full])

    monday = future_weekday(0)
    friday = monday + timedelta(days=4)
    cal = client.get(
        f"{API}/calendar", params={"date_from": monday.isoformat(), "date_to": friday.isoformat()}, headers=studio.h
    ).json()
    by_group = {e["class_group_id"]: e for e in cal}
    assert by_group[full["id"]]["status"] == "confirmed"
    assert by_group[full["id"]]["attendees_count"] == 1 and by_group[full["id"]]["available_spots"] == 2
    assert by_group[empty["id"]]["status"] == "inactive"
    assert by_group[full["id"]]["starts_at"].endswith("07:00:00")

    r = client.post(f"{API}/lessons/{full['id']}/{monday.isoformat()}/cancel", json={"reason": "Professora doente"}, headers=studio.h)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    detail = studio.lesson(full, monday)
    assert detail["cancel_reason"] == "Professora doente"
    assert detail["teacher"]["name"] == "Ana" and detail["students"][0]["student"]["name"] == "Maria"

    # filtro por professor e dias sem turma
    other = studio.teacher("Beto")
    assert client.get(f"{API}/calendar", params={"date_from": monday.isoformat(), "teacher_id": other["id"]}, headers=studio.h).json() == []
    saturday = monday + timedelta(days=5)
    assert client.get(f"{API}/calendar", params={"date_from": saturday.isoformat(), "date_to": saturday.isoformat()}, headers=studio.h).json() == []
