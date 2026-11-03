from datetime import date, timedelta

from tests.conftest import API, future_weekday, login, past_weekday


def _service(studio, name="Fisioterapia", price="150.00"):
    return studio.post("/services", {"name": name, "price": price, "description": f"Sessão de {name}"})


def _contract(client, studio, student, room, teacher, hour=10, expected=201, headers=None, **body):
    r = client.post(
        f"{API}/students/{student['id']}/services",
        json={"room_id": room["id"], "teacher_id": teacher["id"], "start_hour": hour, **body},
        headers=headers or studio.h,
    )
    assert r.status_code == expected, r.text
    return r.json()


def _setup(studio):
    return studio.room("Sala 1"), studio.room("Sala 2"), studio.teacher("Ana"), studio.teacher("Beto")


def test_catalog_crud_and_permissions(client, studio):
    fisio = _service(studio)
    _service(studio, "RPG", "180.00")
    assert [s["name"] for s in client.get(f"{API}/services", headers=studio.h).json()] == ["Fisioterapia", "RPG"]
    r = client.patch(f"{API}/services/{fisio['id']}", json={"is_active": False}, headers=studio.h)
    assert r.json()["is_active"] is False
    assert [s["name"] for s in client.get(f"{API}/services", headers=studio.h).json()] == ["RPG"]

    teacher = studio.teacher("Ana")
    studio.post("/users", {"name": "Ana", "email": "ana@alpha.com", "password": "secret123", "role": "teacher", "teacher_id": teacher["id"]})
    ana = login(client, "alpha", "ana@alpha.com")
    assert client.get(f"{API}/services", headers=ana).status_code == 200
    assert client.post(f"{API}/services", json={"name": "X", "price": "1"}, headers=ana).status_code == 403


def test_contract_price_recurrence_and_frozen_values(client, studio):
    s1, _, ana, _ = _setup(studio)
    rpg = _service(studio, "RPG", "180.00")
    maria = studio.student("Maria")

    single = _contract(client, studio, maria, s1, ana, service_id=rpg["id"], start_date="2026-12-01")
    assert single["occurrences"] == 1 and [s["date"] for s in single["sessions"]] == ["2026-12-01"]
    assert single["sessions"][0]["start_hour"] == 10 and single["sessions"][0]["room"]["name"] == "Sala 1"
    assert single["teacher"]["name"] == "Ana"

    custom = _contract(client, studio, maria, s1, ana, hour=11, service_id=rpg["id"], price="150.00", recurrence="weekly",
                       start_date="2026-11-02")
    assert (custom["price"], custom["list_price"], custom["price_changed"], custom["total_price"]) == ("150.00", "180.00", True, "600.00")
    assert [s["date"] for s in custom["sessions"]] == ["2026-11-02", "2026-11-09", "2026-11-16", "2026-11-23"]

    monthly = _contract(client, studio, maria, s1, ana, hour=12, service_id=rpg["id"], recurrence="monthly", occurrences=3,
                        start_date="2027-02-01")
    assert [s["date"] for s in monthly["sessions"]] == ["2027-02-01", "2027-03-01", "2027-04-01"]

    client.patch(f"{API}/services/{rpg['id']}", json={"price": "220.00", "name": "RPG Premium"}, headers=studio.h)
    history = client.get(f"{API}/students/{maria['id']}/services", headers=studio.h).json()
    assert {(h["service_name"], h["list_price"]) for h in history} == {("RPG", "180.00")}

    # validações
    _contract(client, studio, maria, s1, ana, expected=422, service_id=rpg["id"], occurrences=3)  # sem recorrência
    _contract(client, studio, maria, s1, ana, expected=400, service_id=rpg["id"], start_date="2026-12-05")  # sábado
    _contract(client, studio, maria, s1, ana, hour=19, expected=400, service_id=rpg["id"], start_date="2026-12-02")  # fechado


