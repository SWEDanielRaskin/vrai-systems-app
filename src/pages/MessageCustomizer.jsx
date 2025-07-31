import React, { useState, useRef, useEffect } from 'react';
import { ArrowLeft, Plus, RotateCcw } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { getMessageTemplates, updateMessageTemplate } from '../services/api';

const MessageCustomizer = () => {
  const navigate = useNavigate();
  const canvasRef = useRef(null);
  
  // Get theme color from localStorage or CSS variables
  const [currentThemeColor, setCurrentThemeColor] = useState('#ec4899'); // Default pink
  
  // Load theme color on component mount
  useEffect(() => {
    const savedColor = localStorage.getItem('themeColor');
    if (savedColor) {
      setCurrentThemeColor(savedColor);
    } else {
      // Fallback to CSS variable
      const cssColor = getComputedStyle(document.documentElement).getPropertyValue('--primary-color');
      if (cssColor) {
        setCurrentThemeColor(cssColor);
      }
    }
  }, []);
  
  // Canvas state
  const [canvasPosition, setCanvasPosition] = useState({ x: -1600, y: -600 });
  const [isDraggingCanvas, setIsDraggingCanvas] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  
  // Test send state
  const [testPhoneNumbers, setTestPhoneNumbers] = useState({});
  const [testSending, setTestSending] = useState({});
  const [testMessages, setTestMessages] = useState({});
  
  // Restore defaults state
  const [showRestoreConfirm, setShowRestoreConfirm] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);
  const [restoreMessage, setRestoreMessage] = useState('');

  // Message boxes state
  const [messageBoxes, setMessageBoxes] = useState([
    {
      id: 1,
      title: '24-Hour Reminder',
      position: { x: 1350, y: 750 },
      isDragging: false,
      dragStart: { x: 0, y: 0 },
      // Message data
      hoursInAdvance: 30,
      hoursBeforeAppointment: 24,
      messageContent: "Hi {name}! Your {service} appointment is tomorrow at {time}. We're excited to see you! - Your Spa Name Med Spa",
      isEnabled: true,
      hasChanges: false,
      maxChars: 160,
      cursorPosition: 0 // Track cursor position
    },
    {
      id: 2,
      title: 'Thank You + Review',
      position: { x: 1856, y: 750 },
      isDragging: false,
      dragStart: { x: 0, y: 0 },
      // Message data
      hoursAfterAppointment: 1,
      messageContent: "Thanks for visiting Your Spa Name Med Spa, {name}! We hope you loved your {service}! Leave us a review for 15% off your next visit: https://www.yourspa.com/testimonials/ Code: REVIEW15",
      isEnabled: true,
      hasChanges: false,
      maxChars: 320,
      cursorPosition: 0
    },
    {
      id: 3,
      title: 'Appointment Confirmation',
      description: 'This is sent when the customer books an appointment',
      position: { x: 2362, y: 750 },
      isDragging: false,
      dragStart: { x: 0, y: 0 },
      // Message data
      messageContent: "Your {service} appointment with {specialist} is confirmed for {date} at {time}. Price: ${price}. Duration: {duration} minutes. See you then!",
      isEnabled: true,
      hasChanges: false,
      maxChars: 320,
      cursorPosition: 0
    },
    {
      id: 4,
      title: 'Cancellation Confirmation',
      description: 'This is sent when a customer cancels their appointment',
      position: { x: 2868, y: 750 },
      isDragging: false,
      dragStart: { x: 0, y: 0 },
      // Message data
      messageContent: "Your {service} appointment on {date} at {time} has been cancelled. If you had a deposit, it will be refunded to your payment method. Please call us to reschedule if needed. Thank you!",
      isEnabled: true,
      hasChanges: false,
      maxChars: 320,
      cursorPosition: 0
    },
    {
      id: 5,
      title: 'Refund Notification',
      description: 'This is sent when a customer shows up for their appointment and their deposit is refunded',
      position: { x: 3374, y: 750 },
      isDragging: false,
      dragStart: { x: 0, y: 0 },
      // Message data
      messageContent: "Great news! Your $50 show-up deposit has been refunded to your payment method. Thanks for keeping your appointment at Your Spa Name Med Spa! 💫",
      isEnabled: true,
      hasChanges: false,
      maxChars: 160,
      cursorPosition: 0
    },
    {
      id: 6,
      title: 'Missed Call Notification',
      description: 'This is sent to the caller if the front desk misses their call',
      position: { x: 1856, y: 1300 },
      isDragging: false,
      dragStart: { x: 0, y: 0 },
      // Message data
      messageContent: "Hi! We missed your call to Your Spa Name Med Spa. I'm here to help! How can I assist you today?",
      isEnabled: true,
      hasChanges: false,
      maxChars: 160,
      cursorPosition: 0
    }
  ]);

  // Create refs for textareas
  const textareaRefs = useRef({});

  // Handle canvas dragging
  const handleCanvasMouseDown = (e) => {
    // Only handle canvas dragging if clicking directly on the canvas background
    if (e.target === canvasRef.current) {
      setIsDraggingCanvas(true);
      setDragStart({
        x: e.clientX - canvasPosition.x,
        y: e.clientY - canvasPosition.y
      });
    }
  };

  const handleCanvasMouseMove = (e) => {
    // Only move canvas if we're dragging the canvas (not a box)
    if (isDraggingCanvas) {
      setCanvasPosition({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y
      });
    }
  };

  const handleCanvasMouseUp = () => {
    setIsDraggingCanvas(false);
  };

  // Handle zoom with scroll wheel
  const handleWheel = (e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setZoom(prevZoom => Math.max(0.5, Math.min(2, prevZoom * delta)));
  };

  // Handle message box dragging
  const handleBoxMouseDown = (e, boxId) => {
    // Don't start dragging if clicking on form elements
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'BUTTON' || e.target.tagName === 'LABEL') {
      return;
    }
    
    // Prevent text selection when dragging
    e.preventDefault();
    e.stopPropagation();
    
    const box = messageBoxes.find(b => b.id === boxId);
    if (box) {
      // Account for canvas position and zoom when calculating offset
      const canvasX = (e.clientX - canvasPosition.x) / zoom;
      const canvasY = (e.clientY - canvasPosition.y) / zoom;
      const offsetX = canvasX - box.position.x;
      const offsetY = canvasY - box.position.y;
      
      setMessageBoxes(prev => prev.map(b => 
        b.id === boxId 
          ? { ...b, isDragging: true, dragStart: { x: offsetX, y: offsetY } }
          : b
      ));
    }
  };

  const handleBoxMouseMove = (e) => {
    e.stopPropagation();
    const draggingBox = messageBoxes.find(b => b.isDragging);
    if (draggingBox) {
      // Account for canvas position and zoom when calculating new position
      const canvasX = (e.clientX - canvasPosition.x) / zoom;
      const canvasY = (e.clientY - canvasPosition.y) / zoom;
      let newX = canvasX - draggingBox.dragStart.x;
      let newY = canvasY - draggingBox.dragStart.y;
      
      // Constrain to canvas boundaries
      const boxWidth = 288; // w-72 = 288px
      const boxHeight = 500; // h-[500px]
      const canvasWidth = 4000;
      const canvasHeight = 2000;
      
      // Prevent dragging outside canvas boundaries
      newX = Math.max(0, Math.min(newX, canvasWidth - boxWidth));
      newY = Math.max(0, Math.min(newY, canvasHeight - boxHeight));
      
      setMessageBoxes(prev => prev.map(b => 
        b.id === draggingBox.id 
          ? { ...b, position: { x: newX, y: newY } }
          : b
      ));
    }
  };

  const handleBoxMouseUp = (e) => {
    e.stopPropagation();
    const draggingBox = messageBoxes.find(b => b.isDragging);
    if (draggingBox) {
      // Save position to backend
      saveBoxPosition(draggingBox.id, draggingBox.position);
    }
    setMessageBoxes(prev => prev.map(b => ({ ...b, isDragging: false })));
  };

  // Handle message box changes
  const handleMessageChange = (boxId, field, value) => {
    setMessageBoxes(prev => prev.map(b => 
      b.id === boxId 
        ? { ...b, [field]: value, hasChanges: true }
        : b
    ));
  };

  // Handle message content change with smart tag backspacing
  const handleMessageContentChange = (boxId, value) => {
    const box = messageBoxes.find(b => b.id === boxId);
    if (!box) return;

    // Check if this is a backspace operation
    const oldLength = box.messageContent.length;
    const newLength = value.length;
    
    if (newLength < oldLength) {
      // This is a deletion - check if we need to remove a whole tag
      const deletedChars = oldLength - newLength;
      const textarea = textareaRefs.current[boxId];
      
      if (textarea) {
        const cursorPosition = textarea.selectionStart;
        
        // Find all tags in the original content with their positions
        const tagRegex = /\{[^}]+\}/g;
        const originalContent = box.messageContent;
        const tags = [];
        let match;
        
        while ((match = tagRegex.exec(originalContent)) !== null) {
          tags.push({
            tag: match[0],
            start: match.index,
            end: match.index + match[0].length
          });
        }
        
        // Check if cursor is within or adjacent to any tag
        for (const tagInfo of tags) {
          // Check if cursor is within the tag or immediately after it
          if (cursorPosition >= tagInfo.start && cursorPosition <= tagInfo.end) {
            // Remove the entire tag
            const beforeTag = originalContent.substring(0, tagInfo.start);
            const afterTag = originalContent.substring(tagInfo.end);
            const newValue = beforeTag + afterTag;
            
            setMessageBoxes(prev => prev.map(b => 
              b.id === boxId 
                ? { ...b, messageContent: newValue, cursorPosition: tagInfo.start, hasChanges: true }
                : b
            ));
            
            // Set cursor position after state update
            setTimeout(() => {
              const textarea = textareaRefs.current[boxId];
              if (textarea) {
                textarea.focus();
                textarea.setSelectionRange(tagInfo.start, tagInfo.start);
              }
            }, 0);
            return;
          }
        }
      }
    }
    
    // Normal change - update content and cursor position
    const textarea = textareaRefs.current[boxId];
    const newCursorPosition = textarea ? textarea.selectionStart : box.cursorPosition;
    
    setMessageBoxes(prev => prev.map(b => 
      b.id === boxId 
        ? { ...b, messageContent: value, cursorPosition: newCursorPosition, hasChanges: true }
        : b
    ));
  };

  // Handle tag insertion
  const insertTag = (boxId, tag) => {
    const box = messageBoxes.find(b => b.id === boxId);
    if (box && box.messageContent.length + tag.length <= box.maxChars) {
      const newContent = box.messageContent.substring(0, box.cursorPosition) + tag + box.messageContent.substring(box.cursorPosition);
      const newCursorPosition = box.cursorPosition + tag.length;
      
      setMessageBoxes(prev => prev.map(b => 
        b.id === boxId 
          ? { ...b, messageContent: newContent, cursorPosition: newCursorPosition, hasChanges: true }
          : b
      ));
      
      // Set cursor position after state update
      setTimeout(() => {
        const textarea = textareaRefs.current[boxId];
        if (textarea) {
          textarea.focus();
          textarea.setSelectionRange(newCursorPosition, newCursorPosition);
        }
      }, 0);
    }
  };



  // Handle cancel changes
  const handleCancelChanges = async (boxId) => {
    try {
      // Get the original template from backend
      const templateTypeMap = {
        1: '24hr_reminder',
        2: 'thank_you_review',
        3: 'appointment_confirmation', 
        4: 'cancellation_confirmation',
        5: 'refund_notification',
        6: 'missed_call_notification'
      };
      
      const templateType = templateTypeMap[boxId];
      if (!templateType) return;
      
      const templates = await getMessageTemplates();
      const template = templates.find(t => t.template_type === templateType);
      
      if (template) {
        // Reset to original values
        setMessageBoxes(prev => prev.map(b => 
          b.id === boxId 
            ? {
                ...b,
                messageContent: template.message_content,
                isEnabled: template.is_enabled,
                maxChars: template.max_chars,
                // Reset conditions to original values
                hoursInAdvance: template.conditions?.hours_in_advance || b.hoursInAdvance,
                hoursBeforeAppointment: template.conditions?.hours_before_appointment || b.hoursBeforeAppointment,
                hoursAfterAppointment: template.conditions?.hours_after_appointment || b.hoursAfterAppointment,
                cursorPosition: 0, // Reset cursor position
                hasChanges: false
              }
            : b
        ));
      }
    } catch (error) {
      console.error('Error canceling changes:', error);
    }
  };

  // Load templates from backend on component mount
  useEffect(() => {
    const loadTemplates = async () => {
      try {
        const templates = await getMessageTemplates();
        
        // Map backend templates to frontend format
        const updatedBoxes = messageBoxes.map(box => {
          const template = templates.find(t => {
            const templateTypeMap = {
              1: '24hr_reminder',
              2: 'thank_you_review', 
              3: 'appointment_confirmation',
              4: 'cancellation_confirmation',
              5: 'refund_notification',
              6: 'missed_call_notification'
            };
            return t.template_type === templateTypeMap[box.id];
          });
          
          if (template) {
            return {
              ...box,
              messageContent: template.message_content,
              isEnabled: template.is_enabled,
              maxChars: template.max_chars,
              // Map conditions
              hoursInAdvance: template.conditions?.hours_in_advance || box.hoursInAdvance,
              hoursBeforeAppointment: template.conditions?.hours_before_appointment || box.hoursBeforeAppointment,
              hoursAfterAppointment: template.conditions?.hours_after_appointment || box.hoursAfterAppointment,
              // Load saved position or use default
              position: template.position || box.position,
              cursorPosition: 0, // Reset cursor position
              hasChanges: false
            };
          }
          return box;
        });
        
        setMessageBoxes(updatedBoxes);
      } catch (error) {
        console.error('Error loading templates:', error);
      }
    };
    
    loadTemplates();
  }, []);

  // Save box position to backend
  const saveBoxPosition = async (boxId, position) => {
    const templateTypeMap = {
      1: '24hr_reminder',
      2: 'thank_you_review',
      3: 'appointment_confirmation', 
      4: 'cancellation_confirmation',
      5: 'refund_notification',
      6: 'missed_call_notification'
    };
    
    const templateType = templateTypeMap[boxId];
    if (!templateType) return;
    
    try {
      await updateMessageTemplate(templateType, { position });
      console.log(`Position saved for ${templateType}`);
    } catch (error) {
      console.error('Error saving position:', error);
    }
  };

  // Test send functions
  const validatePhoneNumber = (phone) => {
    // Remove all non-digits
    const cleaned = phone.replace(/\D/g, '');
    
    // Check if it's a valid US number (10 or 11 digits)
    if (cleaned.length === 10) {
      return `+1${cleaned}`;
    } else if (cleaned.length === 11 && cleaned.startsWith('1')) {
      return `+${cleaned}`;
    } else if (cleaned.length === 11 && cleaned.startsWith('+')) {
      return cleaned;
    }
    
    return null;
  };

  const formatTestMessage = (messageContent) => {
    const testData = {
      name: 'John Doe',
      service: 'Botox',
      time: '1:00 PM',
      date: 'January 1st',
      specialist: 'Sarah',
      price: '100',
      duration: '60'
    };

    let formattedMessage = messageContent;
    
    // Replace all tags with test data
    Object.entries(testData).forEach(([key, value]) => {
      const tag = `{${key}}`;
      formattedMessage = formattedMessage.replace(new RegExp(tag, 'g'), value);
    });

    return formattedMessage;
  };

  const handleTestSend = async (boxId) => {
    const phoneNumber = testPhoneNumbers[boxId];
    if (!phoneNumber) {
      setTestMessages(prev => ({ ...prev, [boxId]: { type: 'error', message: 'Please enter a phone number' } }));
      return;
    }

    const formattedPhone = validatePhoneNumber(phoneNumber);
    if (!formattedPhone) {
      setTestMessages(prev => ({ ...prev, [boxId]: { type: 'error', message: 'Please enter a valid US phone number (e.g., 555-123-4567)' } }));
      return;
    }

    const box = messageBoxes.find(b => b.id === boxId);
    if (!box) return;

    setTestSending(prev => ({ ...prev, [boxId]: true }));
    setTestMessages(prev => ({ ...prev, [boxId]: null })); // Clear previous messages

    try {
      const formattedMessage = formatTestMessage(box.messageContent);
      
      const response = await fetch('/api/test-send-sms', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          to_number: formattedPhone,
          message: formattedMessage
        })
      });

      if (response.ok) {
        setTestMessages(prev => ({ ...prev, [boxId]: { type: 'success', message: 'Test message sent successfully!' } }));
      } else {
        const error = await response.json();
        setTestMessages(prev => ({ ...prev, [boxId]: { type: 'error', message: `Failed to send test message: ${error.error || 'Unknown error'}` } }));
      }
    } catch (error) {
      console.error('Error sending test message:', error);
      setTestMessages(prev => ({ ...prev, [boxId]: { type: 'error', message: 'Failed to send test message. Please try again.' } }));
    } finally {
      setTestSending(prev => ({ ...prev, [boxId]: false }));
    }
  };

  // Restore defaults function
  const handleRestoreDefaults = async () => {
    setIsRestoring(true);
    try {
      const response = await fetch('/api/message-templates/restore-defaults', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        }
      });

      if (response.ok) {
        // Reload templates from backend
        const templates = await getMessageTemplates();
        
        // Map backend templates to frontend format
        const updatedBoxes = messageBoxes.map(box => {
          const template = templates.find(t => {
            const templateTypeMap = {
              1: '24hr_reminder',
              2: 'thank_you_review', 
              3: 'appointment_confirmation',
              4: 'cancellation_confirmation',
              5: 'refund_notification',
              6: 'missed_call_notification'
            };
            return t.template_type === templateTypeMap[box.id];
          });
          
          if (template) {
            return {
              ...box,
              messageContent: template.message_content,
              isEnabled: template.is_enabled,
              maxChars: template.max_chars,
              // Map conditions
              hoursInAdvance: template.conditions?.hours_in_advance || box.hoursInAdvance,
              hoursBeforeAppointment: template.conditions?.hours_before_appointment || box.hoursBeforeAppointment,
              hoursAfterAppointment: template.conditions?.hours_after_appointment || box.hoursAfterAppointment,
              // Reset position to default
              position: template.position || box.position,
              cursorPosition: 0, // Reset cursor position
              hasChanges: false
            };
          }
          return box;
        });
        
        setMessageBoxes(updatedBoxes);
        setShowRestoreConfirm(false);
        setRestoreMessage('Templates restored to defaults successfully!');
        setTimeout(() => setRestoreMessage(''), 3000); // Clear after 3 seconds
      } else {
        const error = await response.json();
        setRestoreMessage(`Failed to restore defaults: ${error.error || 'Unknown error'}`);
        setTimeout(() => setRestoreMessage(''), 5000); // Clear after 5 seconds
      }
    } catch (error) {
      console.error('Error restoring defaults:', error);
      setRestoreMessage('Failed to restore defaults. Please try again.');
      setTimeout(() => setRestoreMessage(''), 5000); // Clear after 5 seconds
    } finally {
      setIsRestoring(false);
    }
  };

  // Save template to backend
  const handleSaveChanges = async (boxId) => {
    const box = messageBoxes.find(b => b.id === boxId);
    if (!box) return;
    
    const templateTypeMap = {
      1: '24hr_reminder',
      2: 'thank_you_review',
      3: 'appointment_confirmation', 
      4: 'cancellation_confirmation',
      5: 'refund_notification',
      6: 'missed_call_notification'
    };
    
    const templateType = templateTypeMap[boxId];
    if (!templateType) return;
    
    try {
      const templateData = {
        message_content: box.messageContent,
        is_enabled: box.isEnabled,
        conditions: {
          ...(box.hoursInAdvance && { hours_in_advance: box.hoursInAdvance }),
          ...(box.hoursBeforeAppointment && { hours_before_appointment: box.hoursBeforeAppointment }),
          ...(box.hoursAfterAppointment && { hours_after_appointment: box.hoursAfterAppointment })
        }
      };
      
      await updateMessageTemplate(templateType, templateData);
      
      // Update local state to clear changes
      setMessageBoxes(prev => prev.map(b => 
        b.id === boxId 
          ? { ...b, hasChanges: false }
          : b
      ));
      
      console.log(`Template ${templateType} saved successfully`);
    } catch (error) {
      console.error('Error saving template:', error);
      alert('Failed to save template. Please try again.');
    }
  };

  // Add event listeners
  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas) {
      canvas.addEventListener('mousedown', handleCanvasMouseDown);
      canvas.addEventListener('mousemove', handleCanvasMouseMove);
      canvas.addEventListener('mouseup', handleCanvasMouseUp);
      canvas.addEventListener('wheel', handleWheel);
      
      return () => {
        canvas.removeEventListener('mousedown', handleCanvasMouseDown);
        canvas.removeEventListener('mousemove', handleCanvasMouseMove);
        canvas.removeEventListener('mouseup', handleCanvasMouseUp);
        canvas.removeEventListener('wheel', handleWheel);
      };
    }
  }, [isDraggingCanvas, canvasPosition, dragStart]);

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => navigate('/settings')}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <ArrowLeft className="h-5 w-5 text-gray-600" />
            </button>
            <div className="flex items-center space-x-2">
              <h1 className="text-2xl font-bold text-gray-900">Message Customizer</h1>
              <span className="px-2 py-1 text-xs font-bold text-white rounded-full" style={{ backgroundColor: currentThemeColor }}>
                NEW
              </span>
            </div>
          </div>
          <div className="flex items-center space-x-4">
            {restoreMessage && (
              <div className={`text-sm px-3 py-1 rounded ${
                restoreMessage.includes('successfully') 
                  ? 'bg-green-100 text-green-700' 
                  : 'bg-red-100 text-red-700'
              }`}>
                {restoreMessage}
              </div>
            )}
            <button
              onClick={() => setShowRestoreConfirm(true)}
              disabled={isRestoring}
              className="flex items-center space-x-2 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-400 text-white rounded-lg transition-colors"
            >
              <RotateCcw className="h-4 w-4" />
              <span>{isRestoring ? 'Restoring...' : 'Restore Defaults'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Canvas Container */}
      <div className="relative w-full h-[calc(100vh-80px)] overflow-hidden bg-gray-100">
        {/* Canvas */}
        <div
          ref={canvasRef}
          className="absolute inset-0 cursor-grab active:cursor-grabbing bg-white"
          style={{
            backgroundImage: `
              radial-gradient(circle at 25px 25px, #d1d5db 2px, transparent 2px)
            `,
            backgroundSize: '50px 50px',
            transform: `translate(${canvasPosition.x}px, ${canvasPosition.y}px) scale(${zoom})`,
            transformOrigin: '0 0',
            minWidth: '4000px',
            minHeight: '2000px'
          }}
        >
          {/* Message Boxes */}
          {messageBoxes.map((box) => (
            <div
              key={box.id}
              className="absolute"
              style={{
                left: box.position.x,
                top: box.position.y,
              }}
            >
              {/* Message Box */}
              <div
                className={`w-72 h-[500px] bg-white border border-gray-300 rounded-lg shadow-lg cursor-move transition-opacity duration-300 ${
                  !box.isEnabled ? 'opacity-50' : 'opacity-100'
                }`}
                style={{
                  transform: box.isDragging ? 'scale(1.02)' : 'scale(1)',
                  transition: box.isDragging ? 'none' : 'transform 0.1s ease'
                }}
                onMouseDown={(e) => handleBoxMouseDown(e, box.id)}
                onMouseMove={handleBoxMouseMove}
                onMouseUp={handleBoxMouseUp}
                onMouseLeave={handleBoxMouseUp}
              >
                {/* Message Box Content */}
                <div className="p-4 h-full flex flex-col">
                  {/* Header */}
                  <div className="text-sm font-semibold text-gray-700 mb-2 select-none">
                    {box.title}
                  </div>
                  {box.description && (
                    <div className="text-xs text-gray-500 mb-4 select-none">
                      {box.description}
                    </div>
                  )}

                  {/* Conditional Fields */}
                  <div className="space-y-3 mb-4">
                    {box.hoursInAdvance !== undefined && (
                      <div>
                        <label className="block text-xs text-gray-600 mb-1 select-none">
                          Send if booked {box.hoursInAdvance || 0} or more hours in advance
                        </label>
                        <input
                          type="number"
                          value={box.hoursInAdvance || ''}
                          onChange={(e) => {
                            const value = e.target.value;
                            const parsedValue = value === '' ? 0 : parseInt(value) || 0;
                            handleMessageChange(box.id, 'hoursInAdvance', parsedValue);
                          }}
                          className="w-full text-sm border border-gray-300 rounded px-2 py-1"
                          min="1"
                          max="168"
                        />
                      </div>
                    )}
                    {box.hoursBeforeAppointment !== undefined && (
                      <div>
                        <label className="block text-xs text-gray-600 mb-1 select-none">
                          Send {box.hoursBeforeAppointment || 0} hours before appointment
                        </label>
                        <input
                          type="number"
                          value={box.hoursBeforeAppointment || ''}
                          onChange={(e) => {
                            const value = e.target.value;
                            const parsedValue = value === '' ? 0 : parseInt(value) || 0;
                            handleMessageChange(box.id, 'hoursBeforeAppointment', parsedValue);
                          }}
                          className="w-full text-sm border border-gray-300 rounded px-2 py-1"
                          min="1"
                          max="72"
                        />
                      </div>
                    )}
                    {box.hoursAfterAppointment !== undefined && (
                      <div>
                        <label className="block text-xs text-gray-600 mb-1 select-none">
                          Send {box.hoursAfterAppointment || 0} hours after appointment
                        </label>
                        <input
                          type="number"
                          value={box.hoursAfterAppointment || ''}
                          onChange={(e) => {
                            const value = e.target.value;
                            const parsedValue = value === '' ? 0 : parseInt(value) || 0;
                            handleMessageChange(box.id, 'hoursAfterAppointment', parsedValue);
                          }}
                          className="w-full text-sm border border-gray-300 rounded px-2 py-1"
                          min="1"
                          max="24"
                        />
                      </div>
                    )}
                  </div>

                  {/* Message Content */}
                  <div className="mb-4 flex-1 flex flex-col">
                    <label className="block text-xs text-gray-600 mb-1 select-none">
                      Message Content ({box.messageContent.length}/{box.maxChars})
                    </label>
                    <textarea
                      ref={(el) => textareaRefs.current[box.id] = el}
                      value={box.messageContent}
                      onChange={(e) => handleMessageContentChange(box.id, e.target.value)}
                      onKeyDown={(e) => {
                        const textarea = textareaRefs.current[box.id];
                        if (textarea) {
                          if (e.key === 'Tab') {
                            e.preventDefault();
                            const start = textarea.selectionStart;
                            const end = textarea.selectionEnd;
                            const newContent = box.messageContent.substring(0, start) + '\t' + box.messageContent.substring(end);
                            setMessageBoxes(prev => prev.map(b => 
                              b.id === box.id ? { ...b, messageContent: newContent, cursorPosition: start + 1 } : b
                            ));
                          } else if (e.key === 'Enter') {
                            e.preventDefault();
                            const start = textarea.selectionStart;
                            const end = textarea.selectionEnd;
                            const newContent = box.messageContent.substring(0, start) + '\n' + box.messageContent.substring(end);
                            setMessageBoxes(prev => prev.map(b => 
                              b.id === box.id ? { ...b, messageContent: newContent, cursorPosition: start + 1 } : b
                            ));
                          }
                        }
                      }}
                      onKeyUp={(e) => {
                        const textarea = textareaRefs.current[box.id];
                        if (textarea) {
                          setMessageBoxes(prev => prev.map(b => 
                            b.id === box.id ? { ...b, cursorPosition: textarea.selectionStart } : b
                          ));
                        }
                      }}
                      className="w-full flex-1 text-sm border border-gray-300 rounded px-2 py-1 resize-none"
                      maxLength={box.maxChars}
                      placeholder="Enter your message here..."
                    />
                  </div>

                  {/* Available Tags */}
                  <div className="mb-4">
                    <label className="block text-xs text-gray-600 mb-2 select-none">
                      Available Tags (click to insert):
                    </label>
                    <div className="flex flex-wrap gap-1">
                      {['{name}', '{service}', '{time}', '{date}', '{specialist}', '{price}', '{duration}'].map((tag) => (
                        <button
                          key={tag}
                          onClick={() => insertTag(box.id, tag)}
                          className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 px-2 py-1 rounded border cursor-pointer transition-colors"
                        >
                          {tag}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Bottom Controls */}
                  <div className="flex items-center justify-between mt-auto">
                    <div className="flex items-center space-x-2">
                      <label className="text-xs text-gray-600 select-none">Enable</label>
                      <input
                        type="checkbox"
                        checked={box.isEnabled}
                        onChange={(e) => handleMessageChange(box.id, 'isEnabled', e.target.checked)}
                        className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                      />
                    </div>
                    
                    {box.hasChanges && (
                      <div className="flex space-x-2">
                        <button
                          onClick={() => handleCancelChanges(box.id)}
                          className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-1 rounded border transition-colors"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={() => handleSaveChanges(box.id)}
                          className="text-xs bg-primary-600 hover:bg-primary-700 text-white px-3 py-1 rounded transition-colors"
                        >
                          Save
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
              
              {/* Test Send Section */}
              <div className="mt-2 w-72 bg-gray-50 border border-gray-200 rounded-lg p-3">
                <div className="text-xs font-medium text-gray-700 mb-2">Test Send</div>
                <div className="flex space-x-2">
                  <input
                    type="tel"
                    placeholder="Phone number"
                    value={testPhoneNumbers[box.id] || ''}
                    onChange={(e) => setTestPhoneNumbers(prev => ({ ...prev, [box.id]: e.target.value }))}
                    className="flex-1 text-xs border border-gray-300 rounded px-2 py-1"
                  />
                  <button
                    onClick={() => handleTestSend(box.id)}
                    disabled={testSending[box.id]}
                    className="text-xs bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white px-3 py-1 rounded transition-colors"
                  >
                    {testSending[box.id] ? 'Sending...' : 'Send'}
                  </button>
                </div>
                {testMessages[box.id] && (
                  <div className={`mt-2 text-xs ${testMessages[box.id].type === 'success' ? 'text-green-600' : 'text-red-600'}`}>
                    {testMessages[box.id].message}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Zoom Controls */}
        <div className="absolute bottom-4 right-4 flex flex-col space-y-2">
          <button
            onClick={() => setZoom(prev => Math.min(2, prev + 0.1))}
            className="w-10 h-10 bg-white border border-gray-300 rounded-lg shadow-lg flex items-center justify-center hover:bg-gray-50 transition-colors"
          >
            <Plus className="h-5 w-5 text-gray-600" />
          </button>
          <button
            onClick={() => setZoom(prev => Math.max(0.5, prev - 0.1))}
            className="w-10 h-10 bg-white border border-gray-300 rounded-lg shadow-lg flex items-center justify-center hover:bg-gray-50 transition-colors"
          >
            <span className="text-gray-600 font-bold">−</span>
          </button>
        </div>

        {/* Zoom Level Display */}
        <div className="absolute bottom-4 left-4 bg-white border border-gray-300 rounded-lg px-3 py-2 shadow-lg">
          <span className="text-sm text-gray-600">
            {Math.round(zoom * 100)}%
          </span>
        </div>
      </div>

      {/* Restore Defaults Confirmation Modal */}
      {showRestoreConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              Restore Default Templates
            </h3>
            <p className="text-gray-600 mb-6">
              This will reset all message templates to their original default values. 
              All customizations will be lost. Are you sure you want to continue?
            </p>
            <div className="flex space-x-3">
              <button
                onClick={() => setShowRestoreConfirm(false)}
                className="flex-1 px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-800 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleRestoreDefaults}
                disabled={isRestoring}
                className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-400 text-white rounded-lg transition-colors"
              >
                {isRestoring ? 'Restoring...' : 'Restore Defaults'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MessageCustomizer; 