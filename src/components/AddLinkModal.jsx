import React, { useState } from 'react';
import { X, Link, Plus, Loader2 } from 'lucide-react';

// New multi-select modal for page selection
const COMMON_PATHS = [
  '/about',
  '/services',
  '/contact',
  '/team',
  '/staff',
  '/appointments',
  '/book',
  '/faq',
  '/hours',
  '/location',
];

const SelectPagesModal = ({ isOpen, onClose, pages, onConfirm }) => {
  // Find the root domain (first page with no path after domain)
  const rootPage = pages.find((p) => {
    try {
      const url = new URL(p.url);
      return url.pathname === '/' || url.pathname === '';
    } catch {
      return false;
    }
  });
  const [selected, setSelected] = useState(() => {
    // Pre-select root domain and common pages
    const preselect = [];
    if (rootPage) preselect.push(rootPage.url);
    preselect.push(
      ...pages
        .filter((p) =>
          COMMON_PATHS.some((path) => p.url.toLowerCase().includes(path))
        )
        .map((p) => p.url)
    );
    // Remove duplicates
    return Array.from(new Set(preselect));
  });

  const toggle = (url) => {
    setSelected((sel) =>
      sel.includes(url) ? sel.filter((u) => u !== url) : [...sel, url]
    );
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4">
        <div className="flex items-center justify-between p-6 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">
            Select Pages to Scrape
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="h-5 w-5 text-gray-600" />
          </button>
        </div>
        <div className="p-6 max-h-96 overflow-y-auto">
          {pages.length === 0 && <p>No pages found.</p>}
          <ul className="space-y-2">
            {pages.map((page, i) => (
              <li key={page.url} className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={selected.includes(page.url)}
                  onChange={() => toggle(page.url)}
                  disabled={!!page.error}
                />
                <span className="font-medium text-gray-800">
                  {page.title || page.url}
                </span>
                <span className="text-xs text-gray-500">{page.url}</span>
                {page.error && (
                  <span className="text-xs text-red-500 ml-2">
                    (Failed to load)
                  </span>
                )}
              </li>
            ))}
          </ul>
          <div className="mt-4 text-sm text-gray-600">
            <span className="font-semibold">Tip:</span> Only select pages that
            contain useful business information (services, about, contact, etc).
          </div>
        </div>
        <div className="flex items-center justify-end space-x-3 p-6 border-t border-gray-200">
          <button onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button
            className="bg-primary-600 hover:bg-primary-700 text-white font-medium px-4 py-2 rounded-lg transition-colors duration-200 flex items-center space-x-2"
            onClick={() => onConfirm(selected)}
            disabled={selected.length === 0}
          >
            <Plus className="h-4 w-4" />
            <span>Add Selected Pages</span>
          </button>
        </div>
      </div>
    </div>
  );
};

const AddLinkModal = ({ isOpen, onClose, onAdd }) => {
  const [url, setUrl] = useState('');
  const [description, setDescription] = useState('');
  const [errors, setErrors] = useState({});
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [pages, setPages] = useState([]);

  const validateForm = () => {
    const newErrors = {};

    if (!url.trim()) {
      newErrors.url = 'URL is required';
    } else if (!isValidUrl(url.trim())) {
      newErrors.url = 'Please enter a valid URL';
    }

    if (!description.trim()) {
      newErrors.description = 'Description is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const isValidUrl = (string) => {
    try {
      new URL(string);
      return true;
    } catch (_) {
      // Try adding https:// if no protocol is specified
      try {
        new URL(`https://${string}`);
        return true;
      } catch (_) {
        return false;
      }
    }
  };

  const formatUrl = (url) => {
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      return `https://${url}`;
    }
    return url;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validateForm()) return;
    setLoading(true);
    setErrors({});
    try {
      const formattedUrl = formatUrl(url.trim());
      const res = await fetch('/api/extract_links', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: formattedUrl }),
      });
      const data = await res.json();
      if (data.links) {
        setPages(data.links);
        setStep(2);
      } else {
        setErrors({ url: 'Failed to extract pages from this site.' });
      }
    } catch (err) {
      setErrors({ url: 'Failed to extract pages. Please try again.' });
    } finally {
      setLoading(false);
    }
  };

  const handlePagesConfirm = (selectedUrls) => {
    if (selectedUrls.length === 0) return;
    onAdd({
      urls: selectedUrls,
      description: description.trim(),
      mainUrl: formatUrl(url.trim()),
    });
    // Reset state
    setUrl('');
    setDescription('');
    setErrors({});
    setStep(1);
    setPages([]);
    onClose();
  };

  const handleClose = () => {
    setUrl('');
    setDescription('');
    setErrors({});
    setStep(1);
    setPages([]);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Step 1: Enter URL/Description */}
      {step === 1 && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4">
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-gray-200">
              <div className="flex items-center space-x-3">
                <div className="bg-primary-100 rounded-full p-2">
                  <Link className="h-5 w-5 text-primary-600" />
                </div>
                <h2 className="text-lg font-semibold text-gray-900">
                  Add Link
                </h2>
              </div>
              <button
                onClick={handleClose}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X className="h-5 w-5 text-gray-600" />
              </button>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              {/* URL Input */}
              <div>
                <label
                  htmlFor="url"
                  className="block text-sm font-medium text-gray-700 mb-2"
                >
                  URL <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  id="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://example.com or example.com"
                  className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent ${
                    errors.url ? 'border-red-300' : 'border-gray-300'
                  }`}
                  disabled={loading}
                />
                {errors.url && (
                  <p className="mt-1 text-sm text-red-600">{errors.url}</p>
                )}
              </div>

              {/* Description Input */}
              <div>
                <label
                  htmlFor="description"
                  className="block text-sm font-medium text-gray-700 mb-2"
                >
                  Description <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="e.g., Company Website, Service Menu, etc."
                  className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent ${
                    errors.description ? 'border-red-300' : 'border-gray-300'
                  }`}
                  disabled={loading}
                />
                {errors.description && (
                  <p className="mt-1 text-sm text-red-600">
                    {errors.description}
                  </p>
                )}
              </div>

              {/* Help Text */}
              <div className="bg-blue-50 rounded-lg p-3">
                <p className="text-sm text-blue-800">
                  💡 <strong>Tip:</strong> The AI will use this link as a
                  reference source. Make sure the URL is accessible and contains
                  relevant information for customer inquiries.
                </p>
              </div>

              {/* Buttons */}
              <div className="flex items-center justify-end space-x-3 pt-4">
                <button
                  type="button"
                  onClick={handleClose}
                  className="btn-secondary"
                  disabled={loading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="bg-primary-600 hover:bg-primary-700 text-white font-medium px-4 py-2 rounded-lg transition-colors duration-200 flex items-center space-x-2"
                  disabled={loading}
                >
                  {loading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Plus className="h-4 w-4" />
                  )}
                  <span>{loading ? 'Fetching Pages...' : 'Add Link'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* Step 2: Select Pages */}
      {step === 2 && (
        <SelectPagesModal
          isOpen={true}
          onClose={handleClose}
          pages={pages}
          onConfirm={handlePagesConfirm}
        />
      )}
    </>
  );
};

export default AddLinkModal;
