from tests.conftest import API, LONG_AGO


def test_plan_price_with_discounts(client, studio):
    plan = studio.plan(price="300.00")
    other = studio.plan(sessions_per_week=1, price="150.00")
    pct = studio.post("/discounts", {"name": "Família", "kind": "percent", "value": "10"})
    fixed = studio.post("/discounts", {"name": "Promo", "kind": "fixed", "value": "50", "plan_id": plan["id"]})

    r = client.get(f"{API}/plans/{plan['id']}/price", params={"discount_id": pct["id"]}, headers=studio.h).json()
    assert r["discount_amount"] == "30.00" and r["final_price"] == "270.00"
    r = client.get(f"{API}/plans/{plan['id']}/price", params={"discount_id": fixed["id"]}, headers=studio.h).json()
    assert r["final_price"] == "250.00"
    # desconto restrito a outro plano
    r = client.get(f"{API}/plans/{other['id']}/price", params={"discount_id": fixed["id"]}, headers=studio.h)
    assert r.status_code == 400
    # percentual acima de 100 é inválido
    assert client.post(f"{API}/discounts", json={"name": "X", "kind": "percent", "value": "120"}, headers=studio.h).status_code == 422


def test_plan_sessions_per_week_limited_to_3(client, studio):
    r = client.post(f"{API}/plans", json={"name": "4x", "sessions_per_week": 4, "total_classes": 16, "price": "1"}, headers=studio.h)
    assert r.status_code == 422


def test_student_detail(client, studio):
    room, teacher = studio.room(), studio.teacher("Carlos")
    g1 = studio.group(room, teacher, 0, 7)
    g2 = studio.group(room, teacher, 2, 7)
    plan = studio.plan(sessions_per_week=2, total_classes=8)
    discount = studio.post("/discounts", {"name": "Indicação", "kind": "fixed", "value": "20"})

    student = studio.post(
        "/students",
        {
            "name": "Maria",
            "phones": ["11999990000", "1133334444"],
            "emails": ["maria@x.com"],
            "notes": "Lombalgia",
            "subscription": {"plan_id": plan["id"], "discount_id": discount["id"]},
            "class_group_ids": [g1["id"], g2["id"]],
        },
    )
    detail = client.get(f"{API}/students/{student['id']}", headers=studio.h).json()
    assert detail["phones"] == ["11999990000", "1133334444"]
    assert detail["emails"] == ["maria@x.com"]
    assert detail["notes"] == "Lombalgia"
    assert detail["subscription"]["plan"]["name"] == "2x semana"
    assert detail["subscription"]["final_price"] == "300.00"
    assert detail["credits_remaining"] == 8 and detail["needs_renewal"] is False
    assert [(s["weekday_name"], s["start_hour"], s["teacher"]) for s in detail["schedule"]] == [
        ("Segunda", 7, "Carlos"),
        ("Quarta", 7, "Carlos"),
    ]
    assert detail["free_schedule_slots"] == 0

    assert len(client.get(f"{API}/students", params={"q": "1133"}, headers=studio.h).json()) == 1


def test_schedule_respects_plan_capacity_and_conflicts(client, studio):
    room, room2, teacher, teacher2 = studio.room(capacity=1), studio.room("Sala 2"), studio.teacher(), studio.teacher("Beto")
    g_mon = studio.group(room, teacher, 0, 8)
    g_tue = studio.group(room, teacher, 1, 8)
    g_wed = studio.group(room, teacher, 2, 8)
    g_mon_other_room = studio.group(room2, teacher2, 0, 8)
    plan2 = studio.plan(sessions_per_week=2)

    s = studio.student("Ana", plan2)
    put = lambda sid, ids: client.put(  # noqa: E731
        f"{API}/students/{sid}/schedule", json={"class_group_ids": ids, "effective_from": LONG_AGO}, headers=studio.h
    )
    r = put(s["id"], [g_mon["id"], g_tue["id"], g_wed["id"]])
    assert r.status_code == 400 and "2 turma" in r.json()["detail"]
    r = put(s["id"], [g_mon["id"], g_mon_other_room["id"]])
    assert r.status_code == 400 and "mesmo dia e horário" in r.json()["detail"]
    assert put(s["id"], [g_mon["id"], g_tue["id"]]).status_code == 200

    # turma lotada (sala com capacidade 1)
    other = studio.student("Bruno", plan2)
    r = put(other["id"], [g_mon["id"]])
    assert r.status_code == 409 and "lotada" in r.json()["detail"]

    # aluno sem plano não entra em turma
    no_plan = studio.student("Sem plano")
    assert put(no_plan["id"], [g_wed["id"]]).status_code == 400
