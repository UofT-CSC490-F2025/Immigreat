import { type ReactElement } from 'react'
import { render, type RenderOptions } from '@testing-library/react'

/**
 * Custom render function with common providers
 */
export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) {
  return render(ui, { ...options })
}

/**
 * Helper to create mock chat responses
 */
export function createMockChatResponse(overrides?: Partial<{
  answer: string
  thinking?: string
  session_id: string
  sources?: Array<{
    id: string
    source: string
    title: string
    similarity: number
  }>
  timings?: {
    history_retrieval_ms: number
    embedding_ms: number
    primary_retrieval_ms: number
    facet_expansion_ms: number
    llm_ms: number
    save_history_ms: number
    total_ms: number
  }
  history_length?: number
}>) {
  return {
    answer: 'Default answer',
    session_id: 'default-session-id',
    ...overrides,
  }
}

/**
 * Helper to create mock saved chats
 */
export function createMockSavedChat(overrides?: Partial<{
  id: string
  title: string
  messages: Array<{
    id: string
    role: 'user' | 'assistant'
    content: string
    timestamp: string
    thinking?: string
  }>
  timestamp: string
  session_id?: string
}>) {
  return {
    id: `chat-${Date.now()}`,
    title: 'Test Chat',
    messages: [],
    timestamp: new Date().toISOString(),
    ...overrides,
  }
}

/**
 * Helper to wait for loading to complete
 */
export async function waitForLoadingToFinish() {
  const { waitFor } = await import('@testing-library/react')
  await waitFor(() => {
    const loadingElements = document.querySelectorAll('.animate-bounce')
    if (loadingElements.length > 0) {
      throw new Error('Still loading')
    }
  }, { timeout: 5000 })
}

/**
 * Helper to setup localStorage with mock chats
 */
export function setupLocalStorageWithChats(chats: any[]) {
  localStorage.setItem('immigreat_chat_history', JSON.stringify(chats))
}

/**
 * Helper to clear all storage
 */
export function clearAllStorage() {
  localStorage.clear()
  sessionStorage.clear()
}

export * from '@testing-library/react'
