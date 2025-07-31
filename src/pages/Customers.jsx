import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  Search,
  Plus,
  Filter,
  Edit2,
  Phone,
  Mail,
  Calendar,
  Clock,
  User,
  FileText,
  ChevronRight,
  RefreshCw,
  Upload,
  Save,
  X,
  Users,
  Camera,
  Trash2
} from 'lucide-react';
import {
  getCustomers,
  getCustomerDetail,
  createCustomer,
  updateCustomer,
  deleteCustomer,
  uploadCustomerProfilePicture,
  updateAppointmentNotes
} from '../services/api';

// Phone number utility functions (moved outside component to prevent recreation)
const cleanPhoneNumber = (phone) => {
  return phone.replace(/\D/g, '');
};

const validatePhoneNumber = (phone) => {
  const cleaned = cleanPhoneNumber(phone);
  
  if (cleaned.length === 10) {
    return { isValid: true, cleaned };
  } else if (cleaned.length === 11 && cleaned.startsWith('1')) {
    return { isValid: true, cleaned };
  } else {
    return { isValid: false, cleaned };
  }
};

const toE164Format = (phone) => {
  const cleaned = cleanPhoneNumber(phone);
  
  if (cleaned.length === 10) {
    return `+1${cleaned}`;
  } else if (cleaned.length === 11 && cleaned.startsWith('1')) {
    return `+${cleaned}`;
  }
  return phone;
};

const formatPhoneNumber = (phone) => {
  if (!phone) return '';
  
  const cleaned = phone.replace(/^\+1?/, '').replace(/\D/g, '');
  
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }
  return phone;
};

const formatDate = (dateString) => {
  if (!dateString) return 'Never';
  
  // Handle both date-only strings (YYYY-MM-DD) and full datetime strings
  let date;
  if (dateString.includes('T')) {
    // Full datetime string, parse directly
    date = new Date(dateString);
  } else {
    // Date-only string, append time
    date = new Date(dateString + 'T12:00:00');
  }
  
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  });
};

