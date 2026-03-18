import re

with open('/home/hfy/APP/All_bot/src/quota.py', 'r') as f:
    content = f.read()

new_method = """
    async def clear_temporary_ingots(self):
        \"\"\"Clear all temporary ingots at midnight\"\"\"
        async with AsyncSessionLocal() as session:
            stmt = update(User).where(User.temporary_ingot > 0).values(temporary_ingot=0)
            await session.execute(stmt)
            await session.commit()
            print(f"🔄 Temporary ingots cleared at {datetime.now().isoformat()}")

"""

if "clear_temporary_ingots" not in content:
    content = content.replace('    async def get_referral_count(self, user_id: int) -> int:', new_method + '    async def get_referral_count(self, user_id: int) -> int:')

    with open('/home/hfy/APP/All_bot/src/quota.py', 'w') as f:
        f.write(content)
