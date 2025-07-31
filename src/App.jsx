import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Appointments from './pages/Appointments';
import VoiceCalls from './pages/VoiceCalls';
import Messages from './pages/Messages';
import Settings from './pages/Settings';
import Notifications from './pages/Notifications';
import ServicesManager from './pages/ServicesManager';
import Customers from './pages/Customers';
import MessageCustomizer from './pages/MessageCustomizer';

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/appointments" element={<Appointments />} />
          <Route path="/voice-calls" element={<VoiceCalls />} />
          <Route path="/messages" element={<Messages />} />
          <Route path="/customers" element={<Customers />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/settings/message-customizer" element={<MessageCustomizer />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/services-manager" element={<ServicesManager />} />
        </Routes>
      </Layout>
    </Router>
  );
}

export default App;
