from __future__ import annotations

from pathlib import Path

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            target = Path(path)
            if target.name and "." in target.name:
                raise
            return await super().get_response("index.html", scope)
