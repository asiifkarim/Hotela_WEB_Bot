import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import { Send, Smile } from "lucide-react";
import { EmojiPicker } from "./EmojiPicker";

type Props = {
  onSend: (message: string) => void;
  disabled: boolean;
  placeholder?: string;
};

export function Composer({
  onSend,
  disabled,
  placeholder = "Ask me anything...",
}: Props) {
  const [value, setValue] = useState("");
  const [showEmoji, setShowEmoji] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleSubmit(event?: FormEvent) {
    if (event) event.preventDefault();
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
    setShowEmoji(false);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function handleEmojiSelect(emoji: string) {
    setValue((prev) => prev + emoji);
    inputRef.current?.focus();
  }

  return (
    <div className="hotela-composer-wrapper">
      {showEmoji && (
        <EmojiPicker
          onSelect={handleEmojiSelect}
          onClose={() => setShowEmoji(false)}
        />
      )}

      <form className="hotela-composer-bar" onSubmit={handleSubmit}>
        <input
          ref={inputRef}
          type="text"
          value={value}
          maxLength={500}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          aria-label="Message to Hotela Assistant"
          disabled={disabled}
          className="hotela-composer-input"
        />

        <button
          type="button"
          onClick={() => setShowEmoji((prev) => !prev)}
          className={`hotela-composer-emoji-btn ${showEmoji ? "is-active" : ""}`}
          aria-label={showEmoji ? "Close emoji picker" : "Open emoji picker"}
          aria-expanded={showEmoji}
          disabled={disabled}
        >
          <Smile size={20} />
        </button>

        <button
          type="submit"
          className="hotela-composer-send-btn"
          aria-label="Send message"
          disabled={disabled || !value.trim()}
        >
          <Send size={18} />
        </button>
      </form>
    </div>
  );
}
