import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';
import AuthModal from './components/AuthModal';
import MainContent from './components/MainContent';

const isLocalDevHost =
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1';
const API_BASE =
  process.env.REACT_APP_API_BASE_URL ||
  (isLocalDevHost ? 'http://localhost:8000' : '/api');

function App() {
  const [authToken, setAuthToken] = useState(localStorage.getItem('token'));
  const [currentUser, setCurrentUser] = useState(localStorage.getItem('user'));
  const [agents, setAgents] = useState([]);
  const [purchasedMap, setPurchasedMap] = useState({});
  const [accessStatus, setAccessStatus] = useState({});
  const [logs, setLogs] = useState([]);
  const [commHistory, setCommHistory] = useState([]);

  useEffect(() => {
    if (authToken) {
      loadAgents();
      loadCommunicationHistory();
      loadLogs();
    }
  }, [authToken]);

  const loadAgents = async () => {
    try {
      const res = await axios.get(`${API_BASE}/agents`, {
        headers: { 'Authorization': `Bearer ${authToken}` }
      });
      setAgents(res.data);

      const purchasesRes = await axios.get(`${API_BASE}/users/me/purchases`, {
        headers: { 'Authorization': `Bearer ${authToken}` }
      });
      setPurchasedMap(purchasesRes.data.purchases || {});

      const accessRes = await axios.get(`${API_BASE}/agents/my-access-status`, {
        headers: { 'Authorization': `Bearer ${authToken}` }
      });
      setAccessStatus(accessRes.data || {});
    } catch (error) {
      console.error('Failed to load agents:', error);
    }
  };

  const loadCommunicationHistory = async () => {
    try {
      const res = await axios.get(`${API_BASE}/agents/communication/history?limit=20`, {
        headers: { 'Authorization': `Bearer ${authToken}` }
      });
      setCommHistory(res.data);
    } catch (error) {
      console.error('Failed to load communication history:', error);
    }
  };

  const loadLogs = async () => {
    try {
      const res = await axios.get(`${API_BASE}/logs?limit=100`, {
        headers: { 'Authorization': `Bearer ${authToken}` }
      });
      setLogs(res.data);
    } catch (error) {
      console.error('Failed to load logs:', error);
    }
  };

  const handleLogin = (token, user) => {
    setAuthToken(token);
    setCurrentUser(user);
    localStorage.setItem('token', token);
    localStorage.setItem('user', user);
  };

  const handleLogout = () => {
    setAuthToken(null);
    setCurrentUser(null);
    localStorage.removeItem('token');
    localStorage.removeItem('user');
  };

  if (!authToken) {
    return <AuthModal onLogin={handleLogin} apiBase={API_BASE} />;
  }

  return (
    <MainContent
      currentUser={currentUser}
      onLogout={handleLogout}
      agents={agents}
      purchasedMap={purchasedMap}
      accessStatus={accessStatus}
      logs={logs}
      commHistory={commHistory}
      authToken={authToken}
      apiBase={API_BASE}
      onLoadAgents={loadAgents}
      onLoadLogs={loadLogs}
      onLoadHistory={loadCommunicationHistory}
    />
  );
}

export default App;