// Add Customer Modal Component (moved outside main component)
const AddCustomerModal = ({ 
  show, 
  onClose, 
  newCustomer, 
  setNewCustomer, 
  phoneError, 
  setPhoneError, 
  onSubmit 
}) => {
  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-md">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Add New Customer</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-100 rounded"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        
        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Phone Number *
            </label>
            <input
              type="tel"
              value={newCustomer.phone_number}
              onChange={(e) => {
                setNewCustomer({...newCustomer, phone_number: e.target.value});
                setPhoneError('');
              }}
              placeholder="+15550123456"
              className={`input w-full ${phoneError ? 'border-red-500' : ''}`}
              required
            />
            {phoneError && (
              <p className="text-red-500 text-sm mt-1">{phoneError}</p>
            )}
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Customer Name
            </label>
            <input
              type="text"
              value={newCustomer.name}
              onChange={(e) => setNewCustomer({...newCustomer, name: e.target.value})}
              placeholder="Customer name"
              className="input w-full"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Email
            </label>
            <input
              type="email"
              value={newCustomer.email}
              onChange={(e) => setNewCustomer({...newCustomer, email: e.target.value})}
              placeholder="customer@example.com"
              className="input w-full"
            />
          </div>
          
          <div className="flex items-center space-x-3 pt-4">
            <button type="submit" className="btn-primary flex-1">
              Create Customer
            </button>
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary flex-1"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// Delete Confirmation Modal Component (moved outside main component)
const DeleteConfirmationModal = ({ 
  show, 
  onClose, 
  customerToDelete, 
  onConfirm 
}) => {
  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-md">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Delete Customer</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-100 rounded"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        
        <div className="mb-6">
          <p className="text-gray-600 mb-4">
            Are you sure you want to delete this customer? This action cannot be undone.
          </p>
          
          {customerToDelete && (
            <div className="bg-gray-50 rounded-lg p-3 border">
              <div className="flex items-center space-x-3">
                <div className="w-10 h-10 bg-primary-100 rounded-full flex items-center justify-center">
                  {customerToDelete.profile_picture_path ? (
                    <img
                      src={`/${customerToDelete.profile_picture_path}`}
                      alt={customerToDelete.name}
                      className="w-10 h-10 rounded-full object-cover"
                    />
                  ) : (
                    <User className="h-5 w-5 text-primary-600" />
                  )}
                </div>
                <div>
                  <p className="font-medium text-gray-900">
                    {customerToDelete.name || 'Unnamed Customer'}
                  </p>
                  <p className="text-sm text-gray-500">
                    {formatPhoneNumber(customerToDelete.phone_number)}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
        
        <div className="flex items-center space-x-3">
          <button
            onClick={onConfirm}
            className="flex-1 bg-red-600 text-white py-2 px-4 rounded-lg hover:bg-red-700 transition-colors font-medium"
          >
            Delete Customer
          </button>
          <button
            onClick={onClose}
            className="flex-1 bg-gray-200 text-gray-800 py-2 px-4 rounded-lg hover:bg-gray-300 transition-colors font-medium"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

// Customer List Component (moved outside main component to prevent recreation)
const CustomerList = ({
  navigate,
  fetchCustomers,
  loading,
  setShowAddModal,
  searchTerm,
  setSearchTerm,
  sortBy,
  setSortBy,
  sortOrder,
  setSortOrder,
  customers,
  handleViewCustomer,
  showDeleteConfirmation
}) => (
  <div className="space-y-6">
    <div className="flex items-center justify-between">
      <div className="flex items-center space-x-4">
        <button
          onClick={() => navigate('/')}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <ArrowLeft className="h-5 w-5 text-gray-600" />
        </button>
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Customer Database</h1>
          <p className="text-gray-600 mt-1">
            Manage all Radiance MD customers
          </p>
        </div>
      </div>
      <div className="flex items-center space-x-2">
        <button
          onClick={fetchCustomers}
          className="btn-secondary flex items-center space-x-1"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
        <button
          onClick={() => setShowAddModal(true)}
          className="btn-primary flex items-center space-x-1"
        >
          <Plus className="h-4 w-4" />
          <span>Add Customer</span>
        </button>
      </div>
    </div>

    <div className="card">
      <div className="flex items-center space-x-4">
        <div className="relative" style={{ width: '600px' }}>
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search customers by name, phone, or email..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="input pl-10 w-full"
          />
        </div>
        <div className="flex-1"></div>
        <div className="flex items-center space-x-2">
          <div className="border border-gray-300 rounded-lg bg-white">
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="input border-0 focus:ring-0"
            >
              <option value="name">Sort by Name</option>
              <option value="total_appointments">Sort by # Appointments</option>
              <option value="last_appointment_date">Sort by Last Visit</option>
              <option value="created_at">Sort by Date Added</option>
            </select>
          </div>
          <div className="border border-gray-300 rounded-lg bg-white">
            <select
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value)}
              className="input border-0 focus:ring-0"
            >
              <option value="ASC">Ascending</option>
              <option value="DESC">Descending</option>
            </select>
          </div>
          <button
            onClick={fetchCustomers}
            className="btn-secondary flex items-center space-x-1"
          >
            <Filter className="h-4 w-4" />
            <span>Apply</span>
          </button>
        </div>
      </div>
    </div>

    <div className="card">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-gray-900 flex items-center space-x-2">
          <Users className="h-5 w-5" />
          <span>Customers ({customers.length})</span>
        </h2>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="h-8 w-8 animate-spin text-primary-600" />
        </div>
      ) : customers.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          <Users className="h-12 w-12 mx-auto mb-4 text-gray-300" />
          <p>No customers found</p>
          {searchTerm && (
            <button
              onClick={() => setSearchTerm('')}
              className="text-primary-600 hover:text-primary-700 mt-2"
            >
              Clear search
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {customers.map((customer) => (
            <div
              key={customer.phone_number}
              onClick={() => handleViewCustomer(customer.phone_number)}
              className="flex items-center p-4 border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors"
            >
              <div className="flex items-center space-x-4 flex-1">
                <div className="w-12 h-12 bg-primary-100 rounded-full flex items-center justify-center">
                  {customer.profile_picture_path ? (
                    <img
                      src={`/${customer.profile_picture_path}`}
                      alt={customer.name}
                      className="w-12 h-12 rounded-full object-cover"
                    />
                  ) : (
                    <User className="h-6 w-6 text-primary-600" />
                  )}
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">
                    {customer.name || 'Unnamed Customer'}
                  </h3>
                  <p className="text-sm text-gray-600">
                    {formatPhoneNumber(customer.phone_number)}
                  </p>
                  {customer.email && (
                    <p className="text-sm text-gray-500">{customer.email}</p>
                  )}
                </div>
              </div>
              <div className="text-right flex-shrink-0 mr-4">
                <div className="text-sm font-medium text-gray-900">
                  {customer.total_appointments || 0} appointments
                </div>
                <div className="text-sm text-gray-500">
                  Last visit: {formatDate(customer.last_appointment_date)}
                </div>
                <div className="text-sm text-gray-500">
                  Customer since: {formatDate(customer.customer_since)}
                </div>
              </div>
              <div className="flex items-center space-x-2 flex-shrink-0">
                <button
                  onClick={(e) => showDeleteConfirmation(e, customer)}
                  className="p-1 text-red-500 hover:text-red-700 hover:bg-red-50 rounded transition-colors"
                  title="Delete customer"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
                <ChevronRight className="h-5 w-5 text-gray-400" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  </div>
);

const Customers = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  
  // State management
  const [view, setView] = useState('list');
  const [customers, setCustomers] = useState([]);
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [sortBy, setSortBy] = useState('name');
  const [sortOrder, setSortOrder] = useState('ASC');
  const [showAddModal, setShowAddModal] = useState(false);
  
  // Delete confirmation states
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [customerToDelete, setCustomerToDelete] = useState(null);
  
  // Inline editing states
  const [editingField, setEditingField] = useState(null);
  const [editingValue, setEditingValue] = useState('');
  
  // Profile picture upload states
  const [uploadingPicture, setUploadingPicture] = useState(false);
  
  // Appointment notes editing states
  const [editingAppointmentNote, setEditingAppointmentNote] = useState(null);
  const [editingNoteValue, setEditingNoteValue] = useState('');
  const textareaRef = useRef(null);
  
  // Form states
  const [newCustomer, setNewCustomer] = useState({
    phone_number: '',
    name: '',
    email: ''
  });

  // Phone number validation states
  const [phoneError, setPhoneError] = useState('');

  // Refs to track search state
  const searchTimeoutRef = useRef(null);

  // Memoized fetchCustomers to prevent recreation
  const fetchCustomers = useCallback(async () => {
    try {
      setLoading(true);
      const params = {
        search: searchTerm || undefined,
        sort_by: sortBy,
        sort_order: sortOrder
      };
      const response = await getCustomers(params);
      setCustomers(response.customers || []);
    } catch (error) {
      console.error('Error fetching customers:', error);
    } finally {
      setLoading(false);
    }
  }, [searchTerm, sortBy, sortOrder]);

  useEffect(() => {
    fetchCustomers();
    
    const customerPhone = searchParams.get('customer');
    if (customerPhone) {
      handleViewCustomer(customerPhone);
    }
  }, [searchParams, fetchCustomers]);

  // Debounced search effect - SIMPLIFIED
  useEffect(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }

    searchTimeoutRef.current = setTimeout(() => {
      fetchCustomers();
    }, 300);

    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, [searchTerm, fetchCustomers]);

  const handleViewCustomer = async (phoneNumber) => {
    try {
      setLoading(true);
      const response = await getCustomerDetail(phoneNumber);
      setSelectedCustomer(response.customer);
      setView('detail');
      setSearchParams({ customer: phoneNumber });
    } catch (error) {
      console.error('Error fetching customer detail:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleBackToList = () => {
    setView('list');
    setSelectedCustomer(null);
    setSearchParams({});
  };

  const handleCreateCustomer = async (e) => {
    e.preventDefault();
    setPhoneError('');
    
    const validation = validatePhoneNumber(newCustomer.phone_number);
    if (!validation.isValid) {
      setPhoneError('Phone number must be 10 digits or 11 digits starting with 1');
      return;
    }
    
    try {
      const customerData = {
        ...newCustomer,
        phone_number: toE164Format(newCustomer.phone_number)
      };
      
      await createCustomer(customerData);
      setShowAddModal(false);
      setPhoneError('');
      setNewCustomer({
        phone_number: '',
        name: '',
        email: ''
      });
      fetchCustomers();
    } catch (error) {
      console.error('Error creating customer:', error);
      alert('Error creating customer. Phone number may already exist.');
    }
  };

  const handleUpdateCustomer = async (phoneNumber, data) => {
    try {
      await updateCustomer(phoneNumber, data);
      if (selectedCustomer && selectedCustomer.phone_number === phoneNumber) {
        handleViewCustomer(phoneNumber);
      }
      fetchCustomers();
    } catch (error) {
      console.error('Error updating customer:', error);
      alert('Error updating customer.');
    }
  };

  const showDeleteConfirmation = (e, customer) => {
    e.stopPropagation();
    setCustomerToDelete(customer);
    setShowDeleteModal(true);
  };

  const handleDeleteCustomer = async () => {
    if (!customerToDelete) return;
    
    try {
      await deleteCustomer(customerToDelete.phone_number);
      setShowDeleteModal(false);
      setCustomerToDelete(null);
      
      if (selectedCustomer && selectedCustomer.phone_number === customerToDelete.phone_number) {
        handleBackToList();
      }
      
      fetchCustomers();
    } catch (error) {
      console.error('Error deleting customer:', error);
      alert('Error deleting customer. Please try again.');
    }
  };

  const cancelDelete = () => {
    setShowDeleteModal(false);
    setCustomerToDelete(null);
  };

  const closeAddModal = () => {
    setShowAddModal(false);
    setPhoneError('');
  };

  // Inline editing functions
  const startEditing = (field, currentValue) => {
    setEditingField(field);
    setEditingValue(currentValue || '');
  };

  const cancelEditing = () => {
    setEditingField(null);
    setEditingValue('');
  };

  const saveEdit = async () => {
    if (!selectedCustomer || !editingField) return;
    
    const updateData = {};
    updateData[editingField] = editingValue;
    
    try {
      await handleUpdateCustomer(selectedCustomer.phone_number, updateData);
      setEditingField(null);
      setEditingValue('');
    } catch (error) {
      console.error('Error saving edit:', error);
      alert('Error saving changes.');
    }
  };

  const handleProfilePictureUpload = async (event) => {
    const file = event.target.files[0];
    if (!file || !selectedCustomer) return;

    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif'];
    if (!allowedTypes.includes(file.type)) {
      alert('Please select a valid image file (JPEG, PNG, or GIF)');
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      alert('File size must be less than 5MB');
      return;
    }

    try {
      setUploadingPicture(true);
      await uploadCustomerProfilePicture(selectedCustomer.phone_number, file);
      await handleViewCustomer(selectedCustomer.phone_number);
      event.target.value = '';
    } catch (error) {
      console.error('Error uploading profile picture:', error);
      alert('Error uploading profile picture. Please try again.');
    } finally {
      setUploadingPicture(false);
    }
  };

  const startEditingAppointmentNote = (appointmentId, currentNotes) => {
    setEditingAppointmentNote(appointmentId);
    setEditingNoteValue(currentNotes || '');
  };

  const cancelEditingAppointmentNote = () => {
    setEditingAppointmentNote(null);
    setEditingNoteValue('');
  };

  const saveAppointmentNote = async (appointmentId) => {
    try {
      await updateAppointmentNotes(appointmentId, editingNoteValue);
      setEditingAppointmentNote(null);
      setEditingNoteValue('');
      await handleViewCustomer(selectedCustomer.phone_number);
    } catch (error) {
      console.error('Error saving appointment note:', error);
      alert('Error saving appointment note. Please try again.');
    }
  };

  const handleAppointmentNoteKeyDown = (e, appointmentId) => {
    if (e.key === 'Enter' && e.ctrlKey) {
      saveAppointmentNote(appointmentId);
    } else if (e.key === 'Escape') {
      cancelEditingAppointmentNote();
    }
  };

  const handleAppointmentNoteChange = (e) => {
    const textarea = e.target;
    const cursorPosition = textarea.selectionStart;
    setEditingNoteValue(e.target.value);
    
    // Preserve cursor position after state update
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.setSelectionRange(cursorPosition, cursorPosition);
      }
    }, 0);
  };

  // Inline editing component
  const EditableField = ({ field, value, label, isTextArea = false, placeholder = '' }) => {
    const isEditing = editingField === field;
    
    const handleKeyDown = (e) => {
      if (e.key === 'Enter' && !isTextArea) {
        saveEdit();
      } else if (e.key === 'Escape') {
        cancelEditing();
      }
    };

    return (
      <div>
        <div className="flex items-center space-x-2 mb-1">
          <label className="block text-xl font-bold text-gray-800">
            {label}
          </label>
          <Edit2 
            className="h-5 w-5 text-black cursor-pointer hover:text-gray-700 transition-colors"
            onClick={() => startEditing(field, value)}
          />
        </div>
        <div className={isTextArea ? "w-full" : "w-1/2"}>
          {isEditing ? (
            <div className="w-full">
              {isTextArea ? (
                <textarea
                  value={editingValue}
                  onChange={(e) => setEditingValue(e.target.value)}
                  onBlur={saveEdit}
                  onKeyDown={handleKeyDown}
                  className="input w-full text-lg"
                  style={{ direction: 'ltr', textAlign: 'left' }}
                  rows={3}
                  autoFocus
                  placeholder={placeholder}
                />
              ) : (
                <input
                  type="text"
                  value={editingValue}
                  onChange={(e) => setEditingValue(e.target.value)}
                  onBlur={saveEdit}
                  onKeyDown={handleKeyDown}
                  className="input w-full text-lg"
                  style={{ direction: 'ltr', textAlign: 'left' }}
                  autoFocus
                  placeholder={placeholder}
                />
              )}
            </div>
          ) : (
            <p 
              className="text-gray-900 text-lg cursor-pointer hover:bg-gray-50 py-2 rounded border border-transparent hover:border-gray-200 transition-all"
              onClick={() => startEditing(field, value)}
            >
              {value || placeholder || 'Not provided'}
            </p>
          )}
        </div>
      </div>
    );
  };

  // Customer Detail Component
  const CustomerDetail = () => {
    if (!selectedCustomer) return null;

    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <button
              onClick={handleBackToList}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <ArrowLeft className="h-5 w-5 text-gray-600" />
            </button>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">
                {selectedCustomer.name || 'Unnamed Customer'}
              </h1>
              <p className="text-gray-600 mt-1">
                Customer since {formatDate(selectedCustomer.customer_since)}
              </p>
            </div>
          </div>
        </div>

        <div className="card">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Profile</h2>
          <div className="flex items-start space-x-6">
            <div className="relative">
              <input
                type="file"
                accept="image/*"
                onChange={handleProfilePictureUpload}
                className="hidden"
                id="profile-picture-upload"
              />
              <label
                htmlFor="profile-picture-upload"
                className="block w-24 h-24 bg-primary-100 rounded-full cursor-pointer group relative overflow-hidden"
              >
                {selectedCustomer.profile_picture_path ? (
                  <img
                    src={`/${selectedCustomer.profile_picture_path}`}
                    alt={selectedCustomer.name}
                    className="w-24 h-24 rounded-full object-cover"
                  />
                ) : (
                  <div className="w-24 h-24 rounded-full flex items-center justify-center">
                    <User className="h-12 w-12 text-primary-600" />
                  </div>
                )}
                
                <div className="absolute inset-0 bg-black bg-opacity-50 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                  {uploadingPicture ? (
                    <RefreshCw className="h-6 w-6 text-white animate-spin" />
                  ) : (
                    <Camera className="h-6 w-6 text-white" />
                  )}
                </div>
              </label>
            </div>
            <div className="flex-1 grid grid-cols-2 gap-2">
              <EditableField 
                field="name"
                value={selectedCustomer.name}
                label="Name"
                placeholder="Customer name"
              />
              <div>
                <label className="block text-xl font-bold text-gray-800 mb-1">
                  Phone Number
                </label>
                <div className="w-1/2">
                  <p className="text-gray-900 text-lg py-2">{formatPhoneNumber(selectedCustomer.phone_number)}</p>
                </div>
              </div>
              <EditableField 
                field="email"
                value={selectedCustomer.email}
                label="Email"
                placeholder="customer@example.com"
              />
              <div>
                <label className="block text-xl font-bold text-gray-800 mb-1">
                  Total Appointments
                </label>
                <div className="w-1/2">
                  <p className="text-gray-900 text-lg py-2">{selectedCustomer.total_appointments || 0}</p>
                </div>
              </div>
              <div className="col-span-2">
                <label className="
                block text-xl font-bold text-gray-800 mb-1">
                  Last Appointment
                </label>
                <div className="w-1/2">
                  <p className="text-gray-900 text-lg py-2">{formatDate(selectedCustomer.last_appointment_date)}</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="mb-6">
            <EditableField 
              field="up_next_from_you"
              value={selectedCustomer.up_next_from_you}
              label={`Up Next for ${selectedCustomer.name}`}
              placeholder="Next expected service or follow-up for this customer..."
            />
          </div>
          
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Appointment History</h2>
          
          <div className="grid grid-cols-2 gap-6">
            <div>
              <h3 className="text-md font-medium text-gray-900 mb-3">
                Past Appointments ({selectedCustomer.past_appointments?.length || 0})
              </h3>
              {selectedCustomer.past_appointments?.length > 0 ? (
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {selectedCustomer.past_appointments.slice(0, 10).map((apt) => (
                    <div key={apt.calendar_event_id} className="border border-red-200 bg-red-50 rounded-lg p-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <h4 className="font-medium text-gray-900 text-sm">{apt.service_name}</h4>
                          <p className="text-xs text-gray-600">
                            {formatDate(apt.appointment_date)} at {apt.appointment_time}
                          </p>
                          {apt.specialist && (
                            <p className="text-xs text-gray-600">with {apt.specialist}</p>
                          )}
                        </div>
                        <div className="text-right">
                          {apt.price && (
                            <p className="text-xs font-medium text-gray-900">${apt.price}</p>
                          )}
                          {apt.duration && (
                            <p className="text-xs text-gray-600">{apt.duration} min</p>
                          )}
                        </div>
                      </div>
                      
                      <div className="mt-2 pt-2 border-t border-red-200">
                        <div className="flex items-center justify-between mb-1">
                          <p className="text-xs text-gray-600 font-medium">Notes:</p>
                          <button
                            onClick={() => startEditingAppointmentNote(apt.calendar_event_id, apt.notes)}
                            className="text-xs text-blue-600 hover:text-blue-800"
                          >
                            <Edit2 className="h-3 w-3" />
                          </button>
                        </div>
                        
                        {editingAppointmentNote === apt.calendar_event_id ? (
                          <div className="space-y-2">
                            <textarea
                              ref={textareaRef}
                              value={editingNoteValue}
                              onChange={handleAppointmentNoteChange}
                              onKeyDown={(e) => handleAppointmentNoteKeyDown(e, apt.calendar_event_id)}
                              className="w-full text-xs p-2 border border-gray-300 rounded"
                              rows={2}
                              placeholder="Add notes for this appointment... (Ctrl+Enter to save, Esc to cancel)"
                              autoFocus
                            />
                            <div className="flex space-x-2">
                              <button
                                onClick={() => saveAppointmentNote(apt.calendar_event_id)}
                                className="text-xs bg-blue-600 text-white px-2 py-1 rounded hover:bg-blue-700"
                              >
                                Save
                              </button>
                              <button
                                onClick={cancelEditingAppointmentNote}
                                className="text-xs bg-gray-500 text-white px-2 py-1 rounded hover:bg-gray-600"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          <p className="text-xs text-gray-600 bg-white p-2 rounded border cursor-pointer hover:bg-gray-50"
                             onClick={() => startEditingAppointmentNote(apt.calendar_event_id, apt.notes)}>
                            {apt.notes || 'Click to add notes...'}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                  {selectedCustomer.past_appointments.length > 10 && (
                    <p className="text-xs text-gray-500 text-center py-2">
                      ... and {selectedCustomer.past_appointments.length - 10} more
                    </p>
                  )}
                </div>
              ) : (
                <p className="text-gray-500 text-center py-4 text-sm">No past appointments</p>
              )}
            </div>

            <div>
              <h3 className="text-md font-medium text-gray-900 mb-3">
                Upcoming Appointments ({selectedCustomer.upcoming_appointments?.length || 0})
              </h3>
              {selectedCustomer.upcoming_appointments?.length > 0 ? (
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {selectedCustomer.upcoming_appointments.map((apt) => (
                    <div key={apt.calendar_event_id} className="border border-green-200 bg-green-50 rounded-lg p-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <h4 className="font-medium text-gray-900 text-sm">{apt.service_name}</h4>
                          <p className="text-xs text-gray-600">
                            {formatDate(apt.appointment_date)} at {apt.appointment_time}
                          </p>
                          {apt.specialist && (
                            <p className="text-xs text-gray-600">with {apt.specialist}</p>
                          )}
                        </div>
                        <div className="text-right">
                          {apt.price && (
                            <p className="text-xs font-medium text-gray-900">${apt.price}</p>
                          )}
                          {apt.duration && (
                            <p className="text-xs text-gray-600">{apt.duration} min</p>
                          )}
                        </div>
                      </div>
                      
                      <div className="mt-2 pt-2 border-t border-green-200">
                        <div className="flex items-center justify-between mb-1">
                          <p className="text-xs text-gray-600 font-medium">Notes:</p>
                          <button
                            onClick={() => startEditingAppointmentNote(apt.calendar_event_id, apt.notes)}
                            className="text-xs text-blue-600 hover:text-blue-800"
                          >
                            <Edit2 className="h-3 w-3" />
                          </button>
                        </div>
                        
                        {editingAppointmentNote === apt.calendar_event_id ? (
                          <div className="space-y-2">
                            <textarea
                                ref={textareaRef}
                                value={editingNoteValue}
                                onChange={handleAppointmentNoteChange}
                                onKeyDown={(e) => handleAppointmentNoteKeyDown(e, apt.calendar_event_id)}
                                className="w-full text-xs p-2 border border-gray-300 rounded"
                                rows={2}
                                placeholder="Add notes for this appointment... (Ctrl+Enter to save, Esc to cancel)"
                                autoFocus
                              />
                            <div className="flex space-x-2">
                              <button
                                onClick={() => saveAppointmentNote(apt.calendar_event_id)}
                                className="text-xs bg-blue-600 text-white px-2 py-1 rounded hover:bg-blue-700"
                              >
                                Save
                              </button>
                              <button
                                onClick={cancelEditingAppointmentNote}
                                className="text-xs bg-gray-500 text-white px-2 py-1 rounded hover:bg-gray-600"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          <p className="text-xs text-gray-600 bg-white p-2 rounded border cursor-pointer hover:bg-gray-50"
                             onClick={() => startEditingAppointmentNote(apt.calendar_event_id, apt.notes)}>
                            {apt.notes || 'Click to add notes...'}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-gray-500 text-center py-4 text-sm">No upcoming appointments</p>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="p-6">
        {view === 'list' ? (
          <CustomerList
            navigate={navigate}
            fetchCustomers={fetchCustomers}
            loading={loading}
            setShowAddModal={setShowAddModal}
            searchTerm={searchTerm}
            setSearchTerm={setSearchTerm}
            sortBy={sortBy}
            setSortBy={setSortBy}
            sortOrder={sortOrder}
            setSortOrder={setSortOrder}
            customers={customers}
            handleViewCustomer={handleViewCustomer}
            showDeleteConfirmation={showDeleteConfirmation}
          />
        ) : (
          <CustomerDetail />
        )}
        
        <AddCustomerModal
          show={showAddModal}
          onClose={closeAddModal}
          newCustomer={newCustomer}
          setNewCustomer={setNewCustomer}
          phoneError={phoneError}
          setPhoneError={setPhoneError}
          onSubmit={handleCreateCustomer}
        />
        
        <DeleteConfirmationModal
          show={showDeleteModal}
          onClose={cancelDelete}
          customerToDelete={customerToDelete}
          onConfirm={handleDeleteCustomer}
        />
      </div>
    </div>
  );
};

export default Customers;