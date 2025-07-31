import React, { useState, useEffect, useRef } from 'react';
import {
  ArrowLeft,
  Phone,
  Clock,
  User,
  Sparkles,
  RefreshCw,
  ExternalLink,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { getRecentCalls, getCallDetails } from '../services/api';

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

const VoiceCalls = () => {
  const navigate = useNavigate();
  const [selectedCall, setSelectedCall] = useState(null);
  const [voiceCalls, setVoiceCalls] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [error, setError] = useState(null);
  const eventSourceRef = useRef(null);

  // Lock body scroll for this page
  useBodyScrollLock();

  useEffect(() => {
    fetchVoiceCalls();
  }, []);

  const fetchVoiceCalls = async (backgroundUpdate = false) => {
    try {
      setLoading(true);
      setError(null);
      const response = await getRecentCalls();

      // Use the calls array from the enhanced API response
      setVoiceCalls(response.calls || []);

      console.log('Voice calls loaded:', response.calls?.length || 0);
    } catch (error) {
      console.error('Failed to fetch voice calls:', error);
      setError('Failed to load voice calls');
      setVoiceCalls([]);
    } finally {
      setLoading(false);
    }
  };

  // SSE: Listen for call_finished events
  useEffect(() => {
    if (!eventSourceRef.current) {
      const es = new window.EventSource('/events');
      eventSourceRef.current = es;
      es.onopen = () => {
        console.log('[SSE] VoiceCalls: Connection opened');
      };
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'call_finished') {
            console.log(
              '[SSE] VoiceCalls: call_finished event received:',
              data
            );
            fetchVoiceCalls(true); // background update, no spinner
            // If the selected call is the one that just finished, refetch its details
            if (selectedCall && selectedCall.id === data.callId) {
              handleCallSelect({ id: data.callId });
            }
          }
        } catch (e) {
          // Ignore parse errors
        }
      };
      es.onerror = (err) => {
        console.log('[SSE] VoiceCalls: Connection error:', err);
      };
    }
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
        console.log('[SSE] VoiceCalls: Connection closed');
      }
    };
  }, [selectedCall]);

  const handleCallSelect = async (call) => {
    if (selectedCall?.id === call.id) {
      return; // Already selected
    }

    try {
      setLoadingDetails(true);
      setSelectedCall(null); // Clear current selection

      // Fetch detailed call information including transcript
      const callDetails = await getCallDetails(call.id);
      setSelectedCall(callDetails);

      console.log('Call details loaded:', callDetails);
    } catch (error) {
      console.error('Failed to fetch call details:', error);
      // Still set the basic call info even if details fail
      setSelectedCall(call);
    } finally {
      setLoadingDetails(false);
    }
  };

  const getCallTypeIcon = (type) => {
    switch (type) {
      case 'answered_by_ai':
        return <Phone className="h-4 w-4 text-green-600" />;
      case 'missed_call':
        return <Phone className="h-4 w-4 text-red-600" />;
      case 'transferred_to_front_desk':
        return <Phone className="h-4 w-4 text-blue-600" />;
      default:
        return <Phone className="h-4 w-4 text-gray-600" />;
    }
  };

  const getCallTypeBadge = (type) => {
    switch (type) {
      case 'answered_by_ai':
        return <span className="status-badge status-active">AI Answered</span>;
      case 'missed_call':
        return (
          <span className="status-badge bg-red-100 text-red-800">
            Missed Call
          </span>
        );
      case 'ongoing_call':
        return (
          <span className="status-badge bg-orange-100 text-orange-800">
            Ongoing Call
          </span>
        );
      case 'transferred_to_front_desk':
        return (
          <span className="status-badge bg-blue-100 text-blue-800">
            Transferred to Front Desk
          </span>
        );
      default:
        return <span className="status-badge status-inactive">Unknown</span>;
    }
  };

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
            <h1 className="text-3xl font-bold text-gray-900">
              Voice Calls Today
            </h1>
            <p className="text-gray-600 mt-1">
              Loading voice call conversations...
            </p>
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
            <h1 className="text-3xl font-bold text-gray-900">
              Voice Calls Today
            </h1>
            <p className="text-gray-600 mt-1">Error loading voice calls</p>
          </div>
        </div>
        <div className="card">
          <div className="text-center py-8">
            <Phone className="h-12 w-12 mx-auto mb-4 text-red-500 opacity-50" />
            <p className="text-red-600 mb-4">{error}</p>
            <button
              onClick={fetchVoiceCalls}
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
      <div className="shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => navigate('/')}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <ArrowLeft className="h-5 w-5 text-gray-600" />
            </button>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">
                Voice Calls Today
              </h1>
              <p className="text-gray-600 mt-1">
                All voice call conversations from today
              </p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={fetchVoiceCalls}
              className="btn-secondary flex items-center space-x-1"
            >
              <RefreshCw className="h-4 w-4" />
              <span>Reload</span>
            </button>
            <a
              href="https://docs.google.com/spreadsheets/d/1yhI8qk__zwjSukjEa2jSo2vb8rYxpzAbiRWOUMUif00/edit?usp=sharing"
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
      </div>
      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[calc(100vh-120px)] min-h-0">
        {/* Calls List */}
        <div className="card flex flex-col h-full min-h-0 overflow-y-auto">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Today's Calls ({voiceCalls.length})
          </h2>
          <div className="flex-1 min-h-0 overflow-y-auto">
            {voiceCalls.length === 0 ? (
              <div className="flex items-center justify-center h-full text-gray-500">
                <div className="text-center">
                  <Phone className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>No voice calls today</p>
                  <p className="text-sm mt-1">
                    Calls will appear here when customers call
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-3 pr-1">
                {voiceCalls.map((call) => (
                  <div
                    key={call.id}
                    onClick={() => handleCallSelect(call)}
                    className={`p-4 rounded-lg cursor-pointer transition-colors border ${
                      selectedCall?.id === call.id
                        ? 'bg-primary-50 border-primary-200'
                        : 'hover:bg-gray-50 border-gray-200'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center space-x-2">
                        {getCallTypeIcon(call.type)}
                        <p className="font-medium text-gray-900">
                          {call.customerName || 'Unknown Caller'}
                        </p>
                      </div>
                      <p className="text-xs text-gray-500">{call.timestamp}</p>
                    </div>
                    <p className="text-sm text-gray-600 mb-2">{call.phone}</p>
                    <div className="flex items-center justify-between">
                      {getCallTypeBadge(call.type)}
                      <div className="flex items-center space-x-1 text-xs text-gray-500">
                        <Clock className="h-3 w-3" />
                        <span>{call.duration}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        {/* Call Details/Transcript */}
        <div className="lg:col-span-2 card flex flex-col h-full min-h-0 overflow-y-auto">
          {loadingDetails ? (
            <div className="flex items-center justify-center h-full">
              <RefreshCw className="h-8 w-8 animate-spin text-primary-600" />
            </div>
          ) : selectedCall ? (
            <>
              {/* Call Header */}
              <div className="border-b border-gray-200 pb-4 mb-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center space-x-3">
                    <div className="bg-primary-100 rounded-full p-2">
                      <User className="h-5 w-5 text-primary-600" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-gray-900">
                        {selectedCall.customerName || 'Unknown Caller'}
                      </h3>
                      <p className="text-sm text-gray-500">
                        {selectedCall.phone}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-sm text-gray-500">
                      {selectedCall.timestamp}
                    </p>
                    <div className="flex items-center space-x-1 text-xs text-gray-500 mt-1">
                      <Clock className="h-3 w-3" />
                      <span>{selectedCall.duration}</span>
                    </div>
                  </div>
                </div>
                {getCallTypeBadge(selectedCall.type)}
              </div>
              {/* AI Summary */}
              {selectedCall.type === 'answered_by_ai' && (
                <div className="bg-blue-50 rounded-lg p-4 mb-4">
                  <div className="flex items-center space-x-2 mb-2">
                    <Sparkles className="h-4 w-4 text-blue-600" />
                    <h4 className="font-medium text-blue-900">AI Summary</h4>
                  </div>
                  <p className="text-sm text-blue-800">
                    {selectedCall.summary ||
                      'AI summary will be generated automatically for completed calls'}
                  </p>
                </div>
              )}
              {/* Ongoing Call Message */}
              {selectedCall.type === 'ongoing_call' ? (
                <div className="flex-1 flex items-center justify-center text-gray-500 overflow-y-auto">
                  <div className="text-center">
                    <Phone className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p className="font-semibold">
                      This call is currently ongoing.
                    </p>
                    <p className="text-sm mt-2">
                      The transcript will be available after the call is
                      finished.
                    </p>
                  </div>
                </div>
              ) : selectedCall.transcript &&
                selectedCall.transcript.length > 0 ? (
                <div className="flex-1">
                  <h4 className="font-medium text-gray-900 mb-3">
                    Call Transcript
                  </h4>
                  <div className="space-y-3">
                    {selectedCall.transcript.map((message, index) => (
                      <div
                        key={index}
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
                            <p className="text-xs opacity-70">{message.time}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="flex-1 flex items-center justify-center text-gray-500">
                  <div className="text-center">
                    <Phone className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p>
                      {selectedCall.type === 'missed_call'
                        ? 'No transcript available for missed calls'
                        : selectedCall.type === 'transferred_to_front_desk'
                        ? 'This call was transferred to the front desk'
                        : 'Transcript will appear here for completed calls'}
                    </p>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-500">
              <div className="text-center">
                <Phone className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>Select a call to view details and transcript</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default VoiceCalls;
