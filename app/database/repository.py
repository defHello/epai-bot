from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Order


ACTIVE_STATUSES = ("new", "process", "ordered", "stock")
MAX_ACTIVE_ORDERS = 2


async def count_active_orders(session: AsyncSession, client_id: int) -> int:
    result = await session.execute(
        select(func.count(Order.id)).where(
            Order.client_id == client_id,
            Order.status.in_(ACTIVE_STATUSES),
        )
    )
    return result.scalar_one()


async def count_orders_by_status(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(
        select(Order.status, func.count(Order.id)).group_by(Order.status)
    )
    return {status: count for status, count in result.all()}


async def get_active_orders(session: AsyncSession, limit: int = 20) -> list[Order]:
    result = await session.execute(
        select(Order)
        .where(Order.status.in_(ACTIVE_STATUSES))
        .order_by(Order.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_client_active_orders(
    session: AsyncSession,
    client_id: int,
) -> list[Order]:
    result = await session.execute(
        select(Order)
        .where(
            Order.client_id == client_id,
            Order.status.in_(ACTIVE_STATUSES),
        )
        .order_by(Order.created_at.desc())
    )
    return list(result.scalars().all())


async def create_order(
    session: AsyncSession,
    client_id: int,
    name: str,
    phone: str,
    description: str,
    photos: list[str] | None = None,
) -> Order:
    photos_str = ",".join(photos) if photos else ""
    order = Order(
        client_id=client_id,
        name=name,
        phone=phone,
        description=description,
        photos=photos_str,
        price="",
        status="new",
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


async def update_order_status(
    session: AsyncSession,
    order_id: int,
    new_status: str,
) -> Order | None:
    order = await session.get(Order, order_id)
    if order is None:
        return None
    order.status = new_status
    await session.commit()
    await session.refresh(order)
    return order


async def update_order_price(
    session: AsyncSession,
    order_id: int,
    price: str,
) -> Order | None:
    order = await session.get(Order, order_id)
    if order is None:
        return None
    order.price = price
    await session.commit()
    await session.refresh(order)
    return order


async def set_order_card_info(
    session: AsyncSession,
    order_id: int,
    message_id: int,
    card_text: str,
) -> None:
    order = await session.get(Order, order_id)
    if order is None:
        return
    order.card_message_id = message_id
    order.card_text = card_text
    await session.commit()


async def set_order_photos_message_id(
    session: AsyncSession,
    order_id: int,
    message_id: int,
) -> None:
    order = await session.get(Order, order_id)
    if order is None:
        return
    order.photos_message_id = message_id
    await session.commit()


async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    return await session.get(Order, order_id)


async def cancel_order(
    session: AsyncSession,
    order_id: int,
    client_id: int,
) -> Order | None:
    order = await session.get(Order, order_id)
    if order is None:
        return None
    if order.client_id != client_id:
        return None
    if order.status != "new":
        return None
    order.status = "cancelled"
    await session.commit()
    await session.refresh(order)
    return order