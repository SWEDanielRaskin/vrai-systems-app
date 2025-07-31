import axios from 'axios';
import { backendUrl } from '../config';

// Use environment variable for API URL, fallback to localhost for development
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || backendUrl;

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
});

// System Health
export const getSystemHealth = async () => {
  try {
    const response = await api.get('/health');
    return response.data;
  } catch (error) {
    console.error('API Error - getSystemHealth:', error);
    // Return mock data for development
    return {
      status: 'healthy',
      business_hours: false,
      mode: 'after_hours',
      active_calls_tracked: 0,
      timestamp: new Date().toISOString(),
    };
  }
};

// Settings API
export const getSetting = async (key) => {
  try {
    const response = await api.get(`/api/settings/${key}`);
    return response.data;
  } catch (error) {
    console.error(`API Error - getSetting(${key}):`, error);
    throw error;
  }
};

export const updateSetting = async (key, value) => {
  try {
    const response = await api.put(`/api/settings/${key}`, { value });
    return response.data;
  } catch (error) {
    console.error(`API Error - updateSetting(${key}):`, error);
    throw error;
  }
};

// Staff API
export const getStaff = async () => {
  try {
    const response = await api.get('/api/settings/staff');
    return response.data;
  } catch (error) {
    console.error('API Error - getStaff:', error);
    throw error;
  }
};

export const updateStaff = async (staff) => {
  try {
    // Convert the staff array to the format expected by the backend
    const staffData = staff.map((member) => ({
      id: member.id,
      name: member.name,
      position: member.position || 'Specialist',
      active: member.active !== false,
    }));
    const response = await api.put('/api/settings/staff', { staff: staffData });
    return response.data;
  } catch (error) {
    console.error('API Error - updateStaff:', error);
    throw error;
  }
};

// Knowledge Base API
export const getKnowledgeBase = async () => {
  try {
    const response = await api.get('/api/knowledge_base');
    return response.data;
  } catch (error) {
    console.error('API Error - getKnowledgeBase:', error);
    throw error;
  }
};

export const addKnowledgeBaseLink = async (urls, description) => {
  try {
    const response = await api.post('/api/knowledge_base/add_link', {
      urls,
      description,
    });
    return response.data;
  } catch (error) {
    console.error('API Error - addKnowledgeBaseLink:', error);
    throw error;
  }
};

