import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { chatAPI } from './services/api'
import type { ChatResponse } from './services/api'

// Mock the API
vi.mock('./services/api', () => ({
  chatAPI: {
    sendMessage: vi.fn(),
    resetSession: vi.fn(),
    getSessionId: vi.fn(),
    healthCheck: vi.fn(),
  },
  DEFAULT_SETTINGS: {
    k: 3,
    useFacet: false,
    useRerank: false,
  },
}))

// Mock react-markdown
vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => <div data-testid="markdown">{children}</div>,
}))

describe('App', () => {
  const mockSendMessage = vi.mocked(chatAPI.sendMessage)
  const mockResetSession = vi.mocked(chatAPI.resetSession)
  const mockGetSessionId = vi.mocked(chatAPI.getSessionId)

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    mockGetSessionId.mockReturnValue(null)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('Initial Render', () => {
    it('should render the app with header', () => {
      render(<App />)
      
      expect(screen.getByText('Immigreat')).toBeInTheDocument()
      expect(screen.getByText('Canadian Immigration Assistant')).toBeInTheDocument()
    })

    it('should show welcome screen when no messages', () => {
      render(<App />)
      
      expect(screen.getByText('Welcome to Immigreat')).toBeInTheDocument()
      expect(screen.getByText(/Your guide to Canadian immigration/)).toBeInTheDocument()
    })

    it('should show suggestion prompts', () => {
      render(<App />)
      
      expect(screen.getByText(/What are the requirements for Express Entry/)).toBeInTheDocument()
      expect(screen.getByText(/How does the Provincial Nominee Program work/)).toBeInTheDocument()
      expect(screen.getByText(/What documents do I need for a study permit/)).toBeInTheDocument()
      expect(screen.getByText(/Tell me about Canadian work permits/)).toBeInTheDocument()
    })

    it('should have new chat button in sidebar', () => {
      render(<App />)
      
      expect(screen.getByRole('button', { name: /New Chat/i })).toBeInTheDocument()
    })

    it('should have dark mode toggle button', () => {
      render(<App />)
      
      const darkModeButton = screen.getByRole('button', { name: /Toggle dark mode/i })
      expect(darkModeButton).toBeInTheDocument()
    })

    it('should have settings toggle button', () => {
      render(<App />)
      
      const settingsButton = screen.getByRole('button', { name: /Toggle settings/i })
      expect(settingsButton).toBeInTheDocument()
    })
  })

  describe('Message Sending', () => {
    it('should send a message when form is submitted', async () => {
      const user = userEvent.setup()
      const mockResponse: ChatResponse = {
        answer: 'Test response',
        session_id: 'session-123',
      }
      mockSendMessage.mockResolvedValueOnce(mockResponse)

      render(<App />)
      
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)
      const submitButton = screen.getByRole('button', { name: '↑' })

      await user.type(textarea, 'What is Express Entry?')
      await user.click(submitButton)

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledWith(
          'What is Express Entry?',
          expect.any(Object)
        )
      })

      await waitFor(() => {
        const questions = screen.getAllByText('What is Express Entry?')
        expect(questions.length).toBeGreaterThan(0)
        expect(screen.getByText('Test response')).toBeInTheDocument()
      })
    })

    it('should send message on Enter key press', async () => {
      const user = userEvent.setup()
      const mockResponse: ChatResponse = {
        answer: 'Response via Enter',
        session_id: 'session-123',
      }
      mockSendMessage.mockResolvedValueOnce(mockResponse)

      render(<App />)
      
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)

      await user.type(textarea, 'Test query{Enter}')

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledWith('Test query', expect.any(Object))
      })
    })

    it('should allow Shift+Enter for new line', async () => {
      const user = userEvent.setup()

      render(<App />)
      
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)

      await user.type(textarea, 'Line 1{Shift>}{Enter}{/Shift}Line 2')

      expect(textarea).toHaveValue('Line 1\nLine 2')
      expect(mockSendMessage).not.toHaveBeenCalled()
    })

    it('should not send empty messages', async () => {
      const user = userEvent.setup()

      render(<App />)

      const submitButton = screen.getByRole('button', { name: '↑' })

      await user.click(submitButton)
      
      expect(mockSendMessage).not.toHaveBeenCalled()
    })

    it('should disable input while loading', async () => {
      const user = userEvent.setup()
      const mockResponse: ChatResponse = {
        answer: 'Delayed response',
        session_id: 'session-123',
      }
      
      // Create a promise that we can control
      let resolvePromise: (value: ChatResponse) => void
      const promise = new Promise<ChatResponse>((resolve) => {
        resolvePromise = resolve
      })
      mockSendMessage.mockReturnValueOnce(promise)

      render(<App />)
      
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)
      
      await user.type(textarea, 'Test query')
      await user.keyboard('{Enter}')

      // Should be disabled while loading
      await waitFor(() => {
        expect(textarea).toBeDisabled()
      })

      // Resolve the promise
      resolvePromise!(mockResponse)

      // Should be enabled after response
      await waitFor(() => {
        expect(textarea).not.toBeDisabled()
      })
    })

    it('should show loading indicator while waiting for response', async () => {
      const user = userEvent.setup()
      let resolvePromise: (value: ChatResponse) => void
      const promise = new Promise<ChatResponse>((resolve) => {
        resolvePromise = resolve
      })
      mockSendMessage.mockReturnValueOnce(promise)

      render(<App />)
      
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)
      
      await user.type(textarea, 'Test query{Enter}')

      // Loading indicator should appear
      await waitFor(() => {
        const loadingDots = screen.getAllByRole('generic').find(el => 
          el.className.includes('animate-bounce')
        )
        expect(loadingDots).toBeInTheDocument()
      })

      resolvePromise!({ answer: 'Response', session_id: 'session-123' })

      // Loading indicator should disappear
      await waitFor(() => {
        expect(screen.getByText('Response')).toBeInTheDocument()
      })
    })

    it('should handle API errors gracefully', async () => {
      const user = userEvent.setup()
      mockSendMessage.mockRejectedValueOnce(new Error('API Error'))

      render(<App />)
      
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)
      
      await user.type(textarea, 'Error query{Enter}')

      await waitFor(() => {
        expect(screen.getByText(/Sorry, I encountered an error/)).toBeInTheDocument()
      })
    })

    it('should clear input after sending message', async () => {
      const user = userEvent.setup()
      const mockResponse: ChatResponse = {
        answer: 'Response',
        session_id: 'session-123',
      }
      mockSendMessage.mockResolvedValueOnce(mockResponse)

      render(<App />)
      
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)
      
      await user.type(textarea, 'Test query')
      expect(textarea).toHaveValue('Test query')

      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(textarea).toHaveValue('')
      })
    })
  })

  describe('Thinking Process', () => {
    it('should display thinking process when available', async () => {
      const user = userEvent.setup()
      const mockResponse: ChatResponse = {
        answer: '<think>This is my reasoning</think>\n\nThis is the answer',
        session_id: 'session-123',
      }
      mockSendMessage.mockResolvedValueOnce(mockResponse)

      render(<App />)
      
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)
      await user.type(textarea, 'Complex query{Enter}')

      await waitFor(() => {
        expect(screen.getByText(/View thinking process/i)).toBeInTheDocument()
      })
    })

    it('should parse thinking and answer correctly', async () => {
      const user = userEvent.setup()
      const mockResponse: ChatResponse = {
        answer: '<think>Step 1: Analyze question\nStep 2: Retrieve info</think>\n\nFinal answer here',
        session_id: 'session-123',
      }
      mockSendMessage.mockResolvedValueOnce(mockResponse)

      render(<App />)
      
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)
      await user.type(textarea, 'Test{Enter}')

      await waitFor(() => {
        // Thinking should be in a details element
        const details = screen.getByText(/View thinking process/i).closest('details')
        expect(details).toBeInTheDocument()
        
        // Answer should be displayed
        expect(screen.getByText('Final answer here')).toBeInTheDocument()
      })
    })

    it('should handle response without thinking', async () => {
      const user = userEvent.setup()
      const mockResponse: ChatResponse = {
        answer: 'Simple answer without thinking',
        session_id: 'session-123',
      }
      mockSendMessage.mockResolvedValueOnce(mockResponse)

      render(<App />)
      
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)
      await user.type(textarea, 'Simple query{Enter}')

      await waitFor(() => {
        expect(screen.getByText('Simple answer without thinking')).toBeInTheDocument()
        expect(screen.queryByText(/View thinking process/i)).not.toBeInTheDocument()
      })
    })
  })

  describe('Dark Mode', () => {
    it('should toggle dark mode when button is clicked', async () => {
      const user = userEvent.setup()

      render(<App />)
      
      const darkModeButton = screen.getByRole('button', { name: /Toggle dark mode/i })

      // Initially not dark mode
      expect(document.documentElement.classList.contains('dark')).toBe(false)

      await user.click(darkModeButton)

      // Should enable dark mode
      expect(document.documentElement.classList.contains('dark')).toBe(true)

      await user.click(darkModeButton)

      // Should disable dark mode
      expect(document.documentElement.classList.contains('dark')).toBe(false)
    })
  })

  describe('Settings Panel', () => {
    it('should toggle settings panel', async () => {
      const user = userEvent.setup()

      render(<App />)
      
      const settingsButton = screen.getByRole('button', { name: /Toggle settings/i })

      await user.click(settingsButton)

      expect(screen.getByText('Advanced Search Settings')).toBeInTheDocument()
      expect(screen.getByText(/Documents to retrieve/)).toBeInTheDocument()

      await user.click(settingsButton)

      expect(screen.queryByText('Advanced Search Settings')).not.toBeInTheDocument()
    })

    it('should allow changing k value', async () => {
      const user = userEvent.setup()
      const mockResponse: ChatResponse = {
        answer: 'Response',
        session_id: 'session-123',
      }
      mockSendMessage.mockResolvedValueOnce(mockResponse)

      render(<App />)
      
      const settingsButton = screen.getByRole('button', { name: /Toggle settings/i })
      await user.click(settingsButton)

      const kSlider = screen.getByRole('slider') as HTMLInputElement
      
      // Change k value to 7 using fireEvent
      fireEvent.change(kSlider, { target: { value: '7' } })

      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)
      await user.type(textarea, 'Test{Enter}')

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledWith(
          'Test',
          expect.objectContaining({ k: 7 })
        )
      })
    })

    it('should allow toggling faceted search', async () => {
      const user = userEvent.setup()
      const mockResponse: ChatResponse = {
        answer: 'Response',
        session_id: 'session-123',
      }
      mockSendMessage.mockResolvedValueOnce(mockResponse)

      render(<App />)
      
      const settingsButton = screen.getByRole('button', { name: /Toggle settings/i })
      await user.click(settingsButton)

      const facetCheckbox = screen.getByLabelText(/Use faceted search/)
      await user.click(facetCheckbox)

      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)
      await user.type(textarea, 'Test{Enter}')

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledWith(
          'Test',
          expect.objectContaining({ useFacet: true })
        )
      })
    })

    it('should allow toggling rerank', async () => {
      const user = userEvent.setup()
      const mockResponse: ChatResponse = {
        answer: 'Response',
        session_id: 'session-123',
      }
      mockSendMessage.mockResolvedValueOnce(mockResponse)

      render(<App />)
      
      const settingsButton = screen.getByRole('button', { name: /Toggle settings/i })
      await user.click(settingsButton)

      const rerankCheckbox = screen.getByLabelText(/Rerank results/)
      await user.click(rerankCheckbox)

      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)
      await user.type(textarea, 'Test{Enter}')

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledWith(
          'Test',
          expect.objectContaining({ useRerank: true })
        )
      })
    })
  })

  describe('Suggestion Prompts', () => {
    it('should populate input when suggestion is clicked', async () => {
      const user = userEvent.setup()

      render(<App />)
      
      const suggestion = screen.getByText(/What are the requirements for Express Entry/)
      await user.click(suggestion)

      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)
      expect(textarea).toHaveValue('What are the requirements for Express Entry?')
    })
  })

  describe('Chat History', () => {
    it('should save chat to localStorage', async () => {
      const user = userEvent.setup()
      const mockResponse: ChatResponse = {
        answer: 'Test response',
        session_id: 'session-123',
      }
      mockSendMessage.mockResolvedValueOnce(mockResponse)

      render(<App />)
      
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)
      await user.type(textarea, 'Save this chat{Enter}')

      await waitFor(() => {
        const stored = localStorage.getItem('immigreat_chat_history')
        expect(stored).toBeTruthy()
        
        const chats = JSON.parse(stored!)
        expect(chats).toHaveLength(1)
        expect(chats[0].title).toContain('Save this chat')
      })
    })

    it('should load chat from history when selected', async () => {
      const user = userEvent.setup()
      
      // Create a saved chat
      const savedChat = {
        id: 'test-chat-1',
        title: 'Previous conversation',
        messages: [
          { id: '1', role: 'user', content: 'Old question', timestamp: new Date().toISOString() },
          { id: '2', role: 'assistant', content: 'Old answer', timestamp: new Date().toISOString() },
        ],
        timestamp: new Date().toISOString(),
      }
      localStorage.setItem('immigreat_chat_history', JSON.stringify([savedChat]))

      render(<App />)
      
      const chatButton = screen.getByText('Previous conversation')
      await user.click(chatButton)

      const oldQuestions = screen.getAllByText('Old question')
      expect(oldQuestions.length).toBeGreaterThan(0)
      expect(screen.getByText('Old answer')).toBeInTheDocument()
    })

    it('should start new chat and reset session', async () => {
      const user = userEvent.setup()
      const mockResponse: ChatResponse = {
        answer: 'First response',
        session_id: 'session-123',
      }
      mockSendMessage.mockResolvedValueOnce(mockResponse)

      render(<App />)
      
      // Send a message
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/) as HTMLTextAreaElement
      await user.click(textarea)
      await user.paste('First message')
      await user.keyboard('{Enter}')

      // Wait for both user message and response
      await waitFor(() => {
        const messages = screen.getAllByText('First message')
        expect(messages.length).toBeGreaterThan(0)
      }, { timeout: 15000 })

      await waitFor(() => {
        expect(screen.getByText('First response')).toBeInTheDocument()
      }, { timeout: 15000 })

      // Click New Chat
      const newChatButton = screen.getByRole('button', { name: /New Chat/i })
      await user.click(newChatButton)

      expect(mockResetSession).toHaveBeenCalled()
      // Check for welcome screen instead (message may still be in sidebar history)
      await waitFor(() => {
        expect(screen.getByText('Welcome to Immigreat')).toBeInTheDocument()
      })
    })

    it('should delete chat when delete button is clicked', async () => {
      const user = userEvent.setup()
      
      const savedChat = {
        id: 'test-chat-1',
        title: 'Chat to delete',
        messages: [
          { id: '1', role: 'user', content: 'Question', timestamp: new Date().toISOString() },
        ],
        timestamp: new Date().toISOString(),
      }
      localStorage.setItem('immigreat_chat_history', JSON.stringify([savedChat]))

      // Mock window.confirm
      vi.stubGlobal('confirm', vi.fn(() => true))

      render(<App />)
      
      expect(screen.getByText('Chat to delete')).toBeInTheDocument()

      // Find delete button - it's a sibling button with SVG
      const deleteButtons = screen.getAllByRole('button')
      const deleteButton = deleteButtons.find(btn => btn.getAttribute('title') === 'Delete chat')
      expect(deleteButton).toBeInTheDocument()

      await user.click(deleteButton!)

      await waitFor(() => {
        expect(screen.queryByText('Chat to delete')).not.toBeInTheDocument()
      })

      vi.unstubAllGlobals()
    })

    it('should group chats by date', () => {
      const now = new Date()
      const yesterday = new Date(now)
      yesterday.setDate(yesterday.getDate() - 1)
      const lastWeek = new Date(now)
      lastWeek.setDate(lastWeek.getDate() - 8)

      const savedChats = [
        {
          id: 'today-chat',
          title: 'Today chat',
          messages: [{ id: '1', role: 'user', content: 'Q', timestamp: now.toISOString() }],
          timestamp: now.toISOString(),
        },
        {
          id: 'yesterday-chat',
          title: 'Yesterday chat',
          messages: [{ id: '2', role: 'user', content: 'Q', timestamp: yesterday.toISOString() }],
          timestamp: yesterday.toISOString(),
        },
        {
          id: 'older-chat',
          title: 'Older chat',
          messages: [{ id: '3', role: 'user', content: 'Q', timestamp: lastWeek.toISOString() }],
          timestamp: lastWeek.toISOString(),
        },
      ]
      localStorage.setItem('immigreat_chat_history', JSON.stringify(savedChats))

      render(<App />)
      
      expect(screen.getByText('Today')).toBeInTheDocument()
      expect(screen.getByText('Yesterday')).toBeInTheDocument()
      expect(screen.getByText('Older')).toBeInTheDocument()
    })

    it('should show message count for each chat', () => {
      const savedChat = {
        id: 'test-chat',
        title: 'Test chat',
        messages: [
          { id: '1', role: 'user', content: 'Q1', timestamp: new Date().toISOString() },
          { id: '2', role: 'assistant', content: 'A1', timestamp: new Date().toISOString() },
          { id: '3', role: 'user', content: 'Q2', timestamp: new Date().toISOString() },
        ],
        timestamp: new Date().toISOString(),
      }
      localStorage.setItem('immigreat_chat_history', JSON.stringify([savedChat]))

      render(<App />)
      
      expect(screen.getByText('3 messages')).toBeInTheDocument()
    })

    it('should show "No chats yet" when no saved chats', () => {
      render(<App />)
      
      expect(screen.getByText(/No chats yet. Start a new conversation!/)).toBeInTheDocument()
    })

    it('should show total saved chats count', () => {
      const savedChats = [
        {
          id: '1',
          title: 'Chat 1',
          messages: [],
          timestamp: new Date().toISOString(),
        },
        {
          id: '2',
          title: 'Chat 2',
          messages: [],
          timestamp: new Date().toISOString(),
        },
      ]
      localStorage.setItem('immigreat_chat_history', JSON.stringify(savedChats))

      render(<App />)
      
      expect(screen.getByText('2 saved chats')).toBeInTheDocument()
    })
  })

  describe('Message Display', () => {
    it('should show user avatar for user messages', async () => {
      const user = userEvent.setup()
      const mockResponse: ChatResponse = {
        answer: 'Response',
        session_id: 'session-123',
      }
      mockSendMessage.mockResolvedValueOnce(mockResponse)

      render(<App />)
      
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)
      await user.type(textarea, 'Test{Enter}')

      await waitFor(() => {
        const userMessages = screen.getAllByText('You')
        expect(userMessages.length).toBeGreaterThan(0)
      })
    })

    it('should show assistant avatar for assistant messages', async () => {
      const user = userEvent.setup()
      const mockResponse: ChatResponse = {
        answer: 'Response',
        session_id: 'session-123',
      }
      mockSendMessage.mockResolvedValueOnce(mockResponse)

      render(<App />)
      
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)
      await user.type(textarea, 'Test{Enter}')

      await waitFor(() => {
        const immigreatLabels = screen.getAllByText('Immigreat')
        expect(immigreatLabels.length).toBeGreaterThan(0)
      })
    })
  })

  describe('Edge Cases', () => {
    it('should handle multiple rapid message sends', async () => {
      const user = userEvent.setup()
      mockSendMessage
        .mockResolvedValueOnce({ answer: 'Response 1', session_id: 'session-1' })
        .mockResolvedValueOnce({ answer: 'Response 2', session_id: 'session-2' })

      render(<App />)
      
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/)

      await user.type(textarea, 'Query 1{Enter}')
      
      // Wait for first response before sending second
      await waitFor(() => {
        expect(screen.getByText('Response 1')).toBeInTheDocument()
      }, { timeout: 10000 })

      await user.type(textarea, 'Query 2{Enter}')

      await waitFor(() => {
        expect(screen.getByText('Response 2')).toBeInTheDocument()
      }, { timeout: 10000 })

      expect(mockSendMessage).toHaveBeenCalledTimes(2)
    })

    it('should handle very long input text', async () => {
      const user = userEvent.setup()
      const longText = 'A'.repeat(500) // Reduced for faster test
      const mockResponse: ChatResponse = {
        answer: 'Response to long text',
        session_id: 'session-123',
      }
      mockSendMessage.mockResolvedValueOnce(mockResponse)

      render(<App />)
      
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/) as HTMLTextAreaElement
      // Use paste for long text instead of typing
      await user.click(textarea)
      await user.paste(longText)
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledWith(longText, expect.any(Object))
      }, { timeout: 10000 })
    })

    it('should trim whitespace from input', async () => {
      const user = userEvent.setup()
      const mockResponse: ChatResponse = {
        answer: 'Response',
        session_id: 'session-123',
      }
      mockSendMessage.mockResolvedValueOnce(mockResponse)

      render(<App />)
      
      const textarea = screen.getByPlaceholderText(/Ask about Canadian immigration/) as HTMLTextAreaElement
      await user.click(textarea)
      await user.paste('   Trimmed query   ')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledWith('Trimmed query', expect.any(Object))
      })
    })

    it('should handle localStorage errors gracefully', () => {
      // Mock localStorage to throw error
      const originalSetItem = Storage.prototype.setItem
      const originalGetItem = Storage.prototype.getItem
      Storage.prototype.setItem = vi.fn(() => {
        throw new Error('Storage error')
      })
      Storage.prototype.getItem = vi.fn(() => {
        throw new Error('Storage error')
      })

      // Should not crash
      expect(() => render(<App />)).not.toThrow()

      Storage.prototype.setItem = originalSetItem
      Storage.prototype.getItem = originalGetItem
    })
  })
})