def test_services_and_classes_cannot_share_room_or_professional(client, studio):
    s1, s2, ana, beto = _setup(studio)
    carla = studio.teacher("Carla")
    fisio = _service(studio)
    group = studio.group(s1, ana, 0, 7)  # turma de segunda 7h na Sala 1 com a Ana
    maria = studio.student("Maria")
    monday = future_weekday(0)

    r = client.post(f"{API}/students/{maria['id']}/services", headers=studio.h, json={
        "service_id": fisio["id"], "room_id": s1["id"], "teacher_id": beto["id"], "start_hour": 7, "start_date": monday.isoformat()})
    assert r.status_code == 409 and "Sala 1" in r.json()["detail"]
    r = client.post(f"{API}/students/{maria['id']}/services", headers=studio.h, json={
        "service_id": fisio["id"], "room_id": s2["id"], "teacher_id": ana["id"], "start_hour": 7, "start_date": monday.isoformat()})
    assert r.status_code == 409 and "profissional" in r.json()["detail"]

    # sala 2 com o Beto está livre
    _contract(client, studio, maria, s2, beto, hour=7, service_id=fisio["id"], start_date=monday.isoformat())
    # outro serviço na mesma sala/hora conflita
    joao = studio.student("João")
    _contract(client, studio, joao, s2, carla, hour=7, expected=409, service_id=fisio["id"], start_date=monday.isoformat())
    # e uma turma nova na Sala 2 às segundas 7h também (o serviço já ocupa a sala)
    r = client.post(f"{API}/class-groups", headers=studio.h, json={
        "room_id": s2["id"], "teacher_id": carla["id"], "weekday": 0, "start_hour": 7})
    assert r.status_code == 409 and "Fisioterapia" in r.json()["detail"]

    # aula cancelada libera a sala naquele dia
    next_monday = monday + timedelta(weeks=1)
    client.post(f"{API}/lessons/{group['id']}/{next_monday.isoformat()}/cancel", json={"reason": "Feriado"}, headers=studio.h)
    _contract(client, studio, joao, s1, carla, hour=7, service_id=fisio["id"], start_date=next_monday.isoformat())


def test_services_show_in_calendar_and_pending_list(client, studio):
    s1, _, ana, _ = _setup(studio)
    fisio = _service(studio)
    maria = studio.student("Maria")
    past = past_weekday(0)
    c = _contract(client, studio, maria, s1, ana, hour=9, service_id=fisio["id"], start_date=past.isoformat())

    cal = client.get(f"{API}/calendar", params={"date_from": past.isoformat(), "date_to": past.isoformat()}, headers=studio.h).json()
    [entry] = [e for e in cal if e["kind"] == "service"]
    assert entry["class_group_id"] is None and entry["service_session_id"] == c["sessions"][0]["id"]
    assert entry["class_group_name"] == "Fisioterapia · Maria" and entry["student"]["name"] == "Maria"
    assert entry["room"]["name"] == "Sala 1" and entry["teacher"]["name"] == "Ana"
    assert entry["starts_at"].endswith("09:00:00") and entry["status"] == "confirmed"

    pending = client.get(f"{API}/lessons/pending", params={"date_from": past.isoformat(), "date_to": past.isoformat()}, headers=studio.h).json()
    assert [p["service_session_id"] for p in pending if p["kind"] == "service"] == [entry["service_session_id"]]


