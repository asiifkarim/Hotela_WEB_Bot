import { useState, useCallback } from "react";

export type MessageSender = "user" | "bot";

export type MessageType = {
  id: string;
  text: string;
  sender: MessageSender;
  timestamp: Date;
};

// Also export alias for compatibility with legacy types
export type ChatMessage = MessageType;
export type ChatAction = "lead_form" | "handoff" | null;

const INITIAL_GREETING = "Hi there, how can I help you today? Here are a few options:";

export const DEFAULT_SUGGESTIONS = [
  "Special Offers",
  "Hotela Product",
  "Hotela Software",
  "Hotela Prices",
  "What does Hotela include?",
  "ہوٹلا کیا ہے؟",
];

function getSessionId(forceNew = false): string {
  const key = "hotela-chat-session";
  if (!forceNew) {
    const existing = sessionStorage.getItem(key);
    if (existing) return existing;
  }
  const created = typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `session-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  sessionStorage.setItem(key, created);
  return created;
}

export function useChat(apiUrl: string) {
  const [messages, setMessages] = useState<MessageType[]>([
    {
      id: "greeting-1",
      text: INITIAL_GREETING,
      sender: "bot",
      timestamp: new Date(),
    },
  ]);
  const [isBotTyping, setIsBotTyping] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [action, setAction] = useState<ChatAction>(null);
  const [showOptions, setShowOptions] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const send = useCallback(async (messageText: string) => {
    const text = messageText.trim();
    if (!text || loading) return;

    setError(null);
    setShowOptions(false);
    setIsBotTyping(true);
    setLoading(true);
    setAction(null);

    const userMessageId = `user-${Date.now()}`;
    const botMessageId = `bot-${Date.now()}`;

    const userMessage: MessageType = {
      id: userMessageId,
      text,
      sender: "user",
      timestamp: new Date(),
    };

    // Prepare current history for backend before state update
    const historyPayload = messages
      .filter((m) => m.id !== "greeting-1" && m.text.trim().length > 0)
      .slice(-10)
      .map((m) => ({
        role: m.sender === "user" ? "user" : "assistant",
        content: m.text,
      }));

    // Add user message and empty bot placeholder
    setMessages((prev) => [
      ...prev,
      userMessage,
      {
        id: botMessageId,
        text: "",
        sender: "bot",
        timestamp: new Date(),
      },
    ]);

    try {
      const cleanUrl = apiUrl.replace(/\/$/, "");
      const response = await fetch(`${cleanUrl}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          session_id: getSessionId(),
          message: text,
          history: historyPayload,
        }),
      });

      if (!response.ok) {
        let errDetail = "Chat request failed";
        try {
          const jsonErr = await response.json();
          if (jsonErr && (jsonErr.detail || jsonErr.message)) {
            errDetail = jsonErr.detail || jsonErr.message;
          }
        } catch {
          errDetail = `HTTP ${response.status}: ${response.statusText}`;
        }
        throw new Error(errDetail);
      }

      if (!response.body) {
        throw new Error("No response body received from server");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let hasReceivedFirstToken = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";

        for (const event of events) {
          if (!event.trim()) continue;

          // Parse event name and data lines
          const lines = event.split("\n");
          let dataContent = "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              dataContent = line.slice(6).trim();
            }
          }

          if (!dataContent) continue;

          try {
            const parsed = JSON.parse(dataContent) as {
              type: string;
              value: string;
            };

            if (parsed.type === "token") {
              if (!hasReceivedFirstToken) {
                hasReceivedFirstToken = true;
                setIsBotTyping(false); // Stop typing indicator once text starts streaming
              }
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last && last.id === botMessageId) {
                  updated[updated.length - 1] = {
                    ...last,
                    text: last.text + parsed.value,
                  };
                }
                return updated;
              });
            } else if (parsed.type === "action") {
              setAction(parsed.value as ChatAction);
            } else if (parsed.type === "error") {
              throw new Error(parsed.value);
            }
          } catch (jsonErr) {
            if (jsonErr instanceof Error && jsonErr.message !== "Unexpected end of JSON input") {
              // Ignore non-fatal JSON parse glitches on chunk boundaries
            }
          }
        }
      }
    } catch (err) {
      const errMsg =
        err instanceof Error
          ? err.message
          : "The assistant is temporarily unavailable. Please try again.";
      setError(errMsg);

      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.id === botMessageId) {
          updated[updated.length - 1] = {
            ...last,
            text: `⚠️ ${errMsg}`,
          };
        } else {
          updated.push({
            id: `err-${Date.now()}`,
            text: `⚠️ ${errMsg}`,
            sender: "bot",
            timestamp: new Date(),
          });
        }
        return updated;
      });
    } finally {
      setIsBotTyping(false);
      setLoading(false);
    }
  }, [apiUrl, loading, messages]);

  const clear = useCallback(() => {
    getSessionId(true); // force generate new session
    setMessages([
      {
        id: `greeting-${Date.now()}`,
        text: INITIAL_GREETING,
        sender: "bot",
        timestamp: new Date(),
      },
    ]);
    setAction(null);
    setShowOptions(true);
    setError(null);
    setIsBotTyping(false);
    setLoading(false);
  }, []);

  return {
    messages,
    setMessages,
    isBotTyping,
    loading,
    action,
    showOptions,
    setShowOptions,
    error,
    send,
    clear,
  };
}
