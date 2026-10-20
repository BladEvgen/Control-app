from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

import edge_tts
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

logger = logging.getLogger(__name__)

FACE_LAB_TTS_PHRASES: dict[str, dict[str, str]] = {
    "loading": {
        "ru": "Включаю камеру. Подождите пару секунд.",
        "kk": "Камераны қосып жатырмын. Бірнеше секунд күтіңіз.",
        "en": "Starting the camera. Please wait a couple of seconds.",
    },
    "face": {
        "ru": "Посмотрите в камеру. Лицо должно быть целиком в овале.",
        "kk": "Камераға қараңыз. Бетіңіз толығымен сопақтың ішінде болсын.",
        "en": "Look at the camera and keep your whole face inside the oval.",
    },
    "blink": {
        "ru": "Теперь медленно моргните.",
        "kk": "Енді баяу көзіңізді жұмып ашыңыз.",
        "en": "Now blink slowly.",
    },
    "turn_left": {
        "ru": "Плавно поверните голову влево, затем верните прямо.",
        "kk": "Басыңызды баяу солға бұрып, қайта тура қараңыз.",
        "en": "Slowly turn your head to the left, then back to the center.",
    },
    "turn_right": {
        "ru": "Плавно поверните голову вправо, затем верните прямо.",
        "kk": "Басыңызды баяу оңға бұрып, қайта тура қараңыз.",
        "en": "Slowly turn your head to the right, then back to the center.",
    },
    "smile": {
        "ru": "Улыбнитесь.",
        "kk": "Күлімсіреңіз.",
        "en": "Now smile.",
    },
    "mouth_open": {
        "ru": "Приоткройте рот, как будто говорите «а».",
        "kk": "Аузыңызды сәл ашыңыз, «а» дегендей.",
        "en": 'Open your mouth a little, as if saying "ah".',
    },
    "hold": {
        "ru": "Замрите.",
        "kk": "Қозғалмаңыз.",
        "en": "Hold still.",
    },
    "unavailable": {
        "ru": "Автоматическая проверка не запустилась. Сделайте снимок кнопкой внизу.",
        "kk": "Автоматты тексеру іске қосылмады. Төмендегі батырмамен суретке түсіріңіз.",
        "en": "The automatic check did not start. Take the photo with the button below.",
    },
    "setup_profile_photo": {
        "ru": "Посмотрите прямо в камеру. Лицо в центре рамки, свет спереди.",
        "kk": "Камераға тура қараңыз. Бетіңіз жақтаудың ортасында, жарық алдыңғы жақтан түссін.",
        "en": "Look straight at the camera, face in the center, light in front of you.",
    },
    "setup_bootstrap_front": {
        "ru": "Первый снимок. Посмотрите прямо в камеру, голову держите ровно.",
        "kk": "Бірінші сурет. Камераға тура қарап, басыңызды түзу ұстаңыз.",
        "en": "First photo. Look straight at the camera and keep your head level.",
    },
    "setup_bootstrap_left": {
        "ru": "Второй снимок. Немного поверните голову влево и не наклоняйте её.",
        "kk": "Екінші сурет. Басыңызды сәл солға бұрыңыз, еңкейтпеңіз.",
        "en": "Second photo. Turn your head a little to the left without tilting it.",
    },
    "setup_bootstrap_right": {
        "ru": "Третий снимок. Немного поверните голову вправо и не наклоняйте её.",
        "kk": "Үшінші сурет. Басыңызды сәл оңға бұрыңыз, еңкейтпеңіз.",
        "en": "Third photo. Turn your head a little to the right without tilting it.",
    },
}

_ALLOWED_PHASES = frozenset(FACE_LAB_TTS_PHRASES.keys())
_ALLOWED_LANGS = frozenset({"ru", "kk", "en"})

_CACHE_PREFIX = "face_lab_tts:v6"
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
    """Return MP3 for Face Lab: liveness phases + setup_profile/bootstrap (phase + lang)."""
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
    response["X-Tts-Text"] = quote(text)
    return response
