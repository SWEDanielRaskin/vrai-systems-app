import React from 'react'
import { AlertTriangle, AlertCircle, Star, Clock, Phone, MessageSquare, ArrowRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

const NotificationPreview = ({ notifications = [], onResolveNotification, onClearNotification }) => {
  const navigate = useNavigate()

  const getNotificationIcon = (type) => {
    switch (type) {
      case 'critical':
        return <AlertTriangle className="h-4 w-4 text-red-600" />
      case 'urgent':
        return <AlertCircle className="h-4 w-4 text-orange-600" />
      case 'interest':
        return <Star className="h-4 w-4 text-yellow-600" />
      default:
        return <AlertCircle className="h-4 w-4 text-gray-600" />
    }
  }

  const getNotificationTypeLabel = (type) => {
    switch (type) {
      case 'critical':
        return 'Critical'
      case 'urgent':
        return 'Urgent Action'
      case 'interest':
        return 'Interest'
      default:
        return 'Unknown'
    }
  }

  const getNotificationBgColor = (type) => {
    switch (type) {
      case 'critical':
        return 'bg-red-50 border-red-200'
      case 'urgent':
        return 'bg-orange-50 border-orange-200'
      case 'interest':
        return 'bg-yellow-50 border-yellow-200'
      default:
        return 'bg-gray-50 border-gray-200'
    }
  }

  // Format timestamp for display
  const formatTimestamp = (timestamp) => {
    try {
      const date = new Date(timestamp)
      const now = new Date()
      const diffMs = now - date
      const diffMinutes = Math.floor(diffMs / 60000)
      const diffHours = Math.floor(diffMs / 3600000)
      const diffDays = Math.floor(diffMs / 86400000)
      
      if (diffMinutes < 1) return 'Just now'
      if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes > 1 ? 's' : ''} ago`
      if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`
      if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`
      
      return date.toLocaleDateString()
    } catch (error) {
      return timestamp // Return original if parsing fails
    }
  }

  // Sort notifications by priority and take top 4
  const sortedNotifications = [...notifications]
    .filter(n => !n.resolved)
    .sort((a, b) => {
      const typeOrder = { critical: 0, urgent: 1, interest: 2 }
      return typeOrder[a.type] - typeOrder[b.type]
    })
    .slice(0, 4)

  if (sortedNotifications.length === 0) {
    return (
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Notifications</h2>
          <button
            onClick={() => navigate('/notifications')}
            className="text-sm text-primary-600 hover:text-primary-700 flex items-center space-x-1"
          >
            <span>View All</span>
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
        <div className="text-center py-8 text-gray-500">
          <AlertCircle className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>No notifications at this time</p>
          <p className="text-sm mt-1">All caught up! 🎉</p>
        </div>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-gray-900">Notifications</h2>
        <button
          onClick={() => navigate('/notifications')}
          className="text-sm text-primary-600 hover:text-primary-700 flex items-center space-x-1"
        >
          <span>View All ({notifications.filter(n => !n.resolved).length})</span>
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {sortedNotifications.map((notification) => (
          <div
            key={notification.id}
            onClick={() => navigate('/notifications')}
            className={`p-4 rounded-lg cursor-pointer hover:shadow-md transition-all duration-200 border ${getNotificationBgColor(notification.type)}`}
          >
            {/* Notification Type Header */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center space-x-2">
                {getNotificationIcon(notification.type)}
                <span className="text-sm font-medium text-gray-700">
                  {getNotificationTypeLabel(notification.type)}
                </span>
              </div>
              
              {/* Removed action buttons - users must go to notifications page */}
              <ArrowRight className="h-4 w-4 text-gray-400" />
            </div>

            {/* Summary */}
            <p className="text-sm text-gray-900 font-medium mb-2 line-clamp-2">
              {notification.summary}
            </p>

            {/* Details */}
            <div className="flex items-center justify-between text-xs text-gray-500">
              <div className="flex items-center space-x-3">
                <div className="flex items-center space-x-1">
                  <Phone className="h-3 w-3" />
                  <span>{notification.phone}</span>
                </div>
                <div className="flex items-center space-x-1">
                  {notification.conversation_type === 'voice' ? (
                    <Phone className="h-3 w-3" />
                  ) : (
                    <MessageSquare className="h-3 w-3" />
                  )}
                  <span>{notification.conversation_type === 'voice' ? 'Call' : 'SMS'}</span>
                </div>
              </div>
              <div className="flex items-center space-x-1">
                <Clock className="h-3 w-3" />
                <span>{formatTimestamp(notification.created_at)}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default NotificationPreview