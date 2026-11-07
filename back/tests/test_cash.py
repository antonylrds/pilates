from datetime import date, timedelta

from tests.conftest import API, LONG_AGO, future_weekday, login, past_weekday


def test_cash_report_receipts_teacher_payments_and_pending(client, studio):
    today = date.today()
    inside, outside = (today - timedelta(days=5)).isoformat(), (today - timedelta(days=60)).isoformat()
    period = {"date_from": (today - timedelta(days=10)).isoformat(), "date_to": today.isoformat()}

    room = studio.room(capacity=5)
    ana = studio.teacher("Ana", pay_per_class="50.00")
    group = studio.group(room, ana, 0, 7)
    plan = studio.plan(sessions_per_week=1, total_classes=10, price="500.00")
    free = studio.plan(sessions_per_week=0, total_classes=1, price="0.00", name="Gratuito")
    disc = studio.post("/discounts", {"name": "Indicação", "kind": "percent", "value": "10"})

    def student(name, plan, **sub):
        return studio.post("/students", {"name": name, "subscription": {"plan_id": plan["id"], "start_date": LONG_AGO, **sub}})

    maria = student("Maria", plan, is_paid=True, paid_at=inside, discount_id=disc["id"])  # recebe 450
    student("Velho", plan, is_paid=True, paid_at=outside)  # fora do período
    joao = student("João", plan)  # não pago -> a receber 500
    student("Gratis", free)  # R$ 0: não entra em "a receber"
    r = client.put(f"{API}/students/{maria['id']}/schedule", json={"class_group_ids": [group["id"]], "effective_from": LONG_AGO},
                   headers=studio.h)
    assert r.status_code == 200, r.text

    svc = studio.post("/services", {"name": "Fisioterapia", "price": "150.00"})
    r = client.post(f"{API}/students/{joao['id']}/services", json={
        "service_id": svc["id"], "room_id": room["id"], "teacher_id": ana["id"], "start_hour": 15,
        "price": "120.00", "start_date": future_weekday(2).isoformat(), "is_paid": True, "paid_at": inside}, headers=studio.h)
    assert r.status_code == 201, r.text

    # aula da Ana no período: 50 fixo + 40% de (450/10) = 50 + 18 = 68
    studio.complete(group, past_weekday(0), [(maria, "present")])

    cash = client.get(f"{API}/reports/cash", params=period, headers=studio.h)
    assert cash.status_code == 200, cash.text
    cash = cash.json()
    assert [(r["kind"], r["student"]["name"], r["gross"], r["discount"], r["amount"]) for r in cash["receipts"]] == [
        ("service", "João", "150.00", "30.00", "120.00"),
        ("plan", "Maria", "500.00", "50.00", "450.00"),
    ]
    assert cash["plans_total"] == "450.00" and cash["services_total"] == "120.00"
    assert cash["received_total"] == "570.00"
    assert cash["discounts_total"] == "80.00"
    assert [(t["teacher"]["name"], t["amount"]) for t in cash["teachers"]] == [("Ana", "68.00")]
    assert cash["teacher_payments_total"] == "68.00"  # devido pelas aulas
    assert cash["teacher_paid_total"] == "0.00" and cash["teacher_payments"] == []
    assert cash["net_total"] == "570.00"  # nada foi pago ao professor ainda: o resultado não desconta o devido
    assert [(p["kind"], p["student"]["name"], p["amount"]) for p in cash["pending"]] == [("plan", "João", "500.00")]
    assert cash["pending_total"] == "500.00"

    # O que foi PAGO ao professor no período entra como desconto; pendente/cancelado/fora do período não.
    def teacher_payment(amount, **extra):
        return studio.post("/payments", {"kind": "teacher", "teacher_id": ana["id"], "amount": amount, **extra})

    teacher_payment("60.00", is_paid=True, paid_at=inside, notes="Adiantamento")
    teacher_payment("100.00")  # pendente
    teacher_payment("999.00", is_paid=True, paid_at=outside)
    cancelled = teacher_payment("50.00", is_paid=True, paid_at=inside)
    client.post(f"{API}/payments/{cancelled['id']}/cancel", headers=studio.h)

    cash = client.get(f"{API}/reports/cash", params=period, headers=studio.h).json()
    assert [(p["teacher"]["name"], p["amount"], p["notes"]) for p in cash["teacher_payments"]] == [("Ana", "60.00", "Adiantamento")]
    assert cash["teacher_paid_total"] == "60.00"
    assert cash["teacher_payments_total"] == "68.00"
    assert [(t["teacher"]["name"], t["amount"], t["paid"]) for t in cash["teachers"]] == [("Ana", "68.00", "60.00")]
    assert cash["net_total"] == "510.00"  # 570 recebidos - 60 pagos


def test_cash_report_is_admin_only(client, studio):
    ana = studio.teacher("Ana")
    studio.post("/users", {"name": "Ana", "email": "ana@alpha.com", "password": "secret123", "role": "teacher",
                           "teacher_id": ana["id"]})
    headers = login(client, "alpha", "ana@alpha.com")
    today = date.today().isoformat()
    r = client.get(f"{API}/reports/cash", params={"date_from": today, "date_to": today}, headers=headers)
    assert r.status_code == 403
