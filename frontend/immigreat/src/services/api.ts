// src/services/api.ts
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface ChatRequest {
  query: string;
  k?: number;           // Number of documents to retrieve (default: 3)
  use_facet?: boolean;  // Use faceted search (default: false)
  use_rerank?: boolean; // Rerank results (default: false)
}

export interface ChatResponse {
  response?: string;
  answer?: string;
  // Add other fields based on your backend's actual response
  sources?: Array<{
    title: string;
    content: string;
    score?: number;
  }>;
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
      // Set timeout to 30 seconds (Lambda takes ~12s, so this is safe)
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000);

      const response = await fetch(API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: message,
          k: settings.k,
          use_facet: settings.useFacet,
          use_rerank: settings.useRerank,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`API error ${response.status}: ${errorText}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          throw new Error('Request timed out after 30 seconds. Please try again.');
        }
        console.error('Error calling chat API:', error);
        throw error;
      }
      throw new Error('Unknown error occurred');
    }
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
