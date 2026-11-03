import { useState, useRef, useEffect } from "react";
import { Minus, RotateCcw, Mail, Phone } from "lucide-react";
import { useChat, DEFAULT_SUGGESTIONS } from "./useChat";
import { HOTELA_LOGO_URL } from "./theme";
import { MessageList } from "./MessageList";
import { Composer } from "./Composer";
import { LeadForm } from "./LeadForm";
import "./styles.css";

type Props = {
  apiUrl?: string;
};

export const Chatbot = ({ apiUrl }: Props) => {
  const resolvedApiUrl =
    apiUrl ||
    import.meta.env.VITE_API_URL ||
    (typeof window !== "undefined"
      ? `${window.location.protocol}//${window.location.hostname}:8000`
      : "http://localhost:8000");

  const [isExpanded, setIsExpanded] = useState(false);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  const {
    messages,
    isBotTyping,
    loading,
    action,
    showOptions,
    send,
    clear,
  } = useChat(resolvedApiUrl);

  // Auto-scroll to bottom when messages or typing status updates
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTo({
        top: chatContainerRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messages, isBotTyping, action]);

  // Suggested options click handler (fixes the previous race condition by sending option directly)
  const handleOptionClick = (option: string) => {
    send(option);
  };

  // Format date for the timestamp badge
  const formatHeaderDate = (date: Date) => {
    const today = new Date();
    return date.toDateString() === today.toDateString()
      ? "Today"
      : date.toLocaleDateString(undefined, {
          month: "short",
          day: "numeric",
          year: "numeric",
        });
  };

  return (
    <div className="hotela-widget-root">
      {isExpanded ? (
        <section
          className="hotela-window"
          aria-label="Hotela AI Chatbot"
          role="dialog"
          aria-modal="false"
        >
          {/* Header */}
          <div className="hotela-window-header">
            <div className="hotela-header-controls">
              <button
                type="button"
                onClick={clear}
                className="hotela-header-icon-btn"
                title="Restart conversation"
                aria-label="Restart conversation"
              >
                <RotateCcw size={16} />
              </button>
              <button
                type="button"
                onClick={() => setIsExpanded(false)}
                className="hotela-header-icon-btn"
                title="Minimize chat"
                aria-label="Minimize chat"
              >
                <Minus size={18} />
              </button>
            </div>

            {/* Brand Hero */}
            <div className="hotela-header-hero">
              <div className="hotela-header-logo-circle">
                <img src={HOTELA_LOGO_URL} alt="Hotela Logo" />
              </div>
              <h1 className="hotela-header-title">Hotela AI Chatbot</h1>
              <p className="hotela-header-subtitle">You can ask me anything</p>
            </div>
          </div>

          {/* Chat Body Area */}
          <div className="hotela-chat-body">
            {/* Date pill separator */}
            <div className="hotela-date-pill-wrapper">
              <span className="hotela-date-pill">{formatHeaderDate(new Date())}</span>
            </div>

            {/* Messages Scroll Container */}
            <div ref={chatContainerRef} className="hotela-messages-scroll-area">
              <MessageList messages={messages} isBotTyping={isBotTyping} />

              {/* Action: Lead Generation Form */}
              {action === "lead_form" && (
                <LeadForm apiUrl={resolvedApiUrl} />
              )}

              {/* Action: Human Support Handoff */}
              {action === "handoff" && (
                <div className="hotela-action-card hotela-handoff-card">
                  <div className="hotela-action-card-header">
                    <strong>Talk to a Human</strong>
                    <p>Our dedicated support team is available to assist you directly.</p>
                  </div>
                  <div className="hotela-handoff-links">
                    <a
                      href="mailto:hotelaapp@gmail.com"
                      className="hotela-handoff-btn"
                      aria-label="Email Hotela support"
                    >
                      <Mail size={16} />
                      <span>Email: hotelaapp@gmail.com</span>
                    </a>
                    <a
                      href="tel:+923555871667"
                      className="hotela-handoff-btn"
                      aria-label="Call Hotela support"
                    >
                      <Phone size={16} />
                      <span>Call: +92 355 5871667</span>
                    </a>
                  </div>
                </div>
              )}
            </div>

            {/* Suggested Options Pills */}
            {showOptions && (
              <div
                className="hotela-suggestions-container"
                aria-label="Suggested questions"
              >
                <div className="hotela-suggestions-heading">Suggested options:</div>
                <div className="hotela-suggestions-pills">
                  {DEFAULT_SUGGESTIONS.map((option, index) => (
                    <button
                      key={index}
                      type="button"
                      className="hotela-suggestion-chip"
                      onClick={() => handleOptionClick(option)}
                    >
                      {option}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Input Composer */}
            <Composer onSend={send} disabled={loading} />
          </div>
        </section>
      ) : (
        /* Floating Launcher */
        <div className="hotela-launcher-container">
          <button
            type="button"
            className="hotela-floating-launcher"
            onClick={() => setIsExpanded(true)}
            aria-label="Open Hotela chat assistant"
          >
            <div className="hotela-launcher-tooltip" aria-hidden="true">
              Need help?
            </div>
            <div className="hotela-launcher-avatar">
              <img src={HOTELA_LOGO_URL} alt="Hotela Assistant" />
            </div>
          </button>
        </div>
      )}
    </div>
  );
};

export default Chatbot;
