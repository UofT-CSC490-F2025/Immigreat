import { useState, useRef, useEffect } from 'react'
import { chatAPI, DEFAULT_SETTINGS } from './services/api'
import type { ChatSettings } from './services/api'
import logo from './assets/logo.png'

// ==================== TYPES ====================
interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

interface SavedChat {
  id: string
  title: string
  messages: Message[]
  timestamp: Date
  session_id?: string
}

// ==================== CHAT HISTORY MANAGER ====================
const STORAGE_KEY = 'immigreat_chat_history'
const MAX_CHATS = 50

const chatHistoryManager = {
  getAllChats(): SavedChat[] {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (!stored) return []

      const chats = JSON.parse(stored)
      return chats.map((chat: any) => ({
        ...chat,
        timestamp: new Date(chat.timestamp),
        messages: chat.messages.map((msg: any) => ({
          ...msg,
          timestamp: new Date(msg.timestamp)
        }))
      }))
    } catch (error) {
      console.error('Error loading chat history:', error)
      return []
    }
  },

  saveChat(chatId: string | null, messages: Message[], session_id?: string): string {
    try {
      const chats = this.getAllChats()

      const firstUserMsg = messages.find(m => m.role === 'user')
      const title = firstUserMsg
        ? firstUserMsg.content.slice(0, 50) + (firstUserMsg.content.length > 50 ? '...' : '')
        : 'New Chat'

      if (chatId) {
        const index = chats.findIndex(c => c.id === chatId)
        if (index !== -1) {
          chats[index] = {
            ...chats[index],
            title,
            messages,
            timestamp: new Date(),
            session_id
          }
          localStorage.setItem(STORAGE_KEY, JSON.stringify(chats))
          return chatId
        }
      }

      const newChat: SavedChat = {
        id: Date.now().toString(),
        title,
        messages,
        timestamp: new Date(),
        session_id
      }

      const updatedChats = [newChat, ...chats].slice(0, MAX_CHATS)
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedChats))
      return newChat.id
    } catch (error) {
      console.error('Error saving chat:', error)
      return chatId || ''
    }
  },

  loadChat(id: string): SavedChat | null {
    const chats = this.getAllChats()
    return chats.find(chat => chat.id === id) || null
  },

  deleteChat(id: string): void {
    try {
      const chats = this.getAllChats()
      const filtered = chats.filter(chat => chat.id !== id)
      localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered))
    } catch (error) {
      console.error('Error deleting chat:', error)
    }
  },
}

// ==================== SIDEBAR COMPONENT ====================
interface SidebarProps {
  chats: SavedChat[]
  currentChatId: string | null
  onSelectChat: (chatId: string) => void
  onNewChat: () => void
  onDeleteChat: (chatId: string) => void
}

