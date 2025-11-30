import { useState, useRef, useEffect } from 'react'
import { chatAPI, DEFAULT_SETTINGS } from './services/api'
import type { ChatSettings } from './services/api'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isDarkMode, setIsDarkMode] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [settings, setSettings] = useState<ChatSettings>(DEFAULT_SETTINGS)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [isDarkMode])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!input.trim() || isLoading) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date()
    }

    setMessages(prev => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    try {
      // Call your actual backend API with RAG parameters
      const response = await chatAPI.sendMessage(userMessage.content, settings)

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        // Handle different response formats from backend
        content: response.response || response.answer || 'No response received',
        timestamp: new Date()
      }

      setMessages(prev => [...prev, assistantMessage])
    } catch (error) {
      console.error('Error sending message:', error)

      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Sorry, I encountered an error processing your request. Please try again.',
        timestamp: new Date()
      }

      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const suggestionPrompts = [
    { icon: "📄", text: "What are the requirements for Express Entry?" },
    { icon: "🏛️", text: "How does the Provincial Nominee Program work?" },
    { icon: "🎓", text: "What documents do I need for a study permit?" },
    { icon: "💼", text: "Tell me about Canadian work permits" },
  ]

  return (
    <div className="flex flex-col h-screen bg-gray-50 dark:bg-gray-900 transition-colors duration-300">
      {/* Header */}
      <header className="bg-gradient-to-r from-canada-red to-canada-red-dark text-white px-8 py-6 shadow-lg relative">
        <div className="w-full">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-4xl animate-bounce-slow">🍁</span>
            <h1 className="text-3xl font-semibold">Immigreat</h1>
          </div>
          <p className="text-sm opacity-90">Your Canadian Immigration Assistant</p>
        </div>

        {/* Settings Toggle */}
        <button
          onClick={() => setShowSettings(!showSettings)}
          className="absolute top-6 right-20 w-10 h-10 flex items-center justify-center bg-white/20 hover:bg-white/30 rounded-full transition-all duration-300 hover:scale-110 text-xl"
          aria-label="Toggle settings"
          title="Advanced settings"
        >
          ⚙️
        </button>

        {/* Dark Mode Toggle */}
        <button
          onClick={() => setIsDarkMode(!isDarkMode)}
          className="absolute top-6 right-8 w-10 h-10 flex items-center justify-center bg-white/20 hover:bg-white/30 rounded-full transition-all duration-300 hover:scale-110 text-xl"
          aria-label="Toggle dark mode"
        >
          {isDarkMode ? '☀' : '🌙'}
        </button>
      </header>

      {/* Settings Panel */}
      {showSettings && (
        <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-8 py-4 shadow-md">
          <div className="max-w-5xl mx-auto">
            <h3 className="text-sm font-semibold mb-3 text-gray-700 dark:text-gray-300">
              Advanced Search Settings
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Number of Results */}
              <div>
                <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">
                  Documents to retrieve (k): {settings.k}
                </label>
                <input
                  type="range"
                  min="1"
                  max="10"
                  value={settings.k}
                  onChange={(e) => setSettings({...settings, k: parseInt(e.target.value)})}
                  className="w-full"
                />
              </div>

              {/* Use Facet */}
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="facet"
                  checked={settings.useFacet}
                  onChange={(e) => setSettings({...settings, useFacet: e.target.checked})}
                  className="w-4 h-4"
                />
                <label htmlFor="facet" className="text-sm text-gray-700 dark:text-gray-300">
                  Use faceted search
                </label>
              </div>

              {/* Use Rerank */}
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="rerank"
                  checked={settings.useRerank}
                  onChange={(e) => setSettings({...settings, useRerank: e.target.checked})}
                  className="w-4 h-4"
                />
                <label htmlFor="rerank" className="text-sm text-gray-700 dark:text-gray-300">
                  Rerank results
                </label>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Chat Area */}
      <main className="flex-1 overflow-y-auto px-8 py-8">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center w-full max-w-5xl px-8">
              <div className="text-6xl mb-6 animate-bounce-slow">🍁</div>
              <h2 className="text-4xl font-bold mb-4 text-canada-red-dark dark:text-red-400">
                Welcome to Immigreat
              </h2>
              <p className="text-xl text-gray-600 dark:text-gray-300 mb-8">
                Your guide to Canadian immigration. Ask me anything about moving to Canada!
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-8">
                {suggestionPrompts.map((prompt, index) => (
                  <button
                    key={index}
                    onClick={() => setInput(prompt.text)}
                    className="bg-white dark:bg-gray-800 border-2 border-gray-200 dark:border-gray-700 hover:border-canada-red dark:hover:border-canada-red rounded-xl p-5 text-left transition-all duration-200 hover:-translate-y-1 hover:shadow-lg dark:text-gray-200"
                  >
                    <span className="text-2xl mr-3">{prompt.icon}</span>
                    {prompt.text}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="w-full max-w-5xl mx-auto px-8">
            {messages.map((message) => (
              <div
                key={message.id}
                className="mb-6 animate-fadeIn"
              >
                <div className="flex gap-4 items-start">
                  <div className="w-9 h-9 rounded-full bg-white dark:bg-gray-800 shadow-md flex items-center justify-center text-xl flex-shrink-0">
                    {message.role === 'user' ? '👤' : '🤖'}
                  </div>
                  <div className="flex-1 bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm">
                    <div className="font-semibold text-sm mb-2 text-canada-red dark:text-red-400">
                      {message.role === 'user' ? 'You' : 'Immigreat'}
                    </div>
                    <p className="text-gray-800 dark:text-gray-200 whitespace-pre-wrap leading-relaxed">
                      {message.content}
                    </p>
                  </div>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="mb-6 animate-fadeIn">
                <div className="flex gap-4 items-start">
                  <div className="w-9 h-9 rounded-full bg-white dark:bg-gray-800 shadow-md flex items-center justify-center text-xl flex-shrink-0">
                    🤖
                  </div>
                  <div className="flex-1 bg-gray-100 dark:bg-gray-700 rounded-xl p-5 shadow-sm">
                    <div className="font-semibold text-sm mb-2 text-canada-red-dark dark:text-red-400">
                      Immigreat
                    </div>
                    <div className="flex gap-1 py-2">
                      <span className="w-2 h-2 bg-canada-red-dark dark:bg-red-400 rounded-full animate-bounce"></span>
                      <span className="w-2 h-2 bg-canada-red-dark dark:bg-red-400 rounded-full animate-bounce [animation-delay:0.2s]"></span>
                      <span className="w-2 h-2 bg-canada-red-dark dark:bg-red-400 rounded-full animate-bounce [animation-delay:0.4s]"></span>
                    </div>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </main>

      {/* Input Area */}
      <footer className="bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 px-5 py-5 shadow-lg transition-colors duration-300">
        <form onSubmit={handleSubmit} className="w-full max-w-5xl mx-auto">
          <div className="flex gap-3 items-end bg-white dark:bg-gray-700 border-2 border-gray-200 dark:border-gray-600 focus-within:border-canada-red dark:focus-within:border-canada-red rounded-xl p-2 transition-colors duration-200">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about Canadian immigration, Express Entry, work permits, study permits..."
              className="flex-1 bg-transparent border-none outline-none px-3 py-2 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 resize-none max-h-48 font-sans"
              rows={1}
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="w-10 h-10 flex items-center justify-center bg-gradient-to-r from-canada-red to-canada-red-dark text-white rounded-lg transition-all duration-200 hover:scale-105 hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
            >
              <span className="inline-block transform rotate-90 text-xl font-bold">↑</span>
            </button>
          </div>
        </form>
      </footer>
    </div>
  )
}

export default App
