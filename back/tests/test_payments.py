from datetime import date, timedelta

from tests.conftest import API, LONG_AGO, login


def _list(client, studio, **params):
    r = client.get(f"{API}/payments", params=params, headers=studio.h)
    assert r.status_code == 200, r.text
    return r.json()


def _student(studio, name, plan, **sub):
    return studio.post("/students", {"name": name, "subscription": {"plan_id": plan["id"], "start_date": LONG_AGO, **sub}})


def test_new_plan_creates_pending_payment_or_paid_when_requested(client, studio):
    plan = studio.plan(price="320.00", name="Mensal")
    disc = studio.post("/discounts", {"name": "Indicação", "kind": "percent", "value": "10"})
    ana = _student(studio, "Ana", plan, discount_id=disc["id"])
    bia = _student(studio, "Bia", plan, is_paid=True, paid_at="2026-10-05")

    data = _list(client, studio)
    assert data["count"] == 2
    by_student = {p["student"]["name"]: p for p in data["items"]}
    pending, paid = by_student["Ana"], by_student["Bia"]
    assert (pending["kind"], pending["status"], pending["amount"], pending["plan_name"]) == ("student", "pending", "288.00", "Mensal")
    assert pending["paid_at"] is None and pending["cancelled_at"] is None and pending["created_at"]
    assert (paid["status"], paid["paid_at"], paid["amount"]) == ("paid", "2026-10-05", "320.00")
    assert data["totals"] == {"pending": "288.00", "paid": "320.00", "cancelled": "0.00"}
    assert ana["subscription"]["is_paid"] is False and bia["subscription"]["is_paid"] is True


def test_adding_plan_to_existing_student_creates_payment(client, studio):
    plan = studio.plan()
    student = studio.student("Carla")
    r = client.post(f"{API}/students/{student['id']}/subscriptions",
                    json={"plan_id": plan["id"], "is_paid": True}, headers=studio.h)
    assert r.status_code == 201, r.text
    payments = _list(client, studio, student_id=student["id"])["items"]
    assert [(p["status"], p["paid_at"]) for p in payments] == [("paid", date.today().isoformat())]


def test_pay_pending_cancel_keep_subscription_in_sync(client, studio):
    plan = studio.plan()
    student = _student(studio, "Ana", plan)
    payment = _list(client, studio)["items"][0]
    sub_id = student["subscription"]["id"]

    def sub():
        return client.get(f"{API}/students/{student['id']}/subscriptions", headers=studio.h).json()[0]

    r = client.post(f"{API}/payments/{payment['id']}/pay", json={"paid_at": "2026-10-10"}, headers=studio.h)
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["paid_at"]) == ("paid", "2026-10-10")
    assert (sub()["is_paid"], sub()["paid_at"]) == (True, "2026-10-10")

    r = client.post(f"{API}/payments/{payment['id']}/pending", headers=studio.h)
    assert (r.json()["status"], r.json()["paid_at"]) == ("pending", None)
    assert sub()["is_paid"] is False

    r = client.post(f"{API}/payments/{payment['id']}/cancel", json={"notes": "Aluno desistiu"}, headers=studio.h)
    body = r.json()
    assert (body["status"], body["cancelled_at"], body["notes"]) == ("cancelled", date.today().isoformat(), "Aluno desistiu")
    # pagamento cancelado é terminal
    assert client.post(f"{API}/payments/{payment['id']}/pay", headers=studio.h).status_code == 400
    assert client.post(f"{API}/payments/{payment['id']}/pending", headers=studio.h).status_code == 400
    assert client.post(f"{API}/payments/{payment['id']}/cancel", headers=studio.h).status_code == 400
    assert sub()["id"] == sub_id


