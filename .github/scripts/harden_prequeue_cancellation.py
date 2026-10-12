from __future__ import annotations

from pathlib import Path

path = Path("acestep/openrouter_adapter.py")
text = path.read_text(encoding="utf-8")

old_marker = '''async def _admit_openrouter_job(
'''
new_helper = '''async def _run_prequeue_cover_conversion(handler: Any, src_audio_path: str) -> Any:
    """Keep the prequeue bound held until a started conversion thread exits.

    ``asyncio.to_thread`` cannot terminate a running Python/native thread when
    its awaiting request is cancelled. Waiting for that thread before
    propagating cancellation prevents repeated disconnects from creating an
    unbounded set of pre-admission conversion workers.
    """
    conversion = asyncio.create_task(
        asyncio.to_thread(handler.convert_src_audio_to_codes, src_audio_path)
    )
    try:
        return await asyncio.shield(conversion)
    except asyncio.CancelledError:
        while not conversion.done():
            try:
                await asyncio.shield(conversion)
            except asyncio.CancelledError:
                continue
        try:
            conversion.result()
        except BaseException:
            pass
        raise


async def _admit_openrouter_job(
'''
if text.count(old_marker) != 1:
    raise RuntimeError(f"expected one admission marker, found {text.count(old_marker)}")
text = text.replace(old_marker, new_helper, 1)

old_call = '''                            codes_str = await asyncio.to_thread(
                                handler.convert_src_audio_to_codes,
                                src_audio_path,
                            )
'''
new_call = '''                            codes_str = await _run_prequeue_cover_conversion(
                                handler,
                                src_audio_path,
                            )
'''
if text.count(old_call) != 1:
    raise RuntimeError(f"expected one conversion call, found {text.count(old_call)}")
text = text.replace(old_call, new_call, 1)
path.write_text(text, encoding="utf-8")
print("prequeue cancellation containment integrated")
