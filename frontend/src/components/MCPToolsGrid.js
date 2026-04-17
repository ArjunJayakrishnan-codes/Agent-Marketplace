import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

function MCPToolsGrid({ authToken, apiBase, refreshKey, isActive }) {
  const [mcpServers, setMcpServers] = useState([]);
  const [purchasedServers, setPurchasedServers] = useState({});
  const [agentNames, setAgentNames] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedTool, setSelectedTool] = useState({});
  const [toolArgs, setToolArgs] = useState({});
  const [executing, setExecuting] = useState({});
  const [executionOutput, setExecutionOutput] = useState({});
  const [executionError, setExecutionError] = useState({});

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      
      // Load installed MCP servers only (non-discovery mode)
      const purchasesRes = await axios.get(`${apiBase}/users/me/mcp-purchases`, {
        headers: { Authorization: `Bearer ${authToken}` }
      });
      const installedServers = Object.entries(purchasesRes.data.details || {}).map(([serverId, detail]) => ({
        id: detail.id || serverId,
        name: detail.server_name,
        description: detail.description || 'Installed MCP server',
        category: detail.category || 'tooling',
        status: detail.status || 'active',
        price: detail.price || 0,
        tools: detail.tools || []
      }));
      setMcpServers(installedServers);

      const purchased = {};
      installedServers.forEach((server) => {
        purchased[server.id] = true;
      });
      setPurchasedServers(purchased);

      // Load all agents to show which use each tool
      const agentsRes = await axios.get(`${apiBase}/agents`, {
        headers: { Authorization: `Bearer ${authToken}` }
      });
      const agents = {};
      agentsRes.data.forEach(agent => {
        agents[agent.id] = agent;
      });
      setAgentNames(agents);

      setError('');
    } catch (err) {
      setError('Error loading data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [authToken, apiBase]);

  useEffect(() => {
    if (isActive) {
      loadData();
    }
  }, [loadData, refreshKey, isActive]);

  const getAgentsUsingServer = (serverId) => {
    return Object.values(agentNames)
      .filter(agent => agent.mcp_server_ids && agent.mcp_server_ids.includes(serverId))
      .map(agent => agent.name);
  };

  const getServerMonogram = (name) => {
    const words = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (words.length === 0) return 'MC';
    if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
    return `${words[0][0]}${words[1][0]}`.toUpperCase();
  };

  const handleExecute = async (serverId) => {
    let toolToRun = selectedTool[serverId];
    if (!toolToRun) {
      setExecutionError(prev => ({ ...prev, [serverId]: 'Select a tool first.' }));
      return;
    }

    let parsedArgs = {};
    try {
      const raw = (toolArgs[serverId] || '{}').trim() || '{}';
      parsedArgs = JSON.parse(raw);

      // Support pasting full execute payload into the arguments box:
      // { "tool": "read_file", "arguments": { ... } }
      if (
        parsedArgs &&
        typeof parsedArgs === 'object' &&
        !Array.isArray(parsedArgs) &&
        parsedArgs.arguments &&
        typeof parsedArgs.arguments === 'object' &&
        !Array.isArray(parsedArgs.arguments)
      ) {
        if (typeof parsedArgs.tool === 'string' && parsedArgs.tool.trim()) {
          toolToRun = parsedArgs.tool.trim();
        }
        parsedArgs = parsedArgs.arguments;
      }
    } catch (e) {
      setExecutionError(prev => ({ ...prev, [serverId]: 'Arguments must be valid JSON.' }));
      return;
    }

    setExecuting(prev => ({ ...prev, [serverId]: true }));
    setExecutionError(prev => ({ ...prev, [serverId]: '' }));
    setExecutionOutput(prev => ({ ...prev, [serverId]: null }));

    try {
      const response = await axios.post(
        `${apiBase}/mcp-servers/${serverId}/execute`,
        {
          tool: toolToRun,
          arguments: parsedArgs
        },
        {
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json'
          }
        }
      );
      setExecutionOutput(prev => ({ ...prev, [serverId]: response.data }));
    } catch (err) {
      setExecutionError(prev => ({
        ...prev,
        [serverId]: err.response?.data?.detail || 'Failed to execute MCP tool.'
      }));
    } finally {
      setExecuting(prev => ({ ...prev, [serverId]: false }));
    }
  };

  if (loading) {
    return <div style={{ padding: '2rem', textAlign: 'center' }}>Loading MCP Tools...</div>;
  }

  return (
    <div style={{ padding: '2rem' }}>
      <h2 style={{ marginBottom: '1.5rem', color: '#1e2630' }}>Installed MCP Tools</h2>
      
      {error && (
        <div style={{
          padding: '1rem',
          backgroundColor: '#fee',
          color: '#c33',
          borderRadius: '0.5rem',
          marginBottom: '1rem'
        }}>
          {error}
        </div>
      )}

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))',
        gap: '1.5rem'
      }}>
        {mcpServers.map(server => {
          const isInstalled = purchasedServers[server.id];
          const agentsUsing = getAgentsUsingServer(server.id);
          const activeTool = selectedTool[server.id] || server.tools[0] || '';
          const defaultArgs = toolArgs[server.id] ?? '{}';

          return (
            <div
              key={server.id}
              style={{
                border: isInstalled ? '1px solid #d4e7d9' : '1px solid #ded7ca',
                borderRadius: '14px',
                padding: '1.5rem',
                backgroundColor: isInstalled ? '#f6fbf8' : '#ffffff',
                boxShadow: isInstalled ? '0 10px 24px rgba(29,131,72,0.09)' : '0 10px 24px rgba(33,45,54,0.08)',
                transition: 'transform 0.2s, box-shadow 0.2s',
                cursor: 'pointer'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-4px)';
                e.currentTarget.style.boxShadow = isInstalled 
                  ? '0 4px 12px rgba(76,175,80,0.3)' 
                  : '0 4px 12px rgba(0,0,0,0.2)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.boxShadow = isInstalled 
                  ? '0 2px 8px rgba(76,175,80,0.2)' 
                  : '0 2px 8px rgba(0,0,0,0.1)';
              }}
            >
              {/* Header */}
              <div style={{ marginBottom: '0.75rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '0.3rem' }}>
                  <span style={{
                    width: '36px',
                    height: '36px',
                    borderRadius: '10px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 700,
                    fontSize: '0.78rem',
                    color: '#12324a',
                    background: 'linear-gradient(145deg, #f8d9b8, #f0bb81)'
                  }}>
                    {getServerMonogram(server.name)}
                  </span>
                  <h3 style={{ margin: 0, color: '#1e2630', fontFamily: 'Space Grotesk, sans-serif' }}>{server.name}</h3>
                </div>
                <div style={{
                  display: 'inline-block',
                  padding: '0.25rem 0.75rem',
                  backgroundColor: '#e8f1f7',
                  color: '#1f5a78',
                  borderRadius: '1rem',
                  fontSize: '0.75rem',
                  fontWeight: 'bold',
                  marginRight: '0.5rem'
                }}>
                  {server.category}
                </div>
                <div style={{
                  display: 'inline-block',
                  padding: '0.25rem 0.75rem',
                  backgroundColor: '#e9f6ed',
                  color: '#1d8348',
                  borderRadius: '1rem',
                  fontSize: '0.75rem',
                  fontWeight: 'bold'
                }}>
                  {isInstalled ? '✓ Installed' : server.status}
                </div>
              </div>

              {/* Description */}
              <p style={{
                margin: '0.75rem 0',
                color: '#5f6f80',
                fontSize: '0.95rem',
                lineHeight: '1.4'
              }}>
                {server.description}
              </p>

              {/* Tools List */}
              <div style={{ marginTop: '1rem', marginBottom: '1rem' }}>
                <p style={{
                  margin: '0 0 0.5rem 0',
                  color: '#1e2630',
                  fontWeight: 'bold',
                  fontSize: '0.9rem'
                }}>
                  Available Tools:
                </p>
                <div style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: '0.5rem'
                }}>
                  {server.tools.map((tool, idx) => (
                    <span
                      key={idx}
                      style={{
                        padding: '0.25rem 0.6rem',
                        backgroundColor: '#f5f1ea',
                        border: '1px solid #e4d9c8',
                        borderRadius: '0.25rem',
                        fontSize: '0.8rem',
                        color: '#5f6f80'
                      }}
                    >
                      {tool}
                    </span>
                  ))}
                </div>
              </div>

              {/* Agents Using This Tool */}
              {agentsUsing.length > 0 && (
                <div style={{ marginTop: '1rem', marginBottom: '1rem', paddingTop: '1rem', borderTop: '1px solid #eee2d3' }}>
                  <p style={{
                    margin: '0 0 0.5rem 0',
                    color: '#1e2630',
                    fontWeight: 'bold',
                    fontSize: '0.9rem'
                  }}>
                    Used by Agents:
                  </p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                    {agentsUsing.map((agentName, idx) => (
                      <span
                        key={idx}
                        style={{
                          padding: '0.25rem 0.6rem',
                          backgroundColor: '#fff1dd',
                          border: '1px solid #f2c089',
                          borderRadius: '0.25rem',
                          fontSize: '0.75rem',
                          color: '#8a5a27'
                        }}
                      >
                        {agentName}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Footer */}
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                borderTop: '1px solid #eee2d3',
                paddingTop: '0.75rem',
                marginTop: '0.75rem'
              }}>
                <div style={{
                  color: '#1d8348',
                  fontWeight: 'bold',
                  fontSize: '0.95rem'
                }}>
                  {server.price === 0 ? 'Free' : `$${server.price}`}
                </div>
                <span style={{ color: '#1d8348', fontWeight: 'bold', fontSize: '0.9rem' }}>Installed</span>
              </div>

              {isInstalled && (
                <div style={{ marginTop: '0.9rem', paddingTop: '0.9rem', borderTop: '1px solid #eee2d3' }}>
                  <p style={{ margin: '0 0 0.4rem 0', color: '#1e2630', fontWeight: 'bold', fontSize: '0.9rem' }}>
                    Run MCP Tool
                  </p>
                  <select
                    value={activeTool}
                    onChange={(e) => setSelectedTool(prev => ({ ...prev, [server.id]: e.target.value }))}
                    style={{
                      width: '100%',
                      padding: '0.45rem',
                      borderRadius: '0.25rem',
                      border: '1px solid #ded7ca',
                      marginBottom: '0.5rem'
                    }}
                  >
                    {server.tools.map((tool) => (
                      <option key={tool} value={tool}>{tool}</option>
                    ))}
                  </select>
                  <textarea
                    value={defaultArgs}
                    onChange={(e) => setToolArgs(prev => ({ ...prev, [server.id]: e.target.value }))}
                    rows={4}
                    style={{
                      width: '100%',
                      padding: '0.5rem',
                      borderRadius: '0.25rem',
                      border: '1px solid #ded7ca',
                      fontFamily: 'monospace',
                      fontSize: '0.8rem'
                    }}
                    placeholder='{"query":"SELECT COUNT(*) AS total_tracks FROM Track;"}'
                  />
                  <button
                    onClick={() => handleExecute(server.id)}
                    disabled={executing[server.id]}
                    style={{
                      marginTop: '0.5rem',
                      padding: '0.45rem 0.9rem',
                      backgroundColor: '#1f5a78',
                      color: 'white',
                      border: 'none',
                      borderRadius: '0.25rem',
                      cursor: executing[server.id] ? 'wait' : 'pointer',
                      opacity: executing[server.id] ? 0.7 : 1,
                      fontWeight: 'bold'
                    }}
                  >
                    {executing[server.id] ? 'Running...' : 'Execute'}
                  </button>

                  {executionError[server.id] && (
                    <div style={{ marginTop: '0.6rem', color: '#b91c1c', fontSize: '0.8rem' }}>
                      {executionError[server.id]}
                    </div>
                  )}

                  {executionOutput[server.id] && (
                    <pre style={{
                      marginTop: '0.6rem',
                      backgroundColor: '#1e2630',
                      color: '#ecf1f5',
                      borderRadius: '0.25rem',
                      padding: '0.6rem',
                      maxHeight: '220px',
                      overflow: 'auto',
                      fontSize: '0.75rem'
                    }}>
                      {JSON.stringify(executionOutput[server.id], null, 2)}
                    </pre>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {mcpServers.length === 0 && (
        <div style={{
          textAlign: 'center',
          padding: '3rem',
          color: '#999'
        }}>
          No MCP servers are installed for this account yet. Purchase an agent to auto-provision required MCP tools.
        </div>
      )}
    </div>
  );
}

export default MCPToolsGrid;
