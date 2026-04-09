from __future__ import annotations

import asyncio
import logging

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
        "ru": "Пожалуйста, подождите несколько секунд — мы готовим проверку.",
        "kk": "Өтінеміз, бірнеше секунд күтіңіз — тексеруді дайындаймыз.",
        "en": "Please wait a moment while we prepare the check for you.",
    },
    "blink": {
        "ru": "Пожалуйста, один раз моргните.",
        "kk": "Өтінеміз, көзіңізді бір рет жұмыңыз.",
        "en": "Please blink once, when you are ready.",
    },
    "yaw": {
        "ru": "Пожалуйста, слегка поверните голову влево или вправо.",
        "kk": "Өтінеміз, басыңызды сәл солға немесе оңға бұраңыз.",
        "en": "Please turn your head gently to the left or to the right.",
    },
    "smile": {
        "ru": "Пожалуйста, слегка улыбнитесь.",
        "kk": "Өтінеміз, жеңіл күлімсіреңіз.",
        "en": "Please give a slight smile, if you would.",
    },
    "unavailable": {
        "ru": "К сожалению, в этом браузере проверка недоступна. "
        "Вы можете снять кадр вручную — спасибо за понимание.",
        "kk": "Өкінішке орай, бұл браузерде тексеру қолжетімсіз. "
        "Суретті қолмен түсіре аласыз — түсінгеніңізге рахмет.",
        "en": "We are sorry — this check is not available in this browser. "
        "You may take a photo manually. Thank you for your understanding.",
    },
    # Ручная съёмка Face Lab / профиль (те же phase, что фронт: setup_<context>).
    "setup_profile_photo": {
        "ru": "Пожалуйста, смотрите прямо в камеру. В светлой рамке на видео показан "
        "силуэт головы фронтально; совместите своё лицо с ним и нажмите затвор.",
        "kk": "Өтінеміз, камераға тік қараңыз. Бейнедегі жарық рамка ішінде беттің алдыңғы "
        "силуэті көрсетілген; бетіңізді сәйкестендіріп, түсіріңіз батырмасын басыңыз.",
        "en": "Please look straight at the camera. Inside the bright frame you will see a "
        "front-facing head silhouette; align your face with it, then tap the shutter.",
    },
    "setup_bootstrap_front": {
        "ru": "Пожалуйста, встаньте прямо перед камерой.",
        "kk": "Өтінеміз, камера алдында тік тұрыңыз.",
        "en": "Please stand squarely in front of the camera.",
    },
    "setup_bootstrap_left": {
        "ru": "Пожалуйста, слегка поверните голову влево примерно на двадцать градусов — "
        "разворот лица к камере, не наклон ухом к плечу. В рамке лицо на анимации уходит "
        "вглубь экрана — повторите такой поворот и снимите.",
        "kk": "Өтінеміз, басыңызды шамамен жиырма градусқа солға бұраңыз — "
        "бетті камераға бұраңыз, құлақты иіспей. Рамкадағы анимация бетті экран тереңіне қарай "
        "бұрады — соған сәйкестендіріп түсіріңіз.",
        "en": "Please turn your head slightly left, about twenty degrees — swivel your face "
        "toward the camera, not an ear-to-shoulder tilt. The face in the frame moves into the "
        "screen in 3D — match that turn, then capture.",
    },
    "setup_bootstrap_right": {
        "ru": "Пожалуйста, слегка поверните голову вправо примерно на двадцать градусов — "
        "разворот лица к камере, не наклон ухом к плечу. В рамке лицо на анимации уходит "
        "вглубь экрана — повторите такой поворот и снимите.",
        "kk": "Өтінеміз, басыңызды шамамен жиырма градусқа оңға бұраңыз — "
        "бетті камераға бұраңыз, құлақты иіспей. Рамкадағы анимация бетті экран тереңіне қарай "
        "бұрады — соған сәйкестендіріп түсіріңіз.",
        "en": "Please turn your head slightly right, about twenty degrees — swivel your face "
        "toward the camera, not an ear-to-shoulder tilt. The face in the frame moves into the "
        "screen in 3D — match that turn, then capture.",
    },
}

_ALLOWED_PHASES = frozenset(FACE_LAB_TTS_PHRASES.keys())
_ALLOWED_LANGS = frozenset({"ru", "kk", "en"})

_CACHE_PREFIX = "face_lab_tts:v2"
_CACHE_TTL = 60 * 60 * 24 * 30


def _voice_for_lang(lang: str) -> str:
    if lang == "kk":
        return (
            getattr(settings, "FACE_LAB_EDGE_TTS_VOICE_KK", "") or "kk-KZ-AigulNeural"
        )
    if lang == "en":
        return (
            getattr(settings, "FACE_LAB_EDGE_TTS_VOICE_EN", "") or "en-US-JennyNeural"
        )
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
            logger.exception(
                "face_lab_tts_view: edge-tts failed for %s/%s", phase, lang
            )
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
