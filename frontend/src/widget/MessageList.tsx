import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { MessageType } from "./useChat";
import { HOTELA_LOGO_URL } from "./theme";

type Props = {
  messages: MessageType[];
  isBotTyping: boolean;
};

function formatTime(date: Date): string {
  try {
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  } catch {
    return "";
  }
}

export function MessageList({ messages, isBotTyping }: Props) {
  return (
    <div className="hotela-messages-list" aria-live="polite">
      {messages.map((msg) => {
        const isUser = msg.sender === "user";
        return (
          <div
            key={msg.id}
            className={`hotela-message-row ${isUser ? "is-user" : "is-bot"}`}
          >
            {!isUser && (
              <div className="hotela-bot-avatar" aria-hidden="true">
                <img src={HOTELA_LOGO_URL} alt="Hotela Assistant" />
              </div>
            )}
            <div className="hotela-message-content-wrapper">
              <div
                className={`hotela-message-bubble ${isUser ? "user" : "bot"}`}
                dir="auto"
              >
                {isUser ? (
                  <p className="hotela-user-text">{msg.text}</p>
                ) : msg.text ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.text}
                  </ReactMarkdown>
                ) : (
                  <span className="hotela-cursor-blink">|</span>
                )}
              </div>
              <div className={`hotela-message-meta ${isUser ? "user" : "bot"}`}>
                <span className="hotela-message-time">
                  {formatTime(msg.timestamp)}
                </span>
              </div>
            </div>
          </div>
        );
      })}

      {/* Typing indicator */}
      {isBotTyping && (
        <div className="hotela-message-row is-bot hotela-typing-row">
          <div className="hotela-bot-avatar" aria-hidden="true">
            <img src={HOTELA_LOGO_URL} alt="Hotela Assistant" />
          </div>
          <div className="hotela-message-bubble bot hotela-typing-bubble" aria-label="Hotela Assistant is typing">
            <span className="hotela-typing-dot"></span>
            <span className="hotela-typing-dot"></span>
            <span className="hotela-typing-dot"></span>
          </div>
        </div>
      )}
    </div>
  );
}
