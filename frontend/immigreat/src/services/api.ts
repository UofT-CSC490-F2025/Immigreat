// src/services/api.ts
const API_URL = import.meta.env.VITE_API_URL;

export interface ChatRequest {
  query: string;
  session_id?: string;  // For conversation persistence
  k?: number;           // Number of documents to retrieve (default: 3)
  use_facet?: boolean;  // Use faceted search (default: false)
  use_rerank?: boolean; // Rerank results (default: false)
}

export interface ChatResponse {
  answer: string;        // Backend uses "answer" not "response"
  thinking?: string;     // Optional thinking/reasoning process from DeepSeek R1
  session_id: string;    // Session ID for conversation history
  sources?: Array<{
    id: string;
    source: string;
    title: string;
    similarity: number;
  }>;
  timings?: {
    history_retrieval_ms: number;
    embedding_ms: number;
    primary_retrieval_ms: number;
    facet_expansion_ms: number;
    llm_ms: number;
    save_history_ms: number;
    total_ms: number;
  };
  history_length?: number;
}

export interface ChatSettings {
  k: number;
  useFacet: boolean;
  useRerank: boolean;
}

export const DEFAULT_SETTINGS: ChatSettings = {
  k: 3,
  useFacet: false,
  useRerank: false,
};

// Store session ID in memory (could also use localStorage)
let currentSessionId: string | null = null;

export const chatAPI = {
  /**
   * Send a message to the chatbot
   * @param message - The user's question
   * @param settings - Optional RAG settings (uses defaults if not provided)
   */
  async sendMessage(
    message: string,
    settings: ChatSettings = DEFAULT_SETTINGS
  ): Promise<ChatResponse> {
    try {
      // Set timeout to 60 seconds (Lambda takes ~12s)
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 60000);

      const requestBody: ChatRequest = {
        query: message,
        k: settings.k,
        use_facet: settings.useFacet,
        use_rerank: settings.useRerank,
      };

      // Include session_id if we have one (for conversation continuity)
      if (currentSessionId) {
        requestBody.session_id = currentSessionId;
      }

      const response = await fetch(API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`API error ${response.status}: ${errorText}`);
      }

      const data = await response.json();

      // Store session_id for next request
      if (data.session_id) {
        currentSessionId = data.session_id;
      }

      return data;
    } catch (error) {
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          throw new Error('Request timed out after 60 seconds. Please try again.');
        }
        console.error('Error calling chat API:', error);
        throw error;
      }
      throw new Error('Unknown error occurred');
    }
  },

  /**
   * Reset conversation (clear session)
   */
  resetSession() {
    currentSessionId = null;
  },

  /**
   * Get current session ID
   */
  getSessionId() {
    return currentSessionId;
  },

  /**
   * Health check - optional, depends on if your backend has this endpoint
   */
  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${API_URL}/health`);
      return response.ok;
    } catch {
      return false;
    }
  },
};