export const uploadKnowledgeBaseDocument = async (file) => {
  try {
    const formData = new FormData();
    formData.append('file', file);

    const response = await api.post('/api/knowledge_base/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  } catch (error) {
    console.error('API Error - uploadKnowledgeBaseDocument:', error);
    throw error;
  }
};

export const removeKnowledgeBaseItem = async (itemId) => {
  try {
    const response = await api.delete(`/api/knowledge_base/${itemId}`);
    return response.data;
  } catch (error) {
    console.error('API Error - removeKnowledgeBaseItem:', error);
    throw error;
  }
};

// Dashboard Data API - ENHANCED WITH REAL DATA
export const getRecentCalls = async () => {
  try {
    const response = await api.get('/api/calls/recent');
    return response.data;
  } catch (error) {
    console.error('API Error - getRecentCalls:', error);
    // Return fallback data
    return {
      count: 0,
      answered: 0,
      missed: 0,
      calls: [], // NEW: Include empty calls array
      recent_calls: [],
      summary: 'No calls today',
    };
  }
};

export const getCallDetails = async (callControlId) => {
  try {
    const response = await api.get(`/api/calls/${callControlId}`);
    return response.data;
  } catch (error) {
    console.error('API Error - getCallDetails:', error);
    throw error;
  }
};

export const getRecentMessages = async () => {
  try {
    const response = await api.get('/api/messages/recent');
    return response.data;
  } catch (error) {
    console.error('API Error - getRecentMessages:', error);
    // Return fallback data
    return {
      count: 0,
      total_messages: 0,
      conversations: [], // NEW: Include empty conversations array
      recent_conversations: [],
      summary: 'No messages today',
    };
  }
};

export const getConversationDetails = async (conversationId) => {
  try {
    const response = await api.get(`/api/messages/${conversationId}`);
    return response.data;
  } catch (error) {
    console.error('API Error - getConversationDetails:', error);
    throw error;
  }
};

export const getNewAppointmentsToday = async () => {
  try {
    const response = await api.get('/api/appointments/new_today');
    return response.data;
  } catch (error) {
    console.error('API Error - getNewAppointmentsToday:', error);
    // Return fallback data
    return {
      count: 0,
      by_service: {},
      recent_appointments: [],
      summary: 'No new appointments today',
    };
  }
};

// Manual SMS sending
export const sendManualSMS = async (
  toNumber,
  message,
  fromNumber = '+18773900002'
) => {
  try {
    const response = await api.post('/send-sms', {
      to_number: toNumber,
      message: message,
      from_number: fromNumber,
    });
    return response.data;
  } catch (error) {
    console.error('API Error - sendManualSMS:', error);
    throw error;
  }
};

// Analytics API
export const getWeeklySummary = async () => {
  try {
    const response = await api.get('/api/analytics/weekly_summary');
    return response.data;
  } catch (error) {
    console.error('API Error - getWeeklySummary:', error);
    throw error;
  }
};

// Notifications API
export const getNotifications = async () => {
  try {
    const response = await api.get('/api/notifications');
    return response.data;
  } catch (error) {
    console.error('API Error - getNotifications:', error);
    throw error;
  }
};

export const resolveNotification = async (notificationId) => {
  try {
    const response = await api.post(
      `/api/notifications/${notificationId}/resolve`
    );
    return response.data;
  } catch (error) {
    console.error('API Error - resolveNotification:', error);
    throw error;
  }
};

export const deleteNotification = async (notificationId) => {
  try {
    const response = await api.delete(`/api/notifications/${notificationId}`);
    return response.data;
  } catch (error) {
    console.error('API Error - deleteNotification:', error);
    throw error;
  }
};

// Test SMS
export const testSMS = async () => {
  try {
    const response = await api.get('/test-sms');
    return response.data;
  } catch (error) {
    console.error('API Error - testSMS:', error);
    throw error;
  }
};

// Test Scheduler
export const testScheduler = async () => {
  try {
    const response = await api.get('/test-scheduler');
    return response.data;
  } catch (error) {
    console.error('API Error - testScheduler:', error);
    throw error;
  }
};

// Scheduled Messages
export const getScheduledMessages = async (appointmentId = null) => {
  try {
    const url = appointmentId
      ? `/scheduled-messages?appointment_id=${appointmentId}`
      : '/scheduled-messages';
    const response = await api.get(url);
    return response.data;
  } catch (error) {
    console.error('API Error - getScheduledMessages:', error);
    throw error;
  }
};

// Cancel Messages
export const cancelMessages = async (appointmentId) => {
  try {
    const response = await api.post(`/cancel-messages/${appointmentId}`);
    return response.data;
  } catch (error) {
    console.error('API Error - cancelMessages:', error);
    throw error;
  }
};

// Reschedule Messages
export const rescheduleMessages = async (appointmentId) => {
  try {
    const response = await api.post(`/reschedule-messages/${appointmentId}`);
    return response.data;
  } catch (error) {
    console.error('API Error - rescheduleMessages:', error);
    throw error;
  }
};

// Clear All Messages
export const clearAllMessages = async () => {
  try {
    const response = await api.post('/clear-all-messages');
    return response.data;
  } catch (error) {
    console.error('API Error - clearAllMessages:', error);
    throw error;
  }
};

export const archiveDaily = async () => {
  try {
    const response = await api.post('/archive/daily');
    return response.data;
  } catch (error) {
    console.error('API Error - archiveDaily:', error);
    throw error;
  }
};

export const archiveWeekly = async () => {
  try {
    const response = await api.post('/archive/weekly');
    return response.data;
  } catch (error) {
    console.error('API Error - archiveWeekly:', error);
    throw error;
  }
};

// ==================== CUSTOMER MANAGEMENT API ====================

// Get list of customers
export const getCustomers = async (params = {}) => {
  try {
    const response = await api.get('/api/customers', { params });
    return response.data;
  } catch (error) {
    console.error('API Error - getCustomers:', error);
    throw error;
  }
};

// Get detailed customer information
export const getCustomerDetail = async (phoneNumber) => {
  try {
    const response = await api.get(`/api/customers/${encodeURIComponent(phoneNumber)}`);
    return response.data;
  } catch (error) {
    console.error('API Error - getCustomerDetail:', error);
    throw error;
  }
};

// Create new customer
export const createCustomer = async (customerData) => {
  try {
    const response = await api.post('/api/customers', customerData);
    return response.data;
  } catch (error) {
    console.error('API Error - createCustomer:', error);
    throw error;
  }
};

// Update customer
export const updateCustomer = async (phoneNumber, customerData) => {
  try {
    const response = await api.put(`/api/customers/${encodeURIComponent(phoneNumber)}`, customerData);
    return response.data;
  } catch (error) {
    console.error('API Error - updateCustomer:', error);
    throw error;
  }
};

// Delete customer
export const deleteCustomer = async (phoneNumber) => {
  try {
    const response = await api.delete(`/api/customers/${encodeURIComponent(phoneNumber)}`);
    return response.data;
  } catch (error) {
    console.error('API Error - deleteCustomer:', error);
    throw error;
  }
};

// Upload customer profile picture
export const uploadCustomerProfilePicture = async (phoneNumber, file) => {
  try {
    const formData = new FormData();
    formData.append('profile_picture', file);
    
    const response = await api.post(
      `/api/customers/${encodeURIComponent(phoneNumber)}/profile-picture`, 
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response.data;
  } catch (error) {
    console.error('API Error - uploadCustomerProfilePicture:', error);
    throw error;
  }
};

// Update appointment notes
export const updateAppointmentNotes = async (appointmentId, notes) => {
  try {
    const response = await api.put(`/api/appointments/${appointmentId}/notes`, { notes });
    return response.data;
  } catch (error) {
    console.error('API Error - updateAppointmentNotes:', error);
    throw error;
  }
};

// ==================== MESSAGE TEMPLATES API ====================

// Get all message templates
export const getMessageTemplates = async () => {
  try {
    const response = await api.get('/api/message-templates');
    return response.data;
  } catch (error) {
    console.error('API Error - getMessageTemplates:', error);
    throw error;
  }
};

// Get a specific message template
export const getMessageTemplate = async (templateType) => {
  try {
    const response = await api.get(`/api/message-templates/${templateType}`);
    return response.data;
  } catch (error) {
    console.error('API Error - getMessageTemplate:', error);
    throw error;
  }
};

// Update a message template
export const updateMessageTemplate = async (templateType, templateData) => {
  try {
    const response = await api.put(`/api/message-templates/${templateType}`, templateData);
    return response.data;
  } catch (error) {
    console.error('API Error - updateMessageTemplate:', error);
    throw error;
  }
};

// Initialize default message templates
export const initializeMessageTemplates = async () => {
  try {
    const response = await api.post('/api/message-templates/initialize');
    return response.data;
  } catch (error) {
    console.error('API Error - initializeMessageTemplates:', error);
    throw error;
  }
};

export default api;
