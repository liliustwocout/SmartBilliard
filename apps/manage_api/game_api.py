"""Gamification theo từng quán: check-in qua wifi/mã tại quầy, chuỗi ngày (streak), điểm, vòng quay may mắn
có tỷ lệ chỉnh được và thưởng đảm bảo mỗi ngày, voucher.

Nguyên tắc: mọi kết quả quay do BACKEND quyết định bằng `secrets`; client chỉ chạy hoạt ảnh. Điểm ghi vào sổ chỉ
thêm, idempotent theo (khách, lý do, tham chiếu). Phần thưởng chỉ là điểm/voucher dùng trong quán, không quy đổi tiền."""
import hashlib
import hmac
import secrets
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Annotated, Callable, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.manage_api.auth import Principal, audit, utc_naive
from apps.manage_api.models import (Checkin, CustomerGame, GameSettings, PointLedger, SpinResult, SpinTicket, User,
                                    VenueNetwork, Voucher, WheelDailyPlan, WheelPrize)
from apps.manage_api.netutil import client_ip, ip_in_networks, normalize_cidr

LEVELS = ((0, "Đồng"), (100, "Bạc"), (500, "Vàng"), (1500, "Kim cương"))
DEFAULT_MILESTONES = [[3, 20], [7, 50], [14, 100], [30, 300]]
MODES = ("off", "wifi", "code", "wifi_or_code", "wifi_and_code")
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_ATTEMPTS = 10
CODE_WINDOW = 300


class Milestone(BaseModel):
    days: int = Field(ge=2, le=365)
    bonus: int = Field(ge=0, le=10000)


class GameSettingsBody(BaseModel):
    checkin_mode: Literal["off", "wifi", "code", "wifi_or_code", "wifi_and_code"]
    checkin_points: int = Field(ge=0, le=1000)
    streak_milestones: list[Milestone] = Field(max_length=8)
    wheel_enabled: bool
    min_daily_prizes: int = Field(ge=0, le=2)
    max_daily_prizes: int = Field(ge=0, le=50)
    expected_daily_checkins: int = Field(ge=1, le=1000)
    spin_expiry_days: int = Field(ge=1, le=14)
    code_rotation_seconds: int = Field(ge=60, le=3600)


class NetworkItem(BaseModel):
    cidr: str = Field(min_length=3, max_length=50)
    label: str | None = Field(default=None, max_length=60)


class NetworksBody(BaseModel):
    networks: list[NetworkItem] = Field(max_length=10)


class PrizeItem(BaseModel):
    id: int | None = None
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["points", "discount_vnd", "free_minutes", "nothing"]
    value: int = Field(default=0, ge=0, le=1_000_000)
    weight_bp: int = Field(ge=0, le=10000)
    stock: int | None = Field(default=None, ge=0, le=100000)
    voucher_valid_days: int = Field(default=30, ge=1, le=365)


class WheelBody(BaseModel):
    prizes: list[PrizeItem] = Field(min_length=2, max_length=12)


class CheckinBody(BaseModel):
    code: str | None = Field(default=None, max_length=12)


def iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def level_for(points: int) -> dict:
    index = max(i for i, (threshold, _) in enumerate(LEVELS) if points >= threshold)
    nxt = LEVELS[index + 1][0] if index + 1 < len(LEVELS) else None
    return {"name": LEVELS[index][1], "next_at": nxt}


