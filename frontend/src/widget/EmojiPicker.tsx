import { useEffect, useRef, useState } from "react";

type Props = {
  onSelect: (emoji: string) => void;
  onClose: () => void;
};

type Category = {
  name: string;
  icon: string;
  emojis: string[];
};

const CATEGORIES: Category[] = [
  {
    name: "Smileys",
    icon: "😊",
    emojis: [
      "😀", "😃", "😄", "😁", "😆", "😅", "😂", "🤣", "🙂", "😉",
      "😊", "😇", "🥰", "😍", "🤩", "😘", "😗", "😋", "😛", "😜",
      "🤪", "🤓", "😎", "🥳", "😏", "🧐", "🤔", "😐", "😑", "😴",
    ],
  },
  {
    name: "Gestures",
    icon: "👍",
    emojis: [
      "👋", "🤚", "✋", "🖐️", "👌", "🤌", "🤏", "✌️", "🤞", "🫰",
      "🤟", "🤘", "🤙", "👈", "👉", "👆", "🖕", "👇", "👍", "👎",
      "✊", "👊", "🤛", "🤜", "👏", "🙌", "👐", "🤲", "🤝", "🙏",
    ],
  },
  {
    name: "Hotels & Travel",
    icon: "🏨",
    emojis: [
      "🏨", "🏩", "🏬", "🏢", "🛏️", "🛎️", "🚪", "🍽️", "🍴", "☕",
      "🍹", "🍸", "🍷", "🍕", "🍔", "🛫", "🛬", "✈️", "🧳", "🗺️",
      "🚕", "🚗", "📍", "🏖️", "🌴", "🏊", "🛁", "🧼", "📶", "💳",
    ],
  },
  {
    name: "Business & Tech",
    icon: "💼",
    emojis: [
      "💼", "📁", "📊", "📈", "📉", "💻", "🖥️", "📱", "📞", "☎️",
      "📧", "✉️", "📝", "📋", "📌", "🔑", "🔒", "💡", "💰", "💵",
      "🤝", "🏷️", "🧾", "📅", "📆", "⏰", "⏱️", "⏳", "⚙️", "🔧",
    ],
  },
  {
    name: "Symbols",
    icon: "✨",
    emojis: [
      "✨", "⭐", "🌟", "🔥", "❤️", "💖", "🎉", "🎊", "✔️", "✅",
      "❌", "❓", "❗", "💬", "🗨️", "📢", "🔔", "🟢", "🔴", "💯",
    ],
  },
];

export function EmojiPicker({ onSelect, onClose }: Props) {
  const [activeCategory, setActiveCategory] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        onClose();
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  return (
    <div
      ref={containerRef}
      className="hotela-emoji-popover"
      role="dialog"
      aria-label="Emoji Picker"
    >
      <div className="hotela-emoji-tabs" role="tablist">
        {CATEGORIES.map((cat, idx) => (
          <button
            key={cat.name}
            role="tab"
            aria-selected={activeCategory === idx}
            className={`hotela-emoji-tab ${activeCategory === idx ? "is-active" : ""}`}
            title={cat.name}
            onClick={() => setActiveCategory(idx)}
            type="button"
          >
            <span aria-hidden="true">{cat.icon}</span>
          </button>
        ))}
      </div>

      <div className="hotela-emoji-grid" role="tabpanel">
        <div className="hotela-emoji-category-title">
          {CATEGORIES[activeCategory].name}
        </div>
        <div className="hotela-emoji-list">
          {CATEGORIES[activeCategory].emojis.map((emoji) => (
            <button
              key={emoji}
              type="button"
              className="hotela-emoji-item"
              onClick={() => onSelect(emoji)}
              aria-label={`Insert ${emoji}`}
            >
              {emoji}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
