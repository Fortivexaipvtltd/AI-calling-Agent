from __future__ import annotations

# The 22 scheduled languages of India + widely used regional/other tongues,
# covering the "all 28 languages" ask. Each maps to the codes providers expect:
#   deepgram: STT language code (Nova-2/enhanced where available)
#   bcp47:    used for TTS engines / ElevenLabs multilingual voices
# Hinglish is handled as Hindi STT with code-switch friendly prompts.
LANGUAGES: dict[str, dict] = {
    "en":  {"name": "English (India)", "deepgram": "en-IN", "bcp47": "en-IN"},
    "hi":  {"name": "Hindi",           "deepgram": "hi",    "bcp47": "hi-IN"},
    "hinglish": {"name": "Hinglish",   "deepgram": "hi",    "bcp47": "hi-IN"},
    "bn":  {"name": "Bengali",         "deepgram": "bn",    "bcp47": "bn-IN"},
    "ta":  {"name": "Tamil",           "deepgram": "ta",    "bcp47": "ta-IN"},
    "te":  {"name": "Telugu",          "deepgram": "te",    "bcp47": "te-IN"},
    "mr":  {"name": "Marathi",         "deepgram": "mr",    "bcp47": "mr-IN"},
    "gu":  {"name": "Gujarati",        "deepgram": "gu",    "bcp47": "gu-IN"},
    "kn":  {"name": "Kannada",         "deepgram": "kn",    "bcp47": "kn-IN"},
    "ml":  {"name": "Malayalam",       "deepgram": "ml",    "bcp47": "ml-IN"},
    "pa":  {"name": "Punjabi",         "deepgram": "pa",    "bcp47": "pa-IN"},
    "or":  {"name": "Odia",            "deepgram": "or",    "bcp47": "or-IN"},
    "as":  {"name": "Assamese",        "deepgram": "as",    "bcp47": "as-IN"},
    "ur":  {"name": "Urdu",            "deepgram": "ur",    "bcp47": "ur-IN"},
    "sa":  {"name": "Sanskrit",        "deepgram": "hi",    "bcp47": "sa-IN"},
    "ks":  {"name": "Kashmiri",        "deepgram": "ur",    "bcp47": "ks-IN"},
    "sd":  {"name": "Sindhi",          "deepgram": "ur",    "bcp47": "sd-IN"},
    "ne":  {"name": "Nepali",          "deepgram": "ne",    "bcp47": "ne-NP"},
    "kok": {"name": "Konkani",         "deepgram": "hi",    "bcp47": "kok-IN"},
    "mni": {"name": "Manipuri",        "deepgram": "hi",    "bcp47": "mni-IN"},
    "brx": {"name": "Bodo",            "deepgram": "hi",    "bcp47": "brx-IN"},
    "sat": {"name": "Santali",         "deepgram": "hi",    "bcp47": "sat-IN"},
    "mai": {"name": "Maithili",        "deepgram": "hi",    "bcp47": "mai-IN"},
    "doi": {"name": "Dogri",           "deepgram": "hi",    "bcp47": "doi-IN"},
    "bho": {"name": "Bhojpuri",        "deepgram": "hi",    "bcp47": "bho-IN"},
    "raj": {"name": "Rajasthani",      "deepgram": "hi",    "bcp47": "raj-IN"},
    "tcy": {"name": "Tulu",            "deepgram": "kn",    "bcp47": "tcy-IN"},
    "mag": {"name": "Magahi",          "deepgram": "hi",    "bcp47": "mag-IN"},
}

DEFAULT = "en"


def resolve(code: str) -> dict:
    entry = LANGUAGES.get((code or "").lower(), LANGUAGES[DEFAULT])
    return {"code": (code or DEFAULT).lower(), **entry}


def deepgram_code(code: str) -> str:
    return resolve(code)["deepgram"]


def tts_locale(code: str) -> str:
    return resolve(code)["bcp47"]


def supported() -> list[dict]:
    return [{"code": k, "name": v["name"]} for k, v in LANGUAGES.items()]
