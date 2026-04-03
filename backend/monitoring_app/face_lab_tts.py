from __future__ import annotations

import asyncio
import logging

import edge_tts
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

logger = logging.getLogger(__name__)

FACE_LAB_TTS_PHRASES: dict[str, dict[str, str]] = {
    "loading": {
        "ru": "Секунду, готовим проверку.",
        "kk": "Бір секунд, тексеруді дайындаймыз.",
        "en": "One moment, we are getting the check ready.",
    },
    "blink": {
        "ru": "Моргните один раз, пожалуйста.",
        "kk": "Көзіңізді бір рет жұмыңыз, өтінеміз.",
        "en": "Please blink once.",
    },
    "yaw": {
        "ru": "Слегка поверните голову в сторону: влево или вправо, пожалуйста.",
        "kk": "Басыңызды сәл жаққа бұраңыз: солға немесе оңға, өтінеміз.",
        "en": "Please turn your head slightly to the side — left or right.",
    },
    "smile": {
        "ru": "Слегка улыбнитесь, пожалуйста.",
        "kk": "Жеңіл күлімсіреңіз, өтінеміз.",
        "en": "Please smile a little.",
    },
    "unavailable": {
        "ru": "В этом браузере проверка недоступна. Можно снять кадр вручную.",
        "kk": "Бұл браузерде тексеру жоқ. Суретті қолмен ала аласыз.",
        "en": "This check is not available in this browser. You can take a photo manually.",
    },
}

_ALLOWED_PHASES = frozenset(FACE_LAB_TTS_PHRASES.keys())
_ALLOWED_LANGS = frozenset({"ru", "kk", "en"})

_CACHE_PREFIX = "face_lab_tts:v1.1"
_CACHE_TTL = 60 * 60 * 24 * 30


def _voice_for_lang(lang: str) -> str:
    if lang == "kk":
        return getattr(settings, "FACE_LAB_EDGE_TTS_VOICE_KK", "") or "kk-KZ-AigulNeural"
    if lang == "en":
        return getattr(settings, "FACE_LAB_EDGE_TTS_VOICE_EN", "") or "en-US-JennyNeural"
    return getattr(settings, "FACE_LAB_EDGE_TTS_VOICE_RU", "") or "ru-RU-SvetlanaNeural"


async def _edge_tts_mp3_async(text: str, voice: str) -> bytes:
    communicate = edge_tts.Communicate(text, voice)
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk.get("type") != "audio":
            continue
        raw = chunk.get("data")
        if isinstance(raw, (bytes, bytearray)):
            chunks.append(bytes(raw))
    return b"".join(chunks)


def _edge_tts_mp3(text: str, voice: str) -> bytes:
    return asyncio.run(_edge_tts_mp3_async(text, voice))


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def face_lab_tts_view(request):
    """Return MP3 for a fixed Face Lab liveness phrase (phase + lang)."""
    phase = (request.query_params.get("phase") or "").strip()
    lang = (request.query_params.get("lang") or "").strip()
    if phase not in _ALLOWED_PHASES or lang not in _ALLOWED_LANGS:
        return Response(
            {"error": "Invalid phase or lang."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    text = FACE_LAB_TTS_PHRASES[phase][lang]
    cache_key = f"{_CACHE_PREFIX}:{phase}:{lang}"

    audio = cache.get(cache_key)
    if audio is None:
        voice = _voice_for_lang(lang)
        try:
            audio = _edge_tts_mp3(text, voice)
        except Exception:
            logger.exception("face_lab_tts_view: edge-tts failed for %s/%s", phase, lang)
            return Response(
                {"error": "TTS synthesis failed."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if audio:
            cache.set(cache_key, audio, timeout=_CACHE_TTL)

    if not audio:
        return Response(
            {"error": "Empty TTS response."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    response = HttpResponse(audio, content_type="audio/mpeg")
    response["Cache-Control"] = "private, max-age=86400"
    return response
