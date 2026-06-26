from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity):
        self._session.add(entity)
        await self._session.flush()

    async def get(self, entity_class, entity_id):
        return await self._session.get(entity_class, entity_id)

    async def list(self, query):
        result = await self._session.execute(query)
        return result.scalars().all()
