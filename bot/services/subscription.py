import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Subscription, User

logger = logging.getLogger(__name__)

TRIAL_DAYS = 2


async def register_user(session: AsyncSession, user_id: int, username: str | None, first_name: str | None) -> User:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        return user

    now = datetime.utcnow()
    user = User(
        id=user_id,
        username=username,
        first_name=first_name,
        registered_at=now,
        trial_start=now,
        trial_end=now + timedelta(days=TRIAL_DAYS),
        access_status="trial",
    )
    session.add(user)
    await session.commit()
    logger.info("New user registered: %d", user_id)
    return user


async def check_access(session: AsyncSession, user_id: int) -> bool:
    now = datetime.utcnow()
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return False

    if user.access_status == "active":
        sub_result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id, Subscription.is_active.is_(True), Subscription.end_date > now)
            .order_by(Subscription.end_date.desc())
            .limit(1)
        )
        sub = sub_result.scalar_one_or_none()
        if sub:
            return True
        user.access_status = "expired"

    if user.access_status == "trial" and user.trial_end and user.trial_end > now:
        return True

    if user.access_status == "trial":
        user.access_status = "expired"

    await session.commit()
    return False


async def activate_subscription(session: AsyncSession, user_id: int, sub_type: str, duration_days: int) -> None:
    now = datetime.utcnow()
    result = await session.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.is_active.is_(True), Subscription.end_date > now)
        .order_by(Subscription.end_date.desc())
        .limit(1)
    )
    active_sub = result.scalar_one_or_none()
    start = active_sub.end_date if active_sub else now

    sub = Subscription(
        user_id=user_id,
        start_date=start,
        end_date=start + timedelta(days=duration_days),
        sub_type=sub_type,
        is_active=True,
    )
    session.add(sub)

    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one()
    user.access_status = "active"

    await session.commit()
    logger.info("Subscription activated: user=%d type=%s", user_id, sub_type)


async def grant_access(session: AsyncSession, user_id: int, days: int) -> None:
    await activate_subscription(session, user_id, "manual", days)
