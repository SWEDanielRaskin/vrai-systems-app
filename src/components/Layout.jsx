import React, { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Calendar,
  Phone,
  MessageSquare,
  Settings,
  Bell,
  Package,
  LogOut,
} from 'lucide-react';

const Layout = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const location = useLocation();

  // Simple authentication - in production you'd want proper auth
  const handleLogin = (e) => {
    e.preventDefault();
    // Simple password check - replace with your desired password
    if (password === 'radiance2024') {
      setIsAuthenticated(true);
      localStorage.setItem('dashboard_authenticated', 'true');
      setError('');
    } else {
      setError('Invalid password');
    }
  };

  const handleLogout = () => {
    setIsAuthenticated(false);
    localStorage.removeItem('dashboard_authenticated');
  };

  useEffect(() => {
    // Check if already authenticated
    const auth = localStorage.getItem('dashboard_authenticated');
    if (auth === 'true') {
      setIsAuthenticated(true);
    }
  }, []);

  // Show login screen if not authenticated
  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-purple-50 to-blue-50 flex items-center justify-center">
        <div className="bg-white p-8 rounded-lg shadow-lg w-full max-w-md">
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold text-gray-900 mb-2">
              Radiance MD Dashboard
            </h1>
            <p className="text-gray-600">
              Enter password to access the dashboard
            </p>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password"
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                required
              />
            </div>

            {error && (
              <div className="text-red-600 text-sm text-center">{error}</div>
            )}

            <button
              type="submit"
              className="w-full bg-purple-600 text-white py-3 rounded-lg hover:bg-purple-700 transition-colors"
            >
              Access Dashboard
            </button>
          </form>
        </div>
      </div>
    );
  }

  // Main dashboard layout
  const isScrollLocked =
    location.pathname === '/messages' || location.pathname === '/voice-calls';
  return (
    <div className="flex h-screen bg-gray-50">
      {/* Main content - now full width, sidebar removed */}
      <div className={`flex-1${isScrollLocked ? '' : ' overflow-auto'}`}>
        <div className="p-6">{children}</div>
      </div>
    </div>
  );
};

export default Layout;
