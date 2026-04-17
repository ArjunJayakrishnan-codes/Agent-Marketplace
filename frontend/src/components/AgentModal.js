import React, { useState } from 'react';
import axios from 'axios';

function AgentModal({
  agent,
  purchased,
  accessStatus,
  authToken,
  apiBase,
  mcpServersById = {},
  onMcpDataChanged,
  onClose,
  onLoadAgents
}) {
  const [question, setQuestion] = useState('');
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showPurchasePrompt, setShowPurchasePrompt] = useState(false);
  const [purchaseLoading, setPurchaseLoading] = useState(false);
  const [purchaseSuccess, setPurchaseSuccess] = useState(null);
  const [showAccessDetails, setShowAccessDetails] = useState(false);
  const [accessDetails, setAccessDetails] = useState(null);
  const [loadingAccessDetails, setLoadingAccessDetails] = useState(false);

  const handleAsk = async (e) => {
    e.preventDefault();
    if (!question.trim()) return;

    setError('');
    setResponse('');
    setLoading(true);

    try {
      const res = await axios.post(
        `${apiBase}/agents/${agent.id}/ask`,
        { question: question.trim() },
        {
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json'
          }
        }
      );

      setResponse(res.data.response);
      setQuestion('');
      onLoadAgents();
    } catch (err) {
      if (err.response?.status === 403) {
        setShowPurchasePrompt(true);
        setError('Purchase required to use this agent.');
        onLoadAgents();
      } else {
        setError(err.response?.data?.detail || 'Error asking agent');
      }
    } finally {
      setLoading(false);
    }
  };

  const handlePurchase = async () => {
    setPurchaseLoading(true);
    setError('');
    try {
      const res = await axios.post(
        `${apiBase}/agents/${agent.id}/purchase`,
        {},
        {
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json'
          }
        }
      );

      setPurchaseSuccess({
        message: res.data.message,
        url: res.data.url,
        accessKey: res.data.access_key,
        purchasedAt: res.data.purchased_at
      });
      setShowPurchasePrompt(false);
      onLoadAgents();
      if (onMcpDataChanged) {
        await onMcpDataChanged();
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Error purchasing agent');
    } finally {
      setPurchaseLoading(false);
    }
  };

  const handleShowAccessDetails = async () => {
    setLoadingAccessDetails(true);
    setError('');
    try {
      const res = await axios.get(
        `${apiBase}/agents/${agent.id}/access-details`,
        {
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json'
          }
        }
      );
      console.log('Access Details Response:', res.data);
      setAccessDetails({
        url: res.data.url,
        accessKey: res.data.access_key,
        example_queries: res.data.example_queries || []
      });
      setShowAccessDetails(true);
    } catch (err) {
      console.error('Error fetching access details:', err);
      setError(err.response?.data?.detail || 'Error fetching access details');
    } finally {
      setLoadingAccessDetails(false);
    }
  };

  const isPurchased = accessStatus.is_purchased;
  const linkedMcpServers = (agent.mcp_server_ids || [])
    .map((serverId) => mcpServersById[serverId])
    .filter(Boolean);

  return (
    <div
      className="modal-overlay"
      onClick={onClose}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0,0,0,0.7)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000
      }}
    >
      <div
        className="modal-content"
        style={{
          backgroundColor: '#fcfaf6',
          borderRadius: '14px',
          padding: '2rem',
          maxWidth: '600px',
          width: '90%',
          maxHeight: '90vh',
          overflow: 'auto',
          border: '1px solid #ded7ca'
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '1.5rem' }}>{agent.name}</h2>
            <p style={{ margin: '0.5rem 0 0 0', color: '#5f6f80', fontSize: '0.875rem' }}>
              {isPurchased ? (
                <span style={{ color: '#86efac' }}>✓ Owned</span>
              ) : (
                <span style={{ color: '#f97316' }}>Purchase required</span>
              )}
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {isPurchased && !purchaseSuccess && !showAccessDetails && (
              <button
                className="btn btn-success"
                onClick={handleShowAccessDetails}
                disabled={loadingAccessDetails}
                style={{ opacity: loadingAccessDetails ? 0.5 : 1 }}
              >
                {loadingAccessDetails ? 'Loading...' : 'Access Details'}
              </button>
            )}
            {!isPurchased && !purchaseSuccess && (
              <button
                className="btn btn-primary"
                onClick={handlePurchase}
                disabled={purchaseLoading}
                style={{ opacity: purchaseLoading ? 0.5 : 1 }}
              >
                {purchaseLoading ? '...' : 'Buy Now'}
              </button>
            )}
            <button
              onClick={onClose}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                fontSize: '1.5rem',
                color: '#5f6f80'
              }}
            >
              ✕
            </button>
          </div>
        </div>

        <p style={{ color: '#5f6f80', marginBottom: '1rem' }}>{agent.description}</p>

        <div style={{ marginBottom: '1.5rem', padding: '1rem', backgroundColor: '#f5f1ea', borderRadius: '0.5rem', border: '1px solid #e4d9c8' }}>
          <h4 style={{ margin: '0 0 0.5rem 0', color: '#1f5a78' }}>Purpose</h4>
          <p style={{ margin: 0, color: '#1e2630' }}>{agent.purpose}</p>
        </div>

        <div style={{ marginBottom: '1.5rem', padding: '1rem', backgroundColor: '#f5f1ea', borderRadius: '0.5rem', border: '1px solid #e4d9c8' }}>
          <h4 style={{ margin: '0 0 0.5rem 0', color: '#1f5a78' }}>Capabilities</h4>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {agent.capabilities.map((cap, idx) => (
              <span
                key={idx}
                style={{
                  backgroundColor: '#e8f1f7',
                  color: '#1f5a78',
                  padding: '0.25rem 0.75rem',
                  borderRadius: '9999px',
                  fontSize: '0.875rem',
                  border: '1px solid #c8dce9'
                }}
              >
                {cap}
              </span>
            ))}
          </div>
        </div>

        <div style={{ marginBottom: '1.5rem', padding: '1rem', backgroundColor: '#f5f1ea', borderRadius: '0.5rem', border: '1px solid #e4d9c8' }}>
          <h4 style={{ margin: '0 0 0.5rem 0', color: '#1f5a78' }}>Status</h4>
          <div style={{ display: 'flex', gap: '1rem' }}>
            <div>
              <span style={{ color: '#5f6f80' }}>Operational: </span>
              <span style={{ color: '#1d8348' }}>{agent.status}</span>
            </div>
            <div>
              {isPurchased ? (
                <span style={{ color: '#86efac' }}>✓ Owned</span>
              ) : (
                <span style={{ color: '#f97316' }}>Purchase required</span>
              )}
            </div>
          </div>
        </div>

        <div style={{ marginBottom: '1.5rem', padding: '1rem', backgroundColor: '#f5f1ea', borderRadius: '0.5rem', border: '1px solid #e4d9c8' }}>
          <h4 style={{ margin: '0 0 0.75rem 0', color: '#1f5a78' }}>MCP Tool Access</h4>
          {linkedMcpServers.length > 0 ? (
            <div style={{ display: 'grid', gap: '0.75rem' }}>
              {linkedMcpServers.map((server) => (
                <div
                  key={server.id}
                  style={{
                    border: '1px solid #ded7ca',
                    borderRadius: '0.5rem',
                    padding: '0.75rem',
                    backgroundColor: '#ffffff'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'center' }}>
                    <span style={{ color: '#1e2630', fontWeight: 600 }}>{server.name}</span>
                    <span style={{ color: '#5f6f80', fontSize: '0.75rem' }}>{server.category}</span>
                  </div>
                  <p style={{ margin: '0.5rem 0 0.6rem 0', color: '#5f6f80', fontSize: '0.85rem' }}>
                    {server.description}
                  </p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                    {server.tools.map((tool) => (
                      <span
                        key={tool}
                        style={{
                          padding: '0.2rem 0.45rem',
                          fontSize: '0.72rem',
                          borderRadius: '9999px',
                          border: '1px solid #c8dce9',
                          color: '#1f5a78',
                          backgroundColor: '#e8f1f7'
                        }}
                      >
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ margin: 0, color: '#5f6f80', fontSize: '0.875rem' }}>
              No MCP tools linked to this agent.
            </p>
          )}
        </div>

        {showAccessDetails && accessDetails ? (
          <div style={{ padding: '1rem', backgroundColor: '#064e3b', borderRadius: '0.5rem', borderLeft: '4px solid #86efac', marginBottom: '1rem' }}>
            <h4 style={{ margin: '0 0 0.5rem 0', color: '#86efac' }}>✓ Agent Access Details</h4>
            <div style={{ margin: '1rem 0', padding: '0.75rem', backgroundColor: '#1e2630', borderRadius: '0.375rem', fontFamily: 'monospace', fontSize: '0.875rem', color: '#ecf1f5', wordBreak: 'break-all' }}>
              <p style={{ margin: '0 0 0.5rem 0', color: '#f0bb81' }}>Access URL:</p>
              <p style={{ margin: 0 }}>{accessDetails.url}</p>
              <p style={{ margin: '0.75rem 0 0 0', color: '#9ab0c0', fontSize: '0.75rem' }}>
                Access Key: {accessDetails.accessKey}
              </p>
            </div>
            
            {accessDetails.example_queries && accessDetails.example_queries.length > 0 ? (
              <div style={{ margin: '1rem 0', padding: '0.75rem', backgroundColor: '#ffffff', borderRadius: '0.375rem', border: '1px solid #ded7ca' }}>
                <p style={{ margin: '0 0 0.75rem 0', color: '#1f5a78', fontSize: '0.875rem', fontWeight: 'bold' }}>Example Queries by Domain:</p>
                <ul style={{ margin: 0, paddingLeft: '1.5rem' }}>
                  {accessDetails.example_queries.map((query, idx) => (
                    <li key={idx} style={{ color: '#1e2630', fontSize: '0.875rem', marginBottom: '0.5rem', lineHeight: '1.4' }}>
                      {query}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div style={{ margin: '1rem 0', padding: '0.75rem', backgroundColor: '#ffffff', borderRadius: '0.375rem', color: '#5f6f80', fontSize: '0.875rem', border: '1px solid #ded7ca' }}>
                No example queries available yet
              </div>
            )}
            
            <button
              style={{
                backgroundColor: '#1f5a78',
                color: '#fff',
                padding: '0.5rem 1rem',
                border: 'none',
                borderRadius: '0.375rem',
                cursor: 'pointer',
                fontSize: '0.875rem',
                marginRight: '0.5rem'
              }}
              onClick={() => {
                navigator.clipboard.writeText(accessDetails.url);
                alert('URL copied to clipboard!');
              }}
            >
              Copy URL
            </button>
            <button
              style={{
                backgroundColor: '#5f6f80',
                color: '#fff',
                padding: '0.5rem 1rem',
                border: 'none',
                borderRadius: '0.375rem',
                cursor: 'pointer',
                fontSize: '0.875rem'
              }}
              onClick={() => setShowAccessDetails(false)}
            >
              Close
            </button>
          </div>
        ) : showPurchasePrompt ? (
          <div style={{ padding: '1rem', backgroundColor: '#fff3eb', borderRadius: '0.5rem', borderLeft: '4px solid #f28c38', marginBottom: '1rem' }}>
            <h4 style={{ margin: '0 0 0.5rem 0', color: '#8a5a27' }}>Purchase Required</h4>
            <p style={{ margin: '0 0 1rem 0', color: '#8a5a27' }}>
              Purchase this agent to unlock full access.
            </p>
            <button
              className="btn btn-primary"
              onClick={handlePurchase}
              disabled={purchaseLoading}
              style={{ opacity: purchaseLoading ? 0.5 : 1 }}
            >
              {purchaseLoading ? 'Processing...' : 'Purchase Now'}
            </button>
          </div>
        ) : purchaseSuccess ? (
          <div style={{ padding: '1rem', backgroundColor: '#064e3b', borderRadius: '0.5rem', borderLeft: '4px solid #86efac', marginBottom: '1rem' }}>
            <h4 style={{ margin: '0 0 0.5rem 0', color: '#86efac' }}>✓ Purchase Successful!</h4>
            <p style={{ margin: '0.5rem 0', color: '#a7f3d0' }}>
              <strong>Agent:</strong> {agent.name}
            </p>
            <p style={{ margin: '0.5rem 0', color: '#a7f3d0' }}>
              <strong>Purchased:</strong> {new Date(purchaseSuccess.purchasedAt).toLocaleString()}
            </p>
            <div style={{ margin: '1rem 0', padding: '0.75rem', backgroundColor: '#1e2630', borderRadius: '0.375rem', fontFamily: 'monospace', fontSize: '0.875rem', color: '#ecf1f5', wordBreak: 'break-all' }}>
              <p style={{ margin: '0 0 0.5rem 0', color: '#f0bb81' }}>Access URL:</p>
              <p style={{ margin: 0 }}>{purchaseSuccess.url}</p>
              <p style={{ margin: '0.75rem 0 0 0', color: '#9ab0c0', fontSize: '0.75rem' }}>
                Access Key: {purchaseSuccess.accessKey}
              </p>
            </div>
            <button
              style={{
                backgroundColor: '#1f5a78',
                color: '#fff',
                padding: '0.5rem 1rem',
                border: 'none',
                borderRadius: '0.375rem',
                cursor: 'pointer',
                fontSize: '0.875rem'
              }}
              onClick={() => {
                navigator.clipboard.writeText(purchaseSuccess.url);
                alert('URL copied to clipboard!');
              }}
            >
              Copy URL
            </button>
            <p style={{ margin: '1rem 0 0 0', color: '#a7f3d0', fontSize: '0.875rem' }}>
              You can now ask unlimited questions! Start typing below or use the URL with your access key.
            </p>
          </div>
        ) : null}

        {!purchaseSuccess && !showAccessDetails && (
          <form onSubmit={handleAsk} style={{ marginBottom: '1rem' }}>
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: '#1e2630' }}>
                Ask a question:
              </label>
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                disabled={loading || !isPurchased}
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  backgroundColor: '#ffffff',
                  color: '#1e2630',
                  border: '1px solid #ded7ca',
                  borderRadius: '0.375rem',
                  fontFamily: 'inherit',
                  fontSize: '0.875rem',
                  minHeight: '100px',
                  resize: 'vertical',
                  opacity: !isPurchased ? 0.5 : 1
                }}
                placeholder="Type your question here..."
              />
            </div>
            <button
              type="submit"
              disabled={loading || !question.trim() || !isPurchased}
              className="btn btn-primary"
              style={{
                opacity: loading || !question.trim() || !isPurchased ? 0.5 : 1
              }}
            >
              {loading ? 'Asking...' : 'Ask Agent'}
            </button>
          </form>
        )}

        {error && (
          <div style={{ padding: '1rem', backgroundColor: '#fff3eb', borderRadius: '0.5rem', borderLeft: '4px solid #f28c38', marginBottom: '1rem', color: '#8a5a27' }}>
            {error}
          </div>
        )}

        {response && (
          <div style={{ padding: '1rem', backgroundColor: '#ffffff', borderRadius: '0.5rem', borderLeft: '4px solid #1d8348', border: '1px solid #d4e7d9' }}>
            <h4 style={{ margin: '0 0 0.5rem 0', color: '#1d8348' }}>Response</h4>
            <p style={{ margin: 0, color: '#1e2630', whiteSpace: 'pre-wrap' }}>{response}</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default AgentModal;