def build_game_api(get_db: Callable, require_venue_roles: Callable, now_fn: Callable[[], datetime], timezone_name: str,
                   trusted_proxies: tuple[str, ...] = ()) -> APIRouter:
    router = APIRouter(prefix="/api/venues/{venue_id}", tags=["game"])
    zone = ZoneInfo(timezone_name)
    Db = Annotated[Session, Depends(get_db)]
    Customer = Annotated[Principal, Depends(require_venue_roles("customer"))]
    Operator = Annotated[Principal, Depends(require_venue_roles("owner", "staff"))]
    OwnerOnly = Annotated[Principal, Depends(require_venue_roles("owner"))]
    code_attempts: dict[int, deque] = defaultdict(deque)

    # ---------------- helpers ----------------
    def local_day(now: datetime) -> str:
        return now.astimezone(zone).date().isoformat()

    def day_start_utc(day: str, plus_days: int = 0) -> datetime:
        start = datetime.fromisoformat(day).replace(tzinfo=zone) + timedelta(days=plus_days)
        return start.astimezone(timezone.utc).replace(tzinfo=None)

    def settings_for(db: Session, venue_id: int) -> GameSettings:
        row = db.get(GameSettings, venue_id)
        if row is None:
            row = GameSettings(venue_id=venue_id, streak_milestones=[list(m) for m in DEFAULT_MILESTONES], code_secret=secrets.token_hex(16))
            db.add(row)
            db.flush()
        return row

    def settings_view(row: GameSettings) -> dict:
        return {"checkin_mode": row.checkin_mode, "checkin_points": row.checkin_points,
                "streak_milestones": [{"days": d, "bonus": b} for d, b in row.streak_milestones],
                "wheel_enabled": row.wheel_enabled, "min_daily_prizes": row.min_daily_prizes, "max_daily_prizes": row.max_daily_prizes,
                "expected_daily_checkins": row.expected_daily_checkins, "spin_expiry_days": row.spin_expiry_days,
                "code_rotation_seconds": row.code_rotation_seconds}

    def game_for(db: Session, venue_id: int, customer_id: int) -> CustomerGame:
        row = db.get(CustomerGame, (venue_id, customer_id))
        if row is None:
            row = CustomerGame(venue_id=venue_id, customer_id=customer_id, points=0, streak=0, best_streak=0)
            db.add(row)
            db.flush()
        return row

    def add_points(db: Session, venue_id: int, customer_id: int, delta: int, reason: str, ref: str, now: datetime) -> bool:
        """Cộng điểm idempotent: trùng (reason, ref) thì bỏ qua và trả False."""
        if delta == 0:
            return False
        exists = db.scalar(select(PointLedger.id).where(PointLedger.venue_id == venue_id, PointLedger.customer_id == customer_id,
                                                        PointLedger.reason == reason, PointLedger.ref == ref))
        if exists:
            return False
        db.add(PointLedger(venue_id=venue_id, customer_id=customer_id, delta=delta, reason=reason, ref=ref, created_at=utc_naive(now)))
        game = game_for(db, venue_id, customer_id)
        game.points += delta
        return True

    def active_prizes(db: Session, venue_id: int) -> list[WheelPrize]:
        return list(db.scalars(select(WheelPrize).where(WheelPrize.venue_id == venue_id, WheelPrize.status == "ACTIVE")
                               .order_by(WheelPrize.position, WheelPrize.id)))

    def wheel_ready(prizes: list[WheelPrize]) -> bool:
        return len(prizes) >= 2 and any(p.kind == "nothing" for p in prizes)

    def prize_view(p: WheelPrize, owner: bool = False) -> dict:
        view = {"id": p.id, "name": p.name, "kind": p.kind, "value": p.value}  # khách không nhận tỷ lệ trúng
        if owner:
            view.update({"percent": p.weight_bp / 100, "weight_bp": p.weight_bp, "stock": p.stock_remaining, "voucher_valid_days": p.voucher_valid_days})
        return view

    def expire_tickets(db: Session, venue_id: int, customer_id: int | None, now: datetime) -> None:
        query = update(SpinTicket).where(SpinTicket.venue_id == venue_id, SpinTicket.status == "UNUSED", SpinTicket.expires_at <= utc_naive(now))
        if customer_id is not None:
            query = query.where(SpinTicket.customer_id == customer_id)
        db.execute(query.values(status="EXPIRED"))
        expired = db.execute(update(Voucher).where(Voucher.venue_id == venue_id, Voucher.status == "UNUSED", Voucher.expires_at <= utc_naive(now))
                             .values(status="EXPIRED"))
        db.commit()

    def code_for(settings: GameSettings, venue_id: int, slot: int) -> str:
        digest = hmac.new(settings.code_secret.encode(), f"{venue_id}:{slot}".encode(), hashlib.sha256).digest()
        return "".join(CODE_ALPHABET[b % len(CODE_ALPHABET)] for b in digest[:6])

    def current_slot(settings: GameSettings, now: datetime) -> int:
        return int(now.timestamp() // settings.code_rotation_seconds)

    def valid_code(settings: GameSettings, venue_id: int, given: str, now: datetime) -> bool:
        slot = current_slot(settings, now)
        given = (given or "").strip().upper()
        return any(hmac.compare_digest(code_for(settings, venue_id, s), given) for s in (slot, slot - 1))

    # ---------------- khách: trạng thái ----------------
    def streak_view(game: CustomerGame, today: str) -> int:
        """Chuỗi hiện tại; nếu bỏ lỡ từ hôm kia trở về trước thì coi như đã đứt."""
        if game.last_checkin_day is None:
            return 0
        yesterday = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
        return game.streak if game.last_checkin_day in (today, yesterday) else 0

    @router.get("/my/game")
    def my_game(venue_id: int, principal: Customer, db: Db):
        now = now_fn()
        uid = principal.user.id
        expire_tickets(db, venue_id, uid, now)
        settings = settings_for(db, venue_id)
        game = game_for(db, venue_id, uid)
        db.commit()
        today = local_day(now)
        streak = streak_view(game, today)
        days = [(datetime.fromisoformat(today) - timedelta(days=i)).date().isoformat() for i in range(13, -1, -1)]
        checked = set(db.scalars(select(Checkin.day).where(Checkin.venue_id == venue_id, Checkin.customer_id == uid, Checkin.day.in_(days))))
        tickets = db.scalars(select(SpinTicket).where(SpinTicket.venue_id == venue_id, SpinTicket.customer_id == uid, SpinTicket.status == "UNUSED")
                             .order_by(SpinTicket.id)).all()
        prizes = active_prizes(db, venue_id)
        vouchers = db.scalars(select(Voucher).where(Voucher.venue_id == venue_id, Voucher.customer_id == uid, Voucher.status == "UNUSED")
                              .order_by(Voucher.expires_at)).all()
        ledger = db.scalars(select(PointLedger).where(PointLedger.venue_id == venue_id, PointLedger.customer_id == uid)
                            .order_by(PointLedger.id.desc()).limit(10)).all()
        milestones = sorted(settings.streak_milestones)
        upcoming = next(([d, b] for d, b in milestones if d > streak), None)
        return {
            "points": game.points, "level": level_for(game.points), "streak": streak, "best_streak": game.best_streak,
            "checked_in_today": today in checked, "checkin_mode": settings.checkin_mode, "checkin_points": settings.checkin_points,
            "needs_code": settings.checkin_mode in ("code", "wifi_or_code", "wifi_and_code"),
            "calendar": [{"day": d, "checked": d in checked} for d in days],
            "next_milestone": {"days": upcoming[0], "bonus": upcoming[1]} if upcoming else None,
            "tickets": [{"id": t.id, "day": t.day, "expires_at": iso(t.expires_at)} for t in tickets],
            "wheel": {"enabled": settings.wheel_enabled and wheel_ready(prizes), "prizes": [prize_view(p) for p in prizes],
                      "daily_guarantee": settings.min_daily_prizes > 0},
            "vouchers": [{"id": v.id, "code": v.code, "label": v.label, "kind": v.kind, "value": v.value, "expires_at": iso(v.expires_at)} for v in vouchers],
            "ledger": [{"delta": r.delta, "reason": r.reason, "at": iso(r.created_at)} for r in ledger],
        }

    # ---------------- khách: check-in ----------------
    @router.post("/my/checkin")
    def checkin(venue_id: int, body: CheckinBody, request: Request, principal: Customer, db: Db):
        now = now_fn()
        uid = principal.user.id
        settings = settings_for(db, venue_id)
        if settings.checkin_mode == "off":
            raise HTTPException(409, "Quán chưa bật tính năng check-in.")
        today = local_day(now)
        game = game_for(db, venue_id, uid)
        already = db.scalar(select(Checkin.id).where(Checkin.venue_id == venue_id, Checkin.customer_id == uid, Checkin.day == today))
        if already:  # bấm lặp: không cộng thêm
            return {"already_checked_in": True, "points_added": 0, "streak": streak_view(game, today), "ticket_id": None}

        ip = client_ip(request.client.host if request.client else None, request.headers.get("x-forwarded-for"), trusted_proxies)
        networks = [n.cidr for n in db.scalars(select(VenueNetwork).where(VenueNetwork.venue_id == venue_id))]
        wants_wifi = settings.checkin_mode in ("wifi", "wifi_or_code", "wifi_and_code")
        wants_code = settings.checkin_mode in ("code", "wifi_or_code", "wifi_and_code")
        if wants_wifi and not networks and settings.checkin_mode != "wifi_or_code":
            raise HTTPException(409, "Quán chưa cài đặt mạng wifi để xác minh check-in.")
        wifi_ok = wants_wifi and ip_in_networks(ip, networks)
        code_ok = False
        if wants_code and body.code:
            hits = code_attempts[uid]
            ts = now.timestamp()
            while hits and ts - hits[0] > CODE_WINDOW:
                hits.popleft()
            if len(hits) >= CODE_ATTEMPTS:
                raise HTTPException(429, "Nhập sai mã quá nhiều lần. Đợi vài phút rồi thử lại.")
            code_ok = valid_code(settings, venue_id, body.code, now)
            if not code_ok:
                hits.append(ts)
        mode = settings.checkin_mode
        passed = {"wifi": wifi_ok, "code": code_ok, "wifi_or_code": wifi_ok or code_ok, "wifi_and_code": wifi_ok and code_ok}[mode]
        if not passed:
            messages = {"wifi": "Bạn cần kết nối wifi của quán để check-in.", "code": "Mã check-in không đúng hoặc đã hết hạn.",
                        "wifi_or_code": "Hãy kết nối wifi của quán hoặc nhập mã check-in đang hiện tại quầy.",
                        "wifi_and_code": "Cần kết nối wifi của quán và nhập đúng mã check-in tại quầy."}
            audit(db, now, "checkin_rejected", actor=principal.user, venue_id=venue_id, detail={"mode": mode, "wifi": wifi_ok, "code": code_ok})
            db.commit()
            raise HTTPException(403, messages[mode])

        method = "+".join(m for m, ok in (("wifi", wifi_ok), ("code", code_ok)) if ok)
        record = Checkin(venue_id=venue_id, customer_id=uid, day=today, method=method, ip=ip[:45], created_at=utc_naive(now))
        db.add(record)
        try:
            db.flush()
        except IntegrityError:  # hai request cùng lúc: request kia đã check-in
            db.rollback()
            return {"already_checked_in": True, "points_added": 0, "streak": streak_view(game_for(db, venue_id, uid), today), "ticket_id": None}

        yesterday = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
        game = game_for(db, venue_id, uid)
        game.streak = game.streak + 1 if game.last_checkin_day == yesterday else 1
        game.best_streak = max(game.best_streak, game.streak)
        game.last_checkin_day = today
        added = settings.checkin_points if add_points(db, venue_id, uid, settings.checkin_points, "checkin", today, now) else 0
        bonus = 0
        for days, amount in settings.streak_milestones:
            if game.streak == days and add_points(db, venue_id, uid, amount, "streak_bonus", f"{days}:{today}", now):
                bonus += amount
        ticket_id = None
        prizes = active_prizes(db, venue_id)
        if settings.wheel_enabled and wheel_ready(prizes):
            ticket = SpinTicket(venue_id=venue_id, customer_id=uid, day=today, expires_at=day_start_utc(today, settings.spin_expiry_days),
                                checkin_id=record.id, created_at=utc_naive(now))
            db.add(ticket)
            db.flush()
            ticket_id = ticket.id
        audit(db, now, "checkin", actor=principal.user, venue_id=venue_id, detail={"method": method, "streak": game.streak})
        db.commit()
        return {"already_checked_in": False, "points_added": added, "streak_bonus": bonus, "streak": game.streak, "ticket_id": ticket_id,
                "points": game.points}

    # ---------------- khách: quay ----------------
    def pick(pool: list[WheelPrize]) -> WheelPrize:
        total = sum(p.weight_bp for p in pool)
        if total <= 0:
            return pool[secrets.randbelow(len(pool))]
        roll = secrets.randbelow(total)
        for prize in pool:
            if roll < prize.weight_bp:
                return prize
            roll -= prize.weight_bp
        return pool[-1]

    def new_voucher_code(db: Session) -> str:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
            if not db.scalar(select(Voucher.id).where(Voucher.code == code)):
                return code

    def result_view(db: Session, result: SpinResult, prizes: list[WheelPrize], duplicate: bool) -> dict:
        voucher = db.scalar(select(Voucher).where(Voucher.source_result_id == result.id))
        index = next((i for i, p in enumerate(prizes) if p.id == result.prize_id), None)
        game = db.get(CustomerGame, (result.venue_id, result.customer_id))
        return {"duplicate": duplicate, "prize": {"id": result.prize_id, "name": result.prize_name, "kind": result.prize_kind, "value": result.prize_value},
                "prize_index": index, "voucher": {"code": voucher.code, "label": voucher.label, "expires_at": iso(voucher.expires_at)} if voucher else None,
                "points": game.points if game else 0}

    @router.post("/my/spins/{ticket_id}/spin")
    def spin(venue_id: int, ticket_id: int, principal: Customer, db: Db):
        now = now_fn()
        naive_now = utc_naive(now)
        ticket = db.get(SpinTicket, ticket_id)
        if ticket is None or ticket.venue_id != venue_id or ticket.customer_id != principal.user.id:
            raise HTTPException(404, "Không tìm thấy lượt quay.")
        prizes = active_prizes(db, venue_id)
        existing = db.scalar(select(SpinResult).where(SpinResult.ticket_id == ticket.id))
        if existing:  # quay lại cùng một vé: trả đúng kết quả cũ
            return result_view(db, existing, prizes, True)
        if ticket.status == "EXPIRED" or ticket.expires_at <= naive_now:
            ticket.status = "EXPIRED"
            db.commit()
            raise HTTPException(409, "Lượt quay đã hết hạn.")
        settings = settings_for(db, venue_id)
        if not settings.wheel_enabled or not wheel_ready(prizes):
            raise HTTPException(409, "Vòng quay của quán đang tạm tắt.")
        # Chiếm vé trước (khoá ghi của SQLite): hai request cùng vé chỉ một cái được quay.
        claimed = db.execute(update(SpinTicket).where(SpinTicket.id == ticket.id, SpinTicket.status == "UNUSED").values(status="USED"))
        if claimed.rowcount != 1:
            db.rollback()
            again = db.scalar(select(SpinResult).where(SpinResult.ticket_id == ticket_id))
            if again:
                return result_view(db, again, prizes, True)
            raise HTTPException(409, "Lượt quay này không dùng được.")

        day = local_day(now)
        plan = db.scalar(select(WheelDailyPlan).where(WheelDailyPlan.venue_id == venue_id, WheelDailyPlan.day == day))
        if plan is None:
            expected = settings.expected_daily_checkins
            k = min(settings.min_daily_prizes, expected)
            slots = sorted(secrets.SystemRandom().sample(range(1, expected + 1), k)) if k else []
            plan = WheelDailyPlan(venue_id=venue_id, day=day, expected=expected, guaranteed=slots, min_prizes=settings.min_daily_prizes,
                                  max_prizes=max(settings.max_daily_prizes, settings.min_daily_prizes))
            db.add(plan)
            db.flush()
        db.execute(update(WheelDailyPlan).where(WheelDailyPlan.id == plan.id).values(spin_count=WheelDailyPlan.spin_count + 1))
        db.refresh(plan)
        index = plan.spin_count
        slots = list(plan.guaranteed)

        real = [p for p in prizes if p.kind != "nothing" and (p.stock_remaining is None or p.stock_remaining > 0)]
        nothing = [p for p in prizes if p.kind == "nothing"]
        owed = len(slots) - plan.guaranteed_given  # thưởng đảm bảo còn nợ
        forced = index in slots or (index >= plan.expected and owed > 0)
        future_forced = sum(1 for s in slots if s > index)
        natural_allowed = plan.prizes_given + future_forced < plan.max_prizes
        if forced and real:
            prize = pick(real)
        elif forced:
            prize = pick(nothing)  # hết quà thật: không thể giữ cam kết, ghi nhận qua thống kê
        else:
            prize = pick([p for p in prizes if p.kind == "nothing" or (natural_allowed and p in real)])  # giữ thứ tự ô trên vòng quay
        if prize.kind != "nothing" and prize.stock_remaining is not None:
            taken = db.execute(update(WheelPrize).where(WheelPrize.id == prize.id, WheelPrize.stock_remaining > 0)
                               .values(stock_remaining=WheelPrize.stock_remaining - 1))
            if taken.rowcount != 1:
                prize = pick(nothing)
                forced = False

        result = SpinResult(ticket_id=ticket.id, venue_id=venue_id, customer_id=principal.user.id, prize_id=prize.id, prize_name=prize.name,
                            prize_kind=prize.kind, prize_value=prize.value, odds_bp=prize.weight_bp, spin_index=index, forced=forced,
                            day=day, created_at=naive_now)
        db.add(result)
        db.flush()
        if prize.kind == "points":
            add_points(db, venue_id, principal.user.id, prize.value, "wheel", str(result.id), now)
        elif prize.kind in ("discount_vnd", "free_minutes"):
            label = prize.name
            db.add(Voucher(venue_id=venue_id, customer_id=principal.user.id, code=new_voucher_code(db), kind=prize.kind, value=prize.value,
                           label=label, expires_at=naive_now + timedelta(days=prize.voucher_valid_days), source_result_id=result.id, created_at=naive_now))
        if prize.kind != "nothing":
            plan.prizes_given += 1
            if forced:
                plan.guaranteed_given += 1
        audit(db, now, "wheel_spin", actor=principal.user, venue_id=venue_id, target=prize.name,
              detail={"result_id": result.id, "spin_index": index, "kind": prize.kind, "odds_bp": prize.weight_bp})
        db.commit()
        return result_view(db, result, prizes, False)

    # ---------------- chủ quán: cài đặt ----------------
    @router.get("/game-settings")
    def get_game_settings(venue_id: int, _: OwnerOnly, db: Db):
        row = settings_for(db, venue_id)
        db.commit()
        return settings_view(row)

    @router.put("/game-settings")
    def put_game_settings(venue_id: int, body: GameSettingsBody, principal: OwnerOnly, db: Db):
        if body.max_daily_prizes < body.min_daily_prizes:
            raise HTTPException(400, "Số thưởng tối đa mỗi ngày phải lớn hơn hoặc bằng số thưởng tối thiểu.")
        days = [m.days for m in body.streak_milestones]
        if len(set(days)) != len(days):
            raise HTTPException(400, "Các mốc chuỗi ngày không được trùng nhau.")
        row = settings_for(db, venue_id)
        before = settings_view(row)
        prizes = active_prizes(db, venue_id)
        if body.min_daily_prizes > 0 and not any(p.kind != "nothing" and p.stock_remaining != 0 for p in prizes) and prizes:
            raise HTTPException(400, "Cần ít nhất một phần thưởng thật còn hàng trong vòng quay để đảm bảo thưởng mỗi ngày.")
        row.checkin_mode, row.checkin_points = body.checkin_mode, body.checkin_points
        row.streak_milestones = [[m.days, m.bonus] for m in sorted(body.streak_milestones, key=lambda m: m.days)]
        row.wheel_enabled, row.min_daily_prizes, row.max_daily_prizes = body.wheel_enabled, body.min_daily_prizes, body.max_daily_prizes
        row.expected_daily_checkins, row.spin_expiry_days, row.code_rotation_seconds = body.expected_daily_checkins, body.spin_expiry_days, body.code_rotation_seconds
        audit(db, now_fn(), "game_settings_changed", actor=principal.user, venue_id=venue_id, detail={"from": before, "to": settings_view(row)})
        db.commit()
        return settings_view(row)

    @router.get("/networks")
    def get_networks(venue_id: int, request: Request, _: OwnerOnly, db: Db):
        rows = db.scalars(select(VenueNetwork).where(VenueNetwork.venue_id == venue_id).order_by(VenueNetwork.id)).all()
        ip = client_ip(request.client.host if request.client else None, request.headers.get("x-forwarded-for"), trusted_proxies)
        return {"networks": [{"cidr": n.cidr, "label": n.label} for n in rows], "your_ip": ip}

    @router.put("/networks")
    def put_networks(venue_id: int, body: NetworksBody, principal: OwnerOnly, db: Db):
        normalized: dict[str, str | None] = {}
        for item in body.networks:
            try:
                normalized[normalize_cidr(item.cidr)] = (item.label or "").strip() or None
            except ValueError as err:
                raise HTTPException(400, str(err))
        old = db.scalars(select(VenueNetwork).where(VenueNetwork.venue_id == venue_id)).all()
        for row in old:
            db.delete(row)
        db.flush()
        for cidr, label in normalized.items():
            db.add(VenueNetwork(venue_id=venue_id, cidr=cidr, label=label))
        audit(db, now_fn(), "networks_changed", actor=principal.user, venue_id=venue_id,
              detail={"from": [n.cidr for n in old], "to": list(normalized)})
        db.commit()
        return {"networks": [{"cidr": c, "label": label} for c, label in normalized.items()]}

    # ---------------- chủ quán: vòng quay ----------------
    @router.get("/wheel")
    def get_wheel(venue_id: int, _: OwnerOnly, db: Db):
        prizes = active_prizes(db, venue_id)
        return {"prizes": [prize_view(p, owner=True) for p in prizes], "total_bp": sum(p.weight_bp for p in prizes)}

    @router.put("/wheel")
    def put_wheel(venue_id: int, body: WheelBody, principal: OwnerOnly, db: Db):
        items = body.prizes
        names = [i.name.strip().lower() for i in items]
        if len(set(names)) != len(names) or any(not n for n in names):
            raise HTTPException(400, "Tên các ô thưởng phải khác nhau và không để trống.")
        if sum(i.weight_bp for i in items) != 10000:
            raise HTTPException(400, f"Tổng tỷ lệ các ô phải đúng 100% (hiện {sum(i.weight_bp for i in items) / 100:g}%).")
        if not any(i.kind == "nothing" for i in items):
            raise HTTPException(400, "Cần ít nhất một ô \"Chúc may mắn\" (không trúng).")
        for i in items:
            if i.kind == "points" and not 1 <= i.value <= 100000:
                raise HTTPException(400, f"Ô \"{i.name}\": số điểm từ 1 đến 100.000.")
            if i.kind == "discount_vnd" and not 1000 <= i.value <= 1_000_000:
                raise HTTPException(400, f"Ô \"{i.name}\": giảm từ 1.000 đến 1.000.000 ₫.")
            if i.kind == "free_minutes" and not 5 <= i.value <= 600:
                raise HTTPException(400, f"Ô \"{i.name}\": số phút miễn phí từ 5 đến 600.")
        settings = settings_for(db, venue_id)
        if settings.min_daily_prizes > 0 and not any(i.kind != "nothing" and i.stock != 0 for i in items):
            raise HTTPException(400, "Cần ít nhất một phần thưởng thật còn hàng để đảm bảo thưởng mỗi ngày.")
        existing = {p.id: p for p in db.scalars(select(WheelPrize).where(WheelPrize.venue_id == venue_id, WheelPrize.status == "ACTIVE"))}
        before = [[p.name, p.weight_bp] for p in existing.values()]
        kept: set[int] = set()
        for position, item in enumerate(items):
            row = existing.get(item.id) if item.id else None
            if row is None:
                row = WheelPrize(venue_id=venue_id, name=item.name.strip(), kind=item.kind, value=item.value, weight_bp=item.weight_bp,
                                 position=position, voucher_valid_days=item.voucher_valid_days)
                db.add(row)
            else:
                kept.add(row.id)
                row.name, row.kind, row.value, row.weight_bp, row.position = item.name.strip(), item.kind, item.value, item.weight_bp, position
                row.voucher_valid_days = item.voucher_valid_days
            row.stock_remaining = None if item.kind == "nothing" else item.stock
        for prize_id, row in existing.items():
            if prize_id not in kept:
                row.status = "INACTIVE"
        db.flush()
        audit(db, now_fn(), "wheel_changed", actor=principal.user, venue_id=venue_id,
              detail={"from": before, "to": [[i.name, i.weight_bp] for i in items]})
        db.commit()
        prizes = active_prizes(db, venue_id)
        return {"prizes": [prize_view(p, owner=True) for p in prizes], "total_bp": sum(p.weight_bp for p in prizes)}

    # ---------------- quầy: mã check-in, thống kê ----------------
    @router.get("/checkin-code")
    def checkin_code(venue_id: int, _: Operator, db: Db):
        now = now_fn()
        settings = settings_for(db, venue_id)
        db.commit()
        slot = current_slot(settings, now)
        remaining = int((slot + 1) * settings.code_rotation_seconds - now.timestamp())
        return {"mode": settings.checkin_mode, "enabled": settings.checkin_mode in ("code", "wifi_or_code", "wifi_and_code"),
                "code": code_for(settings, venue_id, slot), "expires_in_seconds": remaining, "rotation_seconds": settings.code_rotation_seconds}

    @router.get("/game-stats")
    def game_stats(venue_id: int, _: OwnerOnly, db: Db):
        now = now_fn()
        today = local_day(now)
        plan = db.scalar(select(WheelDailyPlan).where(WheelDailyPlan.venue_id == venue_id, WheelDailyPlan.day == today))
        settings = settings_for(db, venue_id)
        db.commit()
        checkins = db.scalar(select(func.count()).select_from(Checkin).where(Checkin.venue_id == venue_id, Checkin.day == today))
        recent = db.execute(select(SpinResult, User.display_name).join(User, User.id == SpinResult.customer_id)
                            .where(SpinResult.venue_id == venue_id).order_by(SpinResult.id.desc()).limit(10)).all()
        return {
            "day": today, "checkins_today": checkins,
            "plan": {"expected": plan.expected if plan else settings.expected_daily_checkins,
                     "min_prizes": plan.min_prizes if plan else settings.min_daily_prizes,
                     "max_prizes": plan.max_prizes if plan else settings.max_daily_prizes,
                     "spins": plan.spin_count if plan else 0, "prizes_given": plan.prizes_given if plan else 0,
                     "guaranteed_total": len(plan.guaranteed) if plan else min(settings.min_daily_prizes, settings.expected_daily_checkins),
                     "guaranteed_given": plan.guaranteed_given if plan else 0, "created": plan is not None},
            "recent": [{"at": iso(r.created_at), "customer": name, "prize": r.prize_name, "kind": r.prize_kind} for r, name in recent],
        }

    return router
