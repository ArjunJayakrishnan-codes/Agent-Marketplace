import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import AgentGrid from './AgentGrid';
import AgentModal from './AgentModal';
import MCPToolsGrid from './MCPToolsGrid';

function MainContent({
  currentUser,
  onLogout,
  agents,
  purchasedMap,
  accessStatus,
  logs,
  commHistory,
  authToken,
  apiBase,
  onLoadAgents,
  onLoadLogs,
  onLoadHistory
}) {
  const [activeTab, setActiveTab] = useState('exchange');
  const [directAgentId, setDirectAgentId] = useState(null);
  const [mcpServersById, setMcpServersById] = useState({});
  const [mcpRefreshVersion, setMcpRefreshVersion] = useState(0);

  // Check URL for direct agent access (without exposing tokens in URL)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const agentId = params.get('agent');
    if (agentId) {
      setDirectAgentId(agentId);
      // Clean up URL to remove any exposed tokens/keys
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  const loadMcpServers = useCallback(async () => {
    try {
      const res = await axios.get(`${apiBase}/users/me/mcp-purchases`, {
        headers: { Authorization: `Bearer ${authToken}` }
      });
      const byId = {};
      Object.entries(res.data.details || {}).forEach(([serverId, detail]) => {
        byId[serverId] = {
          id: detail.id || serverId,
          name: detail.server_name,
          description: detail.description || 'Installed MCP server',
          category: detail.category || 'tooling',
          status: detail.status || 'active',
          price: detail.price || 0,
          tools: detail.tools || []
        };
      });
      setMcpServersById(byId);
    } catch (error) {
      console.error('Failed to load MCP servers:', error);
    }
  }, [authToken, apiBase]);

  useEffect(() => {
    if (authToken) {
      loadMcpServers();
    }
  }, [authToken, loadMcpServers]);

  const handleMcpDataChanged = useCallback(async () => {
    await loadMcpServers();
    setMcpRefreshVersion((v) => v + 1);
  }, [loadMcpServers]);

  return (
    <div className="app-container">
      <header className="header">
        <div className="brand-lockup">
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
        <div className="user-info">
          <span>Logged in as: <strong>{currentUser}</strong></span>
          <button className="logout-btn" onClick={onLogout}>
            Logout
          </button>
        </div>
      </header>

      <main className="main-content">
        <div className="tabs">
          <button
            className={`tab-btn ${activeTab === 'exchange' ? 'active' : ''}`}
            onClick={() => setActiveTab('exchange')}
          >
            Agent Exchange
          </button>
          <button
            className={`tab-btn ${activeTab === 'mcp-tools' ? 'active' : ''}`}
            onClick={() => setActiveTab('mcp-tools')}
          >
            MCP Tools
          </button>
        </div>

        <div className={`tab-content ${activeTab === 'exchange' ? 'active' : ''}`}>
          <AgentGrid
            agents={agents}
            purchasedMap={purchasedMap}
            accessStatus={accessStatus}
            authToken={authToken}
            apiBase={apiBase}
            mcpServersById={mcpServersById}
            onLoadAgents={onLoadAgents}
            onMcpDataChanged={handleMcpDataChanged}
          />
        </div>

        <div className={`tab-content ${activeTab === 'mcp-tools' ? 'active' : ''}`}>
          <MCPToolsGrid
            authToken={authToken}
            apiBase={apiBase}
            refreshKey={mcpRefreshVersion}
            isActive={activeTab === 'mcp-tools'}
          />
        </div>

      </main>

      {directAgentId && agents.length > 0 && (
        <AgentModal
          agent={agents.find(a => a.id === directAgentId)}
          purchased={purchasedMap && purchasedMap[directAgentId]}
          accessStatus={accessStatus[directAgentId] || {}}
          authToken={authToken}
          apiBase={apiBase}
          mcpServersById={mcpServersById}
          onMcpDataChanged={handleMcpDataChanged}
          onClose={() => {
            setDirectAgentId(null);
            window.history.pushState({}, '', window.location.pathname);
          }}
          onLoadAgents={onLoadAgents}
        />
      )}
    </div>
  );
}

export default MainContent;
