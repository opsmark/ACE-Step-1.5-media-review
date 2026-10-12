from __future__ import annotations

from pathlib import Path

path = Path("acestep/api/generation_resource_middleware_test.py")
text = path.read_text(encoding="utf-8")
old_signature = '''async def _exercise_middleware(*, path="/release_task", chunks=(), headers=(), limit=10):\n'''
new_signature = '''async def _exercise_middleware(\n    *, path="/release_task", chunks=(), headers=(), limit=10, limited_path="/release_task"\n):\n'''
old_constructor = '''    middleware = RequestBodyLimitMiddleware(app, path_limits={path: limit})\n'''
new_constructor = '''    middleware = RequestBodyLimitMiddleware(app, path_limits={limited_path: limit})\n'''
if text.count(old_signature) != 1 or text.count(old_constructor) != 1:
    raise RuntimeError("Unexpected middleware test helper shape")
text = text.replace(old_signature, new_signature, 1).replace(old_constructor, new_constructor, 1)
path.write_text(text, encoding="utf-8")
print("middleware non-target test harness repaired")
