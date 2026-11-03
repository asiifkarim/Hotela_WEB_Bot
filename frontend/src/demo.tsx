import { createRoot } from "react-dom/client";
import { HotelaChatWidget } from "./widget/ChatWidget";
import "./widget/styles.css";

const apiUrl =
  import.meta.env.VITE_API_URL ||
  `${window.location.protocol}//${window.location.hostname}:8000`;
createRoot(document.getElementById("root")!).render(<HotelaChatWidget apiUrl={apiUrl} />);
