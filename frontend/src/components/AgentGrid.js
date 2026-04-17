import React, { useState } from 'react';
import AgentModal from './AgentModal';

function AgentGrid({
  agents,
  purchasedMap,
  accessStatus,
  authToken,
  apiBase,
  mcpServersById = {},
  onMcpDataChanged,
  onLoadAgents
}) {
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [showModal, setShowModal] = useState(false);

  const getAgentMcpServers = (agent) => {
    if (!agent?.mcp_server_ids || agent.mcp_server_ids.length === 0) {
      return [];
    }
    return agent.mcp_server_ids
      .map((serverId) => mcpServersById[serverId])
      .filter(Boolean);
  };

  const handleAgentClick = (agent) => {
    setSelectedAgent(agent);
    setShowModal(true);
  };

  const handleCloseModal = () => {
    setShowModal(false);
    setTimeout(() => setSelectedAgent(null), 300);
  };

  const getAgentBrand = (agent) => {
    const map = {
      'agent-001': { tone: 'catalog' },
      'agent-002': { tone: 'revenue' },
      'agent-003': { tone: 'lifecycle' },
      'agent-004': { tone: 'artist' },
      'agent-005': { tone: 'ops' }
    };
    if (map[agent.id]) {
      return map[agent.id];
    }
    return { tone: 'catalog' };
  };

  const renderAgentGlyph = (tone) => {
    if (tone === 'catalog') {
      return (
        <svg viewBox="0 0 24 24" className="agent-logo-glyph" role="img" focusable="false" aria-hidden="true">
          <path d="M4 5a2 2 0 0 1 2-2h5v18H6a2 2 0 0 1-2-2V5Zm9-2h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5V3Zm-6 3v1h2V6H7Zm8 0v1h2V6h-2Z" />
        </svg>
      );
    }
    if (tone === 'revenue') {
      return (
        <svg viewBox="0 0 24 24" className="agent-logo-glyph" role="img" focusable="false" aria-hidden="true">
          <path d="M4 18h16v2H4v-2Zm2-2V9h3l2 3 3-6 4 10h-3l-1-3-2 3-2-3-1 3H6Z" />
        </svg>
      );
    }
    if (tone === 'lifecycle') {
      return (
        <svg viewBox="0 0 24 24" className="agent-logo-glyph" role="img" focusable="false" aria-hidden="true">
          <path d="M12 2a10 10 0 1 1-9.2 6H6V5L1 9l5 4V10H3.3A8 8 0 1 0 12 4v2Z" />
        </svg>
      );
    }
    if (tone === 'artist') {
      return (
        <svg viewBox="0 0 24 24" className="agent-logo-glyph" role="img" focusable="false" aria-hidden="true">
          <path d="M18 4v10.5a2.5 2.5 0 1 1-2-2.45V6.3l-8 1.8v8.4a2.5 2.5 0 1 1-2-2.45V6.5l12-2.5Z" />
        </svg>
      );
    }
    return (
      <svg viewBox="0 0 24 24" className="agent-logo-glyph" role="img" focusable="false" aria-hidden="true">
        <path d="M10 2h4v3h-4V2Zm-5 5h14v4h-2v9h-4v-6h-2v6H7v-9H5V7Z" />
      </svg>
    );
  };

  return (
    <>
      <div className="agent-grid">
        {agents.map((agent) => {
          const status = accessStatus[agent.id] || {};
          const isPurchased = status.is_purchased;
          const mcpServers = getAgentMcpServers(agent);
          const brand = getAgentBrand(agent);

          return (
            <div
              key={agent.id}
              className="agent-card"
              onClick={() => handleAgentClick(agent)}
            >
              <div className="agent-card-content">
                <div className="agent-header-row">
                  <div className={`agent-logo-mark agent-logo-${brand.tone}`}>
                    {renderAgentGlyph(brand.tone)}
                  </div>
                  <div>
                    <h3 className="agent-name">{agent.name}</h3>
                    <p className="agent-description">{agent.description}</p>
                  </div>
                </div>

                <div className="agent-purpose">
                  <strong>Purpose:</strong> {agent.purpose}
                </div>

                <div className="capabilities">
                  {agent.capabilities.map((cap, idx) => (
                    <span key={idx} className="capability-badge">
                      {cap}
                    </span>
                  ))}
                </div>

                <div className="agent-status">
                  {agent.status}
                </div>

                <div className="agent-mcp-section">
                  <div style={{ fontSize: '0.8rem', color: '#5f6f80', marginBottom: '0.5rem' }}>
                    MCP Tools
                  </div>
                  {mcpServers.length > 0 ? (
                    <div style={{ display: 'grid', gap: '0.5rem' }}>
                      {mcpServers.map((server) => (
                        <div
                          key={server.id}
                          style={{
                            border: '1px solid #ded7ca',
                            borderRadius: '0.375rem',
                            padding: '0.5rem',
                            backgroundColor: '#ffffff'
                          }}
                        >
                          <div style={{ fontSize: '0.8rem', color: '#1f5a78', fontWeight: 600 }}>
                            {server.name}
                          </div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', marginTop: '0.35rem' }}>
                            {server.tools.slice(0, 3).map((tool) => (
                              <span
                                key={tool}
                                style={{
                                  padding: '0.15rem 0.4rem',
                                  fontSize: '0.7rem',
                                  border: '1px solid #c8dce9',
                                  borderRadius: '9999px',
                                  color: '#1f5a78',
                                  backgroundColor: '#e8f1f7'
                                }}
                              >
                                {tool}
                              </span>
                            ))}
                            {server.tools.length > 3 && (
                              <span style={{ fontSize: '0.7rem', color: '#5f6f80' }}>
                                +{server.tools.length - 3} more
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <span style={{ fontSize: '0.75rem', color: '#5f6f80' }}>
                      No MCP tools linked
                    </span>
                  )}
                </div>
              </div>
              <div className="agent-ownership">
                {isPurchased ? (
                  <span style={{ color: '#86efac' }}>✓ Owned</span>
                ) : (
                  <span>Purchase required</span>
                )}
              </div>
              <div className="agent-card-actions">
                <span style={{ fontSize: '0.75rem', color: '#f97316' }}>
                  Click for details
                </span>
                {isPurchased ? (
                  <button 
                    className="btn btn-success" 
                    style={{ marginLeft: 'auto' }}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleAgentClick(agent);
                    }}
                    title="Click to view access details and credentials"
                  >
                    Access
                  </button>
                ) : (
                  <button 
                    className="btn btn-primary" 
                    style={{ marginLeft: 'auto' }}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleAgentClick(agent);
                    }}
                  >
                    Buy
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {showModal && selectedAgent && (
        <AgentModal
          agent={selectedAgent}
          purchased={purchasedMap && purchasedMap[selectedAgent.id]}
          accessStatus={accessStatus[selectedAgent.id] || {}}
          authToken={authToken}
          apiBase={apiBase}
          mcpServersById={mcpServersById}
          onMcpDataChanged={onMcpDataChanged}
          onClose={handleCloseModal}
          onLoadAgents={onLoadAgents}
        />
      )}
    </>
  );
}

export default AgentGrid;
