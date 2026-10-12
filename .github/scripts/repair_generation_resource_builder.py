from __future__ import annotations

from pathlib import Path

path = Path(__file__).with_name("apply_generation_resource_bounds.py")
text = path.read_text(encoding="utf-8")

old_count = '''    expected=3,\n)\n# release_task has the same block without a blank line after content_type.\n'''
new_count = '''    expected=2,\n)\n# format_input and release_task use the same parser without the extra blank line.\nreplace_once(\n    "acestep/ui/gradio/api/api_routes.py",\n    \'\'\'    content_type = (request.headers.get("content-type") or "").lower()\\n    if "json" in content_type:\\n        body = await request.json()\\n    else:\\n        form = await request.form()\\n        body = {k: v for k, v in form.items()}\\n\\n    verify_token_from_request(body, authorization)\\n\\n    caption = body.get("prompt", "") or ""\\n\'\'\',\n    \'\'\'    body = await _read_api_payload(request)\\n\\n    verify_token_from_request(body, authorization)\\n\\n    caption = body.get("prompt", "") or ""\\n\'\'\',\n)\n# release_task has the same block and is anchored by task_id creation.\n'''

if text.count(old_count) != 1:
    raise RuntimeError("Expected exactly one parser-count repair target")
path.write_text(text.replace(old_count, new_count, 1), encoding="utf-8")
print("generation resource builder parser coverage repaired")
