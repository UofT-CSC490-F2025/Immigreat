import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { chatAPI, DEFAULT_SETTINGS } from './api'
import type { ChatResponse } from './api'

// Mock fetch globally
const mockFetch = vi.fn()
global.fetch = mockFetch

describe('chatAPI', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    chatAPI.resetSession()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('sendMessage', () => {
    it('should send a message with default settings', async () => {
      const mockResponse: ChatResponse = {
        answer: 'Test response',
        session_id: 'test-session-123',
        sources: [],
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })

      const result = await chatAPI.sendMessage('Test query')

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            query: 'Test query',
            k: DEFAULT_SETTINGS.k,
            use_facet: DEFAULT_SETTINGS.useFacet,
            use_rerank: DEFAULT_SETTINGS.useRerank,
          }),
        })
      )

      expect(result).toEqual(mockResponse)
      expect(chatAPI.getSessionId()).toBe('test-session-123')
    })

    it('should send a message with custom settings', async () => {
      const mockResponse: ChatResponse = {
        answer: 'Test response',
        session_id: 'test-session-456',
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })

      const customSettings = {
        k: 5,
        useFacet: true,
        useRerank: true,
      }

      await chatAPI.sendMessage('Custom query', customSettings)

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: JSON.stringify({
            query: 'Custom query',
            k: 5,
            use_facet: true,
            use_rerank: true,
          }),
        })
      )
    })

    it('should include session_id in subsequent requests', async () => {
      const mockResponse: ChatResponse = {
        answer: 'Test response',
        session_id: 'existing-session',
      }

      // First request
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })
      await chatAPI.sendMessage('First query')

      // Second request
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ...mockResponse, answer: 'Second response' }),
      })
      await chatAPI.sendMessage('Second query')

      const secondCallBody = JSON.parse(mockFetch.mock.calls[1][1].body)
      expect(secondCallBody.session_id).toBe('existing-session')
    })

    it('should handle API errors', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        text: async () => 'Internal Server Error',
      })

      await expect(chatAPI.sendMessage('Error query')).rejects.toThrow(
        'API error 500: Internal Server Error'
      )
    })

    it('should handle network errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'))

      await expect(chatAPI.sendMessage('Network error query')).rejects.toThrow(
        'Network error'
      )
    })

    it('should handle timeout errors', async () => {
      mockFetch.mockImplementationOnce(() => {
        return new Promise((_, reject) => {
          setTimeout(() => {
            const error = new Error('Timeout')
            error.name = 'AbortError'
            reject(error)
          }, 100)
        })
      })

      await expect(chatAPI.sendMessage('Timeout query')).rejects.toThrow(
        'Request timed out after 60 seconds'
      )
    })

    it('should handle response with thinking', async () => {
      const mockResponse: ChatResponse = {
        answer: 'Final answer',
        thinking: 'Reasoning process',
        session_id: 'session-with-thinking',
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })

      const result = await chatAPI.sendMessage('Query with thinking')

      expect(result.thinking).toBe('Reasoning process')
      expect(result.answer).toBe('Final answer')
    })

    it('should handle response with sources', async () => {
      const mockSources = [
        { id: '1', source: 'doc1', title: 'Title 1', similarity: 0.95 },
        { id: '2', source: 'doc2', title: 'Title 2', similarity: 0.87 },
      ]

      const mockResponse: ChatResponse = {
        answer: 'Answer with sources',
        session_id: 'session-123',
        sources: mockSources,
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })

      const result = await chatAPI.sendMessage('Query for sources')

      expect(result.sources).toEqual(mockSources)
      expect(result.sources?.length).toBe(2)
    })

    it('should handle response with timings', async () => {
      const mockTimings = {
        history_retrieval_ms: 10,
        embedding_ms: 245,
        primary_retrieval_ms: 87,
        facet_expansion_ms: 112,
        llm_ms: 1834,
        save_history_ms: 15,
        total_ms: 2802,
      }

      const mockResponse: ChatResponse = {
        answer: 'Answer with timings',
        session_id: 'session-123',
        timings: mockTimings,
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })

      const result = await chatAPI.sendMessage('Performance query')

      expect(result.timings).toEqual(mockTimings)
    })
  })

  describe('resetSession', () => {
    it('should clear the current session', async () => {
      const mockResponse: ChatResponse = {
        answer: 'Response',
        session_id: 'test-session',
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })

      await chatAPI.sendMessage('Test')
      expect(chatAPI.getSessionId()).toBe('test-session')

      chatAPI.resetSession()
      expect(chatAPI.getSessionId()).toBeNull()
    })
  })

  describe('getSessionId', () => {
    it('should return null initially', () => {
      expect(chatAPI.getSessionId()).toBeNull()
    })

    it('should return session_id after a successful request', async () => {
      const mockResponse: ChatResponse = {
        answer: 'Response',
        session_id: 'new-session',
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })

      await chatAPI.sendMessage('Test')
      expect(chatAPI.getSessionId()).toBe('new-session')
    })
  })

  describe('healthCheck', () => {
    it('should return true when health endpoint is ok', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
      })

      const result = await chatAPI.healthCheck()
      expect(result).toBe(true)
    })

    it('should return false when health endpoint fails', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
      })

      const result = await chatAPI.healthCheck()
      expect(result).toBe(false)
    })

    it('should return false on network error', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'))

      const result = await chatAPI.healthCheck()
      expect(result).toBe(false)
    })
  })
})
