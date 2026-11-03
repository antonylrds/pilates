from datetime import date, timedelta

from tests.conftest import API, future_weekday, past_weekday


def test_discount_can_be_edited_without_changing_existing_subscriptions(client, studio):
    plan = studio.plan(price="300.00")
    disc = studio.post("/discounts", {"name": "Promo", "kind": "percent", "value": "10"})
    maria = studio.post("/students", {"name": "Maria", "subscription": {"plan_id": plan["id"], "discount_id": disc["id"]}})
    assert maria["subscription"]["final_price"] == "270.00"

    r = client.patch(f"{API}/discounts/{disc['id']}", json={"kind": "fixed", "value": "50", "plan_id": plan["id"]}, headers=studio.h)
    assert r.status_code == 200
    assert (r.json()["kind"], r.json()["value"], r.json()["plan_id"]) == ("fixed", "50.00", plan["id"])
    # contratação existente não muda
    [sub] = client.get(f"{API}/students/{maria['id']}/subscriptions", headers=studio.h).json()
    assert sub["final_price"] == "270.00"
    # volta a valer para todos os planos
    r = client.patch(f"{API}/discounts/{disc['id']}", json={"plan_id": None}, headers=studio.h)
    assert r.json()["plan_id"] is None
    # percentual > 100 é recusado
    r = client.patch(f"{API}/discounts/{disc['id']}", json={"kind": "percent", "value": "150"}, headers=studio.h)
    assert r.status_code == 400


def test_catalog_overview_counts(client, studio):
    room, teacher = studio.room(), studio.teacher()
    small = studio.plan(sessions_per_week=1, total_classes=4, name="Pequeno")
    big = studio.plan(sessions_per_week=2, total_classes=8, name="Grande")
    unused = studio.plan(name="Sem alunos")

    a = studio.post("/students", {"name": "Ana", "subscription": {"plan_id": small["id"], "is_paid": True}})
    studio.post("/students", {"name": "Bia", "subscription": {"plan_id": small["id"]}})  # pendente
    # A renova antecipadamente para o Grande (fica na fila, pendente)
    client.post(f"{API}/students/{a['id']}/subscriptions", json={"plan_id": big["id"]}, headers=studio.h)

    fisio = studio.post("/services", {"name": "Fisio", "price": "100"})
    start = past_weekday(0)
    client.post(f"{API}/students/{a['id']}/services", headers=studio.h, json={
        "service_id": fisio["id"], "room_id": room["id"], "teacher_id": teacher["id"], "start_hour": 15,
        "recurrence": "weekly", "occurrences": 3, "start_date": start.isoformat()})

    overview = client.get(f"{API}/catalog/overview", headers=studio.h).json()
    plans = {p["plan_id"]: p for p in overview["plans"]}
    assert (plans[small["id"]]["in_use"], plans[small["id"]]["queued"], plans[small["id"]]["unpaid"]) == (2, 0, 1)
    assert (plans[big["id"]]["in_use"], plans[big["id"]]["queued"], plans[big["id"]]["unpaid"]) == (0, 1, 1)
    assert plans[unused["id"]]["in_use"] == 0
    [svc] = overview["services"]
    # semanal a partir da última segunda: 1 passada + 2 futuras
    assert svc["active_contracts"] == 1 and svc["upcoming_sessions"] == 2
