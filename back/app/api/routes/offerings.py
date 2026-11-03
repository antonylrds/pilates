"""Serviços avulsos: catálogo (/services) e contratações dos alunos (/students/{id}/services)."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import Admin, Staff, apply_update, get_or_404
from app.models.tenant import Service, ServiceContract, ServiceSession, Student
from app.models.tenant.enums import ServiceContractStatus, ServiceSessionStatus
from app.schemas.offerings import (
    ServiceContractCreate,
    ServiceContractRead,
    ServiceContractUpdate,
    ServiceCreate,
    ServiceRead,
    ServiceSessionComplete,
    ServiceSessionDetail,
    ServiceSessionRead,
    ServiceSessionUpdate,
    ServiceUpdate,
)
from app.schemas.people import StudentSummary
from app.services import audit
from app.services.offerings import (
    RECURRENCE_LABELS,
    cancel_contract,
    complete_session,
    contract_service,
    ensure_slot_free,
    has_started,
    reopen_session,
)

router = APIRouter(tags=["extra services"])


# ---------- Catálogo ----------
@router.get("/services", response_model=list[ServiceRead], summary="Catálogo de serviços avulsos")
def list_services(ctx: Staff, is_active: bool | None = True):
    query = select(Service).order_by(Service.name)
    if is_active is not None:
        query = query.where(Service.is_active == is_active)
    return ctx.db.scalars(query).all()


@router.post("/services", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
def create_service(data: ServiceCreate, ctx: Admin):
    service = Service(**data.model_dump())
    ctx.db.add(service)
    ctx.db.commit()
    ctx.db.refresh(service)
    return service


@router.patch(
    "/services/{service_id}",
    response_model=ServiceRead,
    summary="Altera o serviço (não afeta contratações já feitas)",
)
def update_service(service_id: int, data: ServiceUpdate, ctx: Admin):
    service = get_or_404(ctx.db, Service, service_id, "Serviço")
    apply_update(service, data)
    ctx.db.commit()
    ctx.db.refresh(service)
    return service


# ---------- Contratações ----------
def _student(ctx, student_id: int) -> Student:
    return get_or_404(ctx.db, Student, student_id, "Aluno")


def _contract(ctx, student_id: int, contract_id: int) -> ServiceContract:
    contract = ctx.db.scalar(
        select(ServiceContract)
        .options(selectinload(ServiceContract.sessions))
        .where(ServiceContract.id == contract_id, ServiceContract.student_id == student_id)
    )
    if contract is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Serviço contratado não encontrado")
    return contract


def _reload(ctx, contract: ServiceContract) -> ServiceContract:
    ctx.db.expire_all()
    return _contract(ctx, contract.student_id, contract.id)


@router.get(
    "/students/{student_id}/services",
    response_model=list[ServiceContractRead],
    summary="Histórico de serviços avulsos do aluno",
)
def student_services(student_id: int, ctx: Staff):
    _student(ctx, student_id)
    return ctx.db.scalars(
        select(ServiceContract)
        .options(selectinload(ServiceContract.sessions))
        .where(ServiceContract.student_id == student_id)
        .order_by(ServiceContract.start_date.desc(), ServiceContract.id.desc())
    ).all()


@router.post(
    "/students/{student_id}/services",
    response_model=ServiceContractRead,
    status_code=status.HTTP_201_CREATED,
    summary="Contrata um serviço avulso (valor do catálogo ou alterado; recorrência opcional)",
)
def contract(student_id: int, data: ServiceContractCreate, ctx: Admin):
    student = _student(ctx, student_id)
    if not student.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aluno está inativo")
    c = contract_service(ctx.db, ctx.studio, student, data)
    price = audit.money(c.price)
    if c.price_changed:
        price += f" (tabela {audit.money(c.list_price)})"
    when = (
        f"em {audit.fmt_date(c.start_date)}"
        if c.occurrences == 1
        else f"{RECURRENCE_LABELS[c.recurrence]}, {c.occurrences} sessões a partir de {audit.fmt_date(c.start_date)}"
    )
    paid = "pago" if c.is_paid else "pagamento pendente"
    audit.log(
        ctx,
        student.id,
        audit.Action.SERVICE_CONTRACTED,
        f"Serviço avulso contratado: {c.service_name}, {price} por sessão, {when} às {c.start_hour:02d}h, "
        f"sala {c.room.name}, com {c.teacher.name}, {paid}",
    )
    ctx.db.commit()
    return _reload(ctx, c)


@router.patch(
    "/students/{student_id}/services/{contract_id}",
    response_model=ServiceContractRead,
    summary="Altera observações e pagamento de um serviço contratado",
)
def update_contract(student_id: int, contract_id: int, data: ServiceContractUpdate, ctx: Admin):
    c = _contract(ctx, student_id, contract_id)
    values = data.model_dump(exclude_unset=True)
    if "is_paid" in values:
        values["paid_at"] = (values.get("paid_at") or c.paid_at or date.today()) if values["is_paid"] else None
    changes = audit.diff(c, values)
    if changes:
        for field, value in values.items():
            setattr(c, field, value)
        labels = {"notes": "observações", "is_paid": "pagamento", "paid_at": "data do pagamento"}
        what = ", ".join(dict.fromkeys(labels[f] for f in changes))
        audit.log(ctx, student_id, audit.Action.SERVICE_UPDATED, f"Serviço {c.service_name}: alterou {what}", changes)
        ctx.db.commit()
    return _reload(ctx, c)


@router.post(
    "/students/{student_id}/services/{contract_id}/cancel",
    response_model=ServiceContractRead,
    summary="Cancela o serviço contratado e as sessões futuras",
)
def cancel(student_id: int, contract_id: int, ctx: Admin):
    c = _contract(ctx, student_id, contract_id)
    n = cancel_contract(c)
    audit.log(
        ctx, student_id, audit.Action.SERVICE_CANCELLED, f"Serviço {c.service_name} cancelado ({n} sessão(ões) futura(s))"
    )
    ctx.db.commit()
    return _reload(ctx, c)


@router.patch(
    "/students/{student_id}/services/{contract_id}/sessions/{session_id}",
    response_model=ServiceContractRead,
    summary="Cancela ou reativa uma sessão ainda não finalizada",
)
def update_session(student_id: int, contract_id: int, session_id: int, data: ServiceSessionUpdate, ctx: Admin):
    c = _contract(ctx, student_id, contract_id)
    session = next((x for x in c.sessions if x.id == session_id), None)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sessão não encontrada")
    if session.is_completed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sessão finalizada: reabra antes de alterar")
    if data.status == ServiceSessionStatus.SCHEDULED and session.status == ServiceSessionStatus.CANCELLED:
        if c.status == ServiceContractStatus.CANCELLED:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Serviço cancelado")
        ensure_slot_free(ctx.db, session.date, session.start_hour, session.room_id, session.teacher_id, session.id)
    session.status = data.status
    ctx.db.commit()
    return _reload(ctx, c)


# ---------- Sessões: detalhe e finalização ----------
def _session(ctx, session_id: int) -> ServiceSession:
    session = ctx.db.scalar(
        select(ServiceSession)
        .options(
            selectinload(ServiceSession.contract).selectinload(ServiceContract.student),
            selectinload(ServiceSession.room),
            selectinload(ServiceSession.teacher),
        )
        .where(ServiceSession.id == session_id)
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sessão não encontrada")
    return session


def _session_detail(ctx, session_id: int) -> ServiceSessionDetail:
    ctx.db.expire_all()
    s = _session(ctx, session_id)
    pending = s.status == ServiceSessionStatus.SCHEDULED and s.contract.status == ServiceContractStatus.ACTIVE
    return ServiceSessionDetail(
        **ServiceSessionRead.model_validate(s).model_dump(),
        contract_id=s.contract_id,
        service_name=s.contract.service_name,
        student=StudentSummary.model_validate(s.contract.student),
        price=s.contract.price,
        notes=s.contract.notes,
        can_complete=pending and has_started(s),
    )


@router.get("/service-sessions/{session_id}", response_model=ServiceSessionDetail, summary="Detalhe da sessão de serviço")
def get_session(session_id: int, ctx: Staff):
    return _session_detail(ctx, session_id)


@router.post(
    "/service-sessions/{session_id}/complete",
    response_model=ServiceSessionDetail,
    summary="Finaliza a sessão (presente/falta); presente gera % do valor ao profissional",
)
def complete(session_id: int, data: ServiceSessionComplete, ctx: Staff):
    session = _session(ctx, session_id)
    complete_session(ctx, session, data.status == "present", data.justification)
    ctx.db.commit()
    return _session_detail(ctx, session_id)


@router.post(
    "/service-sessions/{session_id}/reopen",
    response_model=ServiceSessionDetail,
    summary="Reabre uma sessão finalizada (admin)",
)
def reopen(session_id: int, ctx: Staff):
    session = _session(ctx, session_id)
    reopen_session(ctx, session)
    ctx.db.commit()
    return _session_detail(ctx, session_id)
