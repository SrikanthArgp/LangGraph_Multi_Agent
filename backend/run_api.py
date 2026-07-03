"""Run the FastAPI app locally.

`uvicorn api.main:app` does NOT work on Windows for this app: modern uvicorn
(get_loop_factory(), replacing the old set_event_loop_policy()-based setup) hardcodes
asyncio.ProactorEventLoop on win32 whenever the "asyncio" loop is selected (see
uvicorn.loops.asyncio.asyncio_loop_factory) - setting the event loop policy ourselves has no
effect, since uvicorn passes its own loop_factory straight to asyncio.run(), bypassing the
policy mechanism entirely. psycopg's async pool cannot run on Proactor. Passing a custom loop
factory callable (not one of uvicorn's "auto"/"asyncio"/"uvloop" strings) skips uvicorn's
platform check and uses a plain SelectorEventLoop instead.
"""

import asyncio
import sys

import uvicorn


def selector_event_loop_factory() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop()


if __name__ == "__main__":
    # uvicorn's type stub only declares `loop: LoopFactoryType | str`, but Config.get_loop_factory()
    # happily accepts a plain callable at runtime (uvicorn.importer.import_from_string returns
    # non-str input unchanged) - confirmed working, see the module docstring above.
    loop = selector_event_loop_factory if sys.platform == "win32" else "auto"
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False, loop=loop)  # type: ignore[arg-type]
