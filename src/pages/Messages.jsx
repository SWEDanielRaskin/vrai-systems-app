import React, { useState, useEffect, useRef } from 'react';
import {
  ArrowLeft,
  MessageSquare,
  Phone,
  Clock,
  Send,
  Sparkles,
  RefreshCw,
  ExternalLink,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  getRecentMessages,
  getConversationDetails,
  sendManualSMS,
} from '../services/api';
import { formatSmartTimestamp } from '../utils';

// Body scroll lock hook
const useBodyScrollLock = () => {
  useEffect(() => {
    // Store original styles
    const originalBodyOverflow = document.body.style.overflow;
    const originalHtmlOverflow = document.documentElement.style.overflow;
    const originalBodyHeight = document.body.style.height;
    const originalHtmlHeight = document.documentElement.style.height;

    // Lock scrolling on both body and html
    document.body.style.overflow = 'hidden';
    document.documentElement.style.overflow = 'hidden';
    document.body.style.height = '100vh';
    document.documentElement.style.height = '100vh';

    // Cleanup function to restore original styles
    return () => {
      document.body.style.overflow = originalBodyOverflow;
      document.documentElement.style.overflow = originalHtmlOverflow;
      document.body.style.height = originalBodyHeight;
      document.documentElement.style.height = originalHtmlHeight;
    };
  }, []);
};

