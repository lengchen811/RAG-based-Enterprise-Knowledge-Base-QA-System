"""初始化数据库表（开发/测试用；生产建议 Alembic）。"""
import asyncio

from app.database import init_db


async def main() -> None:
    await init_db()
    print("数据库表初始化完成 ✅")


if __name__ == "__main__":
    asyncio.run(main())