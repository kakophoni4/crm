from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.lead import Lead
from app.modules.db.models.lead_opt_order import LeadOptOrder, LeadOptOrderLine
from app.modules.db.models.user import User
from app.modules.leads.access import actor_can_access_lead
from app.modules.leads.opt.mole_client import MoleApiError, post_opt_order
from app.modules.leads.opt.requisites import ensure_unit_requisites, resolve_buyer_requisites
from app.modules.leads.opt.fingerprint import compute_application_fingerprint
from app.modules.leads.opt.parser import parse_application_workbook
from app.modules.leads.opt.queue import dequeue_opt_submit, enqueue_opt_submit
from app.modules.leads.opt.registry_export import build_registry_workbook
from app.modules.leads.opt.repository import OptOrderRepository
from app.modules.leads.opt.schemas import (
    OptAttachmentProbeResponse,
    OptCounterpartyResponse,
    OptOrderExistingRef,
    OptOrderLineResponse,
    OptOrderListResponse,
    OptOrderPaymentCreateRequest,
    OptCommissionAdjustRequest,
    OptOrderResponse,
    OptPaymentResponse,
    OptVolumeCategoryBreakdown,
)
from app.modules.leads.opt.pricing import commission_base_from_breakdown
from app.modules.leads.opt.vat import split_vat_included
from app.modules.leads.repository import LeadRepository
from app.realtime.events import publish
from app.shared.exceptions import NotFound, PermissionDenied, ValidationError
from app.shared.settings import get_settings

logger = structlog.get_logger(__name__)

OPT_SERVICE_NAME = "ОПТ"

_SPREADSHEET_MIMES = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
)
_SPREADSHEET_EXTS = (".xlsx", ".xls")


def _looks_like_spreadsheet(filename: str | None, content_type: str | None) -> bool:
    if content_type:
        lowered = content_type.lower()
        if any(token in lowered for token in ("spreadsheet", "ms-excel", "excel")):
            return True
    if filename:
        name = filename.lower()
        if any(name.endswith(ext) for ext in _SPREADSHEET_EXTS):
            return True
    return False


def _existing_order_ref(order: LeadOptOrder) -> OptOrderExistingRef:
    return OptOrderExistingRef(
        lead_id=order.lead_id,
        order_id=order.id,
        order_no=order.order_no,
    )


def duplicate_order_message(order: LeadOptOrder) -> str:
    return (
        f"Такая заявка уже существует по сделке №{order.lead_id}, "
        f"заявка №{order.order_no}"
    )