const Messages = () => {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState([]);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [error, setError] = useState(null);
  const [newMessage, setNewMessage] = useState('');
  const [sendingMessage, setSendingMessage] = useState(false);
  const messagesPanelRef = useRef(null);
  const eventSourceRef = useRef(null);

  // Lock body scroll for this page
  useBodyScrollLock();

  useEffect(() => {
    fetchConversations();
  }, []);

  const fetchConversations = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await getRecentMessages();

      // Use the conversations array from the enhanced API response
      setConversations(response.conversations || []);

      console.log('Conversations loaded:', response.conversations?.length || 0);
    } catch (error) {
      console.error('Failed to fetch conversations:', error);
      setError('Failed to load conversations');
      setConversations([]);
    } finally {
      setLoading(false);
    }
  };

  const refreshAll = async () => {
    try {
      // Store the currently selected conversation ID
      const currentSelectedId = selectedConversation?.id;

      // Refresh conversations list
      await fetchConversations();

      // If there was a selected conversation, refresh its details
      if (currentSelectedId) {
        try {
          setLoadingDetails(true);
          const conversationDetails = await getConversationDetails(
            currentSelectedId
          );
          setSelectedConversation(conversationDetails);
          console.log('Selected conversation refreshed:', conversationDetails);
        } catch (error) {
          console.error('Failed to refresh selected conversation:', error);
          // If the conversation no longer exists, clear the selection
          setSelectedConversation(null);
        } finally {
          setLoadingDetails(false);
        }
      }
    } catch (error) {
      console.error('Failed to refresh all data:', error);
    }
  };

  const handleConversationSelect = async (conversation) => {
    if (selectedConversation?.id === conversation.id) {
      return; // Already selected
    }

    try {
      setLoadingDetails(true);
      setSelectedConversation(null); // Clear current selection

      // Fetch detailed conversation information including full message history
      const conversationDetails = await getConversationDetails(conversation.id);
      setSelectedConversation(conversationDetails);

      console.log('Conversation details loaded:', conversationDetails);
    } catch (error) {
      console.error('Failed to fetch conversation details:', error);
      // Still set the basic conversation info even if details fail
      setSelectedConversation(conversation);
    } finally {
      setLoadingDetails(false);
    }
  };

  const handleSendMessage = async () => {
    console.log('handleSendMessage called');
    if (!newMessage.trim() || !selectedConversation || sendingMessage) {
      return;
    }

    try {
      setSendingMessage(true);

      // Send manual SMS
      await sendManualSMS(selectedConversation.phone, newMessage.trim());

      // Clear input
      setNewMessage('');

      // Fetch latest conversation details
      const conversationDetails = await getConversationDetails(
        selectedConversation.id
      );
      const oldMessages = selectedConversation.messages || [];
      const newMessages = conversationDetails.messages || [];
      if (newMessages.length > oldMessages.length) {
        setSelectedConversation({
          ...conversationDetails,
          messages: newMessages,
        });
        setTimeout(scrollToBottom, 100);
      }
      // Also refresh the conversations list
      await fetchConversations();
    } catch (error) {
      console.error('Failed to send message:', error);
      alert('Failed to send message. Please try again.');
    } finally {
      setSendingMessage(false);
    }
  };

  // Scroll to bottom helper
  const scrollToBottom = () => {
    if (messagesPanelRef.current) {
      messagesPanelRef.current.scrollTop =
        messagesPanelRef.current.scrollHeight;
    }
  };

  // SSE: Listen for new message events
  useEffect(() => {
    if (!eventSourceRef.current) {
      const es = new window.EventSource('/events');
      eventSourceRef.current = es;
      console.log('[SSE] Connecting to /events');
      es.onopen = () => {
        console.log('[SSE] Connection opened');
      };
      es.onmessage = async (event) => {
        console.log('[SSE] Message received:', event);
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'new_message') {
            if (
              selectedConversation &&
              (selectedConversation.phone === data.phone ||
                selectedConversation.id === data.phone)
            ) {
              // Fetch latest conversation details
              try {
                const conversationDetails = await getConversationDetails(
                  selectedConversation.id
                );
                // Only append new messages
                const oldMessages = selectedConversation.messages || [];
                const newMessages = conversationDetails.messages || [];
                if (newMessages.length > oldMessages.length) {
                  setSelectedConversation({
                    ...conversationDetails,
                    messages: newMessages,
                  });
                  setTimeout(scrollToBottom, 100);
                }
              } catch (err) {
                console.log('[SSE] Error fetching conversation details:', err);
              }
            } else {
              // Refresh conversations list only
              fetchConversations();
            }
          }
        } catch (e) {
          console.log('[SSE] Error parsing event data:', e);
        }
      };
      es.onerror = (err) => {
        console.log('[SSE] Connection error:', err);
      };
    }
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
        console.log('[SSE] Connection closed');
      }
    };
    // eslint-disable-next-line
  }, [selectedConversation]);

  // Scroll to bottom when selectedConversation.messages changes
  useEffect(() => {
    if (selectedConversation && selectedConversation.messages) {
      scrollToBottom();
    }
  }, [selectedConversation]);

  // Remove the previous scroll-to-bottom-on-mount effect and add this:
  useEffect(() => {
    if (
      selectedConversation &&
      selectedConversation.messages &&
      selectedConversation.messages.length > 0
    ) {
      setTimeout(() => {
        scrollToBottom();
      }, 400);
    }
  }, [selectedConversation?.messages?.length]);

  if (loading) {
    return (
      <div className="flex flex-col h-screen overflow-hidden">
        <div className="flex items-center space-x-4">
          <button
            onClick={() => navigate('/')}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="h-5 w-5 text-gray-600" />
          </button>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Messages Today</h1>
            <p className="text-gray-600 mt-1">Loading SMS conversations...</p>
          </div>
        </div>
        <div className="flex items-center justify-center h-64">
          <RefreshCw className="h-8 w-8 animate-spin text-primary-600" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col h-screen overflow-hidden">
        <div className="flex items-center space-x-4">
          <button
            onClick={() => navigate('/')}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="h-5 w-5 text-gray-600" />
          </button>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Messages Today</h1>
            <p className="text-gray-600 mt-1">Error loading conversations</p>
          </div>
        </div>
        <div className="card">
          <div className="text-center py-8">
            <MessageSquare className="h-12 w-12 mx-auto mb-4 text-red-500 opacity-50" />
            <p className="text-red-600 mb-4">{error}</p>
            <button
              onClick={fetchConversations}
              className="btn-primary flex items-center space-x-2 mx-auto"
            >
              <RefreshCw className="h-4 w-4" />
              <span>Retry</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center space-x-4">
          <button
            onClick={() => navigate('/')}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="h-5 w-5 text-gray-600" />
          </button>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Messages Today</h1>
            <p className="text-gray-600 mt-1">
              SMS conversations with customers
            </p>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={refreshAll}
            className="btn-secondary flex items-center space-x-1"
          >
            <RefreshCw className="h-4 w-4" />
            <span>Reload</span>
          </button>
          <a
            href="https://docs.google.com/spreadsheets/d/1FdYk3XCJHCXIXmW94uYG4V2E_wXGmKmwie39Mf-J_JY/edit?usp=sharing"
            target="_blank"
            rel="noopener noreferrer"
            className="btn-secondary flex items-center space-x-1"
            title="Visit Archive"
          >
            <span>Visit Archive</span>
            <ExternalLink className="h-4 w-4 ml-1" />
          </a>
        </div>
      </div>
      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[calc(100vh-120px)] min-h-0">
        {/* Conversations List */}
        <div className="card flex flex-col h-full min-h-0 overflow-y-auto">
          <div className="flex-1 min-h-0 overflow-y-auto">
            {conversations.length === 0 ? (
              <div className="flex items-center justify-center h-full text-gray-500">
                <div className="text-center">
                  <MessageSquare className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>No conversations today</p>
                  <p className="text-sm mt-1">
                    SMS conversations will appear here
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                {conversations.map((conversation) => (
                  <div
                    key={conversation.id}
                    onClick={() => handleConversationSelect(conversation)}
                    className={`p-3 rounded-lg cursor-pointer transition-colors ${
                      selectedConversation?.id === conversation.id
                        ? 'bg-primary-50 border border-primary-200'
                        : 'hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center space-x-2">
                        <div className="bg-primary-100 rounded-full p-1">
                          <MessageSquare className="h-4 w-4 text-primary-600" />
                        </div>
                        <p className="font-medium text-gray-900">
                          {conversation.customerName}
                        </p>
                        {conversation.unread && (
                          <div className="w-2 h-2 bg-primary-600 rounded-full"></div>
                        )}
                      </div>
                      <p className="text-xs text-gray-500">
                        {formatSmartTimestamp(conversation.timestamp)}
                      </p>
                    </div>
                    <div className="flex items-center space-x-2 mb-1">
                      <Phone className="h-3 w-3 text-gray-400" />
                      <p className="text-xs text-gray-500">
                        {conversation.phone}
                      </p>
                    </div>
                    <p className="text-sm text-gray-600 truncate">
                      {conversation.lastMessage}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        {/* Conversation Detail */}
        <div className="lg:col-span-2 card flex flex-col h-full min-h-0 overflow-y-auto">
          {loadingDetails ? (
            <div className="flex items-center justify-center h-full">
              <RefreshCw className="h-8 w-8 animate-spin text-primary-600" />
            </div>
          ) : selectedConversation ? (
            <>
              {/* Conversation Header */}
              <div className="border-b border-gray-200 pb-4 mb-4">
                <div className="flex items-center space-x-3">
                  <div className="bg-primary-100 rounded-full p-2">
                    <MessageSquare className="h-5 w-5 text-primary-600" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-gray-900">
                      {selectedConversation.customerName}
                    </h3>
                    <p className="text-sm text-gray-500">
                      {selectedConversation.phone}
                    </p>
                  </div>
                </div>
              </div>

              {/* AI Summary */}
              <div className="bg-blue-50 rounded-lg p-4 mb-4">
                <div className="flex items-center space-x-2 mb-2">
                  <Sparkles className="h-4 w-4 text-blue-600" />
                  <h4 className="font-medium text-blue-900">AI Summary</h4>
                </div>
                <p className="text-sm text-blue-800">
                  {selectedConversation.summary ||
                    'AI summary will be generated automatically after a few messages'}
                </p>
              </div>

              {/* Messages */}
              {selectedConversation.messages &&
              selectedConversation.messages.length > 0 ? (
                <div
                  ref={messagesPanelRef}
                  className="flex-1 min-h-0 overflow-y-auto space-y-4 mb-4"
                >
                  {selectedConversation.messages.map((msg, index) => (
                    <div
                      key={index}
                      className={`flex ${
                        msg.sender === 'customer'
                          ? 'justify-start'
                          : 'justify-end'
                      }`}
                    >
                      <div
                        className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
                          msg.sender === 'customer'
                            ? 'bg-gray-100 text-gray-900'
                            : 'bg-primary-600 text-white'
                        }`}
                      >
                        <p className="text-sm">{msg.message}</p>
                        <div className="flex items-center justify-end mt-1 space-x-1">
                          <Clock className="h-3 w-3 opacity-70" />
                          <p className="text-xs opacity-70">
                            {formatSmartTimestamp(msg.timestamp)}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex-1 flex items-center justify-center text-gray-500">
                  <div className="text-center">
                    <MessageSquare className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p>No messages in this conversation</p>
                  </div>
                </div>
              )}

              {/* Message Input */}
              <div className="border-t border-gray-200 pt-4">
                <form
                  className="flex space-x-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    console.log('form onSubmit');
                    if (!sendingMessage) handleSendMessage();
                  }}
                >
                  <input
                    type="text"
                    value={newMessage}
                    onChange={(e) => setNewMessage(e.target.value)}
                    placeholder="Type a message..."
                    className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                    disabled={sendingMessage}
                  />
                  <button
                    type="submit"
                    disabled={!newMessage.trim() || sendingMessage}
                    className="btn-primary flex items-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {sendingMessage ? (
                      <RefreshCw className="h-4 w-4 animate-spin" />
                    ) : (
                      <Send className="h-4 w-4" />
                    )}
                    <span>{sendingMessage ? 'Sending...' : 'Send'}</span>
                  </button>
                </form>
                <p className="text-xs text-gray-500 mt-2">
                  💡 Manual messages are sent immediately and logged to the
                  conversation.
                </p>
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-500">
              <div className="text-center">
                <MessageSquare className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>Select a conversation to view messages</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Messages;
