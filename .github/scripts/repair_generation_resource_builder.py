from __future__ import annotations

from pathlib import Path

path = Path(__file__).with_name("apply_generation_resource_bounds.py")
text = path.read_text(encoding="utf-8")

old_count = '''    expected=3,\n)\n# release_task has the same block without a blank line after content_type.\n'''
new_count = '''    expected=2,\n)\n# format_input and release_task use the same parser without the extra blank line.\nreplace_once(\n    "acestep/ui/gradio/api/api_routes.py",\n    \'\'\'    content_type = (request.headers.get("content-type") or "").lower()\\n    if "json" in content_type:\\n        body = await request.json()\\n    else:\\n        form = await request.form()\\n        body = {k: v for k, v in form.items()}\\n\\n    verify_token_from_request(body, authorization)\\n\\n    caption = body.get("prompt", "") or ""\\n\'\'\',\n    \'\'\'    body = await _read_api_payload(request)\\n\\n    verify_token_from_request(body, authorization)\\n\\n    caption = body.get("prompt", "") or ""\\n\'\'\',\n)\n# release_task has the same block and is anchored by task_id creation.\n'''

if text.count(old_count) != 1:
    raise RuntimeError("Expected exactly one parser-count repair target")
text = text.replace(old_count, new_count, 1)

old_cancel = '''        reason = store.cancellation_reason(job_id)\n'''
new_cancel = '''        cancellation_checker = getattr(store, "cancellation_reason", None)\n        reason = cancellation_checker(job_id) if callable(cancellation_checker) else None\n'''
if text.count(old_cancel) != 1:
    raise RuntimeError("Expected exactly one queue cancellation compatibility target")
text = text.replace(old_cancel, new_cancel, 1)

path.write_text(text, encoding="utf-8")
print("generation resource builder parser and queue compatibility repaired")
