import React, { useState, useEffect, useRef } from 'react';
import {
  Phone,
  MessageSquare,
  RefreshCw,
  ArrowRight,
  Clock,
  Calendar,
  Settings,
  Sparkles,
  Users,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import AppleToggle from '../components/AppleToggle';
import NotificationPreview from '../components/NotificationPreview';
import {
  getSystemHealth,
  getSetting,
  updateSetting,
  getRecentCalls,
  getRecentMessages,
  getNewAppointmentsToday,
  getNotifications,
  resolveNotification,
  deleteNotification,
  getCustomers,
} from '../services/api';

const Dashboard = () => {
  const navigate = useNavigate();
  const [systemHealth, setSystemHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [overrideMode, setOverrideMode] = useState('actual');
  const [isToggleLocked, setIsToggleLocked] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null); // Track last update time

  // Dashboard data
  const [callsData, setCallsData] = useState({ count: 0 });
  const [messagesData, setMessagesData] = useState({ count: 0 });
  const [appointmentsData, setAppointmentsData] = useState({ count: 0 });
  const [customersData, setCustomersData] = useState({ count: 0 });

  // UPDATED: Real notifications data from backend
  const [notifications, setNotifications] = useState([]);

  const overrideOptions = [
    {
      value: 'business',
      label: 'Business Hours',
      description:
        'SMS assistant and voice calls off during hours (Overridden)',
    },
    {
      value: 'actual',
      label: 'Actual Time',
      description:
        'SMS assistant and voice calls off during hours, Voice assistant active for off hours',
    },
    {
      value: 'after_hours',
      label: 'After Hours',
      description: 'Voice assistant active for off hours (Overridden)',
    },
  ];

  useEffect(() => {
    fetchAllData();

    // SSE: Listen for backend events and update dashboard gracefully
    const es = new window.EventSource('/events');
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case 'mode_changed':
          case 'call_finished':
          case 'new_call':
          case 'new_message':
          case 'appointment_created':
          case 'notification_created':
          case 'customer_created':
          case 'customer_deleted':
            fetchAllData(false);
            break;
          default:
            break;
        }
      } catch (e) {
        // Ignore parse errors
      }
    };
    es.onerror = (err) => {
      // Optionally handle errors
    };
    return () => {
      es.close();
    };
  }, []);

  const fetchAllData = async (showLoading = true) => {
    try {
      if (showLoading) {
        setLoading(true);
      }

      // Fetch system health
      const health = await getSystemHealth();
      setSystemHealth(health);

      // Set override mode based on current system state
      if (health.override) {
        if (health.override === 'business') {
          setOverrideMode('business');
        } else if (health.override === 'after_hours') {
          setOverrideMode('after_hours');
        } else {
          setOverrideMode('actual');
        }
      } else {
        setOverrideMode('actual');
      }

      // Fetch dashboard data
      try {
        const [calls, messages, appointments, notificationsData, customersResponse] =
          await Promise.all([
            getRecentCalls(),
            getRecentMessages(),
            getNewAppointmentsToday(),
            getNotifications(), // NEW: Fetch real notifications
            getCustomers({ limit: 1 }), // Fetch customers to get total count
          ]);

        setCallsData(calls);
        setMessagesData(messages);
        setAppointmentsData(appointments);
        setNotifications(notificationsData.notifications || []); // NEW: Set real notifications
        setCustomersData({ count: customersResponse.total || 0 }); // NEW: Set customer count
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
        // Keep existing values if API calls fail during auto-refresh
      }

      // Update last updated timestamp
      setLastUpdated(new Date());
    } catch (error) {
      console.error('Failed to fetch system health:', error);
    } finally {
      if (showLoading) {
        setLoading(false);
      }
    }
  };

  const handleOverrideModeChange = async (newMode) => {
    // Only allow change if toggle is unlocked
    if (isToggleLocked) {
      return;
    }

    try {
      setOverrideMode(newMode);
      setIsToggleLocked(true); // Lock again after mode change

      // Update the backend setting
      await updateSetting(
        'business_hours_override',
        newMode === 'actual' ? '' : newMode
      );

      console.log('Override mode changed to:', newMode);

      // Refresh system health to reflect changes
      setTimeout(() => fetchAllData(false), 500); // Small delay to allow backend to update
    } catch (error) {
      console.error('Failed to update override mode:', error);
      // Revert the change if it failed
      setOverrideMode(overrideMode);
    }
  };

  const handleLockToggle = () => {
    setIsToggleLocked(!isToggleLocked);
  };

  const handleRefresh = async () => {
    await fetchAllData();
  };

  // UPDATED: Real notification handlers that call backend APIs
  const handleResolveNotification = async (notificationId) => {
    try {
      await resolveNotification(notificationId);
      // Update local state
      setNotifications((prev) =>
        prev.map((notification) =>
          notification.id === notificationId
            ? { ...notification, resolved: true }
            : notification
        )
      );
      console.log('Notification resolved:', notificationId);
    } catch (error) {
      console.error('Failed to resolve notification:', error);
    }
  };

  const handleClearNotification = async (notificationId) => {
    try {
      await deleteNotification(notificationId);
      // Update local state
      setNotifications((prev) =>
        prev.filter((notification) => notification.id !== notificationId)
      );
      console.log('Notification cleared:', notificationId);
    } catch (error) {
      console.error('Failed to clear notification:', error);
    }
  };

  const getCurrentModeInfo = () => {
    const currentOption = overrideOptions.find(
      (option) => option.value === overrideMode
    );
    const isBusinessHours =
      overrideMode === 'business' ||
      (overrideMode === 'actual' && systemHealth?.business_hours);

    return {
      title: isBusinessHours ? 'SMS Assistant' : 'Voice Assistant Active',
      description: currentOption?.description || 'Unknown mode',
      icon: isBusinessHours ? MessageSquare : Phone,
      color: isBusinessHours ? 'blue' : 'green',
    };
  };

  const isOverridden = () => {
    return overrideMode === 'business' || overrideMode === 'after_hours';
  };

  // Helper function to format last updated time
  const getLastUpdatedText = () => {
    if (!lastUpdated) return 'Never';

    const now = new Date();
    const diffMs = now - lastUpdated;
    const diffMinutes = Math.floor(diffMs / 60000);

    if (diffMinutes < 1) return 'Just now';
    if (diffMinutes === 1) return '1 minute ago';
    return `${diffMinutes} minutes ago`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-primary-600" />
      </div>
    );
  }

  const modeInfo = getCurrentModeInfo();

  return (
    <div className="space-y-8">
      {/* Header with Logo and Controls */}
      <div className="flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center space-x-3">
          <Sparkles className="h-10 w-10 text-primary-600" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Radiance MD</h1>
            <p className="text-sm text-gray-500">Med Spa Dashboard</p>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center space-x-4">
          <button
            onClick={() => navigate('/settings')}
            className="btn-secondary flex items-center space-x-2"
          >
            <Settings className="h-4 w-4" />
            <span>Settings</span>
          </button>
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="btn-secondary flex items-center space-x-2"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
          {/* FIXED: Enhanced auto-refresh indicator with 3-minute timing */}
          <div className="text-xs text-gray-500 flex items-center space-x-2 bg-gray-50 px-3 py-2 rounded-lg">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
            <div className="flex flex-col">
              <span className="font-medium">Auto-Updates</span>
              <span className="text-gray-400">Last updated: just now</span>
            </div>
          </div>
        </div>
      </div>

      {/* System Status - Simplified Inline Layout */}
      <div className="card">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-3">
            <Clock className="h-6 w-6 text-primary-600" />
            <h2 className="text-lg font-semibold text-gray-900">
              System Status
            </h2>
          </div>
          <div
            className={`status-badge ${
              systemHealth?.business_hours ? 'status-active' : 'status-warning'
            }`}
          >
            {systemHealth?.business_hours
              ? 'Business Hours - SMS Only'
              : 'After Hours - Voice AI'}
          </div>
        </div>

        {/* Inline Layout: Business Phone | Current Mode | Lock + Toggle */}
        <div className="flex items-center justify-between space-x-8">
          {/* Business Phone */}
          <div className="flex-1">
            <h3 className="text-sm font-medium text-gray-700 mb-2">
              Business Phone
            </h3>
            <p className="text-lg font-semibold text-gray-900">
              +1 (877) 390-0002
            </p>
          </div>

          {/* Current Mode */}
          <div className="flex-1">
            <div className="flex items-center space-x-2 mb-2">
              <h3 className="text-sm font-medium text-gray-700">
                Current Mode
              </h3>
              {isOverridden() && (
                <span className="text-xs text-orange-600 font-medium">
                  (Overridden)
                </span>
              )}
            </div>
            <div className="flex items-center space-x-2">
              <modeInfo.icon
                className={`h-5 w-5 ${
                  modeInfo.color === 'blue' ? 'text-blue-600' : 'text-green-600'
                }`}
              />
              <span className="text-lg font-semibold text-gray-900">
                {modeInfo.title}
              </span>
            </div>
          </div>

          {/* Lock + Apple Toggle */}
          <div className="flex-1 flex justify-end items-center space-x-3">
            <AppleToggle
              value={overrideMode}
              onChange={handleOverrideModeChange}
              options={overrideOptions}
              isLocked={isToggleLocked}
              onLockToggle={handleLockToggle}
            />
          </div>
        </div>
      </div>

      {/* Today's Activity - Three Item Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Voice Calls Today */}
        <div
          onClick={() => navigate('/voice-calls')}
          className="card hover:shadow-md transition-shadow cursor-pointer group"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="bg-green-100 rounded-full p-3">
                <Phone className="h-6 w-6 text-green-600" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900">
                  Voice Calls Today
                </h3>
                <p className="text-2xl font-bold text-gray-900 mt-1">
                  {callsData.count}
                </p>
                <p className="text-sm text-gray-600">
                  AI handled calls and missed calls
                </p>
              </div>
            </div>
            <ArrowRight className="h-5 w-5 text-gray-400 group-hover:text-gray-600 transition-colors" />
          </div>
        </div>

        {/* Messages Today */}
        <div
          onClick={() => navigate('/messages')}
          className="card hover:shadow-md transition-shadow cursor-pointer group"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="bg-blue-100 rounded-full p-3">
                <MessageSquare className="h-6 w-6 text-blue-600" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900">
                  Messages Today
                </h3>
                <p className="text-2xl font-bold text-gray-900 mt-1">
                  {messagesData.count}
                </p>
                <p className="text-sm text-gray-600">
                  SMS conversations with customers
                </p>
              </div>
            </div>
            <ArrowRight className="h-5 w-5 text-gray-400 group-hover:text-gray-600 transition-colors" />
          </div>
        </div>

        {/* Appointments Today */}
        <div
          onClick={() => navigate('/appointments')}
          className="card hover:shadow-md transition-shadow cursor-pointer group"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="bg-purple-100 rounded-full p-3">
                <Calendar className="h-6 w-6 text-purple-600" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900">
                  Appointments Today
                </h3>
                <p className="text-2xl font-bold text-gray-900 mt-1">
                  {appointmentsData.count}
                </p>
                <p className="text-sm text-gray-600">
                  New appointments created today
                </p>
              </div>
            </div>
            <ArrowRight className="h-5 w-5 text-gray-400 group-hover:text-gray-600 transition-colors" />
          </div>
        </div>


      </div>

      {/* Customer Database */}
      <div
        onClick={() => navigate('/customers')}
        className="card hover:shadow-md transition-shadow cursor-pointer group h-24"
      >
        <div className="flex items-center justify-between h-full">
          <div className="flex items-center space-x-4">
            <div className="bg-orange-100 rounded-full p-3">
              <Users className="h-6 w-6 text-orange-600" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-gray-900">
                Customer Database
              </h3>
              <p className="text-sm text-gray-600">
                Manage customer profiles & history
              </p>
            </div>
          </div>
          <div className="flex items-center space-x-4">
            <div className="text-right">
              <p className="text-2xl font-bold text-gray-900">
                {customersData.count}
              </p>
              <p className="text-sm text-gray-600">
                customers
              </p>
            </div>
            <ArrowRight className="h-5 w-5 text-gray-400 group-hover:text-gray-600 transition-colors" />
          </div>
        </div>
      </div>

      {/* Notifications Panel - UPDATED: Using real data and handlers */}
      <NotificationPreview
        notifications={notifications}
        onResolveNotification={handleResolveNotification}
        onClearNotification={handleClearNotification}
      />
    </div>
  );
};

export default Dashboard;