def test_completion_pays_professional_a_percentage(client, studio):
    s1, s2, ana, beto = _setup(studio)
    client.patch(f"{API}/teachers/{beto['id']}", json={"service_share_percent": "50"}, headers=studio.h)
    rpg = _service(studio, "RPG", "200.00")
    maria = studio.student("Maria")
    w1, w2 = past_weekday(1, 2), past_weekday(1, 1)
    # 4 sessões semanais: as duas primeiras já passaram; a 4ª é sempre futura (a 3ª pode ser hoje)
    c = _contract(client, studio, maria, s2, beto, hour=10, service_id=rpg["id"], price="180.00", recurrence="weekly",
                  occurrences=4, start_date=w1.isoformat())
    first, second, _, future = c["sessions"]

    studio.post("/users", {"name": "Beto", "email": "beto@alpha.com", "password": "secret123", "role": "teacher", "teacher_id": beto["id"]})
    studio.post("/users", {"name": "Ana", "email": "ana@alpha.com", "password": "secret123", "role": "teacher", "teacher_id": ana["id"]})
    beto_h, ana_h = login(client, "alpha", "beto@alpha.com"), login(client, "alpha", "ana@alpha.com")

    # só o profissional da sessão (ou admin) finaliza
    assert client.post(f"{API}/service-sessions/{first['id']}/complete", json={"status": "present"}, headers=ana_h).status_code == 403
    r = client.post(f"{API}/service-sessions/{first['id']}/complete", json={"status": "present"}, headers=beto_h)
    assert r.status_code == 200
    done = r.json()
    assert done["status"] == "done" and done["teacher_pay"] == "90.00" and done["share_percent"] == "50.00"  # 50% de 180
    assert client.post(f"{API}/service-sessions/{first['id']}/complete", json={"status": "present"}, headers=beto_h).status_code == 400

    r = client.post(f"{API}/service-sessions/{second['id']}/complete", json={"status": "absent", "justification": "Gripe"}, headers=beto_h)
    assert r.json()["status"] == "missed" and r.json()["teacher_pay"] == "0.00" and r.json()["justification"] == "Gripe"
    # sessão futura ainda não pode ser finalizada
    assert client.post(f"{API}/service-sessions/{future['id']}/complete", json={"status": "present"}, headers=beto_h).status_code == 400

    # % congelado: mudar depois não afeta
    client.patch(f"{API}/teachers/{beto['id']}", json={"service_share_percent": "10"}, headers=studio.h)
    period = {"date_from": w1.isoformat(), "date_to": w2.isoformat()}
    report = {t["teacher"]["name"]: t for t in client.get(f"{API}/reports/teacher-payments", params=period, headers=studio.h).json()["teachers"]}
    beto_r = report["Beto"]
    assert beto_r["services_given"] == 1 and beto_r["services_amount"] == "90.00" and beto_r["amount"] == "90.00"
    assert [(s["service_name"], s["present"], s["amount"]) for s in beto_r["services"]] == [("RPG", True, "90.00"), ("RPG", False, "0.00")]

    # reabrir (admin) tira do relatório
    assert client.post(f"{API}/service-sessions/{first['id']}/reopen", headers=beto_h).status_code == 403
    client.post(f"{API}/service-sessions/{first['id']}/reopen", headers=studio.h)
    report = {t["teacher"]["name"]: t for t in client.get(f"{API}/reports/teacher-payments", params=period, headers=studio.h).json()["teachers"]}
    assert report["Beto"]["services_amount"] == "0.00"


def test_cancel_contract_and_single_session(client, studio):
    s1, _, ana, _ = _setup(studio)
    fisio = _service(studio)
    maria = studio.student("Maria")
    start = past_weekday(2)
    c = _contract(client, studio, maria, s1, ana, service_id=fisio["id"], recurrence="weekly", occurrences=3, start_date=start.isoformat())
    base = f"{API}/students/{maria['id']}/services/{c['id']}"
    client.post(f"{API}/service-sessions/{c['sessions'][0]['id']}/complete", json={"status": "present"}, headers=studio.h)

    # cancela e reativa uma sessão
    r = client.patch(f"{base}/sessions/{c['sessions'][2]['id']}", json={"status": "cancelled"}, headers=studio.h).json()
    assert r["sessions"][2]["status"] == "cancelled"
    r = client.patch(f"{base}/sessions/{c['sessions'][2]['id']}", json={"status": "scheduled"}, headers=studio.h).json()
    assert r["sessions"][2]["status"] == "scheduled"
    # sessão finalizada não pode ser cancelada direto
    assert client.patch(f"{base}/sessions/{c['sessions'][0]['id']}", json={"status": "cancelled"}, headers=studio.h).status_code == 400

    r = client.patch(base, json={"notes": "Evoluindo bem", "is_paid": True}, headers=studio.h).json()
    assert r["notes"] == "Evoluindo bem" and r["is_paid"] is True
    r = client.post(f"{base}/cancel", headers=studio.h).json()
    assert r["situation"] == "cancelled"
    assert [s["status"] for s in r["sessions"]] == ["done", "cancelled", "cancelled"]

    actions = [e["action"] for e in client.get(f"{API}/students/{maria['id']}/history", headers=studio.h).json()]
    assert actions[:3] == ["service_cancelled", "service_updated", "service_contracted"]


def test_inactive_service_cannot_be_contracted(client, studio):
    s1, _, ana, _ = _setup(studio)
    fisio = _service(studio)
    client.patch(f"{API}/services/{fisio['id']}", json={"is_active": False}, headers=studio.h)
    _contract(client, studio, studio.student("Maria"), s1, ana, expected=400, service_id=fisio["id"],
              start_date=(date.today() + timedelta(days=30)).isoformat())
