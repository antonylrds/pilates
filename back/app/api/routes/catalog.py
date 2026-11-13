"""Salas, planos, descontos e resumo do catálogo."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.core import clock
from app.api.deps import Admin, Staff, apply_update, get_or_404
from app.models.tenant import ClassGroup, Discount, Plan, Room, Service, ServiceContract, Subscription
from app.models.tenant.enums import (
    DiscountKind,
    ServiceContractStatus,
    ServiceSessionStatus,
    SubscriptionStatus,
    SubscriptionUsage,
)
from app.schemas.catalog import (
    CatalogOverview,
    DiscountCreate,
    DiscountRead,
    DiscountUpdate,
    PlanCreate,
    PlanRead,
    PlanUpdate,
    PlanUsage,
    PricePreview,
    RoomCreate,
    RoomRead,
    RoomUpdate,
    ServiceUsage,
)
from app.services.credits import resolve_price

router = APIRouter(tags=["rooms, plans & discounts"])


# ---------- Salas ----------
@router.get("/rooms", response_model=list[RoomRead])
def list_rooms(ctx: Staff, is_active: bool | None = True):
    query = select(Room).order_by(Room.name)
    if is_active is not None:
        query = query.where(Room.is_active == is_active)
    return ctx.db.scalars(query).all()


@router.post("/rooms", response_model=RoomRead, status_code=status.HTTP_201_CREATED)
def create_room(data: RoomCreate, ctx: Admin):
    room = Room(**data.model_dump())
    ctx.db.add(room)
    ctx.db.commit()
    ctx.db.refresh(room)
    return room


@router.patch("/rooms/{room_id}", response_model=RoomRead)
def update_room(room_id: int, data: RoomUpdate, ctx: Admin):
    room = get_or_404(ctx.db, Room, room_id, "Sala")
    if data.capacity is not None:
        bigger = ctx.db.scalar(
            select(ClassGroup.id).where(
                ClassGroup.room_id == room.id, ClassGroup.end_date.is_(None), ClassGroup.capacity > data.capacity
            )
        )
        if bigger:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Há turmas nesta sala com capacidade maior")
    if data.is_active is False:
        _ensure_room_unused(ctx, room.id)
    apply_update(room, data)
    ctx.db.commit()
    ctx.db.refresh(room)
    return room


def _ensure_room_unused(ctx, room_id: int) -> None:
    in_use = ctx.db.scalar(select(ClassGroup.id).where(ClassGroup.room_id == room_id, ClassGroup.end_date.is_(None)))
    if in_use:
        raise HTTPException(status.HTTP_409_CONFLICT, "Sala possui turmas ativas; encerre-as antes")


@router.delete("/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Inativa a sala")
def deactivate_room(room_id: int, ctx: Admin):
    room = get_or_404(ctx.db, Room, room_id, "Sala")
    _ensure_room_unused(ctx, room.id)
    room.is_active = False
    ctx.db.commit()


# ---------- Planos ----------
@router.get("/plans", response_model=list[PlanRead])
def list_plans(ctx: Staff, is_active: bool | None = True):
    query = select(Plan).order_by(Plan.sessions_per_week, Plan.total_classes)
    if is_active is not None:
        query = query.where(Plan.is_active == is_active)
    return ctx.db.scalars(query).all()


@router.post("/plans", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(data: PlanCreate, ctx: Admin):
    plan = Plan(**data.model_dump())
    ctx.db.add(plan)
    ctx.db.commit()
    ctx.db.refresh(plan)
    return plan


@router.get("/plans/{plan_id}", response_model=PlanRead)
def get_plan(plan_id: int, ctx: Staff):
    return get_or_404(ctx.db, Plan, plan_id, "Plano")


@router.get("/plans/{plan_id}/price", response_model=PricePreview, summary="Simula o preço com desconto")
def plan_price(plan_id: int, ctx: Staff, discount_id: int | None = None):
    plan, discount, amount = resolve_price(ctx.db, plan_id, discount_id)
    return PricePreview(
        plan_id=plan.id,
        discount_id=discount.id if discount else None,
        base_price=plan.price,
        discount_amount=amount,
        final_price=plan.price - amount,
    )


@router.patch(
    "/plans/{plan_id}", response_model=PlanRead, summary="Altera o plano (não afeta planos já contratados)"
)
def update_plan(plan_id: int, data: PlanUpdate, ctx: Admin):
    plan = get_or_404(ctx.db, Plan, plan_id, "Plano")
    apply_update(plan, data)
    ctx.db.commit()
    ctx.db.refresh(plan)
    return plan


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Inativa o plano")
def deactivate_plan(plan_id: int, ctx: Admin):
    plan = get_or_404(ctx.db, Plan, plan_id, "Plano")
    plan.is_active = False
    ctx.db.commit()


# ---------- Descontos ----------
@router.get("/discounts", response_model=list[DiscountRead])
def list_discounts(ctx: Staff, plan_id: int | None = None, is_active: bool | None = True):
    query = select(Discount).order_by(Discount.name)
    if is_active is not None:
        query = query.where(Discount.is_active == is_active)
    if plan_id is not None:
        query = query.where(or_(Discount.plan_id.is_(None), Discount.plan_id == plan_id))
    return ctx.db.scalars(query).all()


@router.post("/discounts", response_model=DiscountRead, status_code=status.HTTP_201_CREATED)
def create_discount(data: DiscountCreate, ctx: Admin):
    if data.plan_id is not None:
        get_or_404(ctx.db, Plan, data.plan_id, "Plano")
    discount = Discount(**data.model_dump())
    ctx.db.add(discount)
    ctx.db.commit()
    ctx.db.refresh(discount)
    return discount


@router.patch(
    "/discounts/{discount_id}",
    response_model=DiscountRead,
    summary="Altera o desconto (não afeta planos já contratados)",
)
def update_discount(discount_id: int, data: DiscountUpdate, ctx: Admin):
    discount = get_or_404(ctx.db, Discount, discount_id, "Desconto")
    changes = data.model_dump(exclude_unset=True)
    if changes.get("plan_id") is not None:
        get_or_404(ctx.db, Plan, changes["plan_id"], "Plano")
    kind = changes.get("kind", discount.kind)
    value = changes.get("value", discount.value)
    if kind == DiscountKind.PERCENT and value > 100:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Desconto percentual deve ser no máximo 100")
    apply_update(discount, data)
    ctx.db.commit()
    ctx.db.refresh(discount)
    return discount


# ---------- Resumo do catálogo ----------
@router.get(
    "/catalog/overview",
    response_model=CatalogOverview,
    summary="Uso de cada plano e serviço avulso (alunos em uso, na fila, pagamentos pendentes)",
)
def catalog_overview(ctx: Staff):
    db = ctx.db
    plans: dict[int, PlanUsage] = {p.id: PlanUsage(plan_id=p.id, in_use=0, queued=0, unpaid=0) for p in db.scalars(select(Plan))}
    active = db.scalars(select(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE))
    for sub in active:
        usage = plans.get(sub.plan_id)
        if usage is None:
            continue
        state = sub.usage
        if state == SubscriptionUsage.IN_USE:
            usage.in_use += 1
        elif state == SubscriptionUsage.QUEUED:
            usage.queued += 1
        if not sub.is_paid and state in (SubscriptionUsage.IN_USE, SubscriptionUsage.QUEUED):
            usage.unpaid += 1

    today = clock.today()
    services: dict[int, ServiceUsage] = {
        s.id: ServiceUsage(service_id=s.id, active_contracts=0, upcoming_sessions=0) for s in db.scalars(select(Service))
    }
    contracts = db.scalars(
        select(ServiceContract)
        .options(selectinload(ServiceContract.sessions))
        .where(ServiceContract.status == ServiceContractStatus.ACTIVE)
    )
    for contract in contracts:
        usage = services.get(contract.service_id)
        if usage is None or contract.situation != "active":
            continue
        usage.active_contracts += 1
        usage.upcoming_sessions += sum(
            1 for s in contract.sessions if s.status == ServiceSessionStatus.SCHEDULED and s.date >= today
        )
    return CatalogOverview(plans=list(plans.values()), services=list(services.values()))


@router.delete("/discounts/{discount_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Inativa o desconto")
def deactivate_discount(discount_id: int, ctx: Admin):
    discount = get_or_404(ctx.db, Discount, discount_id, "Desconto")
    discount.is_active = False
    ctx.db.commit()