def test_student_payment_endpoint_still_works_and_updates_payment(client, studio):
    plan = studio.plan()
    student = _student(studio, "Ana", plan)
    sub_id = student["subscription"]["id"]
    r = client.patch(f"{API}/students/{student['id']}/subscriptions/{sub_id}/payment",
                     json={"is_paid": True, "paid_at": "2026-10-12"}, headers=studio.h)
    assert r.status_code == 200, r.text
    payments = _list(client, studio)["items"]
    assert [(p["status"], p["paid_at"]) for p in payments] == [("paid", "2026-10-12")]

    client.patch(f"{API}/students/{student['id']}/subscriptions/{sub_id}/payment", json={"is_paid": False}, headers=studio.h)
    assert [p["status"] for p in _list(client, studio)["items"]] == ["pending"]


def test_cancelling_plan_cancels_pending_payment_but_keeps_paid_one(client, studio):
    plan = studio.plan()
    ana = _student(studio, "Ana", plan)
    bia = _student(studio, "Bia", plan, is_paid=True)
    for student in (ana, bia):
        r = client.post(f"{API}/students/{student['id']}/subscriptions/{student['subscription']['id']}/cancel", headers=studio.h)
        assert r.status_code == 200, r.text
    status = {p["student"]["name"]: p["status"] for p in _list(client, studio)["items"]}
    assert status == {"Ana": "cancelled", "Bia": "paid"}


def test_notes_edited_from_payments_area_and_amount_rules(client, studio):
    plan = studio.plan()
    _student(studio, "Ana", plan)
    payment = _list(client, studio)["items"][0]
    r = client.patch(f"{API}/payments/{payment['id']}", json={"notes": "Combinou pagar dia 10"}, headers=studio.h)
    assert r.status_code == 200 and r.json()["notes"] == "Combinou pagar dia 10"
    # o valor do pagamento de aluno é o do plano
    assert client.patch(f"{API}/payments/{payment['id']}", json={"amount": "1.00"}, headers=studio.h).status_code == 400
    # data de pagamento só em pagamento pago
    assert client.patch(f"{API}/payments/{payment['id']}", json={"paid_at": "2026-10-01"}, headers=studio.h).status_code == 400
    client.post(f"{API}/payments/{payment['id']}/pay", headers=studio.h)
    r = client.patch(f"{API}/payments/{payment['id']}", json={"paid_at": "2026-10-01"}, headers=studio.h)
    assert r.json()["paid_at"] == "2026-10-01"


def test_manual_student_payment_requires_plan_without_active_payment(client, studio):
    plan = studio.plan(price="100.00")
    ana = _student(studio, "Ana", plan)
    bia = studio.student("Bia")
    body = {"kind": "student", "student_id": ana["id"], "subscription_id": ana["subscription"]["id"]}
    assert client.post(f"{API}/payments", json=body, headers=studio.h).status_code == 409  # já tem pagamento ativo

    payment = _list(client, studio)["items"][0]
    client.post(f"{API}/payments/{payment['id']}/cancel", headers=studio.h)
    r = client.post(f"{API}/payments", json={**body, "is_paid": True, "notes": "Pagou em dinheiro"}, headers=studio.h)
    assert r.status_code == 201, r.text
    assert (r.json()["status"], r.json()["amount"], r.json()["notes"]) == ("paid", "100.00", "Pagou em dinheiro")
    assert client.get(f"{API}/students/{ana['id']}/subscriptions", headers=studio.h).json()[0]["is_paid"] is True

    # plano de outro aluno / valor diferente do plano / campos de professor
    assert client.post(f"{API}/payments", json={**body, "student_id": bia["id"]}, headers=studio.h).status_code == 404
    assert client.post(f"{API}/payments", json={**body, "amount": "1.00"}, headers=studio.h).status_code in (400, 409)
    assert client.post(f"{API}/payments", json={**body, "teacher_id": 1}, headers=studio.h).status_code == 422


