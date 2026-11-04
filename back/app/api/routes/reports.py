from datetime import date

from fastapi import APIRouter, HTTPException, status

from app.api.deps import Admin, Staff
from app.schemas.finance import CashReport
from app.schemas.schedule import TeacherPaymentsResponse
from app.services.finance import cash_report
from app.services.reports import teacher_payments

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get(
    "/teacher-payments",
    response_model=TeacherPaymentsResponse,
    summary="Aulas dadas por professor, alunos presentes e valor a receber",
)
def get_teacher_payments(ctx: Staff, date_from: date, date_to: date, teacher_id: int | None = None):
    if date_to < date_from:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_to deve ser igual ou posterior a date_from")
    if not ctx.is_admin:
        # Professor só vê o próprio relatório.
        teacher_id = ctx.user.teacher_id
        if teacher_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuário não vinculado a um professor")
    return teacher_payments(ctx.db, date_from, date_to, teacher_id)


@router.get(
    "/cash",
    response_model=CashReport,
    summary="Caixa: recebimentos, faturamento, pagamento dos professores e valores a receber",
    description="Recebimentos pela data do pagamento; pagamento dos professores pela data da aula/sessão "
    "finalizada. 'A receber' lista planos e serviços não pagos de qualquer data.",
)
def get_cash_report(ctx: Admin, date_from: date, date_to: date):
    if date_to < date_from:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_to deve ser igual ou posterior a date_from")
    if (date_to - date_from).days > 366:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Período máximo do caixa é de 1 ano")
    return cash_report(ctx.db, date_from, date_to)
