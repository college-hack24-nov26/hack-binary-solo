from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..deps import User, staff_or_doctor
from ..schemas import HelpRequests

router = APIRouter(prefix="/api/staff", tags=["staff"])


@router.get("/help-requests", response_model=HelpRequests)
def help_requests(request: Request, _: User = Depends(staff_or_doctor)):
    return {"items": request.app.state.help.open()}


@router.post("/help-requests/{rid}/dismiss", status_code=204)
def dismiss(rid: int, request: Request, user: User = Depends(staff_or_doctor)):
    if not request.app.state.help.dismiss(rid, user.username):
        raise HTTPException(404, "That help request is already closed.")
    request.app.state.events.publish("help.requested", {"id": rid, "dismissed": True})
    return Response(status_code=204)
