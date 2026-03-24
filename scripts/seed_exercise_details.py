import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from flexloop.db.engine import async_session, init_db
from flexloop.models.exercise import Exercise


async def seed():
    await init_db()
    data_path = Path(__file__).parent.parent / "data" / "exercise_details.json"
    with open(data_path) as f:
        details = json.load(f)

    async with async_session() as session:
        result = await session.execute(select(Exercise))
        exercises = result.scalars().all()

        updated = 0
        for ex in exercises:
            if ex.name in details:
                ex.metadata_json = details[ex.name]
                updated += 1

        await session.commit()
        print(f"Updated {updated} exercises with detailed metadata")


if __name__ == "__main__":
    asyncio.run(seed())
