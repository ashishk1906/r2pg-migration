import React, { useState, useRef, useEffect } from 'react';
import type { CollectionSummary, ChatMessage } from '../types/migration';
import { generateCopilotResponse } from '../services/aiCopilot';
import {
  Bot,
  Send,
  Zap,
  Search,
  ArrowRightLeft,
  Layers,
  ShieldCheck,
  ChevronUp,
  ChevronDown,
  Trash2,
  Copy,
  Check,
  Terminal
} from 'lucide-react';

interface AiChatProps {
  collection: CollectionSummary;
  docIndex: number;
}

export const AiChat: React.FC<AiChatProps> = ({ collection, docIndex }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome-msg',
      sender: 'assistant',
      timestamp: '11:45 AM',
      content: `👋 **Welcome to the CT-RPG AI Migration Copilot!**

I am paired with your live session and analyzing the **${collection.name}** domain (\`${collection.ravenCollection}\` ➔ \`${collection.postgresTable}\`).

Use the **minimal action buttons** to run immediate architectural checks, or type any question about data types, indexes, or queries!`,
      actions: [
        { label: '⚡ Schema Mapping', actionKey: 'schema_mapping' },
        { label: '🔍 Parity Audit', actionKey: 'parity_audit' },
        { label: '🔄 RQL ➔ SQL', actionKey: 'rql_to_sql' },
        { label: '📊 JSONB LATERAL', actionKey: 'jsonb_lateral' }
      ]
    }
  ]);
  const [inputVal, setInputVal] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [copiedSnippetId, setCopiedSnippetId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen, isTyping]);

  const handleActionClick = (actionKey: string) => {
    setIsOpen(true);
    setIsTyping(true);
    setTimeout(() => {
      const response = generateCopilotResponse({
        actionKey,
        selectedCollection: collection,
        selectedDocIndex: docIndex
      });
      setMessages(prev => [...prev, response]);
      setIsTyping(false);
    }, 450);
  };

  const handleSendMessage = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputVal.trim()) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      sender: 'user',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      content: inputVal.trim()
    };

    setMessages(prev => [...prev, userMsg]);
    const prompt = inputVal.trim();
    setInputVal('');
    setIsTyping(true);

    setTimeout(() => {
      const assistantMsg = generateCopilotResponse({
        userPrompt: prompt,
        selectedCollection: collection,
        selectedDocIndex: docIndex
      });
      setMessages(prev => [...prev, assistantMsg]);
      setIsTyping(false);
    }, 550);
  };

  const handleCopyCode = (id: string, code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedSnippetId(id);
    setTimeout(() => setCopiedSnippetId(null), 2000);
  };

  const clearChat = () => {
    setMessages([
      {
        id: `init-${Date.now()}`,
        sender: 'assistant',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        content: `Chat cleared. Ready for your questions on **${collection.name}**!`
      }
    ]);
  };

  return (
    <div className={`ai-chat-dock ${isOpen ? 'expanded' : 'collapsed'}`}>
      <div className="chat-dock-header" onClick={() => setIsOpen(!isOpen)}>
        <div className="chat-header-title">
          <div className="bot-avatar">
            <Bot size={18} />
          </div>
          <div className="chat-title-text">
            <strong>AI Copilot</strong>
            <span className="chat-context-badge">
              <code>{collection.ravenCollection}</code> ➔ <code>{collection.postgresTable}</code>
            </span>
          </div>
        </div>

        {/* Minimal Action Buttons in chat header bar */}
        <div className="chat-quick-actions-bar in-header" onClick={e => e.stopPropagation()}>
          <button
            className="quick-action-pill"
            onClick={() => handleActionClick('schema_mapping')}
            title="Explain Schema & Data Type Mappings"
          >
            <Zap size={13} className="text-warning" />
            <span>⚡ Schema Mapping</span>
          </button>
          <button
            className="quick-action-pill"
            onClick={() => handleActionClick('parity_audit')}
            title="Audit Active Record between RavenDB and Postgres"
          >
            <Search size={13} className="text-success" />
            <span>🔍 Parity Audit</span>
          </button>
          <button
            className="quick-action-pill"
            onClick={() => handleActionClick('rql_to_sql')}
            title="Translate RavenDB RQL Query into PostgreSQL SQL"
          >
            <ArrowRightLeft size={13} className="text-primary" />
            <span>🔄 RQL ➔ SQL</span>
          </button>
          <button
            className="quick-action-pill"
            onClick={() => handleActionClick('jsonb_lateral')}
            title="Explain how JSONB LATERAL join replaces C# in-memory joins"
          >
            <Layers size={13} className="text-info" />
            <span>📊 JSONB LATERAL</span>
          </button>
          <button
            className="quick-action-pill"
            onClick={() => handleActionClick('trigger_check')}
            title="Check automatic modified_on trigger logic"
          >
            <ShieldCheck size={13} className="text-secondary" />
            <span>📋 Trigger Check</span>
          </button>
        </div>

        <div className="chat-header-controls" onClick={e => e.stopPropagation()}>
          <button className="icon-btn-minimal" onClick={clearChat} title="Clear Chat History">
            <Trash2 size={15} />
          </button>
          <button className="icon-btn-minimal toggle-dock-btn" onClick={() => setIsOpen(!isOpen)}>
            {isOpen ? <ChevronDown size={18} /> : <ChevronUp size={18} />}
          </button>
        </div>
      </div>

      {isOpen && (
        <div className="chat-dock-body">

          {/* Messages Container */}
          <div className="chat-messages-scroll-area">
            {messages.map(msg => (
              <div key={msg.id} className={`chat-message-row ${msg.sender}`}>
                <div className="chat-avatar">
                  {msg.sender === 'assistant' ? <Bot size={16} /> : <span>U</span>}
                </div>
                <div className="chat-message-bubble">
                  <div className="chat-bubble-header">
                    <span className="sender-name">
                      {msg.sender === 'assistant' ? 'Copilot AI' : 'You'}
                    </span>
                    <span className="message-time">{msg.timestamp}</span>
                  </div>
                  <div className="chat-text-content">
                    {msg.content.split('\n\n').map((paragraph, idx) => (
                      <p key={idx} dangerouslySetInnerHTML={{
                        __html: paragraph
                          .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                          .replace(/`(.*?)`/g, '<code>$1</code>')
                          .replace(/^### (.*$)/gm, '<h4 class="chat-heading">$1</h4>')
                          .replace(/^- (.*$)/gm, '<span class="bullet-item">• $1</span>')
                      }} />
                    ))}
                  </div>

                  {msg.codeSnippet && (
                    <div className="chat-snippet-wrapper">
                      <div className="snippet-header">
                        <span className="snippet-title">
                          <Terminal size={13} /> {msg.codeSnippet.title || msg.codeSnippet.language}
                        </span>
                        <button
                          className="copy-snippet-btn"
                          onClick={() => handleCopyCode(msg.id, msg.codeSnippet!.code)}
                        >
                          {copiedSnippetId === msg.id ? (
                            <>
                              <Check size={13} className="text-success" />
                              <span>Copied</span>
                            </>
                          ) : (
                            <>
                              <Copy size={13} />
                              <span>Copy</span>
                            </>
                          )}
                        </button>
                      </div>
                      <pre className="snippet-code">
                        <code>{msg.codeSnippet.code}</code>
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {isTyping && (
              <div className="chat-message-row assistant">
                <div className="chat-avatar">
                  <Bot size={16} />
                </div>
                <div className="chat-message-bubble typing-bubble">
                  <span className="dot"></span>
                  <span className="dot"></span>
                  <span className="dot"></span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Chat Input */}
          <form className="chat-dock-input-form" onSubmit={handleSendMessage}>
            <input
              type="text"
              placeholder="Ask about GIN indexes, lateral joins, data types, or migration verification..."
              value={inputVal}
              onChange={e => setInputVal(e.target.value)}
              className="chat-text-input"
            />
            <button
              type="submit"
              className="chat-send-btn"
              disabled={!inputVal.trim() || isTyping}
            >
              <Send size={15} />
            </button>
          </form>
        </div>
      )}
    </div>
  );
};
