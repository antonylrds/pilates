from tests.conftest import API, past_weekday


def _detail(client, studio, student):
    return client.get(f"{API}/students/{student['id']}", headers=studio.h).json()


def _history(client, studio, student):
    return client.get(f"{API}/students/{student['id']}/subscriptions", headers=studio.h).json()


def test_early_renewal_keeps_current_plan_until_all_classes_are_used(client, studio):
    room, teacher = studio.room(), studio.teacher()
    group = studio.group(room, teacher, 0, 7)
    trial = studio.plan(sessions_per_week=1, total_classes=3, price="150.00", name="Experimental")
    monthly = studio.plan(sessions_per_week=1, total_classes=8, price="320.00", name="Mensal")
    maria = studio.student("Maria", trial, [group])
    w4, w3, w2, w1 = (past_weekday(0, n) for n in (4, 3, 2, 1))

    studio.complete(group, w4, [(maria, "present")])
    studio.complete(group, w3, [(maria, "present")])

    # renova antes de acabar (resta 1 aula do Experimental)
    r = client.post(f"{API}/students/{maria['id']}/subscriptions", json={"plan_id": monthly["id"]}, headers=studio.h)
    assert r.status_code == 201 and r.json()["usage"] == "queued"

    detail = _detail(client, studio, maria)
    assert detail["subscription"]["plan_name"] == "Experimental"  # segue em uso
    assert detail["subscription"]["usage"] == "in_use"
    assert [s["plan_name"] for s in detail["queued_subscriptions"]] == ["Mensal"]
    assert detail["credits_remaining"] == 1 + 8 and detail["needs_renewal"] is False

    # a última aula do Experimental é debitada dele; sem aviso de renovação (já renovou)
    studio.complete(group, w2, [(maria, "present")])
    assert client.get(f"{API}/notifications", headers=studio.h).json() == []
    detail = _detail(client, studio, maria)
    assert detail["subscription"]["plan_name"] == "Mensal" and detail["subscription"]["credits_used"] == 0
    assert detail["queued_subscriptions"] == []

    # a próxima aula já é do Mensal
    studio.complete(group, w1, [(maria, "present")])
    history = _history(client, studio, maria)
    assert [(h["plan_name"], h["usage"], h["credits_used"]) for h in history] == [
        ("Mensal", "in_use", 1),
        ("Experimental", "finished", 3),
    ]
    mensal, experimental = history
    assert (experimental["first_lesson_date"], experimental["last_lesson_date"]) == (w4.isoformat(), w2.isoformat())
    assert (mensal["first_lesson_date"], mensal["last_lesson_date"]) == (w1.isoformat(), w1.isoformat())


def test_plan_history_values_are_frozen(client, studio):
    plan = studio.plan(sessions_per_week=2, total_classes=12, price="300.00", name="Semestral")
    family = studio.post("/discounts", {"name": "Família", "kind": "percent", "value": "10"})
    student = studio.post(
        "/students", {"name": "Bia", "subscription": {"plan_id": plan["id"], "discount_id": family["id"]}}
    )

    # o estúdio reajusta e renomeia o plano e o desconto depois
    client.patch(f"{API}/plans/{plan['id']}", json={"name": "Semestral 2027", "price": "999.00", "total_classes": 30}, headers=studio.h)
    client.patch(f"{API}/discounts/{family['id']}", json={"name": "Família (novo)"}, headers=studio.h)

    [sub] = _history(client, studio, student)
    assert sub["plan_name"] == "Semestral" and sub["discount_name"] == "Família"
    assert (sub["base_price"], sub["discount_amount"], sub["final_price"]) == ("300.00", "30.00", "270.00")
    assert sub["total_classes"] == 12 and sub["sessions_per_week"] == 2
    assert sub["price_per_lesson"] == "22.50"  # 270 / 12
    assert sub["plan"]["name"] == "Semestral 2027"  # cadastro atual, só como referência

    # nova contratação usa os valores atuais
    r = client.post(f"{API}/students/{student['id']}/subscriptions", json={"plan_id": plan["id"]}, headers=studio.h)
    assert (r.json()["plan_name"], r.json()["final_price"], r.json()["total_classes"]) == ("Semestral 2027", "999.00", 30)


def test_cancelled_plan_is_skipped(client, studio):
    room, teacher = studio.room(), studio.teacher()
    group = studio.group(room, teacher, 0, 7)
    first = studio.plan(sessions_per_week=1, total_classes=4, name="Antigo")
    second = studio.plan(sessions_per_week=1, total_classes=4, name="Novo")
    maria = studio.student("Maria", first, [group])
    renewal = client.post(f"{API}/students/{maria['id']}/subscriptions", json={"plan_id": second["id"]}, headers=studio.h).json()
    old = _detail(client, studio, maria)["subscription"]

    client.post(f"{API}/students/{maria['id']}/subscriptions/{old['id']}/cancel", headers=studio.h)
    studio.complete(group, past_weekday(0), [(maria, "present")])
    history = {h["plan_name"]: h for h in _history(client, studio, maria)}
    assert history["Antigo"]["usage"] == "cancelled" and history["Antigo"]["credits_used"] == 0
    assert history["Novo"]["usage"] == "in_use" and history["Novo"]["credits_used"] == 1
    assert renewal["id"] == history["Novo"]["id"]
