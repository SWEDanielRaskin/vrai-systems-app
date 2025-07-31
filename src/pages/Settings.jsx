import React, { useState, useEffect } from 'react';
import {
  Settings as SettingsIcon,
  Clock,
  Users,
  BookOpen,
  Palette,
  Edit3,
  Check,
  X,
  Plus,
  Trash2,
  Upload,
  Link,
  FileText,
  ArrowLeft,
  Save,
  RefreshCw,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  getSystemHealth,
  getSetting,
  updateSetting,
  getStaff,
  updateStaff,
  getKnowledgeBase,
  addKnowledgeBaseLink,
  uploadKnowledgeBaseDocument,
  removeKnowledgeBaseItem,
} from '../services/api';
import ColorPicker from '../components/ColorPicker';
import AddLinkModal from '../components/AddLinkModal';
import axios from 'axios';
import ServicesManager from './ServicesManager';

const Settings = () => {
  const navigate = useNavigate();
  const [systemHealth, setSystemHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editingHours, setEditingHours] = useState(false);
  const [editingStaff, setEditingStaff] = useState(false);
  const [showColorPicker, setShowColorPicker] = useState(false);
  const [showAddLinkModal, setShowAddLinkModal] = useState(false);
  const [currentThemeColor, setCurrentThemeColor] = useState('#ec4899'); // Default pink
  const [archiveStatus, setArchiveStatus] = useState('');

  // Business Hours State - FIXED: Use ordered days
  const [businessHours, setBusinessHours] = useState({
    Monday: { start: '09:00', end: '16:00' },
    Tuesday: { start: '09:00', end: '16:00' },
    Wednesday: { start: '09:00', end: '16:00' },
    Thursday: { start: '09:00', end: '16:00' },
    Friday: { start: '09:00', end: '16:00' },
    Saturday: { start: '09:00', end: '15:00' },
    Sunday: { start: null, end: null },
  });

  // Store original hours for cancel functionality
  const [originalBusinessHours, setOriginalBusinessHours] = useState({});

  // Staff State
  const [staff, setStaff] = useState([]);
  const [originalStaff, setOriginalStaff] = useState([]);
  const [newStaffName, setNewStaffName] = useState('');
  const [newStaffPosition, setNewStaffPosition] = useState('Specialist');
  const [newStaffActive, setNewStaffActive] = useState(true);

  // Knowledge Base State
  const [knowledgeBase, setKnowledgeBase] = useState([]);

  // FIXED: Define day order for consistent display
  const dayOrder = [
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
    'Saturday',
    'Sunday',
  ];

  useEffect(() => {
    fetchAllData();
    // FIXED: Load and apply saved theme color on component mount
    const savedColor = localStorage.getItem('themeColor');
    if (savedColor) {
      setCurrentThemeColor(savedColor);
      applyThemeColor(savedColor);
    }
  }, []);

  const fetchAllData = async () => {
    try {
      setLoading(true);

      // Fetch system health
      const health = await getSystemHealth();
      setSystemHealth(health);

      // Fetch AI operating hours
      try {
        const hoursResponse = await getSetting('ai_operating_hours');
        if (hoursResponse.value) {
          setBusinessHours(hoursResponse.value);
        }
      } catch (error) {
        console.error('Failed to fetch AI operating hours:', error);
      }

      // Fetch staff
      try {
        const staffResponse = await getStaff();
        setStaff(staffResponse || []);
      } catch (error) {
        console.error('Failed to fetch staff:', error);
      }

      // Fetch knowledge base
      try {
        const kbResponse = await getKnowledgeBase();
        setKnowledgeBase(kbResponse.items || []);
      } catch (error) {
        console.error('Failed to fetch knowledge base:', error);
      }
    } catch (error) {
      console.error('Failed to fetch settings data:', error);
    } finally {
      setLoading(false);
    }
  };

  const applyThemeColor = (color) => {
    // Update CSS custom properties for the primary color
    const root = document.documentElement;

    // Convert hex to HSL for different shades
    const hex = color.replace('#', '');
    const r = parseInt(hex.substr(0, 2), 16);
    const g = parseInt(hex.substr(2, 2), 16);
    const b = parseInt(hex.substr(4, 2), 16);

    // Convert RGB to HSL
    const rNorm = r / 255;
    const gNorm = g / 255;
    const bNorm = b / 255;

    const max = Math.max(rNorm, gNorm, bNorm);
    const min = Math.min(rNorm, gNorm, bNorm);
    let h,
      s,
      l = (max + min) / 2;

    if (max === min) {
      h = s = 0;
    } else {
      const d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      switch (max) {
        case rNorm:
          h = (gNorm - bNorm) / d + (gNorm < bNorm ? 6 : 0);
          break;
        case gNorm:
          h = (bNorm - rNorm) / d + 2;
          break;
        case bNorm:
          h = (rNorm - gNorm) / d + 4;
          break;
      }
      h /= 6;
    }

    h = Math.round(h * 360);
    s = Math.round(s * 100);
    l = Math.round(l * 100);

    // Generate color palette
    root.style.setProperty('--primary-50', `hsl(${h}, ${s}%, 97%)`);
    root.style.setProperty('--primary-100', `hsl(${h}, ${s}%, 93%)`);
    root.style.setProperty('--primary-200', `hsl(${h}, ${s}%, 86%)`);
    root.style.setProperty('--primary-300', `hsl(${h}, ${s}%, 77%)`);
    root.style.setProperty('--primary-400', `hsl(${h}, ${s}%, 65%)`);
    root.style.setProperty('--primary-500', `hsl(${h}, ${s}%, ${l}%)`);
    root.style.setProperty(
      '--primary-600',
      `hsl(${h}, ${s}%, ${Math.max(l - 10, 20)}%)`
    );
    root.style.setProperty(
      '--primary-700',
      `hsl(${h}, ${s}%, ${Math.max(l - 20, 15)}%)`
    );
    root.style.setProperty(
      '--primary-800',
      `hsl(${h}, ${s}%, ${Math.max(l - 30, 10)}%)`
    );
    root.style.setProperty(
      '--primary-900',
      `hsl(${h}, ${s}%, ${Math.max(l - 40, 5)}%)`
    );

    console.log('Theme color applied:', color);
  };

  const handleThemeColorChange = (color) => {
    console.log('Color changed to:', color);
    setCurrentThemeColor(color);
    applyThemeColor(color);
    localStorage.setItem('themeColor', color);
  };

  const convertTo12Hour = (time24) => {
    if (!time24) return '';
    const [hours, minutes] = time24.split(':');
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const hour12 = hour % 12 || 12;
    return `${hour12}:${minutes} ${ampm}`;
  };

  const convertTo24Hour = (time12) => {
    if (!time12) return '';
    const [time, ampm] = time12.split(' ');
    const [hours, minutes] = time.split(':');
    let hour = parseInt(hours);
    if (ampm === 'PM' && hour !== 12) hour += 12;
    if (ampm === 'AM' && hour === 12) hour = 0;
    return `${hour.toString().padStart(2, '0')}:${minutes}`;
  };

  const handleEditHours = () => {
    setOriginalBusinessHours({ ...businessHours });
    setEditingHours(true);
  };

  const handleCancelHours = () => {
    setBusinessHours({ ...originalBusinessHours });
    setEditingHours(false);
  };

  const handleHoursChange = (day, field, value) => {
    setBusinessHours((prev) => ({
      ...prev,
      [day]: {
        ...prev[day],
        [field]: value,
      },
    }));
  };

  const handleSaveHours = async () => {
    try {
      await updateSetting('ai_operating_hours', businessHours);
      setEditingHours(false);
      console.log('AI operating hours saved:', businessHours);
    } catch (error) {
      console.error('Failed to save AI operating hours:', error);
      // Optionally show error message to user
    }
  };

  const handleClearHours = (day) => {
    setBusinessHours((prev) => ({
      ...prev,
      [day]: { start: null, end: null },
    }));
  };

  const handleSetHours = (day) => {
    setBusinessHours((prev) => ({
      ...prev,
      [day]: { start: '09:00', end: '17:00' },
    }));
  };

  const handleEditStaff = () => {
    setOriginalStaff([...staff]);
    setEditingStaff(true);
  };

  const handleCancelStaff = () => {
    setStaff([...originalStaff]);
    setEditingStaff(false);
    setNewStaffName('');
    setNewStaffPosition('Specialist');
    setNewStaffActive(true);
  };

  const handleAddStaff = () => {
    if (newStaffName.trim()) {
      const newStaff = {
        id: null, // Will be assigned by backend
        name: newStaffName.trim(),
        position: newStaffPosition.trim() || 'Specialist',
        active: newStaffActive,
      };
      setStaff((prev) => [...prev, newStaff]);
      setNewStaffName('');
      setNewStaffPosition('Specialist');
      setNewStaffActive(true);
    }
  };

  const handleRemoveStaff = (staffId) => {
    setStaff((prev) => prev.filter((s) => s.id !== staffId));
  };

  const handleStaffNameChange = (staffId, newName) => {
    setStaff((prev) =>
      prev.map((s) => (s.id === staffId ? { ...s, name: newName } : s))
    );
  };

  const handleStaffPositionChange = (staffId, newPosition) => {
    setStaff((prev) =>
      prev.map((s) => (s.id === staffId ? { ...s, position: newPosition } : s))
    );
  };

  const handleStaffActiveChange = (staffId, newActive) => {
    setStaff((prev) =>
      prev.map((s) => (s.id === staffId ? { ...s, active: newActive } : s))
    );
  };

  const handleSaveStaff = async () => {
    try {
      await updateStaff(staff);
      setEditingStaff(false);
      console.log('Staff saved:', staff);

      // Refresh staff data to get updated IDs
      const staffResponse = await getStaff();
      setStaff(staffResponse || []);
    } catch (error) {
      console.error('Failed to save staff:', error);
      // Optionally show error message to user
    }
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (file) {
      try {
        const response = await uploadKnowledgeBaseDocument(file);
        setKnowledgeBase(response.items || []);
      } catch (error) {
        console.error('Failed to upload document:', error);
      }
    }
  };

  const handleAddLink = async (linkData) => {
    try {
      // linkData: { urls: [array], description, mainUrl }
      const response = await addKnowledgeBaseLink(
        linkData.urls,
        linkData.description
      );
      setKnowledgeBase(response.items || []);
    } catch (error) {
      console.error('Failed to add link(s):', error);
    }
  };

  const handleRemoveKnowledgeItem = async (itemId) => {
    try {
      const response = await removeKnowledgeBaseItem(itemId);
      setKnowledgeBase(response.items || []);
    } catch (error) {
      console.error('Failed to remove knowledge base item:', error);
    }
  };

  const getFileIcon = (type) => {
    return type === 'link' ? (
      <Link className="h-4 w-4" />
    ) : (
      <FileText className="h-4 w-4" />
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-primary-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with Back Button */}
      <div className="flex items-center space-x-4">
        <button
          onClick={() => navigate('/')}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <ArrowLeft className="h-5 w-5 text-gray-600" />
        </button>
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Settings</h1>
          <p className="text-gray-600 mt-1">
            System configuration and customization
          </p>
        </div>
      </div>

      {/* AI Operating Hours */}
      <div className="card">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-3">
            <Clock className="h-6 w-6 text-primary-600" />
            <div>
              <h2 className="text-lg font-semibold text-gray-900">
                AI Operating Hours
              </h2>
              <p className="text-sm text-gray-600 mt-1">
                These hours define when the AI is active for calls and SMS. They
                do not change the business hours provided to customers by the
                AI.
              </p>
            </div>
          </div>
          {!editingHours ? (
            <button
              onClick={handleEditHours}
              className="btn-secondary flex items-center space-x-2"
            >
              <Edit3 className="h-4 w-4" />
              <span>Edit</span>
            </button>
          ) : (
            <div className="flex items-center space-x-2">
              <button
                onClick={handleSaveHours}
                className="bg-primary-600 hover:bg-primary-700 text-white font-medium px-4 py-2 rounded-lg transition-colors duration-200 flex items-center space-x-2"
              >
                <Check className="h-4 w-4" />
                <span>Done</span>
              </button>
              <button
                onClick={handleCancelHours}
                className="btn-secondary flex items-center space-x-2"
              >
                <X className="h-4 w-4" />
                <span>Cancel</span>
              </button>
            </div>
          )}
        </div>

        {/* FIXED: Use dayOrder to ensure consistent ordering */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {dayOrder.map((day) => {
            const hours = businessHours[day];
            return (
              <div key={day} className="bg-gray-50 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="font-medium text-gray-900">{day}</span>
                  {editingHours && hours.start && hours.end && (
                    <button
                      onClick={() => handleClearHours(day)}
                      className="text-xs text-red-600 hover:text-red-700 px-2 py-1 hover:bg-red-50 rounded"
                    >
                      Clear Hours
                    </button>
                  )}
                </div>

                {editingHours ? (
                  <div className="space-y-2">
                    {hours.start && hours.end ? (
                      <>
                        <div>
                          <label className="block text-xs text-gray-600 mb-1">
                            Start Time
                          </label>
                          <input
                            type="time"
                            value={hours.start}
                            onChange={(e) =>
                              handleHoursChange(day, 'start', e.target.value)
                            }
                            className="w-full text-sm border border-gray-300 rounded px-2 py-1"
                          />
                        </div>
                        <div>
                          <label className="block text-xs text-gray-600 mb-1">
                            End Time
                          </label>
                          <input
                            type="time"
                            value={hours.end}
                            onChange={(e) =>
                              handleHoursChange(day, 'end', e.target.value)
                            }
                            className="w-full text-sm border border-gray-300 rounded px-2 py-1"
                          />
                        </div>
                      </>
                    ) : (
                      <button
                        onClick={() => handleSetHours(day)}
                        className="w-full text-sm bg-primary-100 text-primary-700 rounded px-2 py-2 hover:bg-primary-200 transition-colors"
                      >
                        Set Hours
                      </button>
                    )}
                  </div>
                ) : (
                  <span className="text-sm text-gray-600">
                    {hours.start && hours.end
                      ? `${convertTo12Hour(hours.start)} - ${convertTo12Hour(
                          hours.end
                        )}`
                      : 'Closed'}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Message Customizer */}
      <div className="card mb-8">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-3">
            <Edit3 className="h-6 w-6 text-primary-600" />
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-lg font-semibold text-gray-900">
                  Message Customizer
                </h2>
                <span className="px-2 py-1 text-xs font-bold text-white rounded-full" style={{ backgroundColor: currentThemeColor }}>
                  NEW
                </span>
              </div>
              <p className="text-sm text-gray-600 mt-1">
                Customize automated messages and appointment reminders
              </p>
            </div>
          </div>
          <button
            onClick={() => navigate('/settings/message-customizer')}
            className="btn-secondary flex items-center space-x-2"
          >
            <Edit3 className="h-4 w-4" />
            <span>Customize</span>
          </button>
        </div>
      </div>

      {/* Services Management */}
      <div className="card mb-8">
        <div className="flex items-center space-x-3 mb-6">
          <SettingsIcon className="h-6 w-6 text-primary-600" />
          <h2 className="text-lg font-semibold text-gray-900">
            Services Management
          </h2>
        </div>
        <ServicesManager />
      </div>

      {/* Knowledge Base */}
      <div className="card">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-3">
            <BookOpen className="h-6 w-6 text-primary-600" />
            <h2 className="text-lg font-semibold text-gray-900">
              Knowledge Base
            </h2>
          </div>
          <div className="flex items-center space-x-2">
            <input
              type="file"
              id="file-upload"
              className="hidden"
              onChange={handleFileUpload}
              accept=".pdf,.doc,.docx,.txt"
            />
            <button
              onClick={() => document.getElementById('file-upload').click()}
              className="btn-secondary flex items-center space-x-2"
            >
              <Upload className="h-4 w-4" />
              <span>Upload Document</span>
            </button>
            <button
              onClick={() => setShowAddLinkModal(true)}
              className="btn-secondary flex items-center space-x-2"
            >
              <Link className="h-4 w-4" />
              <span>Add Link</span>
            </button>
          </div>
        </div>

        <div className="space-y-3">
          {knowledgeBase.map((item) => {
            // For grouped link entries, parse the url field (JSON array) and use the root domain
            let displayUrl = item.url;
            if (item.type === 'link' && item.url && item.url.startsWith('[')) {
              try {
                const urls = JSON.parse(item.url);
                // Find the root domain (no path or just '/')
                const root =
                  urls.find((u) => {
                    try {
                      const urlObj = new URL(u);
                      return urlObj.pathname === '/' || urlObj.pathname === '';
                    } catch {
                      return false;
                    }
                  }) || urls[0];
                displayUrl = root;
              } catch {
                displayUrl = item.url;
              }
            }
            return (
              <div
                key={item.id}
                className="flex items-center justify-between p-4 bg-gray-50 rounded-lg"
              >
                <div className="flex items-center space-x-3">
                  <div className="bg-white rounded-lg p-2">
                    {getFileIcon(item.type)}
                  </div>
                  <div>
                    <h3 className="font-medium text-gray-900">{item.name}</h3>
                    <p className="text-sm text-gray-600">{displayUrl}</p>
                    <div className="flex items-center space-x-4 text-xs text-gray-500 mt-1">
                      <span>
                        Added: {new Date(item.created_at).toLocaleDateString()}
                      </span>
                      {item.type === 'link' && displayUrl && (
                        <a
                          href={displayUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary-600 hover:text-primary-700"
                        >
                          Visit Link
                        </a>
                      )}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => handleRemoveKnowledgeItem(item.id)}
                  className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Staff Management */}
      <div className="card">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-3">
            <Users className="h-6 w-6 text-primary-600" />
            <h2 className="text-lg font-semibold text-gray-900">
              Staff Management
            </h2>
          </div>
          {!editingStaff ? (
            <button
              onClick={handleEditStaff}
              className="btn-secondary flex items-center space-x-2"
            >
              <Edit3 className="h-4 w-4" />
              <span>Edit</span>
            </button>
          ) : (
            <div className="flex items-center space-x-2">
              <button
                onClick={handleSaveStaff}
                className="bg-primary-600 hover:bg-primary-700 text-white font-medium px-4 py-2 rounded-lg transition-colors duration-200 flex items-center space-x-2"
              >
                <Check className="h-4 w-4" />
                <span>Done</span>
              </button>
              <button
                onClick={handleCancelStaff}
                className="btn-secondary flex items-center space-x-2"
              >
                <X className="h-4 w-4" />
                <span>Cancel</span>
              </button>
            </div>
          )}
        </div>

        <div className="space-y-3">
          {staff.map((member) => (
            <div
              key={member.id || member.name}
              className="flex items-center justify-between p-4 bg-gray-50 rounded-lg"
            >
              <div className="flex items-center space-x-3">
                <div className="bg-primary-100 rounded-full p-2">
                  <Users className="h-4 w-4 text-primary-600" />
                </div>
                <div className="flex-1">
                  {editingStaff ? (
                    <div className="space-y-2">
                      <input
                        type="text"
                        value={member.name}
                        onChange={(e) =>
                          handleStaffNameChange(member.id, e.target.value)
                        }
                        className="font-medium text-gray-900 bg-white border border-gray-300 rounded px-2 py-1 w-full"
                        placeholder="Staff name"
                      />
                      <input
                        type="text"
                        value={member.position || ''}
                        onChange={(e) =>
                          handleStaffPositionChange(member.id, e.target.value)
                        }
                        className="text-sm text-gray-600 bg-white border border-gray-300 rounded px-2 py-1 w-full"
                        placeholder="Position (e.g., Specialist, Medical Director)"
                      />
                      <div className="flex items-center space-x-2">
                        <input
                          type="checkbox"
                          id={`active-${member.id}`}
                          checked={member.active !== false}
                          onChange={(e) =>
                            handleStaffActiveChange(member.id, e.target.checked)
                          }
                          className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                        />
                        <label
                          htmlFor={`active-${member.id}`}
                          className="text-sm text-gray-600"
                        >
                          Active (can take appointments)
                        </label>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <h3 className="font-medium text-gray-900">
                        {member.name}
                      </h3>
                      <p className="text-sm text-gray-600">
                        {member.position || 'Specialist'}
                      </p>
                      <div className="flex items-center space-x-2 mt-1">
                        <span
                          className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                            member.active !== false
                              ? 'bg-green-100 text-green-800'
                              : 'bg-gray-100 text-gray-800'
                          }`}
                        >
                          {member.active !== false ? 'Active' : 'Inactive'}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              </div>
              {editingStaff && (
                <button
                  onClick={() => handleRemoveStaff(member.id)}
                  className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors ml-4"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>
          ))}

          {editingStaff && (
            <div className="p-4 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
              <div className="space-y-3">
                <input
                  type="text"
                  value={newStaffName}
                  onChange={(e) => setNewStaffName(e.target.value)}
                  placeholder="Enter staff member name"
                  className="w-full border border-gray-300 rounded px-3 py-2"
                  onKeyPress={(e) => e.key === 'Enter' && handleAddStaff()}
                />
                <input
                  type="text"
                  value={newStaffPosition}
                  onChange={(e) => setNewStaffPosition(e.target.value)}
                  placeholder="Position (e.g., Specialist, Medical Director)"
                  className="w-full border border-gray-300 rounded px-3 py-2"
                  onKeyPress={(e) => e.key === 'Enter' && handleAddStaff()}
                />
                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="new-staff-active"
                    checked={newStaffActive}
                    onChange={(e) => setNewStaffActive(e.target.checked)}
                    className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                  />
                  <label
                    htmlFor="new-staff-active"
                    className="text-sm text-gray-600"
                  >
                    Active (can take appointments)
                  </label>
                </div>
                <button
                  onClick={handleAddStaff}
                  className="bg-primary-600 hover:bg-primary-700 text-white font-medium px-4 py-2 rounded-lg transition-colors duration-200 flex items-center space-x-2"
                >
                  <Plus className="h-4 w-4" />
                  <span>Add Staff Member</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Color Theme */}
      <div className="card">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-3">
            <Palette className="h-6 w-6 text-primary-600" />
            <h2 className="text-lg font-semibold text-gray-900">Color Theme</h2>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-3">
            <span className="text-sm font-medium text-gray-700">
              Primary Color:
            </span>
            <button
              onClick={() => setShowColorPicker(!showColorPicker)}
              className="w-10 h-10 rounded-lg border-2 border-gray-300 shadow-sm hover:shadow-md transition-shadow"
              style={{ backgroundColor: currentThemeColor }}
            />
            <span className="text-sm text-gray-600 font-mono">
              {currentThemeColor.toUpperCase()}
            </span>
          </div>
        </div>

        {showColorPicker && (
          <div className="mt-4 flex justify-start">
            <ColorPicker
              color={currentThemeColor}
              onChange={handleThemeColorChange}
              onClose={() => setShowColorPicker(false)}
            />
          </div>
        )}

        <div className="mt-4 p-4 bg-gray-50 rounded-lg">
          <p className="text-sm text-gray-600">
            💡 <strong>Tip:</strong> The color theme changes are applied
            instantly and saved automatically. Simply close the color picker
            when you're happy with your selection. The changes will persist
            across browser sessions.
          </p>
        </div>
      </div>

      {/* Add Link Modal */}
      <AddLinkModal
        isOpen={showAddLinkModal}
        onClose={() => setShowAddLinkModal(false)}
        onAdd={handleAddLink}
      />
    </div>
  );
};

export default Settings;
