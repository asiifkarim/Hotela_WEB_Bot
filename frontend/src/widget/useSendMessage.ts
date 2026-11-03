/**
 * Adapted useSendMessage hook for Hotela Chatbot.
 *
 * Provides a clean message submission interface adapted to the project's
 * live backend API endpoint (/api/chat) while preserving streaming and error handling.
 */

export interface ChatResponse {
  type: string;
  content: string | string[];
}

export interface UseSendMessageOptions {
  apiUrl?: string;
  onSuccess?: (data: ChatResponse) => void;
  onError?: (error: Error) => void;
}

/**
 * Message sending function interfacing with Hotela backend.
 */
export async function sendMessageToApi(
  message: string,
  apiUrl: string = "http://localhost:8000",
  history: Array<{ role: "user" | "assistant"; content: string }> = []
): Promise<ChatResponse> {
  const cleanUrl = apiUrl.replace(/\/$/, "");
  const response = await fetch(`${cleanUrl}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      session_id: "api-call",
      message: message.trim(),
      history,
    }),
  });

  if (!response.ok) {
    throw new Error(`Chat request failed with status: ${response.status}`);
  }

  if (!response.body) {
    throw new Error("No response body received from chat server");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  const collectedTokens: string[] = [];

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const event of events) {
      const dataLine = event.split("\n").find((line) => line.startsWith("data: "));
      if (!dataLine) continue;
      try {
        const data = JSON.parse(dataLine.slice(6)) as { type: string; value: string };
        if (data.type === "token") {
          collectedTokens.push(data.value);
        } else if (data.type === "error") {
          throw new Error(data.value);
        }
      } catch (e) {
        if (e instanceof Error && e.message !== "Unexpected end of JSON input") {
          throw e;
        }
      }
    }
  }

  return {
    type: "text",
    content: collectedTokens.join(""),
  };
}

export default function useSendMessage() {
  return {
    mutate: async (
      message: string,
      callbacks?: {
        onSuccess?: (data: ChatResponse) => void;
        onError?: (error: Error) => void;
      }
    ) => {
      try {
        const result = await sendMessageToApi(message);
        callbacks?.onSuccess?.(result);
        return result;
      } catch (err) {
        const error = err instanceof Error ? err : new Error(String(err));
        callbacks?.onError?.(error);
        throw error;
      }
    },
    isPending: false,
  };
}
