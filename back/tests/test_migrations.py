"""Migrações aplicadas sobre bancos com dados (os demais testes usam bancos vazios)."""

from alembic import command
from sqlalchemy import create_engine, text

from app.db.engines import tenant_url
from app.db.migrations import _alembic_config


def test_freeze_pay_migration_keeps_data_and_backfills(tmp_path):
    url = tenant_url("migr")
    cfg = _alembic_config("tenant", url)
    command.upgrade(cfg, "45b145767d3d")  # antes do congelamento de pagamento

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (id, name, email, hashed_password, role, is_active) "
            "VALUES (1, 'Admin', 'a@a.com', 'x', 'admin', 1)"
        ))
        conn.execute(text(
            "INSERT INTO teachers (id, name, phones, emails, pay_per_class, pay_per_student, min_pay_per_lesson, is_active) "
            "VALUES (1, 'Ana', '[]', '[]', 30, 10, 50, 1)"
        ))
        conn.execute(text("INSERT INTO rooms (id, name, capacity, is_active) VALUES (1, 'Sala', 5, 1)"))
        conn.execute(text(
            "INSERT INTO class_groups (id, room_id, teacher_id, weekday, start_hour, capacity, start_date) "
            "VALUES (1, 1, 1, 0, 7, 5, '2026-01-05')"
        ))
        for sid in (1, 2, 3):
            conn.execute(text(f"INSERT INTO students (id, name, phones, emails, is_active) VALUES ({sid}, 'S{sid}', '[]', '[]', 1)"))
        # aula 1: 3 presentes (30 + 3x10 = 60); aula 2: 1 presente (40 -> mínimo 50); aula 3: não concluída
        for lid, day, done in ((1, "2026-01-05", True), (2, "2026-01-12", True), (3, "2026-01-19", False)):
            conn.execute(text(
                "INSERT INTO lessons (id, class_group_id, date, teacher_id, is_cancelled, completed_at, completed_by_id) "
                f"VALUES ({lid}, 1, '{day}', 1, 0, {'CURRENT_TIMESTAMP' if done else 'NULL'}, {'1' if done else 'NULL'})"
            ))
        conn.execute(text(
            "INSERT INTO plans (id, name, sessions_per_week, total_classes, price, is_active) "
            "VALUES (1, 'Mensal', 1, 8, 320, 1)"
        ))
        conn.execute(text(
            "INSERT INTO subscriptions (id, student_id, plan_id, start_date, total_classes, sessions_per_week, "
            "base_price, discount_amount, final_price, status) VALUES (1, 1, 1, '2026-01-01', 8, 1, 320, 0, 320, 'active')"
        ))
        rows = [(1, 1, "present"), (1, 2, "present"), (1, 3, "present"), (2, 1, "present"), (2, 2, "absent")]
        for lid, sid, st in rows:
            conn.execute(text(
                f"INSERT INTO attendances (lesson_id, student_id, status, is_makeup) VALUES ({lid}, {sid}, '{st}', 0)"
            ))

    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        # nenhuma chamada foi perdida ao recriar a tabela lessons (SQLite)
        assert conn.scalar(text("SELECT COUNT(*) FROM attendances")) == 5
        pay = conn.execute(
            text("SELECT id, pay_amount, pay_minimum_applied, min_pay_per_lesson FROM lessons ORDER BY id")
        ).fetchall()
    engine.dispose()
    assert [(r[0], float(r[1]) if r[1] is not None else None, bool(r[2])) for r in pay] == [
        (1, 60.0, False),
        (2, 50.0, True),
        (3, None, False),
    ]
    assert float(pay[0][3]) == 50.0

    # migração seguinte (percentual do plano): professor ganha 40% padrão, histórico mantido
    with engine.connect() as conn:
        assert float(conn.scalar(text("SELECT student_share_percent FROM teachers WHERE id = 1"))) == 40.0
        assert conn.scalar(text("SELECT student_share_percent FROM lessons WHERE id = 1")) is None
        # nome do plano congelado nas contratações existentes
        assert conn.scalar(text("SELECT plan_name FROM subscriptions WHERE id = 1")) == "Mensal"
    engine.dispose()
