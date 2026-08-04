"""创建演示用户并生成一份示例文档（便于快速演示）。"""
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

from app.database import AsyncSessionLocal, init_db
from app.models.user import User
from app.core.security import hash_password

SAMPLE_DOC = """# 员工手册（示例）

## 1. 考勤制度

公司实行每周五天工作制，工作时间上午 9:00 至下午 18:00。
员工上下班需使用钉钉打卡，迟到超过 30 分钟记为迟到，月度累计迟到 3 次以上
将影响当月绩效评级。

## 2. 休假制度

### 2.1 年假
员工入职满一年后，每年享有 5 天带薪年假；工龄每增加一年，年假增加 1 天，
上限 15 天。

### 2.2 事假
事假需提前一天通过 OA 系统申请，经直属主管审批后方可休假。

## 3. 报销制度

报销需提供发票原件，金额超过 500 元的需部门负责人审批；
交通费实报实销，餐费标准为 200 元/天。
"""


async def main() -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        # 创建演示用户
        result = await session.execute(select(User).where(User.username == "admin"))
        if result.scalar_one_or_none() is None:
            session.add(User(username="admin", password_hash=hash_password("admin123")))
            print("已创建演示用户：admin / admin123")
        else:
            print("演示用户已存在，跳过")

        # 写入示例文档
        data_dir = Path(__file__).resolve().parent.parent / "data" / "seeds"
        data_dir.mkdir(parents=True, exist_ok=True)
        sample_path = data_dir / "员工手册示例.md"
        sample_path.write_text(SAMPLE_DOC, encoding="utf-8")
        await session.commit()

    print(f"示例文档已生成：{sample_path}")
    print("完成 ✅")


if __name__ == "__main__":
    asyncio.run(main())