function Sidebar({ chats, currentChatId, onSelectChat, onNewChat, onDeleteChat }: SidebarProps) {
  const groupChatsByDate = (chats: SavedChat[]) => {
    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    const lastWeek = new Date(today)
    lastWeek.setDate(lastWeek.getDate() - 7)

    const groups: { [key: string]: SavedChat[] } = {
      Today: [],
      Yesterday: [],
      'Previous 7 Days': [],
      Older: []
    }

    chats.forEach(chat => {
      const chatDate = new Date(chat.timestamp)
      const chatDay = new Date(chatDate.getFullYear(), chatDate.getMonth(), chatDate.getDate())

      if (chatDay.getTime() === today.getTime()) {
        groups.Today.push(chat)
      } else if (chatDay.getTime() === yesterday.getTime()) {
        groups.Yesterday.push(chat)
      } else if (chatDate >= lastWeek) {
        groups['Previous 7 Days'].push(chat)
      } else {
        groups.Older.push(chat)
      }
    })

    return groups
  }

  const groupedChats = groupChatsByDate(chats)

  return (
    <div className="w-64 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 flex flex-col h-screen">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={onNewChat}
          className="w-full bg-gradient-to-r from-canada-red to-canada-red-dark text-white py-2 px-4 rounded-lg hover:opacity-90 transition-all duration-200 flex items-center justify-center gap-2 font-medium"
        >
          <span>+</span>
          <span>New Chat</span>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {Object.entries(groupedChats).map(([groupName, groupChats]) => {
          if (groupChats.length === 0) return null

          return (
            <div key={groupName} className="mb-4">
              <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 px-2 mb-2">
                {groupName}
              </h3>
              <div className="space-y-1">
                {groupChats.map(chat => (
                  <div
                    key={chat.id}
                    className={`group relative rounded-lg transition-all duration-200 ${
                      currentChatId === chat.id
                        ? 'bg-white dark:bg-gray-800 shadow-sm'
                        : 'hover:bg-gray-100 dark:hover:bg-gray-800'
                    }`}
                  >
                    <button
                      onClick={() => onSelectChat(chat.id)}
                      className="w-full text-left px-3 py-2 pr-8"
                    >
                      <div className="text-sm text-gray-900 dark:text-gray-100 truncate">
                        {chat.title}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        {chat.messages.length} messages
                      </div>
                    </button>

                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        if (window.confirm('Delete this chat?')) {
                          onDeleteChat(chat.id)
                        }
                      }}
                      className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-red-100 dark:hover:bg-red-900/20 rounded"
                      title="Delete chat"
                    >
                      <svg className="w-4 h-4 text-red-600 dark:text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )
        })}

        {chats.length === 0 && (
          <div className="text-center text-gray-500 dark:text-gray-400 text-sm mt-8 px-4">
            No chats yet. Start a new conversation!
          </div>
        )}
      </div>

      <div className="p-4 border-t border-gray-200 dark:border-gray-700">
        <div className="text-xs text-gray-500 dark:text-gray-400 text-center">
          {chats.length} saved chat{chats.length !== 1 ? 's' : ''}
        </div>
      </div>
    </div>
  )
}

// ==================== MAIN APP ====================
function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isDarkMode, setIsDarkMode] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [settings, setSettings] = useState<ChatSettings>(DEFAULT_SETTINGS)
  const [currentChatId, setCurrentChatId] = useState<string | null>(null)
  const [savedChats, setSavedChats] = useState(chatHistoryManager.getAllChats())
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

  useEffect(() => {
    if (messages.length > 0) {
      const chatId = chatHistoryManager.saveChat(
        currentChatId,
        messages,
        chatAPI.getSessionId() || undefined
      )
      if (!currentChatId) {
        setCurrentChatId(chatId)
      }
      setSavedChats(chatHistoryManager.getAllChats())
    }
  }, [messages])

  const handleNewChat = () => {
    setMessages([])
    setCurrentChatId(null)
    chatAPI.resetSession()
    setInput('')
  }

  const handleSelectChat = (chatId: string) => {
    const chat = chatHistoryManager.loadChat(chatId)
    if (chat) {
      setMessages(chat.messages)
      setCurrentChatId(chat.id)
    }
  }

  const handleDeleteChat = (chatId: string) => {
    chatHistoryManager.deleteChat(chatId)
    setSavedChats(chatHistoryManager.getAllChats())

    if (currentChatId === chatId) {
      handleNewChat()
    }
  }

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
      const response = await chatAPI.sendMessage(userMessage.content, settings)

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.answer || 'No response received',
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
    <div className={`flex h-screen ${isDarkMode ? 'dark' : ''}`}>
      <Sidebar
        chats={savedChats}
        currentChatId={currentChatId}
        onSelectChat={handleSelectChat}
        onNewChat={handleNewChat}
        onDeleteChat={handleDeleteChat}
      />

      <div className="flex flex-col flex-1 bg-gray-50 dark:bg-gray-900 transition-colors duration-300">
        <header className="bg-gradient-to-r from-canada-red to-canada-red-dark text-white px-8 py-4 shadow-lg">
          <div className="w-full flex items-center justify-between">
            <div className="flex items-center gap-4">
              <img
                src={logo}
                alt="Immigreat Logo"
                className="w-12 h-12 rounded-full object-cover mix-blend-screen"
              />
              <div>
                <h1 className="text-2xl font-semibold">Immigreat</h1>
                <p className="text-xs opacity-90">Canadian Immigration Assistant</p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowSettings(!showSettings)}
                className="w-10 h-10 flex items-center justify-center bg-white/20 hover:bg-white/30 rounded-full transition-all duration-300 hover:scale-110 text-xl"
                aria-label="Toggle settings"
                title="Advanced settings"
              >
                ⚙️
              </button>

              <button
                onClick={() => setIsDarkMode(!isDarkMode)}
                className="w-10 h-10 flex items-center justify-center bg-white/20 hover:bg-white/30 rounded-full transition-all duration-300 hover:scale-110 text-xl"
                aria-label="Toggle dark mode"
              >
                {isDarkMode ? '☀️' : '🌙'}
              </button>
            </div>
          </div>
        </header>

        {showSettings && (
          <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-8 py-4 shadow-md">
            <div className="max-w-5xl mx-auto">
              <h3 className="text-sm font-semibold mb-3 text-gray-700 dark:text-gray-300">
                Advanced Search Settings
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
            <div className="w-full max-w-5xl mx-auto">
              {messages.map((message) => (
                <div key={message.id} className="mb-6 animate-fadeIn">
                  <div className="flex gap-4 items-start">
                    <div className="w-9 h-9 rounded-full bg-white dark:bg-gray-800 shadow-md flex items-center justify-center text-xl flex-shrink-0">
                      {message.role === 'user' ? '🙂' : '🍁'}
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
                      <img
                        src={logo}
                        alt="Immigreat Logo"
                        className="w-12 h-12 rounded-full object-cover mix-blend-screen"
                      />
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
    </div>
  )
}

export default App
