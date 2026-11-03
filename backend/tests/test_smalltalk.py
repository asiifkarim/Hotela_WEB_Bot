from pathlib import Path

from app.chat.service import ChatService
from app.chat.smalltalk import check
from app.config import ROOT_DIR


class DummySettings:
    query_rewrite = False
    top_k = 6
    min_similarity = 0.35
    kb_dir = ROOT_DIR / "kb"


class RecordingLLM:
    def __init__(self):
        self.rewrite_calls = 0
        self.answer_calls = 0

    def rewrite_query(self, message, history):
        self.rewrite_calls += 1
        return message

    def stream_answer(self, message, context, core_facts, history):
        self.answer_calls += 1
        yield "unexpected answer"


class NoRetrievalCollection:
    def query(self, **kwargs):
        raise AssertionError("small talk must skip retrieval")


class DummyEmbedder:
    def embed_one(self, text):
        return [0.0]


def test_smalltalk_replies():
    assert check("hi").reply
    assert check("salam").reply
    assert check("thanks").reply


def test_leading_greeting_is_removed_for_retrieval():
    result = check("hi what plans do you have")
    assert result.reply is None
    assert result.query == "what plans do you have"


def test_ok_after_bot_question_continues_pipeline():
    result = check("ok", last_bot_message="Which Hotela plan interests you?")
    assert result.reply is None
    assert result.query == "ok"


def test_smalltalk_service_skips_llm_and_retrieval():
    llm = RecordingLLM()
    service = ChatService(DummySettings(), NoRetrievalCollection(), object(), llm)
    events = list(service.stream("smalltalk-test", "hi", []))
    assert events[0][0] == "token"
    assert events[-1] == ("done", "")
    assert llm.rewrite_calls == 0
    assert llm.answer_calls == 0


def test_real_question_without_match_uses_handoff_fallback():
    class EmptyCollection:
        def query(self, **kwargs):
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    service = ChatService(DummySettings(), EmptyCollection(), DummyEmbedder(), RecordingLLM())
    events = list(service.stream("fallback-test", "What is the secret feature?", []))
    assert any(event == "token" and "not sure" in value.lower() for event, value in events)
    assert ("action", "handoff") in events
    assert events[-1] == ("done", "")
