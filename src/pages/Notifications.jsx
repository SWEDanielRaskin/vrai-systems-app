import React, { useState, useEffect, useRef } from 'react';
import {
  ArrowLeft,
  AlertTriangle,
  AlertCircle,
  Star,
  Clock,
  Phone,
  MessageSquare,
  CheckCircle,
  X,
  RefreshCw,
  ExternalLink,
  Sparkles,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  getNotifications,
  resolveNotification,
  deleteNotification,
  getCallDetails,
  getConversationDetails,
} from '../services/api';
import { format } from 'date-fns';
import { formatSmartTimestamp } from '../utils';

const Notifications = () => {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [selectedNotification, setSelectedNotification] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notificationTranscript, setNotificationTranscript] = useState(null);
  const [loadingTranscript, setLoadingTranscript] = useState(false);
  const eventSourceRef = useRef(null);

  useEffect(() => {
    fetchNotifications();
  }, []);

  // SSE: Listen for notification_created events (always active)
  useEffect(() => {
    if (!eventSourceRef.current) {
      const es = new window.EventSource('/events');
      eventSourceRef.current = es;
      es.onopen = () => {
        console.log('[SSE] Notifications: Connection opened');
      };
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'notification_created') {
            console.log(
              '[SSE] Notifications: notification_created event received:',
              data
            );
            fetchNotifications();
          }
        } catch (e) {
          // Ignore parse errors
        }
      };
      es.onerror = (err) => {
        console.log('[SSE] Notifications: Connection error:', err);
      };
    }
    // Cleanup on unmount
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
        console.log('[SSE] Notifications: Connection closed');
      }
    };
  }, []);

  const fetchNotifications = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await getNotifications();
      setNotifications(response.notifications || []);
      console.log('Notifications loaded:', response.notifications?.length || 0);
    } catch (error) {
      console.error('Failed to fetch notifications:', error);
      setError('Failed to load notifications');
      setNotifications([]);
    } finally {
      setLoading(false);
    }
  };

  const getNotificationIcon = (type) => {
    switch (type) {
      case 'critical':
        return <AlertTriangle className="h-4 w-4 text-red-600" />;
      case 'urgent':
        return <AlertCircle className="h-4 w-4 text-orange-600" />;
      case 'interest':
        return <Star className="h-4 w-4 text-yellow-600" />;
      default:
        return <AlertCircle className="h-4 w-4 text-gray-600" />;
    }
  };

  const getNotificationTypeLabel = (type) => {
    switch (type) {
      case 'critical':
        return 'Critical';
      case 'urgent':
        return 'Urgent Action';
      case 'interest':
        return 'Interest';
      default:
        return 'Unknown';
    }
  };

  const getNotificationBgColor = (type) => {
    switch (type) {
      case 'critical':
        return 'bg-red-50 border-red-200';
      case 'urgent':
        return 'bg-orange-50 border-orange-200';
      case 'interest':
        return 'bg-yellow-50 border-yellow-200';
      default:
        return 'bg-gray-50 border-gray-200';
    }
  };

  // Format timestamp for display
  const formatTimestamp = (timestamp) => {
    try {
      const date = new Date(timestamp);
      const now = new Date();
      const diffMs = now - date;
      const diffMinutes = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMs / 3600000);
      const diffDays = Math.floor(diffMs / 86400000);

      if (diffMinutes < 1) return 'Just now';
      if (diffMinutes < 60)
        return `${diffMinutes} minute${diffMinutes > 1 ? 's' : ''} ago`;
      if (diffHours < 24)
        return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
      if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;

      return date.toLocaleDateString();
    } catch (error) {
      return timestamp; // Return original if parsing fails
    }
  };

  const handleResolveNotification = async (notificationId) => {
    try {
      await resolveNotification(notificationId);
      setNotifications((prev) =>
        prev.map((notification) =>
          notification.id === notificationId
            ? { ...notification, resolved: true }
            : notification
        )
      );

      // Also update the selectedNotification if it's the one being resolved
      if (selectedNotification && selectedNotification.id === notificationId) {
        setSelectedNotification((prev) => ({ ...prev, resolved: true }));
      }

      console.log('Notification resolved:', notificationId);
    } catch (error) {
      console.error('Failed to resolve notification:', error);
      alert('Failed to resolve notification. Please try again.');
    }
  };

  const handleClearNotification = async (notificationId) => {
    try {
      await deleteNotification(notificationId);
      setNotifications((prev) =>
        prev.filter((notification) => notification.id !== notificationId)
      );

      // If the cleared notification was selected, clear the selection
      if (selectedNotification && selectedNotification.id === notificationId) {
        setSelectedNotification(null);
      }

      console.log('Notification cleared:', notificationId);
    } catch (error) {
      console.error('Failed to clear notification:', error);
      alert('Failed to clear notification. Please try again.');
    }
  };

  const handleNotificationSelect = async (notification) => {
    setSelectedNotification(notification);
    setNotificationTranscript(null);
    if (!notification.conversation_id || !notification.conversation_type)
      return;
    setLoadingTranscript(true);
    try {
      if (notification.conversation_type === 'voice') {
        const callDetails = await getCallDetails(notification.conversation_id);
        setNotificationTranscript({
          type: 'voice',
          transcript: callDetails.transcript || [],
          summary: callDetails.summary || '',
        });
      } else if (notification.conversation_type === 'sms') {
        const convDetails = await getConversationDetails(
          notification.conversation_id
        );
        setNotificationTranscript({
          type: 'sms',
          messages: convDetails.messages || [],
          summary: convDetails.summary || '',
        });
      }
    } catch (e) {
      setNotificationTranscript({ type: 'error' });
    } finally {
      setLoadingTranscript(false);
    }
  };

  const sortedNotifications = [...notifications].sort((a, b) => {
    const typeOrder = { critical: 0, urgent: 1, interest: 2 };
    if (a.resolved !== b.resolved) {
      return a.resolved ? 1 : -1;
    }
    return typeOrder[a.type] - typeOrder[b.type];
  });

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center space-x-4">
          <button
            onClick={() => navigate('/')}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="h-5 w-5 text-gray-600" />
          </button>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Notifications</h1>
            <p className="text-gray-600 mt-1">Loading notifications...</p>
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
      <div className="space-y-6">
        <div className="flex items-center space-x-4">
          <button
            onClick={() => navigate('/')}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="h-5 w-5 text-gray-600" />
          </button>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Notifications</h1>
            <p className="text-gray-600 mt-1">Error loading notifications</p>
          </div>
        </div>
        <div className="card">
          <div className="text-center py-8">
            <AlertTriangle className="h-12 w-12 mx-auto mb-4 text-red-500 opacity-50" />
            <p className="text-red-600 mb-4">{error}</p>
            <button
              onClick={fetchNotifications}
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

  if (selectedNotification) {
    return (
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center space-x-4">
          <button
            onClick={() => setSelectedNotification(null)}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="h-5 w-5 text-gray-600" />
          </button>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">
              Notification Details
            </h1>
            <p className="text-gray-600 mt-1">{selectedNotification.title}</p>
          </div>
        </div>

        {/* Notification Detail */}
        <div className="card">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center space-x-3">
              {getNotificationIcon(selectedNotification.type)}
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  {selectedNotification.title}
                </h2>
                <p className="text-sm text-gray-600">
                  {selectedNotification.summary}
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-3">
              <span
                className={`px-3 py-1 rounded-full text-sm font-medium ${
                  selectedNotification.resolved
                    ? 'bg-green-100 text-green-800'
                    : getNotificationBgColor(selectedNotification.type)
                        .replace('bg-', 'bg-')
                        .replace('border-', 'text-')
                        .replace('-50', '-800')
                        .replace('-200', '')
                }`}
              >
                {selectedNotification.resolved
                  ? 'Resolved'
                  : getNotificationTypeLabel(selectedNotification.type)}
              </span>
              {!selectedNotification.resolved ? (
                <button
                  onClick={() =>
                    handleResolveNotification(selectedNotification.id)
                  }
                  className="btn-primary flex items-center space-x-2"
                >
                  <CheckCircle className="h-4 w-4" />
                  <span>Mark as Resolved</span>
                </button>
              ) : (
                <button
                  onClick={() =>
                    handleClearNotification(selectedNotification.id)
                  }
                  className="bg-red-600 hover:bg-red-700 text-white font-medium px-4 py-2 rounded-lg transition-colors duration-200 flex items-center space-x-2"
                >
                  <X className="h-4 w-4" />
                  <span>Clear</span>
                </button>
              )}
            </div>
          </div>

          {/* Customer Info */}
          <div className="bg-gray-50 rounded-lg p-4 mb-6">
            <h3 className="font-medium text-gray-900 mb-2">
              Customer Information
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
              <div>
                <span className="font-medium text-gray-700">Name:</span>
                <span className="ml-2 text-gray-600">
                  {selectedNotification.customer_name || 'Unknown'}
                </span>
              </div>
              <div>
                <span className="font-medium text-gray-700">Phone:</span>
                <span className="ml-2 text-gray-600">
                  {selectedNotification.phone}
                </span>
              </div>
              <div>
                <span className="font-medium text-gray-700">Time:</span>
                <span className="ml-2 text-gray-600">
                  {formatTimestamp(selectedNotification.created_at)}
                </span>
              </div>
            </div>
          </div>

          {loadingTranscript ? (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="h-8 w-8 animate-spin text-primary-600" />
            </div>
          ) : notificationTranscript &&
            notificationTranscript.type === 'voice' ? (
            <div className="mt-6">
              {/* AI Summary */}
              {notificationTranscript.summary && (
                <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                  <div className="flex items-center space-x-2 mb-2">
                    <Sparkles className="h-4 w-4 text-blue-600" />
                    <h4 className="font-medium text-blue-900">AI Summary</h4>
                  </div>
                  <p className="text-sm text-blue-800">
                    {notificationTranscript.summary}
                  </p>
                </div>
              )}

              <h3 className="font-medium text-gray-900 mb-2">
                Call Transcript
              </h3>
              {notificationTranscript.transcript.length > 0 ? (
                <div className="space-y-3">
                  {notificationTranscript.transcript.map((message, idx) => (
                    <div
                      key={idx}
                      className={`flex ${
                        ['user', 'customer'].includes(message.speaker)
                          ? 'justify-start'
                          : 'justify-end'
                      }`}
                    >
                      <div
                        className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
                          ['user', 'customer'].includes(message.speaker)
                            ? 'bg-gray-100 text-gray-900'
                            : 'bg-primary-600 text-white'
                        }`}
                      >
                        <p className="text-sm italic">"{message.text}"</p>
                        <div className="flex items-center justify-end mt-1 space-x-1">
                          <Clock className="h-3 w-3 opacity-70" />
                          <p className="text-xs opacity-70">
                            {formatSmartTimestamp(message.time)}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-gray-500">
                  No transcript available for this call.
                </div>
              )}
            </div>
          ) : notificationTranscript &&
            notificationTranscript.type === 'sms' ? (
            <div className="mt-6">
              {/* AI Summary */}
              {notificationTranscript.summary && (
                <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                  <div className="flex items-center space-x-2 mb-2">
                    <Sparkles className="h-4 w-4 text-blue-600" />
                    <h4 className="font-medium text-blue-900">AI Summary</h4>
                  </div>
                  <p className="text-sm text-blue-800">
                    {notificationTranscript.summary}
                  </p>
                </div>
              )}

              <h3 className="font-medium text-gray-900 mb-2">
                Message Conversation
              </h3>
              {notificationTranscript.messages.length > 0 ? (
                <div className="space-y-3">
                  {notificationTranscript.messages.map((msg, idx) => (
                    <div
                      key={idx}
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
                <div className="text-gray-500">
                  No messages available for this conversation.
                </div>
              )}
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <button
            onClick={() => navigate('/')}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="h-5 w-5 text-gray-600" />
          </button>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Notifications</h1>
            <p className="text-gray-600 mt-1">
              AI-generated alerts requiring attention
            </p>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={fetchNotifications}
            className="btn-secondary flex items-center space-x-1"
          >
            <RefreshCw className="h-4 w-4" />
            <span>Reload</span>
          </button>
          <a
            href="https://docs.google.com/spreadsheets/d/1qiGx2czQpe-DejlGBRAfRXp5g9QzCPRuLr9E7GTg0g8/edit?usp=sharing"
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

      {/* Notifications List */}
      {sortedNotifications.length === 0 ? (
        <div className="card">
          <div className="text-center py-8 text-gray-500">
            <AlertCircle className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>No notifications at this time</p>
            <p className="text-sm mt-1">All caught up! 🎉</p>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {sortedNotifications.map((notification) => (
            <div
              key={notification.id}
              onClick={() => handleNotificationSelect(notification)}
              className={`card cursor-pointer hover:shadow-md transition-all duration-200 border-l-4 ${
                notification.resolved ? 'opacity-60' : ''
              } ${getNotificationBgColor(notification.type)}`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-4 flex-1">
                  <div className="flex items-center space-x-2">
                    {getNotificationIcon(notification.type)}
                    <span className="text-sm font-medium text-gray-700">
                      {getNotificationTypeLabel(notification.type)}
                    </span>
                  </div>

                  <div className="flex-1">
                    <h3 className="font-semibold text-gray-900 mb-1">
                      {notification.title}
                    </h3>
                    <p className="text-sm text-gray-600 mb-2">
                      {notification.summary}
                    </p>
                    <div className="flex items-center space-x-4 text-xs text-gray-500">
                      <div className="flex items-center space-x-1">
                        <Phone className="h-3 w-3" />
                        <span>{notification.phone}</span>
                      </div>
                      <div className="flex items-center space-x-1">
                        <Clock className="h-3 w-3" />
                        <span>{formatTimestamp(notification.created_at)}</span>
                      </div>
                      <div className="flex items-center space-x-1">
                        {notification.conversation_type === 'voice' ? (
                          <Phone className="h-3 w-3" />
                        ) : (
                          <MessageSquare className="h-3 w-3" />
                        )}
                        <span>
                          {notification.conversation_type === 'voice'
                            ? 'Voice Call'
                            : 'SMS'}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex items-center space-x-3">
                  {notification.resolved && (
                    <span className="status-badge status-active">Resolved</span>
                  )}
                  {!notification.resolved ? (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleResolveNotification(notification.id);
                      }}
                      className="btn-secondary text-xs"
                    >
                      Mark Resolved
                    </button>
                  ) : (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleClearNotification(notification.id);
                      }}
                      className="bg-red-600 hover:bg-red-700 text-white font-medium px-3 py-1 rounded text-xs transition-colors duration-200 flex items-center space-x-1"
                    >
                      <X className="h-3 w-3" />
                      <span>Clear</span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Notifications;
