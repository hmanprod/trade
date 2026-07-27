from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings

clean_url = settings.database_url.split("?")[0]
engine = create_async_engine(clean_url, pool_size=5, max_overflow=2)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session
