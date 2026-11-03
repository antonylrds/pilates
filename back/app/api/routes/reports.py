from datetime import date

from fastapi import APIRouter, HTTPException, status

from app.api.deps import Staff
from app.schemas.schedule import TeacherPaymentsResponse
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