class OptOrderService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = OptOrderRepository(session)
        self._leads = LeadRepository(session)
        self._scope_loader = ScopeLoader(session)

    async def _get_lead_for_actor(self, actor: User, lead_id: int) -> Lead:
        lead = await self._leads.get_by_id(lead_id)
        if lead is None:
            raise NotFound(message="Lead not found")
        ctx = await self._scope_loader.load(actor)
        if not await actor_can_access_lead(self._session, ctx, lead):
            raise NotFound(message="Lead not found")
        return lead

    async def _get_order_for_actor(self, actor: User, lead_id: int, order_id: int) -> LeadOptOrder:
        await self._get_lead_for_actor(actor, lead_id)
        order = await self._repo.get_order(order_id)
        if order is None or order.lead_id != lead_id:
            raise NotFound(message="OPT order not found")
        return order

    def _to_response(self, order: LeadOptOrder) -> OptOrderResponse:
        commission_due = Decimal(str(order.commission_due or 0))
        commission_adjustment = Decimal(str(order.commission_adjustment or 0))
        commission_base = commission_base_from_breakdown(order.volume_by_category)
        if commission_base == 0:
            commission_base = (commission_due - commission_adjustment).quantize(Decimal("0.01"))
        amount_paid = Decimal(str(order.amount_paid or 0))
        remaining = max(Decimal("0"), commission_due - amount_paid).quantize(Decimal("0.01"))
        breakdown: dict[str, OptVolumeCategoryBreakdown] = {}
        raw_breakdown = order.volume_by_category or {}
        if isinstance(raw_breakdown, dict):
            for code, row in raw_breakdown.items():
                if isinstance(row, dict):
                    breakdown[str(code)] = OptVolumeCategoryBreakdown(
                        label=str(row.get("label") or code),
                        volume=Decimal(str(row.get("volume", 0))),
                        rate_percent=Decimal(str(row.get("rate_percent", 0))),
                        commission=Decimal(str(row.get("commission", 0))),
                    )
        return OptOrderResponse(
            id=order.id,
            lead_id=order.lead_id,
            order_no=order.order_no,
            crm_id=order.crm_id,
            status=order.status,
            payment_status=order.payment_status or "unpaid",
            total_volume=Decimal(str(order.total_volume or 0)),
            commission_base=commission_base,
            commission_adjustment=commission_adjustment,
            commission_due=commission_due,
            amount_paid=amount_paid,
            amount_remaining=remaining,
            volume_by_category=breakdown,
            buyer=OptCounterpartyResponse(
                inn=order.buyer_inn,
                kpp=order.buyer_kpp,
                name=order.buyer_name,
            ),
            source_filename=order.source_filename,
            submission_error=order.submission_error,
            submitted_at=order.submitted_at,
            created_at=order.created_at,
            lines=[
                OptOrderLineResponse(
                    id=line.id,
                    crm_id=line.crm_id,
                    line_no=line.line_no,
                    supplier=OptCounterpartyResponse(
                        inn=line.supplier_inn,
                        kpp=line.supplier_kpp,
                        name=line.supplier_name,
                    ),
                    document_date=line.document_date,
                    amount=Decimal(str(line.amount)),
                    vat_amount=Decimal(str(line.vat_amount)),
                    amount_without_vat=Decimal(str(line.amount_without_vat)),
                    document_number=line.document_number,
                )
                for line in sorted(order.lines, key=lambda row: row.line_no)
            ],
            payments=[
                OptPaymentResponse(
                    id=payment.id,
                    amount=Decimal(str(payment.amount)),
                    paid_at=payment.paid_at,
                    payment_type=payment.payment_type,
                    recipient=payment.recipient,
                    created_at=payment.created_at,
                )
                for payment in sorted(order.payments, key=lambda row: row.paid_at)
            ],
        )

    async def add_payment(
        self,
        actor: User,
        lead_id: int,
        order_id: int,
        body: OptOrderPaymentCreateRequest,
    ) -> OptOrderResponse:
        order = await self._get_order_for_actor(actor, lead_id, order_id)
        remaining = Decimal(str(order.commission_due or 0)) - Decimal(str(order.amount_paid or 0))
        if body.amount > remaining + Decimal("0.01"):
            raise ValidationError(
                message=f"Сумма оплаты превышает остаток ({remaining.quantize(Decimal('0.01'))} ₽)",
            )
        await self._repo.add_payment(
            order,
            amount=body.amount,
            paid_at=body.paid_at,
            payment_type=body.payment_type,
            recipient=body.recipient,
            created_by=actor.id,
        )
        await self._session.commit()
        refreshed = await self._repo.get_order(order.id)
        assert refreshed is not None
        return self._to_response(refreshed)

    async def adjust_commission(
        self,
        actor: User,
        lead_id: int,
        order_id: int,
        body: OptCommissionAdjustRequest,
    ) -> OptOrderResponse:
        order = await self._get_order_for_actor(actor, lead_id, order_id)
        if order.payment_status == "paid":
            raise ValidationError(message="Нельзя менять сумму полностью оплаченной заявки")

        current_adjustment = Decimal(str(order.commission_adjustment or 0))
        base_commission = commission_base_from_breakdown(order.volume_by_category)
        if base_commission == 0:
            base_commission = (
                Decimal(str(order.commission_due or 0)) - current_adjustment
            ).quantize(Decimal("0.01"))

        delta = body.amount if body.direction == "increase" else -body.amount
        new_adjustment = (current_adjustment + delta).quantize(Decimal("0.01"))
        new_due = (base_commission + new_adjustment).quantize(Decimal("0.01"))
        amount_paid = Decimal(str(order.amount_paid or 0))

        if new_due < 0:
            raise ValidationError(message="Сумма к оплате не может быть отрицательной")
        if new_due + Decimal("0.01") < amount_paid:
            raise ValidationError(
                message="Сумма к оплате не может быть меньше уже оплаченной суммы",
            )

        await self._repo.apply_commission_adjustment(order, delta=delta)
        await self._session.commit()
        refreshed = await self._repo.get_order(order.id)
        assert refreshed is not None
        return self._to_response(refreshed)

    @staticmethod
    async def assert_lead_won_payment_allowed(
        session: AsyncSession,
        lead_id: int,
        service_name: str | None,
    ) -> None:
        from app.modules.leads.opt.payment_guard import assert_lead_won_payment_allowed

        await assert_lead_won_payment_allowed(session, lead_id, service_name)

    async def list_orders(self, actor: User, lead_id: int) -> OptOrderListResponse:
        await self._get_lead_for_actor(actor, lead_id)
        orders = await self._repo.list_orders_for_lead(lead_id)
        return OptOrderListResponse(items=[self._to_response(order) for order in orders])

    async def _ensure_lead_service_opt(self, lead: Lead) -> None:
        fields = dict(lead.custom_fields or {})
        order = fields.get("order")
        if isinstance(order, dict) and order.get("service") == OPT_SERVICE_NAME:
            return
        if not isinstance(order, dict):
            order = {}
        order = {**order, "service": OPT_SERVICE_NAME}
        fields["order"] = order
        lead.custom_fields = fields
        await self._leads.update_lead_fields(lead.id, custom_fields=fields)

    async def _read_chat_attachment(
        self,
        actor: User,
        *,
        lead: Lead,
        chat_id: int,
        message_id: int,
        attachment_index: int,
    ) -> tuple[bytes, str]:
        from app.modules.chats.messages import ChatMessagesService

        if lead.chat_id is None or lead.chat_id != chat_id:
            raise ValidationError(message="Файл не относится к чату этой сделки")

        messages = ChatMessagesService(self._session)
        content, _content_type, filename = await messages.get_attachment(
            actor,
            chat_id,
            message_id,
            attachment_index,
        )
        return content, filename or "application.xlsx"

    async def probe_chat_attachment(
        self,
        actor: User,
        lead_id: int,
        *,
        chat_id: int,
        message_id: int,
        attachment_index: int,
    ) -> OptAttachmentProbeResponse:
        lead = await self._get_lead_for_actor(actor, lead_id)
        content, filename = await self._read_chat_attachment(
            actor,
            lead=lead,
            chat_id=chat_id,
            message_id=message_id,
            attachment_index=attachment_index,
        )

        existing = await self._repo.get_order_by_source_attachment(message_id, attachment_index)
        if existing is not None:
            return OptAttachmentProbeResponse(
                is_application=True,
                existing_order=_existing_order_ref(existing),
            )

        if not _looks_like_spreadsheet(filename, None):
            return OptAttachmentProbeResponse(is_application=False)

        try:
            parsed = parse_application_workbook(content)
        except ValidationError:
            return OptAttachmentProbeResponse(is_application=False)

        fingerprint = compute_application_fingerprint(parsed)
        existing_fp = await self._repo.get_order_by_content_fingerprint(fingerprint)
        if existing_fp is not None:
            return OptAttachmentProbeResponse(
                is_application=True,
                buyer_inn=parsed.buyer_inn,
                line_count=len(parsed.lines),
                existing_order=_existing_order_ref(existing_fp),
            )

        return OptAttachmentProbeResponse(
            is_application=True,
            buyer_inn=parsed.buyer_inn,
            line_count=len(parsed.lines),
        )

    async def upload_from_chat_attachment(
        self,
        actor: User,
        lead_id: int,
        *,
        chat_id: int,
        message_id: int,
        attachment_index: int,
    ) -> OptOrderResponse:
        lead = await self._get_lead_for_actor(actor, lead_id)
        existing = await self._repo.get_order_by_source_attachment(message_id, attachment_index)
        if existing is not None:
            raise ValidationError(message=duplicate_order_message(existing))

        content, filename = await self._read_chat_attachment(
            actor,
            lead=lead,
            chat_id=chat_id,
            message_id=message_id,
            attachment_index=attachment_index,
        )
        return await self.upload_application(
            actor,
            lead_id,
            filename=filename,
            content=content,
            source_message_id=message_id,
            source_attachment_index=attachment_index,
        )

    async def upload_application(
        self,
        actor: User,
        lead_id: int,
        *,
        filename: str,
        content: bytes,
        source_message_id: int | None = None,
        source_attachment_index: int | None = None,
    ) -> OptOrderResponse:
        lead = await self._get_lead_for_actor(actor, lead_id)

        if source_message_id is not None and source_attachment_index is not None:
            existing = await self._repo.get_order_by_source_attachment(
                source_message_id,
                source_attachment_index,
            )
            if existing is not None:
                raise ValidationError(message=duplicate_order_message(existing))

        if await self._repo.lead_has_pending_submission(lead.id):
            raise ValidationError(
                message=(
                    "По сделке уже есть незавершённая заявка. "
                    "Удалите её и загрузите файл заново — повторная отправка в 1С недоступна."
                ),
            )

        parsed = parse_application_workbook(content)
        content_fingerprint = compute_application_fingerprint(parsed)
        existing_fp = await self._repo.get_order_by_content_fingerprint(content_fingerprint)
        if existing_fp is not None:
            raise ValidationError(message=duplicate_order_message(existing_fp))

        buyer_inn = parsed.buyer_inn
        buyer_kpp, buyer_name = await resolve_buyer_requisites(self._repo, buyer_inn)

        settings = get_settings()
        vat_rate = Decimal(str(settings.opt_vat_rate_percent))
        order_crm_id = self._repo.new_crm_id("crm-order")
        line_payloads: list[dict[str, object]] = []
        missing_suppliers: list[str] = []

        for parsed_line in parsed.lines:
            unit = await self._repo.get_unit_by_inn(parsed_line.supplier_inn)
            if unit is None:
                missing_suppliers.append(parsed_line.supplier_inn)
                supplier_kpp = None
                supplier_name = None
            else:
                unit = await ensure_unit_requisites(self._repo, unit)
                supplier_kpp = unit.kpp
                supplier_name = unit.name

            total, vat, wo_vat = split_vat_included(parsed_line.amount, rate_percent=vat_rate)
            line_payloads.append(
                {
                    "crm_id": self._repo.new_crm_id("crm-line"),
                    "supplier_inn": parsed_line.supplier_inn,
                    "supplier_kpp": supplier_kpp,
                    "supplier_name": supplier_name,
                    "document_date": parsed_line.document_date,
                    "amount": float(total),
                    "vat_amount": float(vat),
                    "amount_without_vat": float(wo_vat),
                },
            )

        if missing_suppliers:
            raise ValidationError(
                message=(
                    "Не найдены лавки (opt_units) для ИНН: "
                    + ", ".join(sorted(set(missing_suppliers)))
                ),
            )

        order = await self._repo.create_order(
            lead_id=lead.id,
            crm_id=order_crm_id,
            buyer_inn=buyer_inn,
            buyer_kpp=buyer_kpp,
            buyer_name=buyer_name,
            source_filename=filename,
            created_by=actor.id,
            lines=line_payloads,
            source_message_id=source_message_id,
            source_attachment_index=source_attachment_index,
            content_fingerprint=content_fingerprint,
        )
        await self._ensure_lead_service_opt(lead)
        await self._session.commit()
        await enqueue_opt_submit(order.id)
        refreshed = await self._repo.get_order(order.id)
        assert refreshed is not None
        return self._to_response(refreshed)

    def _build_mole_payload(self, order: LeadOptOrder) -> dict[str, Any]:
        if not order.buyer_kpp or not order.buyer_name:
            raise ValidationError(
                message=(
                    "Для отправки в 1С нужны КПП и наименование покупателя по этой заявке "
                    f"(ИНН {order.buyer_inn})"
                ),
            )

        registry: list[dict[str, Any]] = []
        for line in sorted(order.lines, key=lambda row: row.line_no):
            if not line.supplier_kpp or not line.supplier_name:
                raise ValidationError(
                    message=f"Для лавки {line.supplier_inn} не заполнены КПП/наименование",
                )
            doc_date = line.document_date
            if isinstance(doc_date, date):
                date_text = doc_date.isoformat()
            else:
                date_text = str(doc_date)
            registry.append(
                {
                    "CRMid": line.crm_id,
                    "Поставщик": {
                        "ИНН": line.supplier_inn,
                        "КПП": line.supplier_kpp,
                        "Наименование": line.supplier_name,
                    },
                    "ДатаДокумента": date_text,
                    "Сумма": float(line.amount),
                    "СуммаНДС": float(line.vat_amount),
                    "СуммаБезНДС": float(line.amount_without_vat),
                },
            )

        return {
            "CRMid": order.crm_id,
            "Покупатель": {
                "ИНН": order.buyer_inn,
                "КПП": order.buyer_kpp,
                "Наименование": order.buyer_name,
            },
            "Реестр": registry,
        }

    @staticmethod
    def _extract_line_numbers(response: dict[str, Any]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        registry = response.get("Реестр") or response.get("Registry") or []
        if not isinstance(registry, list):
            return mapping
        for item in registry:
            if not isinstance(item, dict):
                continue
            crm_id = str(item.get("CRMid") or item.get("ID") or "").strip()
            doc_no = str(item.get("НомерДокумента") or item.get("DocumentNumber") or "").strip()
            if crm_id and doc_no:
                mapping[crm_id] = doc_no
        return mapping

    async def _publish_status(self, order: LeadOptOrder) -> None:
        await publish(
            "opt.order.updated",
            {
                "lead_id": order.lead_id,
                "order_id": order.id,
                "order_no": order.order_no,
                "status": order.status,
            },
        )

    async def _execute_submit(self, order: LeadOptOrder, *, actor_id: int | None) -> None:
        if order.status == "submitted":
            return
        if not order.lines:
            raise ValidationError(message="В заявке нет строк реестра")

        await self._ensure_order_requisites(order)

        payload = self._build_mole_payload(order)
        await self._repo.mark_submitting(order)
        await self._session.flush()
        await self._publish_status(order)

        try:
            response = await post_opt_order(payload)
            line_numbers = self._extract_line_numbers(response)
            if len(line_numbers) != len(order.lines):
                raise MoleApiError(
                    message="1С вернула неполный реестр номеров документов",
                    details={"expected": len(order.lines), "got": len(line_numbers)},
                )
            await self._repo.mark_submitted(
                order,
                actor_id=actor_id,
                request_payload=payload,
                response_payload=response,
                line_numbers=line_numbers,
            )
        except MoleApiError as exc:
            await self._repo.mark_failed(
                order,
                actor_id=actor_id,
                request_payload=payload,
                response_payload=exc.details.get("body") if exc.details else None,
                error_message=exc.message,
            )
            await self._publish_status(order)
            raise

        await self._publish_status(order)

    async def _ensure_order_requisites(self, order: LeadOptOrder) -> None:
        if not order.buyer_kpp or not order.buyer_name:
            kpp, name = await resolve_buyer_requisites(self._repo, order.buyer_inn)
            if kpp and name:
                order.buyer_kpp = kpp
                order.buyer_name = name
        for line in order.lines:
            if line.supplier_kpp and line.supplier_name:
                continue
            unit = await self._repo.get_unit_by_inn(line.supplier_inn)
            if unit is None:
                continue
            unit = await ensure_unit_requisites(self._repo, unit)
            line.supplier_kpp = unit.kpp
            line.supplier_name = unit.name

    async def submit_order_worker(self, order_id: int) -> None:
        order = await self._repo.get_order(order_id)
        if order is None:
            return
        if order.status == "submitted":
            return
        if order.status not in {"queued", "failed", "submitting"}:
            return
        try:
            await self._execute_submit(order, actor_id=order.created_by)
        except MoleApiError:
            return
        except ValidationError as exc:
            await self._repo.mark_failed(
                order,
                actor_id=order.created_by,
                request_payload=None,
                error_message=exc.message,
            )
            await self._publish_status(order)

    async def submit_order(self, actor: User, lead_id: int, order_id: int) -> OptOrderResponse:
        order = await self._get_order_for_actor(actor, lead_id, order_id)
        if order.status == "submitted":
            raise ValidationError(message="Заявка уже отправлена в 1С")
        await self._execute_submit(order, actor_id=actor.id)
        await self._session.commit()
        refreshed = await self._repo.get_order(order.id)
        assert refreshed is not None
        return self._to_response(refreshed)

    async def delete_order(self, actor: User, lead_id: int, order_id: int) -> None:
        order = await self._get_order_for_actor(actor, lead_id, order_id)
        if order.status == "submitted":
            raise ValidationError(message="Нельзя удалить заявку, уже отправленную в 1С")
        if order.payments:
            raise ValidationError(message="Нельзя удалить заявку с записанными оплатами")
        lead_id_value = order.lead_id
        order_no = order.order_no
        try:
            await dequeue_opt_submit(order.id)
        except Exception:
            logger.warning("opt_submit_dequeue_failed", order_id=order.id, exc_info=True)
        await self._repo.delete_order(order)
        await self._session.commit()
        await publish(
            "opt.order.deleted",
            {"lead_id": lead_id_value, "order_id": order_id, "order_no": order_no},
        )

    async def send_registry_to_client(
        self,
        actor: User,
        lead_id: int,
        order_id: int,
    ) -> dict[str, int]:
        from app.modules.chats.messages import ChatMessagesService
        from app.modules.chats.schemas import AttachmentInput, OutboundMessageRequest
        from app.modules.files.service import FilesService

        order = await self._get_order_for_actor(actor, lead_id, order_id)
        if order.status != "submitted":
            raise ValidationError(message="Реестр можно отправить после успешной обработки в 1С")
        lead = await self._get_lead_for_actor(actor, lead_id)
        if lead.chat_id is None:
            raise ValidationError(message="У сделки нет чата — отправка клиенту недоступна")

        content, filename = self._registry_bytes(order)
        files = FilesService(self._session)
        uploaded = await files.create_upload(
            uploaded_by=actor.id,
            data=content,
            original_name=filename,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        text = f"Реестр по заявке №{order.order_no} сделки №{lead_id}."
        messages = ChatMessagesService(self._session)
        message, _, _ = await messages.send_outbound(
            actor,
            lead.chat_id,
            OutboundMessageRequest(
                text=text,
                attachments=[
                    AttachmentInput(
                        file_id=uploaded.id,
                        name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        size=len(content),
                    ),
                ],
            ),
        )
        await self._session.commit()
        return {"message_id": message.id, "chat_id": lead.chat_id}

    def _registry_bytes(self, order: LeadOptOrder) -> tuple[bytes, str]:
        content = build_registry_workbook(order, sorted(order.lines, key=lambda row: row.line_no))
        buyer_slug = (order.buyer_name or order.buyer_inn).replace("/", "-")[:40]
        filename = f"РЕЕСТР СФ ЗАКАЗ {buyer_slug} заявка-{order.order_no}.xlsx"
        return content, filename

    async def export_registry(
        self,
        actor: User,
        lead_id: int,
        order_id: int,
    ) -> tuple[bytes, str]:
        order = await self._get_order_for_actor(actor, lead_id, order_id)
        if order.status != "submitted":
            raise ValidationError(message="Реестр доступен после успешной отправки в 1С")
        return self._registry_bytes(order)
