"""
Small-talk router for the Hotela website assistant.

Why: messages like "hi" or "thanks" have nothing to retrieve from the knowledge base, so the
normal pipeline falls into the "I'm not sure" fallback. This module answers them instantly,
without retrieval, without an LLM call and without logging them as unanswered questions.

Usage in chat/service.py (run BEFORE guards-retrieval-LLM, after basic input limits):

    from app.chat.smalltalk import check

    st = check(message, last_bot_message=last_assistant_text)
    if st.reply:                      # greeting, thanks, goodbye, identity, ...
        yield token_event(st.reply)   # send as one SSE token event
        yield done_event()
        return                        # skip retrieval, LLM, fallback, unanswered log, handoff action
    message = st.query                # greeting stripped ("hi what plans do you have" -> "what plans do you have")
    ... continue the normal RAG pipeline with `message` ...
"""
import re
from dataclasses import dataclass
from typing import Optional

REPLIES = {
    "greeting": {
        "en": "Hi, I'm the Hotela assistant. How can I help you today?",
        "ru": "Assalam o Alaikum! Main Hotela assistant hoon. Main aap ki kya madad kar sakta hoon?",
        "ur": "السلام علیکم! میں Hotela اسسٹنٹ ہوں۔ میں آپ کی کیا مدد کر سکتا ہوں؟",
    },
    "salam_reply": {
        "ru": "Wa Alaikum Assalam! Main Hotela assistant hoon. Main aap ki kya madad kar sakta hoon?",
        "ur": "وعلیکم السلام! میں Hotela اسسٹنٹ ہوں۔ میں آپ کی کیا مدد کر سکتا ہوں؟",
    },
    "how_are_you": {
        "en": "I'm ready to help. What would you like to know about Hotela?",
        "ru": "Main madad ke liye tayyar hoon. Hotela ke bare mein kya jaanna chahte hain?",
        "ur": "میں مدد کے لیے تیار ہوں۔ آپ Hotela کے بارے میں کیا جاننا چاہتے ہیں؟",
    },
    "thanks": {
        "en": "You're welcome! Ask me anything else about Hotela.",
        "ru": "Khushi hui! Hotela ke bare mein koi aur sawal ho to poochein.",
        "ur": "خوشی ہوئی! Hotela کے بارے میں کوئی اور سوال ہو تو پوچھیں۔",
    },
    "bye": {
        "en": "Goodbye! Come back anytime you have a question about Hotela.",
        "ru": "Khuda hafiz! Hotela ke bare mein sawal ho to kabhi bhi poochein.",
        "ur": "خدا حافظ! Hotela کے بارے میں سوال ہو تو کبھی بھی پوچھیں۔",
    },
    "identity": {
        "en": "I'm the Hotela assistant, an AI assistant. I can answer questions about Hotela's features, plans and support.",
        "ru": "Main Hotela assistant hoon, aik AI assistant. Main Hotela ke features, plans aur support ke bare mein jawab de sakta hoon.",
        "ur": "میں Hotela اسسٹنٹ ہوں، ایک AI اسسٹنٹ۔ میں Hotela کے فیچرز، پلانز اور سپورٹ کے بارے میں جواب دے سکتا ہوں۔",
    },
    "capabilities": {
        "en": "I can answer questions about Hotela's hotel and restaurant features, plans and support. What would you like to know?",
        "ru": "Main Hotela ke hotel aur restaurant features, plans aur support ke bare mein jawab de sakta hoon. Aap kya jaanna chahte hain?",
        "ur": "میں Hotela کے ہوٹل اور ریسٹورنٹ فیچرز، پلانز اور سپورٹ کے بارے میں جواب دے سکتا ہوں۔ آپ کیا جاننا چاہتے ہیں؟",
    },
    "ack": {
        "en": "Okay. Ask me anything about Hotela whenever you're ready.",
        "ru": "Theek hai. Hotela ke bare mein jab chahein poochein.",
        "ur": "ٹھیک ہے۔ Hotela کے بارے میں جب چاہیں پوچھیں۔",
    },
    "empty": {
        "en": "I didn't catch that. Ask me anything about Hotela.",
        "ru": "Mujhe samajh nahi aaya. Hotela ke bare mein kuch bhi poochein.",
        "ur": "مجھے سمجھ نہیں آیا۔ Hotela کے بارے میں کچھ بھی پوچھیں۔",
    },
}