def test_teacher_payments(client, studio):
    ana = studio.teacher("Ana")
    r = client.post(f"{API}/payments", json={"kind": "teacher"}, headers=studio.h)
    assert r.status_code == 422
    r = client.post(f"{API}/payments", json={"kind": "teacher", "teacher_id": ana["id"]}, headers=studio.h)
    assert r.status_code == 422  # sem valor
    r = client.post(f"{API}/payments", json={"kind": "teacher", "teacher_id": ana["id"], "amount": "800.00",
                                              "period_start": "2026-10-01", "period_end": "2026-10-31"}, headers=studio.h)
    assert r.status_code == 201, r.text
    payment = r.json()
    assert (payment["kind"], payment["status"], payment["teacher"]["name"], payment["student"]) == ("teacher", "pending", "Ana", None)
    assert (payment["period_start"], payment["period_end"]) == ("2026-10-01", "2026-10-31")

    r = client.patch(f"{API}/payments/{payment['id']}", json={"amount": "850.00"}, headers=studio.h)
    assert r.json()["amount"] == "850.00"
    client.post(f"{API}/payments/{payment['id']}/pay", json={"paid_at": "2026-11-05"}, headers=studio.h)
    assert client.patch(f"{API}/payments/{payment['id']}", json={"amount": "1.00"}, headers=studio.h).status_code == 400
    assert client.post(f"{API}/payments", json={"kind": "teacher", "teacher_id": 999, "amount": "1"}, headers=studio.h).status_code == 404

    only = _list(client, studio, kind="teacher", teacher_id=ana["id"])
    assert only["count"] == 1 and only["totals"]["paid"] == "850.00"


def test_filters_by_student_status_and_date_range(client, studio):
    plan = studio.plan(price="100.00")
    ana = _student(studio, "Ana", plan, is_paid=True, paid_at="2026-09-10")
    _student(studio, "Bia", plan)
    _student(studio, "Caio", plan, is_paid=True, paid_at="2026-10-20")

    assert [p["student"]["name"] for p in _list(client, studio, student_id=ana["id"])["items"]] == ["Ana"]
    assert sorted(p["student"]["name"] for p in _list(client, studio, status="paid")["items"]) == ["Ana", "Caio"]
    assert [p["student"]["name"] for p in _list(client, studio, status="pending")["items"]] == ["Bia"]

    october = _list(client, studio, date_field="paid", date_from="2026-10-01", date_to="2026-10-31")
    assert [p["student"]["name"] for p in october["items"]] == ["Caio"] and october["count"] == 1
    assert october["totals"]["paid"] == "100.00"

    today = date.today()
    created = _list(client, studio, date_from=today.isoformat(), date_to=today.isoformat())
    assert created["count"] == 3
    assert _list(client, studio, date_from=(today + timedelta(days=1)).isoformat())["count"] == 0
    # paginação mantém o total
    page = _list(client, studio, limit=2)
    assert len(page["items"]) == 2 and page["count"] == 3
    assert client.get(f"{API}/payments", params={"date_from": "2026-10-02", "date_to": "2026-10-01"}, headers=studio.h).status_code == 400


def test_payments_are_admin_only_and_audited(client, studio):
    plan = studio.plan()
    student = _student(studio, "Ana", plan)
    payment = _list(client, studio)["items"][0]
    client.post(f"{API}/payments/{payment['id']}/pay", headers=studio.h)
    history = client.get(f"{API}/students/{student['id']}/history", headers=studio.h).json()
    assert any(h["action"] == "payment_updated" for h in history)

    ana = studio.teacher("Prof")
    studio.post("/users", {"name": "Prof", "email": "prof@alpha.com", "password": "secret123", "role": "teacher",
                           "teacher_id": ana["id"]})
    teacher_headers = login(client, "alpha", "prof@alpha.com")
    assert client.get(f"{API}/payments", headers=teacher_headers).status_code == 403
    assert client.post(f"{API}/payments/{payment['id']}/cancel", headers=teacher_headers).status_code == 403
