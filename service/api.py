"""FastAPI surface for the ticket workflow slice.

Endpoints:
  POST /tickets                  create + run decision flow
  GET  /tickets/{ticket_id}      query state / decision / evidence / review status
  GET  /tickets/{ticket_id}/actions   action audit history
  POST /tickets/{ticket_id}/review    approve / edit / reject → idempotent mock action
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, status

from .domain import ReviewOutcome, ReviewRequest, TicketCreate, TicketRecord
from .engine import TicketWorkflowService
from .repository import InvalidTransition, NoEvidenceGate, TicketNotFound


def create_app(service: Optional[TicketWorkflowService] = None) -> FastAPI:
    app = FastAPI(title="support-copilot ticket workflow", version="0.1.0")
    svc = service or TicketWorkflowService()

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post(
        "/tickets",
        response_model=TicketRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def create_ticket(payload: TicketCreate) -> TicketRecord:
        try:
            return svc.create_ticket(payload)
        except InvalidTransition as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    @app.get("/tickets/{ticket_id}", response_model=TicketRecord)
    def get_ticket(ticket_id: str) -> TicketRecord:
        try:
            return svc.get_ticket(ticket_id)
        except TicketNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    @app.get("/tickets/{ticket_id}/actions")
    def get_actions(ticket_id: str):
        try:
            svc.get_ticket(ticket_id)
        except TicketNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        return svc.list_actions(ticket_id)

    @app.post("/tickets/{ticket_id}/review", response_model=ReviewOutcome)
    def review_ticket(ticket_id: str, req: ReviewRequest) -> ReviewOutcome:
        try:
            return svc.review_ticket(ticket_id, req)
        except TicketNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except (InvalidTransition, NoEvidenceGate) as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return app


app = create_app()