PHRASES = [
    ("greeting", "en", ["hi", "hello", "hey", "hallo", "hola", "yo", "sup", "gm", "greetings", "good morning", "good afternoon", "good evening", "good day"]),
    ("greeting", "ur", ["ہیلو", "ہائے", "ہائی", "آداب", "سلام", "السلام علیکم", "السلام علیکم ورحمتہ اللہ"]),
    ("how_are_you", "en", ["how are you", "how are u", "how r u", "how are you doing", "hows it going", "how is it going", "whats up", "wassup", "how do you do"]),
    ("how_are_you", "ru", ["aap kaise hain", "aap kaise ho", "ap kaise hain", "ap kaise ho", "kaise ho", "kaise hain", "tum kaise ho", "kya hal hai", "kia hal hai", "kya haal hai", "aap ka kya hal hai", "ap ka kya hal hai", "kya hal", "kia hal"]),
    ("how_are_you", "ur", ["آپ کیسے ہیں", "کیسے ہو", "کیسے ہیں", "کیا حال ہے", "آپ کا کیا حال ہے"]),
    ("thanks", "en", ["thanks", "thank you", "thankyou", "thx", "ty", "thanks a lot", "thank you so much", "many thanks", "much appreciated", "ok thanks", "okay thanks", "ok thank you", "okay thank you", "thanks bye", "thank you bye"]),
    ("thanks", "ru", ["shukriya", "shukria", "bohat shukriya", "bahut shukriya", "buhat shukriya", "meherbani", "jazakallah", "jazak allah", "jazakallah khair", "jazak allah khair", "shukriya ji", "ok shukriya", "theek hai shukriya"]),
    ("thanks", "ur", ["شکریہ", "بہت شکریہ", "جزاک اللہ", "جزاک اللہ خیر"]),
    ("bye", "en", ["bye", "bye bye", "goodbye", "good bye", "see you", "see ya", "cya", "take care", "good night", "gn"]),
    ("bye", "ru", ["khuda hafiz", "khudahafiz", "allah hafiz", "allahhafiz", "fi amanillah", "allah hafez"]),
    ("bye", "ur", ["خدا حافظ", "اللہ حافظ"]),
    ("identity", "en", ["who are you", "who are u", "what are you", "who is this", "what is your name", "your name", "whats your name", "are you a bot", "are you a robot", "are you ai", "are you an ai", "are you human", "are you real", "are you a human"]),
    ("identity", "ru", ["aap kaun hain", "aap kaun ho", "ap kaun hain", "ap kaun ho", "tum kaun ho", "kaun ho", "aap ka naam kya hai", "ap ka naam kya hai", "tumhara naam kya hai", "naam kya hai"]),
    ("identity", "ur", ["آپ کون ہیں", "تم کون ہو", "آپ کا نام کیا ہے", "کون ہو"]),
    ("capabilities", "en", ["help", "help me", "i need help", "can you help", "can you help me", "what can you do", "how can you help", "how can you help me", "what do you do", "menu", "options", "start"]),
    ("capabilities", "ru", ["madad", "madad karo", "meri madad karo", "help karo", "mujhe madad chahiye", "aap kya kar sakte hain", "aap kya kar sakte ho", "kya kar sakte ho", "aap meri madad kar sakte hain"]),
    ("capabilities", "ur", ["مدد", "میری مدد کریں", "آپ کیا کر سکتے ہیں"]),
    ("ack", "en", ["ok", "okay", "k", "kk", "alright", "fine", "cool", "great", "nice", "got it", "understood", "i see", "noted"]),
    ("ack", "ru", ["theek hai", "thik hai", "acha", "achha", "accha", "samajh gaya", "samajh gai", "samajh gaye", "okay ji", "ok ji"]),
    ("ack", "ur", ["ٹھیک ہے", "اچھا", "جی ٹھیک ہے", "سمجھ گیا", "سمجھ گئی"]),
]

