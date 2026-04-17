import React, { useState } from 'react';
import axios from 'axios';

function AuthModal({ onLogin, apiBase }) {
  const [loginTab, setLoginTab] = useState(true);
  const [loginUsername, setLoginUsername] = useState('admin');
  const [loginPassword, setLoginPassword] = useState('admin123');
  const [registerUsername, setRegisterUsername] = useState('');
  const [registerPassword, setRegisterPassword] = useState('');
  const [error, setError] = useState('');

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const res = await axios.post(`${apiBase}/auth/login`, {
        username: loginUsername,
        password: loginPassword
      });
      onLogin(res.data.access_token, res.data.user);
    } catch (err) {
      setError('Login failed: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    try {
      const res = await axios.post(`${apiBase}/auth/register`, {
        username: registerUsername,
        password: registerPassword
      });
      onLogin(res.data.access_token, res.data.user);
    } catch (err) {
      setError('Registration failed: ' + (err.response?.data?.detail || err.message));
    }
  };

  return (
    <div className="auth-modal">
      <div className="auth-container">
        <div className="brand-lockup" style={{ marginBottom: '1rem' }}>
          <div className="brand-logo" aria-hidden="true">
            <svg viewBox="0 0 24 24" role="img" focusable="false">
              <path d="M12 2 3 6v6c0 5.2 3.6 9.9 9 11 5.4-1.1 9-5.8 9-11V6l-9-4Zm0 3.1 5.9 2.6v4.1c0 3.9-2.5 7.5-5.9 8.8-3.4-1.3-5.9-4.9-5.9-8.8V7.7L12 5.1Zm-2 3.4h4.2c1.9 0 3.1 1.2 3.1 2.9 0 1.1-.6 2-1.7 2.5l2 3.2h-2.7l-1.6-2.7h-1.1V17H10V8.5Zm2.2 2.1H10v1.8h2.2c.8 0 1.3-.4 1.3-.9 0-.6-.5-.9-1.3-.9Z" />
            </svg>
          </div>
          <div className="brand-text">
            <span className="brand-title">Atlas Agents</span>
            <span className="brand-kicker">Enterprise Control Plane</span>
          </div>
        </div>
        <h1 className="auth-title">Secure Sign In</h1>
        
        <div className="auth-tabs">
          <button
            className={`auth-tab ${loginTab ? 'active' : ''}`}
            onClick={() => setLoginTab(true)}
          >
            Login
          </button>
          <button
            className={`auth-tab ${!loginTab ? 'active' : ''}`}
            onClick={() => setLoginTab(false)}
          >
            Register
          </button>
        </div>

        {error && <div style={{ color: '#ff6b6b', marginBottom: '1rem' }}>{error}</div>}

        {loginTab ? (
          <form className="auth-form active" onSubmit={handleLogin}>
            <input
              type="text"
              placeholder="Username"
              value={loginUsername}
              onChange={(e) => setLoginUsername(e.target.value)}
              required
            />
            <input
              type="password"
              placeholder="Password"
              value={loginPassword}
              onChange={(e) => setLoginPassword(e.target.value)}
              required
            />
            <button type="submit">Login</button>
            <p style={{ fontSize: '0.8rem', color: '#5f6f80', marginTop: '1rem' }}>
              Example: admin/admin123 or user1/user123
            </p>
          </form>
        ) : (
          <form className="auth-form active" onSubmit={handleRegister}>
            <input
              type="text"
              placeholder="Username"
              value={registerUsername}
              onChange={(e) => setRegisterUsername(e.target.value)}
              required
            />
            <input
              type="password"
              placeholder="Password"
              value={registerPassword}
              onChange={(e) => setRegisterPassword(e.target.value)}
              required
            />
            <button type="submit">Register</button>
          </form>
        )}
      </div>
    </div>
  );
}

export default AuthModal;
