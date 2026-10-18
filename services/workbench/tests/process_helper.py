"""Test-only service with slow handlers; never installed in the package."""
import asyncio
import time
from workbench.__main__ import main
from workbench.rpc import RpcRouter

register = RpcRouter.register
def with_test_handlers(self, method, handler, *, internal=False):
    register(self, method, handler, internal=internal)
    if method == "system.ping":
        async def slow_async():
            await asyncio.sleep(.6)
            return "slow"
        def slow_sync():
            time.sleep(10)
            return "slow"
        register(self, "test.slow", slow_async)
        register(self, "test.block", slow_sync)

RpcRouter.register = with_test_handlers
main()
