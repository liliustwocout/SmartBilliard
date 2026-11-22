"""API quản lý nhân sự, menu dịch vụ, khách và hoá đơn của một quán."""
import re
from datetime import datetime
from typing import Annotated, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.manage_api.admin import temp_password
from apps.manage_api.auth import Principal, audit, utc_naive
from apps.manage_api.models import AuthSession, BilliardTable, Payment, PlaySession, Product, SessionItem, User, Venue
from apps.manage_api.security import hash_password
from apps.manage_api.textutil import fold

MAX_PRICE = 10_000_000
PHONE_RE = re.compile(r"^0\d{9}$")


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"[\s.\-()]", "", raw)
    if digits.startswith("+84"):
        digits = "0" + digits[3:]
    elif digits.startswith("84") and len(digits) == 11:
        digits = "0" + digits[2:]
    return digits


class StaffCreate(BaseModel):
    login: str = Field(min_length=3, max_length=120)
    display_name: str = Field(min_length=1, max_length=120)


class StaffUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    status: Literal["ACTIVE", "DISABLED"] | None = None


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    price: int = Field(ge=0, le=MAX_PRICE)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    price: int | None = Field(default=None, ge=0, le=MAX_PRICE)
    status: Literal["ACTIVE", "INACTIVE"] | None = None


class ItemAdd(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=99)


class CustomerCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=1, max_length=20)


class CustomerStatus(BaseModel):
    status: Literal["ACTIVE", "DISABLED"]


class SessionCustomer(BaseModel):
    customer_id: int | None = None


