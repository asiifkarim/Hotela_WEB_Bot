import { createRoot } from "react-dom/client";
import { HotelaChatWidget } from "./widget/ChatWidget";

export { HotelaChatWidget };

const script = document.currentScript as HTMLScriptElement | null;
const mount = document.createElement("div");
document.body.appendChild(mount);
createRoot(mount).render(<HotelaChatWidget apiUrl={script?.dataset.api ?? "http://localhost:8000"} />);
