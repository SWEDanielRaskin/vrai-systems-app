import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Upload, ExternalLink, X } from 'lucide-react';

const defaultColumns = [
  { key: 'name', label: 'Service Name' },
  { key: 'price', label: 'Price ($)' },
  { key: 'duration', label: 'Duration (min)' },
  { key: 'requires_deposit', label: 'Deposit Required' },
  { key: 'deposit_amount', label: 'Deposit Amount ($)' },
  { key: 'description', label: 'Description' },
];

const TEMPLATE_URL =
  'https://docs.google.com/spreadsheets/d/1cdj6Fhl7g5OEnCOqMnA4t2VcxQ0PX_xFqrdiN5D2iTI/edit?usp=sharing';

export default function ServicesManager() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState([]);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState('');
  const [error, setError] = useState('');
  const [step, setStep] = useState(1); // 1: upload, 2: preview/edit, 3: done
  const [services, setServices] = useState([]);
  const [servicesLoading, setServicesLoading] = useState(false);
  const [servicesError, setServicesError] = useState('');
  const [editIdx, setEditIdx] = useState(null);
  const [editRow, setEditRow] = useState(null);
  const [addRow, setAddRow] = useState({
    name: '',
    price: 0,
    duration: 0,
    requires_deposit: true,
    deposit_amount: 50,
    description: '',
  });
  const [addMode, setAddMode] = useState(false);
  const fileInputRef = React.useRef();
  const [showModal, setShowModal] = useState(false);
  const [showDeleteAllConfirm, setShowDeleteAllConfirm] = useState(false);

  // Handle file selection
  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
    setError('');
    setSuccess('');
  };

  // Upload and parse file
  const handleUpload = async () => {
    if (!file) return setError('Please select a file.');
    setLoading(true);
    setError('');
    setSuccess('');
    try {
      // 1. Upload file
      const formData = new FormData();
      formData.append('file', file);
      const uploadRes = await axios.post(
        '/api/services/upload-document',
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
        }
      );
      if (!uploadRes.data.success)
        throw new Error(uploadRes.data.error || 'Upload failed');
      // 2. Parse file
      const parseRes = await axios.post('/api/services/parse-document', {
        file_path: uploadRes.data.file_path,
      });
      if (!parseRes.data.success)
        throw new Error(parseRes.data.error || 'Parse failed');
      // 3. Save parsed services directly to DB
      const saveRes = await axios.post('/api/services/save', {
        services: parseRes.data.services,
      });
      if (!saveRes.data.success)
        throw new Error(saveRes.data.error || 'Save failed');
      setSuccess(`Saved ${saveRes.data.added} services!`);
      setStep(1); // Reset step
      setFile(null);
      fetchServices(); // Refresh table
    } catch (err) {
      if (err.response && err.response.status === 400) {
        setError(
          <span>
            The file structure is incorrect. Please{' '}
            <span
              className="underline text-primary-700 cursor-pointer"
              onClick={() => window.open(TEMPLATE_URL, '_blank')}
            >
              reference the template ↗
            </span>
            .
          </span>
        );
      } else {
        setError(err.message || 'Error uploading/parsing/saving file.');
      }
    } finally {
      setLoading(false);
    }
  };

  // Edit a cell in the preview table
  const handleEdit = (idx, key, value) => {
    setPreview((prev) => {
      const updated = [...prev];
      updated[idx] = { ...updated[idx], [key]: value };
      return updated;
    });
  };

  // Remove a row from the preview
  const handleRemove = (idx) => {
    setPreview((prev) => prev.filter((_, i) => i !== idx));
  };

  // Save reviewed services to DB
  const handleSave = async () => {
    setLoading(true);
    setError('');
    setSuccess('');
    try {
      const saveRes = await axios.post('/api/services/save', {
        services: preview,
      });
      if (!saveRes.data.success)
        throw new Error(saveRes.data.error || 'Save failed');
      setSuccess(`Saved ${saveRes.data.added} services!`);
      setStep(3);
    } catch (err) {
      setError(err.message || 'Error saving services.');
    } finally {
      setLoading(false);
    }
  };

  // Fetch all services for persistent table
  const fetchServices = async () => {
    setServicesLoading(true);
    setServicesError('');
    try {
      const res = await axios.get('/api/services');
      if (!res.data.success)
        throw new Error(res.data.error || 'Failed to fetch services');
      setServices(res.data.services);
    } catch (err) {
      setServicesError(err.message || 'Error fetching services');
    } finally {
      setServicesLoading(false);
    }
  };

  useEffect(() => {
    fetchServices();
  }, [step]); // refetch after upload/save

  // Start editing a row
  const handleEditRow = (idx) => {
    setEditIdx(idx);
    setEditRow({ ...services[idx] });
  };
  // Save edit
  const handleSaveEdit = async (id) => {
    try {
      await axios.put(`/api/services/${id}`, editRow);
      setEditIdx(null);
      setEditRow(null);
      fetchServices();
      setSuccess('Service updated!');
    } catch (err) {
      setError(err.message || 'Error updating service.');
    }
  };
  // Cancel edit
  const handleCancelEdit = () => {
    setEditIdx(null);
    setEditRow(null);
  };
  // Delete row
  const handleDelete = async (id) => {
    try {
      await axios.delete(`/api/services/${id}`);
      fetchServices();
      setSuccess('Service deleted!');
    } catch (err) {
      setError(err.message || 'Error deleting service.');
    }
  };
  // Add new service
  const handleAddService = async () => {
    try {
      await axios.post('/api/services', addRow);
      setAddRow({
        name: '',
        price: 0,
        duration: 0,
        requires_deposit: true,
        deposit_amount: 50,
        description: '',
      });
      setAddMode(false);
      fetchServices();
      setSuccess('Service added!');
    } catch (err) {
      setError(err.message || 'Error adding service.');
    }
  };

  // Update deleteAllServices to only delete and close the dialog
  const confirmDeleteAllServices = async () => {
    try {
      await Promise.all(
        services.map((s) => axios.delete(`/api/services/${s.id}`))
      );
      fetchServices();
      setSuccess('All services deleted!');
      setShowDeleteAllConfirm(false);
    } catch (err) {
      setError('Error deleting all services.');
      setShowDeleteAllConfirm(false);
    }
  };

  useEffect(() => {
    if (showModal) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'auto';
    }
    return () => {
      document.body.style.overflow = 'auto';
    };
  }, [showModal]);

  // Render
  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold text-gray-900">
          Services Manager
        </h3>
      </div>
      {/* Help/Instructions Section */}
      <div className="mb-6 p-4 bg-primary-50 rounded-lg border border-primary-200 flex flex-col md:flex-row md:items-center md:justify-between">
        <div className="mb-2 md:mb-0">
          <div className="font-semibold text-primary-700 mb-1">
            How to Upload Services
          </div>
          <ol className="list-decimal list-inside text-sm text-gray-700 space-y-1">
            <div>
              You can manually add services by clicking{' '}
              <b>View/Edit Added Services</b> → <b>Add New Service</b>
            </div>
            <div> -or- </div>
            <li>
              Make a copy of the{' '}
              <span
                className="underline text-primary-700 cursor-pointer"
                onClick={() => window.open(TEMPLATE_URL, '_blank')}
              >
                Services Spreadsheet Template
              </span>
              .
            </li>
            <li>
              Enter your service information in the table (see headers below).
            </li>
            <li>
              Save/download as <b>CSV</b> or <b>XLSX</b> file.
            </li>
            <li>Upload it here using the form below.</li>
          </ol>
        </div>
        <button
          className="btn-secondary flex items-center space-x-2 mt-3 md:mt-0"
          onClick={() => window.open(TEMPLATE_URL, '_blank')}
        >
          <ExternalLink className="h-4 w-4" />
          <span>Open Template</span>
        </button>
      </div>
      {/* Upload Controls */}
      {step === 1 && (
        <div className="flex items-center space-x-4 mb-8">
          <input
            type="file"
            accept=".csv,.xlsx"
            ref={fileInputRef}
            className="hidden"
            onChange={handleFileChange}
          />
          <button
            className="btn-secondary flex items-center space-x-2"
            onClick={() => fileInputRef.current && fileInputRef.current.click()}
          >
            <Upload className="h-4 w-4" />
            <span>Choose File</span>
          </button>
          <span className="text-gray-700 text-sm min-w-[120px]">
            {file ? file.name : 'No file chosen'}
          </span>
          <button
            className="btn-primary flex items-center space-x-2"
            onClick={handleUpload}
            disabled={loading}
          >
            {loading ? 'Uploading...' : 'Upload & Preview'}
          </button>
        </div>
      )}
      {step === 2 && (
        <div className="space-y-4">
          <h3 className="text-lg font-semibold">Preview & Edit Services</h3>
          <div className="overflow-x-auto">
            <table className="min-w-full border">
              <thead>
                <tr>
                  {defaultColumns.map((col) => (
                    <th key={col.key} className="border px-2 py-1 bg-gray-100">
                      {col.label}
                    </th>
                  ))}
                  <th className="border px-2 py-1 bg-gray-100">Remove</th>
                </tr>
              </thead>
              <tbody>
                {preview.map((row, idx) => (
                  <tr key={idx}>
                    {defaultColumns.map((col) => (
                      <td key={col.key} className="border px-2 py-1">
                        {col.key === 'requires_deposit' ? (
                          <input
                            type="checkbox"
                            checked={!!row[col.key]}
                            onChange={(e) =>
                              handleEdit(idx, col.key, e.target.checked)
                            }
                          />
                        ) : (
                          <input
                            type={
                              col.key === 'price' ||
                              col.key === 'deposit_amount' ||
                              col.key === 'duration'
                                ? 'number'
                                : 'text'
                            }
                            value={row[col.key] ?? ''}
                            onChange={(e) =>
                              handleEdit(
                                idx,
                                col.key,
                                col.key === 'price' ||
                                  col.key === 'deposit_amount' ||
                                  col.key === 'duration'
                                  ? Number(e.target.value)
                                  : e.target.value
                              )
                            }
                            className="w-full px-1 py-0.5 border rounded"
                          />
                        )}
                      </td>
                    ))}
                    <td className="border px-2 py-1 text-center">
                      <button
                        className="text-red-500"
                        onClick={() => handleRemove(idx)}
                      >
                        &times;
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            className="btn-primary mt-4"
            onClick={handleSave}
            disabled={loading || preview.length === 0}
          >
            {loading ? 'Saving...' : 'Save to Database'}
          </button>
        </div>
      )}
      {step === 3 && (
        <div className="space-y-4">
          <div className="text-green-600 font-semibold">{success}</div>
          <button
            className="btn-secondary"
            onClick={() => {
              setStep(1);
              setPreview([]);
              setFile(null);
              setSuccess('');
              setError('');
            }}
          >
            Upload Another
          </button>
        </div>
      )}
      {error && <div className="text-red-600 mt-4">{error}</div>}
      {success && step !== 3 && (
        <div className="text-green-600 mt-4">{success}</div>
      )}
      {/* View/Edit Services Button */}
      <button className="btn-primary mb-8" onClick={() => setShowModal(true)}>
        {`View/Edit Added Services (${services.length})`}
      </button>
      {/* Modal for Services Table */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-40">
          <div className="bg-white rounded-lg shadow-lg p-6 w-full max-w-5xl relative overflow-x-auto">
            <button
              className="absolute top-4 right-4 text-gray-500 hover:text-gray-700"
              onClick={() => setShowModal(false)}
            >
              <X className="h-6 w-6" />
            </button>
            <h3 className="text-xl font-semibold mb-4">Current Services</h3>
            <div className="flex justify-end mb-2">
              <button
                className="bg-red-600 hover:bg-red-700 text-white font-medium px-2 py-1 rounded-lg text-sm transition-colors duration-200"
                style={{ fontSize: '0.85rem' }}
                onClick={() => setShowDeleteAllConfirm(true)}
              >
                Delete All Services
              </button>
            </div>
            {showDeleteAllConfirm && (
              <div className="fixed inset-0 z-60 flex items-center justify-center bg-black bg-opacity-30">
                <div className="bg-white rounded-lg shadow-lg p-6 w-full max-w-xs mx-auto flex flex-col items-center">
                  <div className="text-lg font-semibold mb-4 text-center">
                    Are you sure you want to delete all services?
                  </div>
                  <div className="flex space-x-4">
                    <button
                      className="bg-red-600 hover:bg-red-700 text-white font-medium px-4 py-2 rounded-lg text-sm"
                      onClick={confirmDeleteAllServices}
                    >
                      Delete
                    </button>
                    <button
                      className="btn-secondary px-4 py-2 text-sm"
                      onClick={() => setShowDeleteAllConfirm(false)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            )}
            {/* Scrollable table area */}
            <div style={{ maxHeight: '70vh', overflowY: 'auto' }}>
              {servicesLoading ? (
                <div>Loading...</div>
              ) : servicesError ? (
                <div className="text-red-600">{servicesError}</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full border">
                    <thead>
                      <tr>
                        {defaultColumns.map((col) => (
                          <th
                            key={col.key}
                            className="border px-2 py-1 bg-gray-100"
                          >
                            {col.label}
                          </th>
                        ))}
                        <th className="border px-2 py-1 bg-gray-100">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {services.map((row, idx) => (
                        <tr key={row.id}>
                          {editIdx === idx
                            ? defaultColumns.map((col) => (
                                <td key={col.key} className="border px-2 py-1">
                                  {col.key === 'requires_deposit' ? (
                                    <input
                                      type="checkbox"
                                      checked={!!editRow[col.key]}
                                      onChange={(e) =>
                                        setEditRow({
                                          ...editRow,
                                          [col.key]: e.target.checked,
                                        })
                                      }
                                    />
                                  ) : (
                                    <input
                                      type={
                                        col.key === 'price' ||
                                        col.key === 'deposit_amount' ||
                                        col.key === 'duration'
                                          ? 'number'
                                          : 'text'
                                      }
                                      value={editRow[col.key] ?? ''}
                                      onChange={(e) =>
                                        setEditRow({
                                          ...editRow,
                                          [col.key]:
                                            col.key === 'price' ||
                                            col.key === 'deposit_amount' ||
                                            col.key === 'duration'
                                              ? Number(e.target.value)
                                              : e.target.value,
                                        })
                                      }
                                      className="w-full px-1 py-0.5 border rounded"
                                    />
                                  )}
                                </td>
                              ))
                            : defaultColumns.map((col) => (
                                <td key={col.key} className="border px-2 py-1">
                                  {col.key === 'requires_deposit'
                                    ? row[col.key]
                                      ? 'Yes'
                                      : 'No'
                                    : row[col.key]}
                                </td>
                              ))}
                          <td className="border px-2 py-1">
                            <div className="flex flex-row items-center gap-2 justify-center">
                              {editIdx === idx ? (
                                <>
                                  <button
                                    className="btn-primary mr-2"
                                    onClick={() => handleSaveEdit(row.id)}
                                  >
                                    Save
                                  </button>
                                  <button
                                    className="btn-secondary"
                                    onClick={handleCancelEdit}
                                  >
                                    Cancel
                                  </button>
                                </>
                              ) : (
                                <>
                                  <button
                                    className="btn-secondary"
                                    onClick={() => handleEditRow(idx)}
                                  >
                                    Edit
                                  </button>
                                  <button
                                    className="text-red-500 ml-2"
                                    onClick={() => handleDelete(row.id)}
                                  >
                                    &times;
                                  </button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                      {addMode ? (
                        <tr>
                          {defaultColumns.map((col) => (
                            <td key={col.key} className="border px-2 py-1">
                              {col.key === 'requires_deposit' ? (
                                <input
                                  type="checkbox"
                                  checked={!!addRow[col.key]}
                                  onChange={(e) =>
                                    setAddRow({
                                      ...addRow,
                                      [col.key]: e.target.checked,
                                    })
                                  }
                                />
                              ) : (
                                <input
                                  type={
                                    col.key === 'price' ||
                                    col.key === 'deposit_amount' ||
                                    col.key === 'duration'
                                      ? 'number'
                                      : 'text'
                                  }
                                  value={addRow[col.key] ?? ''}
                                  onChange={(e) =>
                                    setAddRow({
                                      ...addRow,
                                      [col.key]:
                                        col.key === 'price' ||
                                        col.key === 'deposit_amount' ||
                                        col.key === 'duration'
                                          ? Number(e.target.value)
                                          : e.target.value,
                                    })
                                  }
                                  className="w-full px-1 py-0.5 border rounded"
                                />
                              )}
                            </td>
                          ))}
                          <td className="border px-2 py-1 text-center">
                            <button
                              className="btn-primary mr-2"
                              onClick={handleAddService}
                            >
                              Add
                            </button>
                            <button
                              className="btn-secondary"
                              onClick={() => setAddMode(false)}
                            >
                              Cancel
                            </button>
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            {/* Add New Service button always visible below table */}
            {!addMode && (
              <button
                className="btn-primary mt-4"
                onClick={() => setAddMode(true)}
              >
                Add New Service
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
