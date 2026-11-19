"""REST entry points using the common durable owner and existing delivery queue."""
from starlette.responses import JSONResponse
from starlette.routing import Route

from .test_client_contract import TEST_TOOLS
from .test_client_operations import execute_test_operation


def endpoint(tool):
    async def handle(request):
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            return JSONResponse({"success": False, "error": "invalid_params: expected application/json"}, status_code=415)
        try:
            arguments = await request.json()
        except (ValueError, UnicodeError):
            return JSONResponse({"success": False, "error": "invalid_params: expected JSON object"}, status_code=400)
        from .rest_api import _get_channel
        return JSONResponse(await execute_test_operation(_get_channel(request), tool, arguments),
                            headers={"Cache-Control": "no-store"})
    return handle


test_client_routes = [Route("/api/" + tool, endpoint(tool), methods=["POST"]) for tool in sorted(TEST_TOOLS)]
