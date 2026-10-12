import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.razorpay import RazorpayClient
from app.models.booking import BookingStatus
from app.models.payment import Payment
from app.repositories.payment_write_repository import PaymentWriteRepository
from app.repositories.booking_repository import BookingRepository
from app.schemas.payment import BookingPaymentCreateRequest, RemainingBalancePaymentRequest


class PaymentWriteService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = PaymentWriteRepository(session)
        self.booking_repository = BookingRepository(session)

    async def create_booking_payment(
        self,
        *,
        booking_id: str,
        actor_id: str,
        payload: BookingPaymentCreateRequest,
    ):
        booking = await self.repository.get_booking_by_id(booking_id)
        if booking is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
        if str(booking.visitor_id) != actor_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No booking access.")
        
        # Allow payment for DRAFT or PAYMENT_PENDING bookings
        if booking.status not in {BookingStatus.DRAFT, BookingStatus.PAYMENT_PENDING}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Booking cannot accept payment. Current status: {booking.status.value}"
            )

        # If booking is in DRAFT, move to PAYMENT_PENDING
        if booking.status == BookingStatus.DRAFT:
            old_status = booking.status
            booking.status = BookingStatus.PAYMENT_PENDING
            await self.booking_repository.add_status_history(
                booking_id=str(booking.id),
                old_status=old_status,
                new_status=BookingStatus.PAYMENT_PENDING,
                changed_by=actor_id,
                note="Payment initiated from draft booking.",
            )
            await self.session.flush()

        # Fetch Hostel Razorpay Keys
        from app.services.payment_config_service import PaymentConfigService
        hostel_keys = await PaymentConfigService(self.session).get_decrypted_keys(str(booking.hostel_id))
        if not hostel_keys:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="This hostel has not configured online payments yet. Please contact the hostel admin."
            )
            
        razorpay_client = RazorpayClient(
            key_id=hostel_keys["key_id"],
            key_secret=hostel_keys["key_secret"]
        )

        # When no security deposit applies, short-stay billing is full payment.
        # Do not trust a smaller client-supplied booking_advance in that case.
        payment_amount = float(payload.booking_advance)
        if float(booking.security_deposit or 0) == 0:
            payment_amount = float(booking.grand_total)

        if payment_amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment amount must be greater than zero.",
            )
        if payment_amount > float(booking.grand_total):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment amount cannot exceed the booking total.",
            )

        # Create Razorpay order
        try:
            order = razorpay_client.create_order(
                amount=payment_amount,
                receipt=str(booking.booking_number),
                notes={"booking_id": str(booking.id), "visitor_id": actor_id},
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Payment gateway error: {str(e)}"
            )

        # Create payment record
        payment = Payment(
            hostel_id=str(booking.hostel_id),
            booking_id=str(booking.id),
            amount=payment_amount,
            payment_type="booking_advance",
            payment_method=payload.payment_method,
            gateway_order_id=order["id"],
            status="pending",
            due_date=booking.check_in_date,
        )
        payment = await self.repository.create_payment(payment)
        await self.session.commit()
        await self.session.refresh(payment)
        
        return {"payment": payment, "razorpay_order": order}

    async def handle_razorpay_webhook(
        self,
        *,
        payload: dict,
        signature: str | None,
        raw_body: bytes | None = None,
        hostel_id: str | None = None,
    ) -> dict:
        """
        Handle Razorpay payment webhook events with idempotency.
        
        This method:
        1. Verifies webhook signature
        2. Checks for duplicate event processing (idempotency)
        3. Processes payment based on event type
        4. Updates booking status if applicable
        5. Persists raw webhook data for audit
        
        Supported Events:
        - payment.captured: Update payment to paid, move booking to pending approval
        - payment.failed: Mark payment as failed
        - order.paid: Additional confirmation
        """
        # Get specific Razorpay Client for this webhook (if hostel_id provided)
        if hostel_id:
            from app.services.payment_config_service import PaymentConfigService
            hostel_keys = await PaymentConfigService(self.session).get_decrypted_keys(hostel_id)
            if hostel_keys:
                razorpay_client = RazorpayClient(
                    key_id=hostel_keys["key_id"],
                    key_secret=hostel_keys["key_secret"],
                    webhook_secret=hostel_keys["webhook_secret"]
                )
            else:
                razorpay_client = RazorpayClient()
        else:
            razorpay_client = RazorpayClient()

        # Step 1: Verify signature
        is_valid_signature = (
            razorpay_client.verify_webhook_signature(raw_body, signature)
            if raw_body is not None
            else razorpay_client.verify_signature(payload, signature)
        )
        if not is_valid_signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid webhook signature."
            )
        
        # Step 2: Extract event details
        event_data = payload.get("payload", {})
        entity_data = event_data.get("payment", {}).get("entity", {}) or event_data.get("order", {}).get("entity", {})
        event_type = payload.get("event", "unknown")
        event_id = entity_data.get("id") or payload.get("id")
        
        # Step 3: Check for idempotency (prevent duplicate processing)
        # Prefer payment entity ID when available.
        payment_entity_id = event_data.get("payment", {}).get("entity", {}).get("id")
        if payment_entity_id:
            existing_payment = await self.repository.get_payment_by_gateway_payment_id(payment_entity_id)
            if existing_payment and existing_payment.status == "captured":
                return {"received": True, "event": event_type, "status": "already_processed"}

        existing_event = await self.repository.get_webhook_event_by_provider_id(
            provider="razorpay",
            event_id=event_id
        )
        if existing_event:
            # Already processed this event
            return {"received": True, "event": event_type, "status": "already_processed"}
        
        # Step 4: Store raw webhook event
        webhook_event = await self.repository.create_webhook_event(
            provider="razorpay",
            event_type=event_type,
            payload=payload,
            status="processing",
            event_id=event_id
        )
        
        try:
            # Step 5: Process based on event type
            if event_type == "payment.captured":
                await self._handle_payment_captured(entity_data)
            elif event_type == "payment.failed":
                await self._handle_payment_failed(entity_data)
            elif event_type == "order.paid":
                await self._handle_order_paid(entity_data)
            else:
                # Log unknown event types but don't fail
                pass
            
            # Mark event as processed
            webhook_event.status = "processed"
            
        except Exception as e:
            # Mark event as failed but don't rollback (we want to record the attempt)
            webhook_event.status = "failed"
            webhook_event.error_message = str(e)
            # Re-raise if it's a critical error
            if isinstance(e, HTTPException):
                raise
        
        await self.session.commit()
        return {"received": True, "event": event_type, "status": "processed"}
    
    async def _handle_payment_captured(self, entity_data: dict) -> None:
        order_id = entity_data.get("order_id")
        payment_id = entity_data.get("id")
        amount_paise = entity_data.get("amount", 0)
        captured_at = entity_data.get("created_at")

        if not order_id:
            return

        payment = await self.repository.get_payment_by_gateway_order_id(order_id)
        if payment is None:
            return  # Cannot create without hostel context — skip

        old_status = payment.status
        payment.gateway_payment_id = payment_id
        payment.status = "captured"
        payment.paid_at = (
            datetime.fromtimestamp(captured_at, tz=UTC) if captured_at else datetime.now(UTC)
        )
        if amount_paise is not None:
            payment.amount = amount_paise / 100

        if payment.booking_id and old_status == "pending":
            await self._update_booking_on_payment_success(str(payment.booking_id))
    
    async def _handle_payment_failed(self, entity_data: dict) -> None:
        order_id = entity_data.get("order_id")
        if not order_id:
            return
        payment = await self.repository.get_payment_by_gateway_order_id(order_id)
        if payment:
            payment.status = "failed"
            payment.failure_reason = entity_data.get("error_description", "Payment failed")
            payment.failure_code = entity_data.get("error_code", "UNKNOWN")
    
    async def _handle_order_paid(self, entity_data: dict) -> None:
        order_id = entity_data.get("id")
        if order_id:
            payment = await self.repository.get_payment_by_gateway_order_id(order_id)
            if payment and payment.status == "pending":
                payment.status = "captured"
                payment.paid_at = datetime.now(UTC)

    async def verify_booking_payment(self, *, booking_id: str, actor_id: str) -> dict:
        """
        Frontend-triggered payment verification (fallback when webhooks aren't configured).
        Marks the pending payment as captured and moves booking to pending_approval.
        """
        from sqlalchemy import select
        from app.models.payment import Payment
        from datetime import UTC, datetime

        booking = await self.repository.get_booking_by_id(booking_id)
        if booking is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
        if str(booking.visitor_id) != actor_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No booking access.")

        # Find the latest pending payment for this booking
        result = await self.session.execute(
            select(Payment).where(
                Payment.booking_id == booking_id,
                Payment.status == "pending",
            ).order_by(Payment.created_at.desc())
        )
        payment = result.scalars().first()
        if payment:
            payment.status = "captured"
            payment.paid_at = datetime.now(UTC)

        # Move booking to pending_approval if still in payment_pending
        if booking.status == BookingStatus.PAYMENT_PENDING:
            await self._update_booking_on_payment_success(booking_id)

        await self.session.commit()
        return {"status": "verified", "booking_id": booking_id}

    async def _update_booking_on_payment_success(self, booking_id: str) -> None:
        from sqlalchemy import select
        from app.models.booking import Booking, BookingStatusHistory

        result = await self.session.execute(
            select(Booking).where(Booking.id == booking_id)
        )
        booking = result.scalar_one_or_none()

        if booking and booking.status == BookingStatus.PAYMENT_PENDING:
            old_status = booking.status
            booking.status = BookingStatus.PENDING_APPROVAL
            self.session.add(BookingStatusHistory(
                booking_id=booking_id,
                old_status=old_status,
                new_status=BookingStatus.PENDING_APPROVAL,
                changed_by=None,
                note="Payment confirmed via Razorpay webhook.",
            ))

            # Send booking confirmation email (fire-and-forget)
            try:
                from app.models.user import User
                user_result = await self.session.execute(
                    select(User).where(User.id == booking.visitor_id)
                )
                user = user_result.scalar_one_or_none()
                if user:
                    from app.integrations.email import EmailService
                    from app.models.hostel import Hostel
                    hostel_result = await self.session.execute(
                        select(Hostel).where(Hostel.id == booking.hostel_id)
                    )
                    hostel = hostel_result.scalar_one_or_none()
                    svc = EmailService()
                    await svc.send_booking_confirmation(
                        recipient_email=user.email,
                        recipient_name=user.full_name,
                        booking_number=booking.booking_number,
                        hostel_name=hostel.name if hostel else "Your Hostel",
                        check_in_date=str(booking.check_in_date),
                        check_out_date=str(booking.check_out_date),
                        total_amount=float(booking.grand_total),
                        payment_status="confirmed",
                    )
            except Exception:
                pass  # Never block booking status update due to email failure

    async def create_remaining_balance_payment(
        self,
        *,
        payload: RemainingBalancePaymentRequest,
        actor_id: str,
    ) -> dict:
        """
        Create a Razorpay order for the remaining balance on a confirmed booking.

        Steps:
        1. Fetch the booking and verify the actor owns it.
        2. Check for existing pending remaining_balance payment (prevent duplicates).
        3. Calculate remaining balance (grand_total - sum of captured payments).
        4. Ensure there is actually something left to pay.
        5. Create a Razorpay order for the remaining amount.
        6. Create a Payment record with type "remaining_balance" in "pending" status.
        """
        from sqlalchemy import select
        from app.models.booking import Booking
        from app.models.student import Student

        # 1. Fetch booking
        result = await self.session.execute(
            select(Booking).where(Booking.id == payload.booking_id)
        )
        booking = result.scalar_one_or_none()
        if booking is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
        if str(booking.visitor_id) != actor_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No booking access.")

        # 1b. Resolve student_id for this user
        student_res = await self.session.execute(
            select(Student).where(Student.user_id == actor_id)
        )
        student = student_res.scalars().first()
        student_id = str(student.id) if student else None

        # 2. Check for existing pending remaining_balance payment (prevent duplicates)
        existing_res = await self.session.execute(
            select(Payment).where(
                Payment.booking_id == payload.booking_id,
                Payment.payment_type == "remaining_balance",
                Payment.status == "pending",
            ).order_by(Payment.created_at.desc())
        )
        existing_payment = existing_res.scalars().first()
        if existing_payment:
            from app.services.payment_config_service import PaymentConfigService
            hostel_keys = await PaymentConfigService(self.session).get_decrypted_keys(str(booking.hostel_id))
            # Return existing payment + its Razorpay order instead of creating a duplicate
            return {
                "payment": existing_payment,
                "razorpay_order": {
                    "id": existing_payment.gateway_order_id,
                    "amount": int(float(existing_payment.amount) * 100),
                    "currency": "INR",
                },
                "remaining_amount": float(existing_payment.amount),
                "payment_id": str(existing_payment.id),
                "razorpay_key_id": hostel_keys.get("key_id") if hostel_keys else None,
                "reused_existing": True,
            }

        # 3. Calculate total already paid (only captured payments)
        paid_result = await self.session.execute(
            select(Payment).where(
                Payment.booking_id == payload.booking_id,
                Payment.status == "captured",
            )
        )
        captured_payments = paid_result.scalars().all()
        total_paid = sum(float(p.amount) for p in captured_payments)
        grand_total = float(booking.grand_total)
        remaining = round(grand_total - total_paid, 2)

        # 4. Validate remaining balance
        if remaining <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No remaining balance to pay. Booking is fully paid (₹{grand_total:.2f}).",
            )

        # 5. Fetch Hostel Razorpay Keys (or fallback to system default keys)
        from app.services.payment_config_service import PaymentConfigService
        hostel_keys = await PaymentConfigService(self.session).get_decrypted_keys(str(booking.hostel_id))
        if hostel_keys and hostel_keys.get("key_id"):
            razorpay_client = RazorpayClient(
                key_id=hostel_keys["key_id"],
                key_secret=hostel_keys["key_secret"]
            )
            key_id_used = hostel_keys["key_id"]
        else:
            razorpay_client = RazorpayClient()
            key_id_used = razorpay_client.key_id

        # 6. Create Razorpay order
        try:
            order = razorpay_client.create_order(
                amount=remaining,
                receipt=str(booking.booking_number),
                notes={
                    "booking_id": str(booking.id),
                    "visitor_id": actor_id,
                    "payment_type": "remaining_balance",
                },
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Payment gateway error: {str(e)}",
            )

        # 7. Create Payment record (with student_id for verify endpoint)
        payment = Payment(
            hostel_id=str(booking.hostel_id),
            student_id=student_id,
            booking_id=str(booking.id),
            amount=remaining,
            payment_type="remaining_balance",
            payment_method=payload.payment_method,
            gateway_order_id=order["id"],
            status="pending",
            due_date=booking.check_out_date,
        )
        self.session.add(payment)
        await self.session.commit()
        await self.session.refresh(payment)

        return {
            "payment": payment,
            "razorpay_order": order,
            "remaining_amount": remaining,
            "payment_id": str(payment.id),
            "razorpay_key_id": key_id_used,
        }
