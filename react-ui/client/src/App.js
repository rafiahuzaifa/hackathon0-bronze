import React, { useState, useEffect, useCallback } from 'react';
import { BrowserRouter, Routes, Route, Navigate, NavLink, useNavigate } from 'react-router-dom';
import Login from './components/Login';
import Dashboard from './components/Dashboard';
import Approvals from './components/Approvals';
import TaskCreator from './components/TaskCreator';
import LogsViewer from './components/LogsViewer';
import './App.css';

// ---- API client ----
export const API_BASE = '';  // proxied to :3001 in dev

export function apiFetch(path, opts = {}) {
  const token = localStorage.getItem('vault_token');
  return fetch(API_BASE + path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {}),
    },
    body: opts.body ? (typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body)) : undefined,
  }).then(async r => {
    if (r.status === 401) { localStorage.removeItem('vault_token'); window.location.href = '/login'; }
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  });
}

// ---- Auth context ----
export const AuthContext = React.createContext(null);

function useAuth() {
  const [token, setToken] = useState(localStorage.getItem('vault_token'));

  const login = useCallback((t) => {
    localStorage.setItem('vault_token', t);
    setToken(t);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('vault_token');
    setToken(null);
  }, []);

  return { token, login, logout, isLoggedIn: !!token };
}

// ---- Nav ----
function Nav({ logout }) {
  return (
    <nav className="nav">
      <span className="nav-brand">🤖 <span className="accent">AI Employee</span> Vault</span>
      <div className="nav-links">
        <NavLink to="/"         end>Dashboard</NavLink>
        <NavLink to="/approvals">Approvals</NavLink>
        <NavLink to="/tasks">   Tasks</NavLink>
        <NavLink to="/logs">    Logs</NavLink>
        <button className="btn-logout" onClick={logout}>Logout</button>
      </div>
    </nav>
  );
}

// ---- Protected route ----
function Private({ children, isLoggedIn }) {
  return isLoggedIn ? children : <Navigate to="/login" replace />;
}

export default function App() {
  const auth = useAuth();

  return (
    <AuthContext.Provider value={auth}>
      <BrowserRouter>
        {auth.isLoggedIn && <Nav logout={auth.logout} />}
        <div className="container">
          <Routes>
            <Route path="/login" element={
              auth.isLoggedIn ? <Navigate to="/" replace /> : <Login onLogin={auth.login} />
            } />
            <Route path="/" element={
              <Private isLoggedIn={auth.isLoggedIn}><Dashboard /></Private>
            } />
            <Route path="/approvals" element={
              <Private isLoggedIn={auth.isLoggedIn}><Approvals /></Private>
            } />
            <Route path="/tasks" element={
              <Private isLoggedIn={auth.isLoggedIn}><TaskCreator /></Private>
            } />
            <Route path="/logs" element={
              <Private isLoggedIn={auth.isLoggedIn}><LogsViewer /></Private>
            } />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </BrowserRouter>
    </AuthContext.Provider>
  );
}
