"""Probe the ordinary embedded EPF without desktop control or database writes."""
import asyncio
import json
import sys
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from onec_mcp_toolkit_proxy.approval_control import SET_APPROVAL_MODE_SCHEMA

RESULT = ROOT / ".local/http-mvp" / ("approval-control-" + sys.argv[1] + ".json")
records = []


async def main():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:17825", timeout=40, trust_env=False) as http:
        async def rest(tool, args):
            r = await http.post("/api/" + tool, json=args)
            data = r.json()
            records.append({"transport": "rest", "tool": tool, "arguments": args, "status": r.status_code, "response": data})
            RESULT.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            return r.status_code, data

        async def state():
            _, r = await rest("execute_code", {"execution_context": "client", "code":
                'Результат = Новый Структура("mode,generation", РежимПодтвержденияОпасныхОпераций, ПоколениеРазрешений);'})
            assert r["success"], r
            return r["data"]

        initial = await state()
        assert initial["mode"] == "ask", initial
        if sys.argv[1] == "after-restart":
            async with streamablehttp_client("http://127.0.0.1:17825/mcp") as streams:
                async with ClientSession(streams[0], streams[1]) as client:
                    await client.initialize()
                    for args in ({"mode": "permanent"}, {"mode": "ask", "persist": True}, {}):
                        response = await client.call_tool("set_approval_mode", args)
                        value = json.loads(response.content[0].text)
                        records.append({"transport": "mcp", "arguments": args, "response": value})
                        assert response.isError and not value["success"], response
                        assert await state() == initial
            print("session_allow reset to ask in fresh EPF session")
            return

        async with streamablehttp_client("http://127.0.0.1:17825/mcp") as streams:
            async with ClientSession(streams[0], streams[1]) as client:
                await client.initialize()
                tool = next(t for t in (await client.list_tools()).tools if t.name == "set_approval_mode")
                assert tool.inputSchema == SET_APPROVAL_MODE_SCHEMA["inputSchema"], tool.inputSchema
                previous = "ask"
                for mode in ("deny", "session_allow", "ask", "session_allow"):
                    r = await client.call_tool("set_approval_mode", {"mode": mode})
                    value = json.loads(r.content[0].text)
                    records.append({"transport": "mcp", "mode": mode, "response": value})
                    assert value == {"success": True, "data": {"mode": mode, "previous_mode": previous, "scope": "toolkit_session"}}, value
                    current = await state()
                    assert current["mode"] == mode and current["generation"] > initial["generation"], current
                    initial = current
                    previous = mode

        for args in ({}, {"mode": "permanent"}, {"mode": "ASK"}, {"mode": True}, {"mode": None},
                     {"mode": "session_allow", "persist": True}):
            status, value = await rest("set_approval_mode", args)
            assert status == 422 and not value["success"], (args, status, value)
            assert await state() == initial
        status, value = await rest("set_approval_mode", {"mode": "session_allow"})
        assert status == 200 and value["data"]["previous_mode"] == "session_allow", value
        assert await state() == initial

        harmless_danger = {"execution_context": "client", "code":
            "МассивПроверки = Новый Массив; МассивПроверки.Добавить(1); МассивПроверки.Удалить(0); Результат = МассивПроверки.Количество();"}
        _, value = await rest("execute_code", harmless_danger)
        assert value["success"] and value["data"] == 0, value
        await rest("set_approval_mode", {"mode": "deny"})
        _, value = await rest("execute_code", harmless_danger)
        assert not value["success"] and "запрещена" in value["error"], value
        await rest("set_approval_mode", {"mode": "ask"})
        assert (await state())["mode"] == "ask"
        await rest("set_approval_mode", {"mode": "session_allow"})
        print("native MCP schema/modes; REST validation/shared state; generation/repeat; allow/deny passed")


asyncio.run(main())