FILLERS = {"there", "sir", "madam", "mam", "maam", "team", "hotela", "bot", "assistant", "bhai", "jee", "ji", "dear", "everyone", "all", "please", "plz", "pls", "ہوٹیلا", "جی"}
_SALAM = re.compile(r"(?:wa\s*)?(?:a?sa?la?m)(?:\s*(?:o|u|e|wa))?(?:\s*(?:a?la?i?ku?m|alikum|alaikum|alykum))?(?:\s*(?:wa)?\s*(?:a?rahmatulah|rehmatulah)(?:\s*(?:wa)?\s*barakatuhu)?)?|aoa|wa\s*a?la?i?ku?m\s*(?:a?sa?la?m)?")
_WAALAIKUM = re.compile(r"^(?:wa\s*a?la?i?ku?m|waalaikum|وعلیکم)")
_LEADING_GREETING = re.compile(r"^(?:(?:hi+|hello+|hey+|helo+|hola)|(?:wa\s*)?(?:a?s+a?la+m+)\w*(?:\s+(?:o|u|e|wa))?(?:\s+\w*(?:alaikum|alikum|alaykum))?|good\s+(?:morning|afternoon|evening)|السلام علیکم|سلام|ہیلو)(?:\s+(?:there|sir|madam|team|hotela|bhai|ji|jee))?[\s,]+(?=\S)")


def _squeeze(text: str) -> str:
    return re.sub(r"(.)\1+", r"\1", text)


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_LOOKUP = {}
for _intent, _lang, _phrases in PHRASES:
    for _phrase in _phrases:
        _LOOKUP.setdefault(_squeeze(_normalize(_phrase)), (_intent, _lang))


def _strip_fillers(squeezed: str) -> str:
    words = squeezed.split()
    while len(words) > 1 and words[-1] in {_squeeze(filler) for filler in FILLERS}:
        words.pop()
    return " ".join(words)


def _match(normalized: str):
    squeezed = _squeeze(normalized)
    for candidate in (squeezed, _strip_fillers(squeezed)):
        if candidate in _LOOKUP:
            return _LOOKUP[candidate]
        if _SALAM.fullmatch(candidate):
            return ("salam", "ru")
    return None


@dataclass
class SmallTalk:
    intent: Optional[str]
    reply: Optional[str]
    lang: str
    query: str


def _reply_for(intent: str, lang: str, original: str) -> str:
    if intent == "salam":
        if _WAALAIKUM.match(_normalize(original)):
            return REPLIES["salam_reply"]["ru"]
        return REPLIES["greeting"]["ru"]
    if intent == "greeting" and lang == "ur" and _normalize(original).startswith("وعلیکم"):
        return REPLIES["salam_reply"]["ur"]
    return REPLIES[intent].get(lang) or REPLIES[intent]["en"]


def check(message: str, last_bot_message: Optional[str] = None) -> SmallTalk:
    raw = (message or "").strip()
    normalized = _normalize(raw)
    if not normalized:
        lang = "ur" if re.search(r"[\u0600-\u06FF]", raw) else "en"
        return SmallTalk("empty", REPLIES["empty"][lang], lang, raw)

    hit = _match(normalized)
    if hit:
        intent, lang = hit
        if intent == "ack" and last_bot_message and last_bot_message.rstrip().endswith(("?", "؟")):
            return SmallTalk(None, None, lang, raw)
        return SmallTalk(intent, _reply_for(intent, lang, raw), lang, raw)

    match = _LEADING_GREETING.match(normalized)
    if match:
        rest = normalized[match.end():].strip()
        if rest:
            rest_hit = _match(rest)
            if rest_hit and rest_hit[0] not in ("ack",):
                intent, lang = rest_hit
                return SmallTalk(intent, _reply_for(intent, lang, rest), lang, rest)
            lang = "ur" if re.search(r"[\u0600-\u06FF]", rest) else "en"
            return SmallTalk(None, None, lang, rest)

    lang = "ur" if re.search(r"[\u0600-\u06FF]", raw) else "en"
    return SmallTalk(None, None, lang, raw)