def build_shop_api(get_db: Callable, require_venue_roles: Callable, now_fn: Callable[[], datetime]) -> APIRouter:
    router = APIRouter(prefix="/api/venues/{venue_id}", tags=["shop"])
    Db = Annotated[Session, Depends(get_db)]
    Operator = Annotated[Principal, Depends(require_venue_roles("owner", "staff"))]
    OwnerOnly = Annotated[Principal, Depends(require_venue_roles("owner"))]

    def revoke_sessions(db: Session, user_id: int) -> None:
        for session in db.scalars(select(AuthSession).where(AuthSession.user_id == user_id)):
            db.delete(session)

    def iso(value: datetime | None) -> str | None:
        return value.isoformat() + "Z" if value else None

    # ---------------- nhân viên (chủ quán) ----------------
    def staff_view(user: User) -> dict:
        return {"id": user.id, "login": user.login, "display_name": user.display_name, "status": user.status,
                "must_change_password": user.must_change_password, "created_at": iso(user.created_at)}

    def staff_or_404(db: Session, venue_id: int, user_id: int) -> User:
        user = db.get(User, user_id)
        if user is None or user.venue_id != venue_id or user.role != "staff":
            raise HTTPException(404, "Không tìm thấy nhân viên.")
        return user

    @router.get("/staff")
    def list_staff(venue_id: int, _: OwnerOnly, db: Db):
        rows = db.scalars(select(User).where(User.venue_id == venue_id, User.role == "staff").order_by(User.id)).all()
        return [staff_view(u) for u in rows]

    @router.post("/staff", status_code=201)
    def create_staff(venue_id: int, body: StaffCreate, principal: OwnerOnly, db: Db):
        login = body.login.strip().lower()
        if len(login) < 3:
            raise HTTPException(400, "Tên đăng nhập quá ngắn.")
        if db.scalar(select(User.id).where(User.login == login, User.role != "customer")):
            raise HTTPException(409, "Tên đăng nhập đã tồn tại.")
        password = temp_password()
        now = now_fn()
        user = User(role="staff", login=login, display_name=body.display_name.strip(), password_hash=hash_password(password),
                    venue_id=venue_id, must_change_password=True, created_at=utc_naive(now))
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Tên đăng nhập đã tồn tại.")
        audit(db, now, "staff_created", actor=principal.user, venue_id=venue_id, target=login)
        db.commit()
        return {"staff": staff_view(user), "temp_password": password}

    @router.patch("/staff/{user_id}")
    def update_staff(venue_id: int, user_id: int, body: StaffUpdate, principal: OwnerOnly, db: Db):
        user = staff_or_404(db, venue_id, user_id)
        changes = {}
        if body.display_name is not None and body.display_name.strip() != user.display_name:
            changes["display_name"] = [user.display_name, body.display_name.strip()]
            user.display_name = body.display_name.strip()
        if body.status is not None and body.status != user.status:
            changes["status"] = [user.status, body.status]
            user.status = body.status
            if body.status == "DISABLED":
                revoke_sessions(db, user.id)
        if changes:
            audit(db, now_fn(), "staff_updated", actor=principal.user, venue_id=venue_id, target=user.login, detail=changes)
            db.commit()
        return staff_view(user)

    @router.post("/staff/{user_id}/reset-password")
    def reset_staff_password(venue_id: int, user_id: int, principal: OwnerOnly, db: Db):
        user = staff_or_404(db, venue_id, user_id)
        password = temp_password()
        user.password_hash, user.must_change_password = hash_password(password), True
        user.failed_attempts, user.locked_until = 0, None
        revoke_sessions(db, user.id)
        audit(db, now_fn(), "staff_password_reset", actor=principal.user, venue_id=venue_id, target=user.login)
        db.commit()
        return {"login": user.login, "temp_password": password}

    # ---------------- menu dịch vụ ----------------
    def product_view(p: Product) -> dict:
        return {"id": p.id, "name": p.name, "price": p.price, "status": p.status}

    @router.get("/products")
    def list_products(venue_id: int, _: Operator, db: Db):
        rows = db.scalars(select(Product).where(Product.venue_id == venue_id).order_by(Product.name)).all()
        return [product_view(p) for p in rows]

    @router.post("/products", status_code=201)
    def create_product(venue_id: int, body: ProductCreate, principal: OwnerOnly, db: Db):
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "Tên món không được để trống.")
        now = now_fn()
        product = Product(venue_id=venue_id, name=name, price=body.price, created_at=utc_naive(now))
        db.add(product)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Quán đã có món trùng tên.")
        audit(db, now, "product_created", actor=principal.user, venue_id=venue_id, target=name, detail={"price": body.price})
        db.commit()
        return product_view(product)

    @router.patch("/products/{product_id}")
    def update_product(venue_id: int, product_id: int, body: ProductUpdate, principal: OwnerOnly, db: Db):
        product = db.get(Product, product_id)
        if product is None or product.venue_id != venue_id:
            raise HTTPException(404, "Không tìm thấy món.")
        changes = {}
        for field in ("name", "price", "status"):
            value = getattr(body, field)
            value = value.strip() if isinstance(value, str) else value
            if value is not None and value != getattr(product, field):
                changes[field] = [getattr(product, field), value]
                setattr(product, field, value)
        if changes:
            if not product.name:
                db.rollback()
                raise HTTPException(400, "Tên món không được để trống.")
            audit(db, now_fn(), "product_updated", actor=principal.user, venue_id=venue_id, target=product.name, detail=changes)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                raise HTTPException(409, "Quán đã có món trùng tên.")
        return product_view(product)

    # ---------------- món trong phiên ----------------
    def lock_active_session(db: Session, venue_id: int, session_id: str) -> PlaySession:
        """Chiếm khoá ghi bằng một UPDATE rỗng có điều kiện ACTIVE: nếu phiên vừa được chốt thì 409,
        nếu chưa thì checkout đồng thời sẽ phải đợi giao dịch này xong."""
        session = db.get(PlaySession, session_id)
        if session is None or session.venue_id != venue_id:
            raise HTTPException(404, "Không tìm thấy phiên.")
        claimed = db.execute(update(PlaySession).where(PlaySession.id == session_id, PlaySession.status == "ACTIVE")
                             .values(id=session_id))
        if claimed.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Phiên đã kết thúc, không thể thay đổi.")
        return session

    def lines(db: Session, session_id: str) -> list[dict]:
        rows = db.scalars(select(SessionItem).where(SessionItem.session_id == session_id).order_by(SessionItem.id)).all()
        return [{"id": i.id, "product_id": i.product_id, "name": i.name_snapshot, "unit_price": i.unit_price,
                 "quantity": i.quantity, "amount": i.unit_price * i.quantity} for i in rows]

    @router.post("/sessions/{session_id}/items", status_code=201)
    def add_item(venue_id: int, session_id: str, body: ItemAdd, principal: Operator, db: Db):
        product = db.get(Product, body.product_id)
        if product is None or product.venue_id != venue_id or product.status != "ACTIVE":
            raise HTTPException(400, "Món không có trong menu của quán hoặc đã ngừng bán.")
        lock_active_session(db, venue_id, session_id)
        now = now_fn()
        existing = db.scalar(select(SessionItem).where(SessionItem.session_id == session_id, SessionItem.product_id == product.id,
                                                       SessionItem.unit_price == product.price))
        if existing:
            if existing.quantity + body.quantity > 99:
                db.rollback()
                raise HTTPException(400, "Tối đa 99 mỗi món trong một phiên.")
            existing.quantity += body.quantity
        else:
            db.add(SessionItem(session_id=session_id, venue_id=venue_id, product_id=product.id, name_snapshot=product.name,
                               unit_price=product.price, quantity=body.quantity, created_by=principal.user.id,
                               created_at=utc_naive(now)))
        audit(db, now, "item_added", actor=principal.user, venue_id=venue_id, target=product.name,
              detail={"session_id": session_id, "quantity": body.quantity, "unit_price": product.price})
        db.commit()
        return {"items": lines(db, session_id)}

    @router.delete("/sessions/{session_id}/items/{item_id}")
    def remove_item(venue_id: int, session_id: str, item_id: int, principal: Operator, db: Db):
        lock_active_session(db, venue_id, session_id)
        item = db.get(SessionItem, item_id)
        if item is None or item.session_id != session_id:
            db.rollback()
            raise HTTPException(404, "Không tìm thấy dòng dịch vụ.")
        audit(db, now_fn(), "item_removed", actor=principal.user, venue_id=venue_id, target=item.name_snapshot,
              detail={"session_id": session_id, "quantity": item.quantity, "unit_price": item.unit_price})
        db.delete(item)
        db.commit()
        return {"items": lines(db, session_id)}

    @router.patch("/sessions/{session_id}/customer")
    def set_session_customer(venue_id: int, session_id: str, body: SessionCustomer, principal: Operator, db: Db):
        if body.customer_id is not None:
            customer = db.get(User, body.customer_id)
            if customer is None or customer.role != "customer" or customer.venue_id != venue_id or customer.status != "ACTIVE":
                raise HTTPException(400, "Khách không thuộc quán này hoặc đã bị khoá.")
        session = lock_active_session(db, venue_id, session_id)
        session.customer_id = body.customer_id
        audit(db, now_fn(), "session_customer_set", actor=principal.user, venue_id=venue_id,
              detail={"session_id": session_id, "customer_id": body.customer_id})
        db.commit()
        return {"customer_id": session.customer_id}

    # ---------------- hoá đơn ----------------
    @router.get("/sessions/{session_id}/invoice")
    def invoice(venue_id: int, session_id: str, _: Operator, db: Db):
        session = db.get(PlaySession, session_id)
        if session is None or session.venue_id != venue_id:
            raise HTTPException(404, "Không tìm thấy phiên.")
        if session.status != "PAID":
            raise HTTPException(409, "Chỉ có hoá đơn cho phiên đã thanh toán.")
        payment = db.scalar(select(Payment).where(Payment.session_id == session.id))
        cashier = db.get(User, session.closed_by) if session.closed_by else None
        customer = db.get(User, session.customer_id) if session.customer_id else None
        return {
            "venue_name": db.get(Venue, venue_id).name, "invoice_no": session.id[:8].upper(),
            "table_name": db.get(BilliardTable, session.table_id).name,
            "started_at": iso(session.started_at), "ended_at": iso(session.ended_at),
            "billable_minutes": session.billable_minutes, "rate": session.rate_snapshot,
            "table_amount": session.table_amount, "items": lines(db, session.id), "items_amount": session.items_amount,
            "total": session.total_amount, "payment_method": payment.method if payment else None,
            "cashier": cashier.display_name if cashier else None, "customer": customer.display_name if customer else None,
        }

    # ---------------- khách của quán ----------------
    def customer_view(u: User) -> dict:
        return {"id": u.id, "login": u.login, "display_name": u.display_name, "status": u.status, "created_at": iso(u.created_at)}

    @router.get("/customers")
    def list_customers(venue_id: int, _: Operator, db: Db, q: str = "", limit: int = 50, offset: int = 0):
        query = select(User).where(User.venue_id == venue_id, User.role == "customer").order_by(User.id.desc())
        if q.strip():
            like = f"%{fold(q.strip())}%"
            query = query.where(or_(func.fold(User.display_name).like(like), User.login.like(like)))
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.limit(max(1, min(limit, 200))).offset(max(0, offset))).all()
        return {"total": total, "items": [customer_view(u) for u in rows]}

    @router.post("/customers", status_code=201)
    def create_customer(venue_id: int, body: CustomerCreate, principal: Operator, db: Db):
        phone = normalize_phone(body.phone)
        if not PHONE_RE.fullmatch(phone):
            raise HTTPException(400, "Số điện thoại cần đủ 10 chữ số, bắt đầu bằng 0.")
        if db.scalar(select(User.id).where(User.venue_id == venue_id, User.role == "customer", User.login == phone)):
            raise HTTPException(409, "Số điện thoại này đã có tài khoản ở quán.")
        password = temp_password()
        now = now_fn()
        user = User(role="customer", login=phone, display_name=body.display_name.strip(), password_hash=hash_password(password),
                    venue_id=venue_id, must_change_password=True, created_at=utc_naive(now))
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Số điện thoại này đã có tài khoản ở quán.")
        audit(db, now, "customer_created", actor=principal.user, venue_id=venue_id, target=phone)
        db.commit()
        return {"customer": customer_view(user), "temp_password": password}

    @router.patch("/customers/{user_id}/status")
    def set_customer_status(venue_id: int, user_id: int, body: CustomerStatus, principal: OwnerOnly, db: Db):
        user = db.get(User, user_id)
        if user is None or user.venue_id != venue_id or user.role != "customer":
            raise HTTPException(404, "Không tìm thấy khách.")
        if user.status != body.status:
            before, user.status = user.status, body.status
            if body.status == "DISABLED":
                revoke_sessions(db, user.id)
            audit(db, now_fn(), "customer_status_changed", actor=principal.user, venue_id=venue_id, target=user.login,
                  detail={"from": before, "to": body.status})
            db.commit()
        return customer_view(user)

    return router
