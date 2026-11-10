from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response

from app.api.dependencies.auth import (
    CurrentUser,
    DbSession,
    SessionUser,
    clear_session_cookie,
    set_session_cookie,
)
from app.core.rate_limit import rate_limit
from app.models import AccountStatus, Role
from app.schemas.auth import (
    ChangePasswordRequest,
    EmailOnlyRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UpdateMeRequest,
    UserOut,
    VerifyEmailRequest,
    VerifyEmailResult,
)
from app.schemas.common import Message
from app.services import audit_service, auth_service
from app.services.user_service import to_user_out

router = APIRouter(prefix="/auth", tags=["Authentication"])

GENERIC_EMAIL_NOTICE = "If an account matching that email exists, we have sent instructions to it."


@router.post("/register", response_model=Message, status_code=201, dependencies=[Depends(rate_limit("register", 10, 3600))])
def register(data: RegisterRequest, background: BackgroundTasks, request: Request, db: DbSession):
    """Register. Company-domain emails enter the employee approval queue; all others become applicants."""
    user = auth_service.register(db, data, background, request)
    if user.role == Role.EMPLOYEE:
        msg = "Check your inbox to verify your email. An administrator will then review your registration."
    else:
        msg = "Check your inbox for a verification link to activate your account."
    return Message(message=msg)


@router.post("/verify-email", response_model=VerifyEmailResult, dependencies=[Depends(rate_limit("verify", 20, 3600))])
def verify_email(data: VerifyEmailRequest, background: BackgroundTasks, request: Request, db: DbSession):
    user = auth_service.verify_email(db, data.token, background, request)
    if user.status == AccountStatus.PENDING_APPROVAL:
        msg = "Email verified. Your registration is now waiting for administrator approval."
    else:
        msg = "Email verified. You can now sign in."
    return VerifyEmailResult(status=user.status, role=user.role, message=msg)


@router.post("/resend-verification", response_model=Message, dependencies=[Depends(rate_limit("resend", 5, 3600))])
def resend_verification(data: EmailOnlyRequest, background: BackgroundTasks, db: DbSession):
    auth_service.resend_verification(db, data.email, background)
    return Message(message=GENERIC_EMAIL_NOTICE)


@router.post("/login", response_model=UserOut, dependencies=[Depends(rate_limit("login", 20, 300))])
def login(data: LoginRequest, response: Response, request: Request, db: DbSession):
    user = auth_service.authenticate(db, data.email, data.password, request)
    set_session_cookie(response, user, remember_me=data.remember_me)
    return to_user_out(db, user)


@router.post("/logout", response_model=Message)
def logout(response: Response, request: Request, db: DbSession):
    clear_session_cookie(response)
    return Message(message="Signed out.")


@router.post("/forgot-password", response_model=Message, dependencies=[Depends(rate_limit("forgot", 5, 3600))])
def forgot_password(data: EmailOnlyRequest, background: BackgroundTasks, request: Request, db: DbSession):
    auth_service.request_password_reset(db, data.email, background, request)
    return Message(message=GENERIC_EMAIL_NOTICE)


@router.post("/reset-password", response_model=Message, dependencies=[Depends(rate_limit("reset", 10, 3600))])
def reset_password(data: ResetPasswordRequest, request: Request, db: DbSession):
    auth_service.reset_password(db, data.token, data.new_password, request)
    return Message(message="Password updated. You can now sign in.")


@router.post("/change-password", response_model=UserOut, dependencies=[Depends(rate_limit("change_pw", 10, 900))])
def change_password(data: ChangePasswordRequest, response: Response, request: Request, user: SessionUser, db: DbSession):
    """Allowed even while a password change is mandatory (first admin login)."""
    auth_service.change_password(db, user, data.current_password, data.new_password, request)
    set_session_cookie(response, user, remember_me=False)  # old sessions were invalidated; keep this one
    return to_user_out(db, user)


@router.get("/me", response_model=UserOut)
def me(user: SessionUser, db: DbSession):
    return to_user_out(db, user)


@router.patch("/me", response_model=UserOut)
def update_me(data: UpdateMeRequest, request: Request, user: CurrentUser, db: DbSession):
    changed = {}
    if data.full_name is not None and data.full_name.strip() != user.full_name:
        user.full_name = data.full_name.strip()
        changed["full_name"] = True
    if data.mobile is not None and data.mobile != user.mobile:
        user.mobile = data.mobile
        changed["mobile"] = True
    if changed:
        audit_service.log_action(db, "user.profile_updated", actor=user, entity_type="user", entity_id=user.id, details=changed, request=request)
        db.commit()
    return to_user_out(db, user)
